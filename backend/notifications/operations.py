"""
Operating the pipeline (docs/NOTIFICATION_SYSTEM.md §4.8, §17): the health
snapshot behind `notification_health`, retention behind `purge_notifications`
(§3 D9), and the admin's Requeue and Retry now.
"""
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Min
from django.utils import timezone

from .conf import notification_setting
from .models import Notification, NotificationDelivery, NotificationEvent

logger = logging.getLogger(__name__)

MAX_WAIT_MINUTES = 5
PURGE_BATCH_SIZE = 1000

# Rows the pipeline is finished with. Anything else is still in flight, so
# purging never deletes it however old it is.
FINISHED_EVENTS = (NotificationEvent.Status.ROUTED, NotificationEvent.Status.DEAD)
FINISHED_DELIVERIES = (
    NotificationDelivery.Status.SENT,
    NotificationDelivery.Status.SKIPPED,
    NotificationDelivery.Status.DEAD,
)
UNFINISHED_DELIVERIES = (
    NotificationDelivery.Status.PENDING,
    NotificationDelivery.Status.PROCESSING,
    NotificationDelivery.Status.FAILED,
)


# --- Health (§4.8) -----------------------------------------------------------


def waiting_since(model, now):
    """
    When the longest-waiting due row became due, or None: a PENDING or
    FAILED row since its available_at, a PROCESSING row whose lease lapsed
    (its worker died) since locked_until. A running worker keeps this within
    seconds of now.
    """
    Status = model.Status
    queued = model.objects.filter(
        status__in=[Status.PENDING, Status.FAILED], available_at__lte=now
    ).aggregate(oldest=Min("available_at"))["oldest"]
    stalled = model.objects.filter(status=Status.PROCESSING, locked_until__lt=now).aggregate(
        oldest=Min("locked_until")
    )["oldest"]
    times = [t for t in (queued, stalled) if t is not None]
    return min(times) if times else None


@dataclass
class HealthReport:
    checked_at: object
    max_wait: timedelta
    events: dict
    deliveries: dict  # {channel: {status: count}}
    event_wait: timedelta | None
    delivery_wait: timedelta | None
    problems: list = field(default_factory=list)

    @property
    def healthy(self):
        return not self.problems


def health_report(*, max_wait_minutes=MAX_WAIT_MINUTES, now=None):
    """
    Counts by status, and how long the oldest due row has waited. Unhealthy
    when anything is DEAD, or when an event or a delivery has waited longer
    than max_wait_minutes for a worker.
    """
    now = now or timezone.now()
    max_wait = timedelta(minutes=max_wait_minutes)

    events = {status: 0 for status in NotificationEvent.Status.values}
    for row in NotificationEvent.objects.values("status").annotate(n=Count("pk")):
        events[row["status"]] = row["n"]
    deliveries = {}
    for row in NotificationDelivery.objects.values("channel", "status").annotate(n=Count("pk")):
        by_status = deliveries.setdefault(
            row["channel"], {status: 0 for status in NotificationDelivery.Status.values}
        )
        by_status[row["status"]] = row["n"]

    event_since = waiting_since(NotificationEvent, now)
    delivery_since = waiting_since(NotificationDelivery, now)
    report = HealthReport(
        checked_at=now,
        max_wait=max_wait,
        events=events,
        deliveries=deliveries,
        event_wait=now - event_since if event_since else None,
        delivery_wait=now - delivery_since if delivery_since else None,
    )

    dead_events = events[NotificationEvent.Status.DEAD]
    dead_deliveries = sum(by_status[NotificationDelivery.Status.DEAD] for by_status in deliveries.values())
    if dead_events:
        report.problems.append(f"{dead_events} dead event(s)")
    if dead_deliveries:
        report.problems.append(f"{dead_deliveries} dead delivery(ies)")
    if report.event_wait and report.event_wait > max_wait:
        report.problems.append(f"an event has waited {format_duration(report.event_wait)} for a worker")
    if report.delivery_wait and report.delivery_wait > max_wait:
        report.problems.append(f"a delivery has waited {format_duration(report.delivery_wait)} for a worker")
    return report


def format_duration(delta):
    """'45s', '7m 03s', '2h 05m', '3d 4h'."""
    seconds = max(int(delta.total_seconds()), 0)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


# --- Retention (§3 D9) -------------------------------------------------------


@dataclass
class PurgeResult:
    notifications: int = 0
    deliveries: int = 0
    events: int = 0


def purge_querysets(*, inbox_days=None, event_days=None, now=None):
    """
    What a purge deletes, in the order it deletes it:
    - inbox notifications older than inbox_days (default 180), unless an email
      of theirs is still in flight; their finished deliveries go with them;
    - finished deliveries (SENT, SKIPPED, DEAD) older than event_days
      (default 90);
    - finished events (ROUTED, DEAD) older than event_days. Inbox rows that
      outlive their event keep everything they show; only the link is cleared.
    """
    now = now or timezone.now()
    inbox_days = notification_setting("INBOX_RETENTION_DAYS") if inbox_days is None else inbox_days
    event_days = notification_setting("EVENT_RETENTION_DAYS") if event_days is None else event_days
    inbox_cutoff = now - timedelta(days=inbox_days)
    event_cutoff = now - timedelta(days=event_days)
    return {
        "notifications": Notification.objects.filter(created_at__lt=inbox_cutoff).exclude(
            deliveries__status__in=UNFINISHED_DELIVERIES
        ),
        "deliveries": NotificationDelivery.objects.filter(
            created_at__lt=event_cutoff, status__in=FINISHED_DELIVERIES
        ),
        "events": NotificationEvent.objects.filter(created_at__lt=event_cutoff, status__in=FINISHED_EVENTS),
    }


def purge(*, inbox_days=None, event_days=None, dry_run=False, batch_size=PURGE_BATCH_SIZE, now=None):
    """
    Deletes what purge_querysets() selects, in batches of batch_size rows,
    each in its own short transaction. A dry run only counts.
    """
    querysets = purge_querysets(inbox_days=inbox_days, event_days=event_days, now=now)
    result = PurgeResult()
    if dry_run:
        for name, queryset in querysets.items():
            setattr(result, name, queryset.count())
        return result

    for name, queryset in querysets.items():
        while True:
            pks = list(queryset.values_list("pk", flat=True)[:batch_size])
            if not pks:
                break
            with transaction.atomic():
                # Re-applying the filter drops a row that changed since it was
                # listed, e.g. a dead event requeued in the meantime.
                _, per_model = queryset.filter(pk__in=pks).delete()
            result.notifications += per_model.get(Notification._meta.label, 0)
            result.deliveries += per_model.get(NotificationDelivery._meta.label, 0)
            result.events += per_model.get(NotificationEvent._meta.label, 0)
            if len(pks) < batch_size:
                break
    logger.info(
        "Purged %d notification(s), %d delivery(ies) and %d event(s)",
        result.notifications, result.deliveries, result.events,
    )
    return result


# --- Requeue and Retry now (the Django admin) --------------------------------


def _reset_rows(model, pks, *, statuses, changes):
    """
    Applies `changes` to the rows among `pks` whose status is in `statuses`,
    under a row lock, so a worker claiming one at the same moment either
    wins it first or waits. Returns [(row, previous_state)] for what changed.
    """
    with transaction.atomic():
        rows = list(model.objects.select_for_update().filter(pk__in=pks, status__in=statuses))
        if not rows:
            return []
        before = [(row, {"status": row.status, "attempts": row.attempts}) for row in rows]
        model.objects.filter(pk__in=[row.pk for row in rows]).update(**changes)
        for row in rows:
            for name, value in changes.items():
                setattr(row, name, value)
    return before


def requeue(model, pks):
    """DEAD or FAILED rows back to PENDING with a fresh set of attempts, due now."""
    return _reset_rows(
        model,
        pks,
        statuses=[model.Status.DEAD, model.Status.FAILED],
        changes={
            "status": model.Status.PENDING,
            "attempts": 0,
            "available_at": timezone.now(),
            "locked_until": None,
            "locked_by": "",
        },
    )


def retry_now(model, pks):
    """FAILED rows due now instead of after their backoff; their attempts count on."""
    return _reset_rows(
        model,
        pks,
        statuses=[model.Status.FAILED],
        changes={"available_at": timezone.now()},
    )

"""
The router (docs/NOTIFICATION_SYSTEM.md §4.4 step 4): turns one outbox event
into inbox rows and delivery rows, exactly once.

route_event() runs in one transaction. It locks the event, runs its handlers,
drops recipients who were deleted or deactivated since, applies the fan-out
cap and preferences, renders the inbox text, inserts the rows and marks the
event ROUTED. An exception rolls all of it back and propagates, leaving the
event as it was; the caller (the fast path or the worker) decides what
happens next.
"""
import logging
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .conf import notification_setting
from .events import get_event_type
from .handlers import handlers_for
from .models import Channel, Notification, NotificationDelivery, NotificationEvent
from .preferences import effective_channels, load_overrides
from .rendering import render_in_app

logger = logging.getLogger(__name__)


class RoutingError(Exception):
    """Raised when a handler returns something the event can't deliver."""


@dataclass(frozen=True)
class RouteResult:
    event_id: object
    status: str
    notifications: int = 0
    deliveries: int = 0


def route_event(event_id, *, skip_locked=False):
    """
    Routes one event. An event that is already ROUTED or DEAD is left alone,
    so running this twice is a no-op. With skip_locked=True an event another
    process is routing right now is skipped rather than waited for; the
    result's status is then "LOCKED".
    """
    with transaction.atomic():
        event = (
            NotificationEvent.objects.select_for_update(skip_locked=skip_locked)
            .filter(pk=event_id)
            .first()
        )
        if event is None:
            if skip_locked and NotificationEvent.objects.filter(pk=event_id).exists():
                return RouteResult(event_id, "LOCKED")
            return RouteResult(event_id, "MISSING")
        if event.status in (NotificationEvent.Status.ROUTED, NotificationEvent.Status.DEAD):
            return RouteResult(event_id, event.status)

        definition = get_event_type(event.event_type)
        recipients = _recipients(event, definition)
        notifications = _insert_notifications(event, definition, recipients)
        deliveries = _insert_deliveries(event, notifications)

        event.status = NotificationEvent.Status.ROUTED
        event.routed_at = timezone.now()
        event.locked_until = None
        event.locked_by = ""
        event.last_error = ""
        event.save(update_fields=["status", "routed_at", "locked_until", "locked_by", "last_error"])

    logger.info(
        "Routed %s %s: %d notification(s), %d delivery row(s)",
        event.event_type, event.id, len(notifications), deliveries,
    )
    return RouteResult(event.id, event.status, len(notifications), deliveries)


def _recipients(event, definition):
    """
    Every handler's recipients, in order: one per user (the first audience
    wins, since a user gets one inbox row per event), only users who still
    exist and are active, and at most FANOUT_CAP of them.
    """
    wanted = []
    seen = set()
    for handler in handlers_for(event.event_type):
        for recipient in handler(event) or ():
            if recipient.audience not in definition.audiences:
                raise RoutingError(
                    f"{handler.__qualname__} returned audience '{recipient.audience}', "
                    f"which {definition.name} doesn't reach."
                )
            user_id = getattr(recipient.user, "pk", None)
            if user_id is None or user_id in seen:
                continue
            seen.add(user_id)
            wanted.append(recipient)

    # Re-read in one query: a user deleted or deactivated since is skipped.
    live = set(
        get_user_model().objects.filter(pk__in=seen, is_active=True).values_list("pk", flat=True)
    )
    recipients = [r for r in wanted if r.user.pk in live]

    cap = notification_setting("FANOUT_CAP")
    if len(recipients) > cap:
        logger.warning(
            "%s %s reaches %d recipients; only the first %d are notified.",
            event.event_type, event.id, len(recipients), cap,
        )
        recipients = recipients[:cap]
    return recipients


def _insert_notifications(event, definition, recipients):
    """Inserts one inbox row per recipient; returns [(notification, channels)]."""
    overrides = load_overrides(
        [r.user.pk for r in recipients], set(definition.audiences.values())
    )
    planned = []
    for recipient in recipients:
        category = definition.audiences[recipient.audience]
        channels = definition.channels & effective_channels(
            recipient.user, category, overrides.get((recipient.user.pk, category), {})
        )
        if recipient.channels is not None:
            channels &= recipient.channels
        context = {
            **event.payload,
            **recipient.context,
            "recipient": recipient.user,
            "audience": recipient.audience,
            "occurred_at": event.occurred_at,
        }
        message = render_in_app(definition.name, event.schema_version, context)
        notification = Notification(
            recipient=recipient.user,
            event=event,
            event_type=event.event_type,
            category=category,
            audience=recipient.audience,
            title=message.title,
            body=message.body,
            action_url=message.action_url,
            priority=definition.priority,
            occurred_at=event.occurred_at,
        )
        planned.append((notification, channels | {Channel.IN_APP}))

    # The event lock and the ROUTED check keep a re-run from getting here;
    # unique(recipient, event) is the backstop and would fail the event loudly.
    # (ignore_conflicts would mean INSERT IGNORE, which on MySQL also turns
    # other errors into silent warnings.) MySQL doesn't return ids from a bulk
    # insert, so the rows are read back for them.
    Notification.objects.bulk_create([n for n, _ in planned])
    ids = dict(Notification.objects.filter(event=event).values_list("recipient_id", "id"))
    for notification, _ in planned:
        notification.pk = ids[notification.recipient_id]
    return planned


def _insert_deliveries(event, notifications):
    """One delivery row per notification per external channel; returns the count."""
    deliveries = []
    for notification, channels in notifications:
        for channel in sorted(channels - {Channel.IN_APP}):
            destination = destination_for(channel, notification.recipient, notification.audience)
            deliveries.append(
                NotificationDelivery(
                    notification=notification,
                    channel=channel,
                    destination=destination,
                    status=(
                        NotificationDelivery.Status.PENDING
                        if destination
                        else NotificationDelivery.Status.SKIPPED
                    ),
                    last_error="" if destination else "No address to send to.",
                )
            )
    NotificationDelivery.objects.bulk_create(deliveries)
    return len(deliveries)


def destination_for(channel, user, audience):
    """
    The address snapshot for one external send. Empty means there is nowhere
    to send it, and the delivery is recorded as SKIPPED. Task 7 adds the
    seller rule (the business email first).
    """
    if channel == Channel.EMAIL:
        return (user.email or "").strip()
    return ""

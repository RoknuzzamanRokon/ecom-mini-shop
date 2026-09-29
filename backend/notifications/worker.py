"""
The worker (docs/NOTIFICATION_SYSTEM.md §4.4 steps 3 and 5, §4.5): drains the
outbox and the delivery queue, safely, with any number of copies running.

- Claims take due rows with SELECT ... FOR UPDATE SKIP LOCKED and mark them
  PROCESSING with a lease, so two workers never take the same row. The lease
  is renewed just before each row is handled. A row whose lease expired (its
  worker died) is claimable again.
- A claim counts as an attempt, so a row that keeps killing its worker still
  reaches DEAD.
- A failure is retried with full-jitter backoff until the maximum attempts,
  then DEAD. An adapter's permanent error goes to DEAD or SKIPPED at once.
- Sends happen outside any transaction.

Where claims come from is the transport. DatabaseTransport reads MySQL; a
broker transport (Stage 2, §4.6) would implement the same two methods.
"""
import logging
import os
import random
import socket
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from .channels import PermanentSendError, get_adapter
from .channels.base import ADAPTERS
from .conf import notification_setting
from .models import Channel, NotificationDelivery, NotificationEvent
from .routing import route_event

logger = logging.getLogger(__name__)

LAST_ERROR_MAX_LENGTH = 2048
BUSY_SLEEP_SECONDS = 2.0
IDLE_SLEEP_SECONDS = 10.0
# Sends per second per channel (§4.5 Backpressure). A channel not listed
# isn't limited.
RATE_SETTINGS = {Channel.EMAIL: "EMAIL_RATE_PER_SECOND"}


def backoff_delay(attempts, *, base=None, cap=None, rand=random.uniform):
    """
    Seconds to wait before retry number `attempts`: full jitter,
    random(0, min(cap, base * 2**(attempts - 1))), so the first retry waits
    up to `base` seconds.
    """
    base = notification_setting("BACKOFF_BASE_SECONDS") if base is None else base
    cap = notification_setting("BACKOFF_CAP_SECONDS") if cap is None else cap
    return rand(0, min(cap, base * 2 ** max(attempts - 1, 0)))


def error_text(exc):
    """The traceback's last 2 KB, which always ends with the error itself."""
    return "".join(traceback.format_exception(exc))[-LAST_ERROR_MAX_LENGTH:]


def default_worker_id():
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"[-64:]


class TokenBucket:
    """At most `rate` acquisitions per second on average, bursting to `rate`."""

    def __init__(self, rate, *, clock=time.monotonic, sleep=time.sleep):
        self.rate = rate
        self.tokens = float(rate or 0)
        self.clock = clock
        self.sleep = sleep
        self.updated = clock()

    def acquire(self):
        if not self.rate:
            return
        self._refill()
        if self.tokens < 1:
            self.sleep((1 - self.tokens) / self.rate)
            self._refill()
        self.tokens -= 1

    def _refill(self):
        now = self.clock()
        self.tokens = min(self.rate, self.tokens + (now - self.updated) * self.rate)
        self.updated = now


class DatabaseTransport:
    """Stage 1: claims come straight from the MySQL tables."""

    def claim_events(self, worker_id, limit):
        return _claim(NotificationEvent, worker_id, limit, notification_setting("EVENT_MAX_ATTEMPTS"))

    def claim_deliveries(self, worker_id, limit, channels):
        return _claim(
            NotificationDelivery,
            worker_id,
            limit,
            notification_setting("DELIVERY_MAX_ATTEMPTS"),
            Q(channel__in=channels),
        )


def due_rows(model, now, extra=Q()):
    """PENDING or FAILED rows whose time has come, and PROCESSING rows whose lease expired."""
    Status = model.Status
    due = Q(status__in=[Status.PENDING, Status.FAILED], available_at__lte=now) | Q(
        status=Status.PROCESSING, locked_until__lt=now
    )
    return model.objects.filter(due & extra)


def _claim(model, worker_id, limit, max_attempts, extra=Q()):
    """Locks up to `limit` due rows, marks them PROCESSING for this worker, returns their ids."""
    if limit <= 0:
        return []
    now = timezone.now()
    with transaction.atomic():
        rows = list(
            due_rows(model, now, extra)
            .select_for_update(skip_locked=True)
            .order_by("available_at")
            .values_list("pk", "status", "attempts")[:limit]
        )
        # A lease that expired on the last attempt means the worker died
        # handling it every time. Stop there instead of trying again.
        exhausted = [
            pk for pk, status, attempts in rows
            if status == model.Status.PROCESSING and attempts >= max_attempts
        ]
        claimed = [pk for pk, _, _ in rows if pk not in exhausted]
        if exhausted:
            model.objects.filter(pk__in=exhausted).update(
                status=model.Status.DEAD,
                locked_until=None,
                locked_by="",
                last_error="The lease expired on the last attempt: the worker stopped while handling it.",
            )
            logger.error("%s %s: dead after the lease expired on the last attempt", model.__name__, exhausted)
        if claimed:
            model.objects.filter(pk__in=claimed).update(
                status=model.Status.PROCESSING,
                attempts=F("attempts") + 1,
                locked_by=worker_id,
                locked_until=now + timedelta(seconds=notification_setting("LEASE_SECONDS")),
            )
    return claimed


def _renew(model, pk, worker_id):
    """
    Extends this worker's lease on a row just before handling it, so the
    lease only has to outlast one row, not a whole batch. False means the lease
    already expired and another worker took the row; it's then left to them.
    """
    renewed = model.objects.filter(pk=pk, status=model.Status.PROCESSING, locked_by=worker_id).update(
        locked_until=timezone.now() + timedelta(seconds=notification_setting("LEASE_SECONDS"))
    )
    if not renewed:
        logger.warning("%s %s: lease lost before it was handled; skipped", model.__name__, pk)
    return bool(renewed)


def _finish(model, pk, worker_id, **fields):
    """Updates a row this worker still holds; False if its lease was lost to another worker."""
    updated = model.objects.filter(
        pk=pk, status=model.Status.PROCESSING, locked_by=worker_id
    ).update(locked_until=None, locked_by="", **fields)
    if not updated:
        logger.warning("%s %s: lease lost before the outcome was recorded", model.__name__, pk)
    return bool(updated)


def _retry_or_die(model, pk, worker_id, exc, max_attempts):
    attempts = model.objects.filter(pk=pk).values_list("attempts", flat=True).first() or 0
    if attempts >= max_attempts:
        _finish(model, pk, worker_id, status=model.Status.DEAD, last_error=error_text(exc))
        logger.error("%s %s: dead after %d attempts: %s", model.__name__, pk, attempts, exc)
    else:
        retry_at = timezone.now() + timedelta(seconds=backoff_delay(attempts))
        _finish(
            model, pk, worker_id,
            status=model.Status.FAILED, available_at=retry_at, last_error=error_text(exc),
        )
        logger.warning("%s %s: attempt %d failed, retrying at %s: %s", model.__name__, pk, attempts, retry_at, exc)


@dataclass
class PassResult:
    events: int = 0
    deliveries: int = 0

    @property
    def total(self):
        return self.events + self.deliveries


class NotificationWorker:
    def __init__(self, *, worker_id=None, transport=None, batch_size=None, stop_event=None):
        self.worker_id = worker_id or default_worker_id()
        self.transport = transport or DatabaseTransport()
        self.batch_size = batch_size or notification_setting("BATCH_SIZE")
        self.stop_event = stop_event or threading.Event()
        self.buckets = {}

    # --- one pass ---------------------------------------------------------

    def run_once(self, only=None):
        """One batch of events, then one of deliveries. Returns how many rows it handled."""
        result = PassResult()
        if only in (None, "events"):
            result.events = self.process_events()
        if only in (None, "deliveries") and not self.stop_event.is_set():
            result.deliveries = self.process_deliveries()
        return result

    def process_events(self):
        ids = self.transport.claim_events(self.worker_id, self.batch_size)
        for index, event_id in enumerate(ids):
            if self.stop_event.is_set():
                self._release(NotificationEvent, ids[index:])
                return index
            if _renew(NotificationEvent, event_id, self.worker_id):
                self._route(event_id)
        return len(ids)

    def process_deliveries(self):
        channels = sorted(ADAPTERS)
        ids = self.transport.claim_deliveries(self.worker_id, self.batch_size, channels) if channels else []
        for index, delivery_id in enumerate(ids):
            if self.stop_event.is_set():
                self._release(NotificationDelivery, ids[index:])
                return index
            if _renew(NotificationDelivery, delivery_id, self.worker_id):
                self._deliver(delivery_id)
        return len(ids)

    # --- the loop ---------------------------------------------------------

    def run(self, *, only=None, idle_sleep=IDLE_SLEEP_SECONDS, busy_sleep=BUSY_SLEEP_SECONDS):
        """
        Passes until stop() is called. A full batch goes straight on to the
        next; otherwise it sleeps busy_sleep after some work and idle_sleep
        after none.
        """
        logger.info("Notification worker %s started", self.worker_id)
        while not self.stop_event.is_set():
            result = self.run_once(only)
            if result.events >= self.batch_size or result.deliveries >= self.batch_size:
                continue
            self.stop_event.wait(busy_sleep if result.total else idle_sleep)
        logger.info("Notification worker %s stopped", self.worker_id)

    def stop(self):
        self.stop_event.set()

    # --- one row ----------------------------------------------------------

    def _route(self, event_id):
        try:
            route_event(event_id)
        except Exception as exc:
            _retry_or_die(
                NotificationEvent, event_id, self.worker_id, exc, notification_setting("EVENT_MAX_ATTEMPTS")
            )

    def _deliver(self, delivery_id):
        delivery = (
            NotificationDelivery.objects.select_related("notification", "notification__recipient")
            .filter(pk=delivery_id, locked_by=self.worker_id)
            .first()
        )
        if delivery is None:
            return
        adapter = get_adapter(delivery.channel)
        self._bucket(delivery.channel).acquire()
        try:
            result = adapter.send(delivery)
        except PermanentSendError as exc:
            status = NotificationDelivery.Status.SKIPPED if exc.skip else NotificationDelivery.Status.DEAD
            _finish(NotificationDelivery, delivery.pk, self.worker_id, status=status, last_error=error_text(exc))
            logger.error("Delivery %s: %s, not retried: %s", delivery.pk, status, exc)
        except Exception as exc:
            _retry_or_die(
                NotificationDelivery, delivery.pk, self.worker_id, exc,
                notification_setting("DELIVERY_MAX_ATTEMPTS"),
            )
        else:
            if _finish(
                NotificationDelivery, delivery.pk, self.worker_id,
                status=NotificationDelivery.Status.SENT,
                sent_at=timezone.now(),
                provider_message_id=(result.provider_message_id or "")[:255],
                last_error="",
            ):
                logger.info("Delivery %s: %s sent on attempt %d", delivery.pk, delivery.channel, delivery.attempts)

    def _bucket(self, channel):
        if channel not in self.buckets:
            setting = RATE_SETTINGS.get(channel)
            self.buckets[channel] = TokenBucket(notification_setting(setting) if setting else 0)
        return self.buckets[channel]

    def _release(self, model, ids):
        """Hands claimed-but-untouched rows back on shutdown, without using up an attempt."""
        model.objects.filter(pk__in=ids, status=model.Status.PROCESSING, locked_by=self.worker_id).update(
            status=model.Status.PENDING,
            attempts=F("attempts") - 1,
            available_at=timezone.now(),
            locked_until=None,
            locked_by="",
        )
        logger.info("%s: released %d unprocessed row(s) on shutdown", model.__name__, len(ids))

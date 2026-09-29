"""
The publisher (docs/NOTIFICATION_SYSTEM.md §4.4): the one call domain code
makes to record that something happened.

    from notifications import events
    from notifications.publisher import publish

    publish(events.ORDER_PLACED, payload={...}, aggregate=order, actor=user,
            idempotency_key=f"order:{order.order_number}:placed")

publish() writes one outbox row inside the caller's transaction, so the event
commits or rolls back with the change it describes. It never picks recipients
or does network I/O; that happens after the commit.

A leaf module: it imports only Django and this app's leaf modules, so any app
can import it without a cycle.
"""
import json
import logging
import uuid

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from .conf import notification_setting
from .events import get_event_type
from .models import NotificationEvent

logger = logging.getLogger(__name__)

IDEMPOTENCY_KEY_MAX_LENGTH = NotificationEvent._meta.get_field("idempotency_key").max_length
AGGREGATE_ID_MAX_LENGTH = NotificationEvent._meta.get_field("aggregate_id").max_length


class PublishError(Exception):
    """Raised when publish() is called wrongly. Always a bug in the caller."""


class InvalidPayloadError(PublishError):
    """Raised for a payload that is missing required keys or isn't plain JSON."""


def publish(event_type, *, payload, aggregate, actor=None, idempotency_key=None, occurred_at=None):
    """
    Records one event in the outbox and returns it.

    - `aggregate` is the model instance the fact is about; it's stored for
      tracing only.
    - `idempotency_key` defaults to a fresh UUID. Pass a natural key (§4.5)
      where the fact has one: publishing the same key again returns the first
      event instead of a second row, and the caller's transaction carries on.
    - Must run inside the caller's transaction (`transaction.atomic`).
    """
    definition = get_event_type(event_type)
    snapshot = _validated_payload(definition, payload)
    aggregate_type, aggregate_id = _aggregate_identity(aggregate)
    key = idempotency_key or str(uuid.uuid4())
    if len(key) > IDEMPOTENCY_KEY_MAX_LENGTH:
        raise PublishError(f"Idempotency key is longer than {IDEMPOTENCY_KEY_MAX_LENGTH} characters.")
    occurred_at = occurred_at or timezone.now()
    if timezone.is_naive(occurred_at):
        raise PublishError("occurred_at must be timezone-aware.")
    if not connection.in_atomic_block:
        raise PublishError(
            "publish() must run inside the transaction that makes the change, so the event "
            "commits or rolls back with it."
        )

    event = NotificationEvent(
        event_type=definition.name,
        schema_version=definition.version,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        payload=snapshot,
        idempotency_key=key,
        occurred_at=occurred_at,
    )
    try:
        # A savepoint, so a duplicate key rolls back only this insert and
        # the caller's transaction survives the IntegrityError.
        with transaction.atomic():
            event.save(force_insert=True)
    except IntegrityError:
        existing = NotificationEvent.objects.filter(idempotency_key=key).first()
        if existing is None:
            raise
        if existing.event_type != definition.name:
            raise PublishError(
                f"Idempotency key '{key}' already belongs to a '{existing.event_type}' event."
            ) from None
        logger.info("Duplicate %s event for key %s; kept %s", definition.name, key, existing.id)
        return existing

    if notification_setting("ROUTE_ON_COMMIT"):
        event_id = event.id
        transaction.on_commit(lambda: _fast_path(event_id))
    logger.info("Published %s %s (%s:%s)", definition.name, event.id, aggregate_type, aggregate_id)
    return event


def _fast_path(event_id):
    # Runs after the caller's commit, so an error here must not reach the
    # caller: their change is already saved and the event waits for the worker.
    try:
        route_after_commit(event_id)
    except Exception:
        logger.exception("Fast-path routing failed for event %s; the worker will retry it.", event_id)


def route_after_commit(event_id):
    """
    The fast path (§4.4 step 2): route the event in this process as soon as
    its transaction commits. An event another process is already routing is
    skipped, not waited for. Whatever happens, the event is never lost: until
    it's ROUTED it stays in the outbox for the worker.
    """
    # Imported here so importing the publisher never pulls in the router.
    from .routing import route_event

    route_event(event_id, skip_locked=True)


def _validated_payload(definition, payload):
    """A JSON round-tripped copy, so a later change to the caller's dict can't alter the event."""
    if not isinstance(payload, dict):
        raise InvalidPayloadError(f"The {definition.name} payload must be a dict, not {type(payload).__name__}.")
    missing = definition.required_keys - payload.keys()
    if missing:
        raise InvalidPayloadError(f"The {definition.name} payload is missing {', '.join(sorted(missing))}.")
    try:
        encoded = json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise InvalidPayloadError(
            f"The {definition.name} payload isn't plain JSON ({exc}). Send money and dates as strings."
        ) from None
    return json.loads(encoded)


def _aggregate_identity(aggregate):
    pk = getattr(aggregate, "pk", None)
    if pk is None:
        raise PublishError("The aggregate must be a saved model instance.")
    aggregate_id = str(pk)
    if len(aggregate_id) > AGGREGATE_ID_MAX_LENGTH:
        raise PublishError(f"The aggregate id is longer than {AGGREGATE_ID_MAX_LENGTH} characters.")
    return type(aggregate).__name__, aggregate_id

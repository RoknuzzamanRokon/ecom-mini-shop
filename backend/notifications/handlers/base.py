"""
The handler registry (docs/NOTIFICATION_SYSTEM.md §4.2).

A handler decides who hears about one event type, in which audience, and with
what extra context for the templates:

    @handles(events.ORDER_PLACED)
    def tell_the_customer(event):
        from shop.models import Order  # domain models are imported lazily (§4.3)
        order = Order.objects.filter(pk=event.payload["order_id"]).select_related("user").first()
        if order and order.user:
            yield Recipient(order.user, Audience.CUSTOMER)

Handlers re-read the database only to find who is responsible now; the facts
for the wording come from the event payload. Several handlers may handle one
event type; they run in registration order.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from ..events import get_event_type

HANDLERS = defaultdict(list)


@dataclass(frozen=True)
class Recipient:
    user: object
    audience: str
    # Extra template context for this recipient, e.g. a seller's own items.
    context: dict = field(default_factory=dict)
    # Narrows the event's external channels for this notification, e.g. email
    # only for some order statuses. None keeps them all. In-app is always sent.
    channels: Optional[frozenset] = None


def handles(event_type):
    """Registers the decorated function as a handler for `event_type`."""
    get_event_type(event_type)

    def register(func):
        HANDLERS[event_type].append(func)
        return func

    return register


def handlers_for(event_type):
    return list(HANDLERS.get(event_type, ()))

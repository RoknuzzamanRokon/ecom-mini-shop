"""
The event registry (docs/NOTIFICATION_SYSTEM.md §5): the contract between the
domain services that publish facts and the handlers that route them.

- `audiences` maps each audience an event can reach to the category its
  notifications file under. One event can reach several audiences, e.g.
  `order.placed` tells the customer (ORDERS) and each seller (SELLER_ORDERS).
- `channels` are the channels the event may use. Handlers can narrow them per
  notification (e.g. email only for some order statuses), and preferences
  narrow them per person; neither can widen them.
- `required_keys` must be present in every payload. A payload is JSON, so money
  travels as a decimal string. Removing or renaming a key, or changing what one
  means, needs a new `version` and a template for it; adding one doesn't.

A leaf module: it imports only `notifications.models` and `.categories`, so
domain apps can import the name constants below.
"""
from dataclasses import dataclass

from . import categories as c
from .models import Audience, Channel, Priority


@dataclass(frozen=True)
class EventType:
    name: str
    version: int
    audiences: dict
    required_keys: frozenset
    channels: frozenset
    priority: str = Priority.NORMAL

    @property
    def categories(self) -> frozenset:
        return frozenset(self.audiences.values())


IN_APP = frozenset({Channel.IN_APP})
IN_APP_AND_EMAIL = frozenset({Channel.IN_APP, Channel.EMAIL})

# Customer-facing
ORDER_PLACED = "order.placed"
ORDER_STATUS_CHANGED = "order.status_changed"
PAYMENT_SUCCEEDED = "payment.succeeded"
PAYMENT_FAILED = "payment.failed"
REFUND_PROCESSED = "refund.processed"
SUPPORT_REPLY_RECEIVED = "support.reply_received"
# Seller-facing
SELLER_STATUS_CHANGED = "seller.status_changed"
SHOP_STATUS_CHANGED = "shop.status_changed"
PRODUCT_MODERATED = "product.moderated"
INVENTORY_LOW_STOCK = "inventory.low_stock"
REVIEW_CREATED = "review.created"
POINTS_ADJUSTED = "points.adjusted"
# Staff-facing
SHOP_SUBMITTED = "shop.submitted"
SUPPORT_TICKET_CREATED = "support.ticket_created"
SUPPORT_TICKET_ASSIGNED = "support.ticket_assigned"
SUPPORT_CUSTOMER_REPLIED = "support.customer_replied"


def _keys(*names):
    return frozenset(names)


EVENT_TYPES = {
    event.name: event
    for event in (
        EventType(
            ORDER_PLACED, 1,
            {Audience.CUSTOMER: c.ORDERS, Audience.SELLER: c.SELLER_ORDERS},
            _keys("order_id", "order_number", "total_amount"),
            IN_APP_AND_EMAIL,
        ),
        EventType(
            ORDER_STATUS_CHANGED, 1,
            {Audience.CUSTOMER: c.ORDERS, Audience.SELLER: c.SELLER_ORDERS},
            # changed_by: "CUSTOMER", "SELLER" or "STAFF". Sellers hear only
            # about a customer's cancellation.
            _keys("order_id", "order_number", "from_status", "to_status", "changed_by"),
            IN_APP_AND_EMAIL,
        ),
        EventType(
            PAYMENT_SUCCEEDED, 1,
            {Audience.CUSTOMER: c.PAYMENTS},
            _keys("payment_id", "payment_number", "order_number", "amount"),
            IN_APP_AND_EMAIL,
        ),
        EventType(
            PAYMENT_FAILED, 1,
            {Audience.CUSTOMER: c.PAYMENTS},
            _keys("payment_id", "payment_number", "order_number", "amount"),
            IN_APP_AND_EMAIL,
            Priority.HIGH,
        ),
        EventType(
            REFUND_PROCESSED, 1,
            {Audience.CUSTOMER: c.PAYMENTS},
            _keys("refund_id", "refund_number", "order_number", "amount"),
            IN_APP_AND_EMAIL,
        ),
        EventType(
            SUPPORT_REPLY_RECEIVED, 1,
            # The ticket's channel decides which one.
            {Audience.CUSTOMER: c.SUPPORT, Audience.SELLER: c.SUPPORT},
            _keys("ticket_id", "ticket_number", "message_id"),
            IN_APP_AND_EMAIL,
        ),
        EventType(
            SELLER_STATUS_CHANGED, 1,
            {Audience.SELLER: c.ACCOUNT},
            _keys("seller_id", "from_status", "to_status"),
            IN_APP_AND_EMAIL,
            Priority.HIGH,
        ),
        EventType(
            SHOP_STATUS_CHANGED, 1,
            {Audience.SELLER: c.SHOPS},
            _keys("shop_id", "shop_name", "from_status", "to_status"),
            IN_APP_AND_EMAIL,
        ),
        EventType(
            PRODUCT_MODERATED, 1,
            {Audience.SELLER: c.CATALOG},
            # action: "approve", "reject", "publish" or "unpublish". Email for
            # rejections only.
            _keys("product_id", "product_name", "action", "from_status", "to_status"),
            IN_APP_AND_EMAIL,
        ),
        EventType(
            INVENTORY_LOW_STOCK, 1,
            {Audience.SELLER: c.INVENTORY},
            _keys("product_id", "product_name", "available_stock", "threshold"),
            IN_APP,
        ),
        EventType(
            REVIEW_CREATED, 1,
            {Audience.SELLER: c.REVIEWS},
            # kind: "product" or "shop"; subject_name is the product or shop name.
            _keys("kind", "review_id", "rating", "subject_name"),
            IN_APP,
        ),
        EventType(
            POINTS_ADJUSTED, 1,
            {Audience.SELLER: c.WALLET},
            _keys("transaction_id", "seller_id", "transaction_type", "amount", "balance_after"),
            IN_APP,
        ),
        EventType(
            SHOP_SUBMITTED, 1,
            {Audience.STAFF: c.STAFF_QUEUE},
            _keys("shop_id", "shop_name"),
            IN_APP,
        ),
        EventType(
            SUPPORT_TICKET_CREATED, 1,
            {Audience.STAFF: c.STAFF_QUEUE},
            _keys("ticket_id", "ticket_number", "subject", "channel"),
            IN_APP,
        ),
        EventType(
            SUPPORT_TICKET_ASSIGNED, 1,
            {Audience.STAFF: c.STAFF_QUEUE},
            _keys("ticket_id", "ticket_number", "assignee_id"),
            IN_APP_AND_EMAIL,
        ),
        EventType(
            SUPPORT_CUSTOMER_REPLIED, 1,
            {Audience.STAFF: c.STAFF_QUEUE},
            _keys("ticket_id", "ticket_number", "message_id"),
            IN_APP,
        ),
    )
}


class UnknownEventTypeError(LookupError):
    """Raised for an event type that isn't in EVENT_TYPES."""


def get_event_type(name: str) -> EventType:
    try:
        return EVENT_TYPES[name]
    except KeyError:
        raise UnknownEventTypeError(f"Unknown notification event type '{name}'.") from None

"""
Who hears about orders (docs/NOTIFICATION_SYSTEM.md §5).

- order.placed: the customer, and each seller with items in the order, told
  only about their own items (§4.7).
- order.status_changed: the customer, when the order is confirmed, shipped,
  delivered or cancelled (email for the last three); each seller in the order,
  when the customer cancels it.
"""
from collections import defaultdict
from decimal import Decimal

from ..events import ORDER_PLACED, ORDER_STATUS_CHANGED
from ..models import Audience
from .base import Recipient, handles

CUSTOMER_STATUSES = {"CONFIRMED", "SHIPPED", "DELIVERED", "CANCELLED"}
EMAILED_STATUSES = {"SHIPPED", "DELIVERED", "CANCELLED"}
IN_APP_ONLY = frozenset()


def _order_customer(order_id):
    from shop.models import Order

    order = Order.objects.select_related("user").filter(pk=order_id).first()
    return order.user if order else None


def _sellers(seller_ids):
    from sellers.models import SellerProfile

    return SellerProfile.objects.filter(pk__in=seller_ids).select_related("user").order_by("pk")


@handles(ORDER_PLACED)
def tell_customer_order_placed(event):
    customer = _order_customer(event.payload["order_id"])
    if customer:
        yield Recipient(customer, Audience.CUSTOMER)


@handles(ORDER_PLACED)
def tell_sellers_order_placed(event):
    lines = defaultdict(list)
    for item in event.payload["items"]:
        if item.get("seller_id"):
            lines[item["seller_id"]].append(item)
    for seller in _sellers(lines):
        mine = lines[seller.pk]
        yield Recipient(
            seller.user,
            Audience.SELLER,
            context={
                "items": mine,
                "seller_total": str(sum((Decimal(item["line_total"]) for item in mine), Decimal("0"))),
            },
        )


@handles(ORDER_STATUS_CHANGED)
def tell_customer_order_status(event):
    to_status = event.payload["to_status"]
    if to_status not in CUSTOMER_STATUSES:
        return
    customer = _order_customer(event.payload["order_id"])
    if customer:
        yield Recipient(
            customer,
            Audience.CUSTOMER,
            channels=None if to_status in EMAILED_STATUSES else IN_APP_ONLY,
        )


@handles(ORDER_STATUS_CHANGED)
def tell_sellers_customer_cancelled(event):
    payload = event.payload
    if payload["to_status"] != "CANCELLED" or payload["changed_by"] != "CUSTOMER":
        return
    from shop.models import OrderItem

    seller_ids = set(
        OrderItem.objects.filter(order_id=payload["order_id"], seller__isnull=False).values_list(
            "seller_id", flat=True
        )
    )
    for seller in _sellers(seller_ids):
        yield Recipient(seller.user, Audience.SELLER)

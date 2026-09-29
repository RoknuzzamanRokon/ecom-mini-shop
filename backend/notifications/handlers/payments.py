"""
Who hears about payments (docs/NOTIFICATION_SYSTEM.md §5): the order's
customer, for a payment that succeeded or failed and for a refund. The
PAYMENTS category always emails.
"""
from ..events import PAYMENT_FAILED, PAYMENT_SUCCEEDED, REFUND_PROCESSED
from ..models import Audience
from .base import Recipient, handles


@handles(PAYMENT_SUCCEEDED)
@handles(PAYMENT_FAILED)
def tell_customer_payment(event):
    from shop.models import Payment

    payment = Payment.objects.select_related("order__user").filter(pk=event.payload["payment_id"]).first()
    if payment and payment.order and payment.order.user:
        yield Recipient(payment.order.user, Audience.CUSTOMER)


@handles(REFUND_PROCESSED)
def tell_customer_refund(event):
    from shop.models import Refund

    refund = Refund.objects.select_related("order__user", "payment__order__user").filter(
        pk=event.payload["refund_id"]
    ).first()
    if not refund:
        return
    order = refund.order or refund.payment.order
    if order and order.user:
        yield Recipient(order.user, Audience.CUSTOMER)

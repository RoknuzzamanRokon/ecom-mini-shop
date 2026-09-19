"""
Platform-wide aggregate metrics.

Single source of truth for both the Django admin dashboard
(`get_platform_metrics`) and the Next.js management console
(`get_console_metrics`, served by shop.admin_views.AdminMetricsAPIView).

Every counter is one `.aggregate()` per table using `Count(filter=Q(...))`,
which compiles to `COUNT(CASE WHEN ... END)` -- one query per model rather
than one per status. Payments need two: refunds are aggregated separately on
Refund, because joining them into the Payment aggregate would fan out its rows
(see `refunded_amount_total`).
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from sellers.models import SellerProfile
from shops.models import Shop

from .models import Order, Payment, Product, ProductInventory, Refund

# Kept in sync with shop.admin.LOW_STOCK_THRESHOLD; override in settings if needed.
LOW_STOCK_THRESHOLD = getattr(settings, "LOW_STOCK_THRESHOLD", 10)

# Statuses that count as realised revenue. "COMPLETED" is not a Payment choice
# but is matched by the pre-existing console contract, so it is preserved here.
# This tuple backs the `paid` *count*; revenue uses the wider tuple below.
PAID_PAYMENT_STATUSES = (Payment.STATUS_PAID, "COMPLETED")

# Payment statuses whose money was actually captured, before refunds are taken
# off. Deliberately wider than PAID_PAYMENT_STATUSES: a partially- or fully-
# refunded payment *was* paid first -- Payment.VALID_TRANSITIONS only reaches
# either state from PAID -- so its captured amount belongs in the gross figure
# and the refunded part is subtracted separately. Excluding those two statuses,
# as summing over PAID_PAYMENT_STATUSES alone used to, is what let a single
# taka of refund erase an entire payment from revenue.
CAPTURED_PAYMENT_STATUSES = PAID_PAYMENT_STATUSES + (
    Payment.STATUS_PARTIALLY_REFUNDED,
    Payment.STATUS_REFUNDED,
)

# Only COMPLETED refunds moved money back out. This mirrors the authority for
# refunds, PaymentService.process_refund, which computes remaining refundable
# as `payment.amount - Sum(COMPLETED refunds)`: a PENDING or FAILED refund
# reduces neither the refundable balance nor revenue. Refund.STATUS_* is the
# existing lifecycle -- no new status is introduced here.
SETTLED_REFUND_STATUSES = (Refund.STATUS_COMPLETED,)

NEW_USER_WINDOW_DAYS = 30


def user_metrics():
    User = get_user_model()
    cutoff = timezone.now() - timezone.timedelta(days=NEW_USER_WINDOW_DAYS)
    return User.objects.aggregate(
        total=Count("pk"),
        active=Count("pk", filter=Q(is_active=True)),
        staff=Count("pk", filter=Q(is_staff=True)),
        new_recently=Count("pk", filter=Q(date_joined__gte=cutoff)),
    )


def seller_metrics():
    return SellerProfile.objects.aggregate(
        total=Count("pk"),
        # Strictly PENDING -- the console contract depends on this.
        pending=Count("pk", filter=Q(status=SellerProfile.STATUS_PENDING)),
        under_review=Count("pk", filter=Q(status=SellerProfile.STATUS_UNDER_REVIEW)),
        active=Count(
            "pk",
            filter=Q(status__in=[SellerProfile.STATUS_APPROVED, SellerProfile.STATUS_ACTIVE]),
        ),
        suspended=Count("pk", filter=Q(status=SellerProfile.STATUS_SUSPENDED)),
        rejected=Count("pk", filter=Q(status=SellerProfile.STATUS_REJECTED)),
    )


def shop_metrics():
    return Shop.objects.aggregate(
        total=Count("pk"),
        draft=Count("pk", filter=Q(status=Shop.STATUS_DRAFT)),
        # Strictly PENDING -- the console contract depends on this.
        pending=Count("pk", filter=Q(status=Shop.STATUS_PENDING)),
        active=Count(
            "pk", filter=Q(status__in=[Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE])
        ),
        suspended=Count("pk", filter=Q(status=Shop.STATUS_SUSPENDED)),
        rejected=Count("pk", filter=Q(status=Shop.STATUS_REJECTED)),
    )


def product_metrics():
    return Product.objects.aggregate(
        total=Count("pk"),
        published=Count(
            "pk", filter=Q(status=Product.STATUS_PUBLISHED, is_active=True)
        ),
        draft=Count("pk", filter=Q(status=Product.STATUS_DRAFT)),
        submitted=Count("pk", filter=Q(status=Product.STATUS_SUBMITTED)),
        rejected=Count("pk", filter=Q(status=Product.STATUS_REJECTED)),
    )


def order_metrics():
    return Order.objects.aggregate(
        total=Count("pk"),
        pending=Count("pk", filter=Q(status=Order.STATUS_PENDING)),
        in_flight=Count(
            "pk",
            filter=Q(
                status__in=[
                    Order.STATUS_CONFIRMED,
                    Order.STATUS_PROCESSING,
                    Order.STATUS_SHIPPED,
                ]
            ),
        ),
        delivered=Count("pk", filter=Q(status=Order.STATUS_DELIVERED)),
        cancelled=Count("pk", filter=Q(status=Order.STATUS_CANCELLED)),
    )


def refunded_amount_total():
    """
    Money handed back to buyers, limited to payments whose capture counts
    toward revenue.

    Aggregated on Refund in a query of its own rather than joined into
    `payment_metrics`: a Payment -> Refund join produces one payment row per
    refund row, which would silently multiply every `Count()` in that aggregate
    and the gross `Sum("amount")` along with them.

    Returns a Decimal, never None -- Coalesce supplies Decimal("0.00") for an
    empty table.
    """
    return Refund.objects.filter(
        status__in=SETTLED_REFUND_STATUSES,
        payment__status__in=CAPTURED_PAYMENT_STATUSES,
    ).aggregate(
        total=Coalesce(
            Sum("amount"),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
    )["total"]


def payment_metrics():
    """
    Payment counters, plus revenue as money actually kept.

    `revenue` is the captured amount minus everything refunded back out of it,
    so a 10,000 payment carrying a 1,000 completed refund reports 9,000 -- not
    0 (which is what filtering on PAID alone produced) and not 10,000 (which is
    what merely widening that filter would produce).

    Decimal end to end: both aggregates are Coalesce-guarded to Decimal("0.00")
    rather than None, so the subtraction is Decimal arithmetic and no value
    passes through float.
    """
    aggregates = Payment.objects.aggregate(
        total=Count("pk"),
        paid=Count("pk", filter=Q(status__in=PAID_PAYMENT_STATUSES)),
        pending=Count(
            "pk",
            filter=Q(status__in=[Payment.STATUS_PENDING, Payment.STATUS_PROCESSING]),
        ),
        failed=Count(
            "pk",
            filter=Q(status__in=[Payment.STATUS_FAILED, Payment.STATUS_CANCELLED]),
        ),
        # Count() is never NULL; only Sum() needs the Coalesce guard.
        captured=Coalesce(
            Sum("amount", filter=Q(status__in=CAPTURED_PAYMENT_STATUSES)),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
    )
    # Replaces `captured`, keeping the key order the dashboard template and the
    # console payload already expect: total, paid, pending, failed, revenue.
    aggregates["revenue"] = aggregates.pop("captured") - refunded_amount_total()
    return aggregates


def inventory_metrics():
    return ProductInventory.objects.aggregate(
        low_stock=Count(
            "pk",
            filter=Q(
                available_quantity__gt=0,
                available_quantity__lte=LOW_STOCK_THRESHOLD,
            ),
        ),
        out_of_stock=Count("pk", filter=Q(available_quantity=0)),
    )


def get_platform_metrics():
    """Nested payload for the Django admin dashboard. Seven aggregate queries."""
    return {
        "users": user_metrics(),
        "sellers": seller_metrics(),
        "shops": shop_metrics(),
        "products": product_metrics(),
        "orders": order_metrics(),
        "payments": payment_metrics(),
        "inventory": inventory_metrics(),
        "low_stock_threshold": LOW_STOCK_THRESHOLD,
        "new_user_window_days": NEW_USER_WINDOW_DAYS,
    }


def get_console_metrics():
    """
    Flat payload for the Next.js management console.

    These seven keys are a published API contract consumed by
    frontend/src/lib/admin-api.ts -- do not rename or re-scope them.

    `total_revenue` is a Decimal. DRF's JSON encoder renders a Decimal as a JSON
    number, so the wire format is unchanged from when this cast to float here --
    but the cast is gone, because rounding money through binary floating point
    on the way out is exactly the kind of error this module should not make.
    """
    metrics = get_platform_metrics()
    return {
        "total_orders": metrics["orders"]["total"],
        "total_revenue": metrics["payments"]["revenue"],
        "pending_shops": metrics["shops"]["pending"],
        "pending_sellers": metrics["sellers"]["pending"],
        "total_shops": metrics["shops"]["total"],
        "total_sellers": metrics["sellers"]["total"],
        "total_products": metrics["products"]["total"],
    }

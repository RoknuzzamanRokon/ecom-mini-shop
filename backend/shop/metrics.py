"""
Platform-wide aggregate metrics.

Single source of truth for both the Django admin dashboard
(`get_platform_metrics`) and the Next.js management console
(`get_console_metrics`, served by shop.admin_views.AdminMetricsAPIView).

Every counter is one `.aggregate()` per table using `Count(filter=Q(...))`,
which compiles to `COUNT(CASE WHEN ... END)` -- one query per model rather
than one per status.
"""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from sellers.models import SellerProfile
from shops.models import Shop

from .models import Order, Payment, Product, ProductInventory

# Kept in sync with shop.admin.LOW_STOCK_THRESHOLD; override in settings if needed.
LOW_STOCK_THRESHOLD = getattr(settings, "LOW_STOCK_THRESHOLD", 10)

# Statuses that count as realised revenue. "COMPLETED" is not a Payment choice
# but is matched by the pre-existing console contract, so it is preserved here.
PAID_PAYMENT_STATUSES = (Payment.STATUS_PAID, "COMPLETED")

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


def payment_metrics():
    return Payment.objects.aggregate(
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
        revenue=Coalesce(
            Sum("amount", filter=Q(status__in=PAID_PAYMENT_STATUSES)),
            Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
    )


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
    """
    metrics = get_platform_metrics()
    return {
        "total_orders": metrics["orders"]["total"],
        "total_revenue": float(metrics["payments"]["revenue"]),
        "pending_shops": metrics["shops"]["pending"],
        "pending_sellers": metrics["sellers"]["pending"],
        "total_shops": metrics["shops"]["total"],
        "total_sellers": metrics["sellers"]["total"],
        "total_products": metrics["products"]["total"],
    }

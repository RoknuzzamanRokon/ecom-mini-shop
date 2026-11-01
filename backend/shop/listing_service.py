"""
Listing periods (docs/LISTING_VALIDITY_PLAN.md).

A Limited Shop Owner's product stays live for
ProductListingPolicy.first_period_months from its first publication. When the
period ends the product becomes EXPIRED and leaves the storefront; the seller
renews it for renewal_points, and each renewal adds renewal_period_months,
also before the end date (docs/FOLLOW_UPS_PLAN.md). While a period runs, the
seller cannot take the product off the storefront; once it has expired they
can delete it. A Full Shop Owner's products have no end date (`live_until`
stays empty).

Like point expiry, an ended period is enforced lazily (the public catalog
checks `live_until`, and seller reads expire their own products) and by the
daily expire_listings command, which moves what nobody touched and tells
sellers whose products enter the ending-soon window.
"""
import logging
import math
from datetime import timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from audit.services import AuditService
from notifications import events
from notifications.publisher import publish
from points.models import PointTransaction
from points.services import PointService
from sellers.models import SellerProfile
from shops.models import Shop
from .models import Product, ProductListingPolicy, listing_running_q

logger = logging.getLogger(__name__)


class ListingError(Exception):
    """A listing rule said no; the message says which, for the seller."""


def end_date_text(moment) -> str:
    """An end date as sellers read it: the day in BUSINESS_TIME_ZONE."""
    return f"{timezone.localtime(moment, ZoneInfo(settings.BUSINESS_TIME_ZONE)):%d %b %Y}"


def _period_key(product: Product) -> str:
    # One notice per product per period: a renewal moves the end date.
    return f"{product.pk}:{product.live_until:%Y%m%d%H%M%S}"


class ListingService:

    @staticmethod
    def has_end_date(seller: Optional[SellerProfile]) -> bool:
        """Only a Limited Shop Owner's products are listed for a period."""
        return seller is not None and seller.seller_type == SellerProfile.TYPE_LIMITED_SHOP_OWNER

    @staticmethod
    def has_ended(product: Product) -> bool:
        return product.live_until is not None and product.live_until <= timezone.now()

    @classmethod
    def start_first_period(cls, product: Product) -> None:
        """
        Dates a product ProductService.publish is about to save, the first
        time it goes live. A re-publication keeps the running clock.
        """
        if product.live_until is None and cls.has_end_date(product.seller):
            product.live_until = ProductListingPolicy.current().first_period_end(timezone.now())

    @staticmethod
    def locked_message(product: Product) -> str:
        return (
            f"'{product.name}' is live until {product.live_until:%d %b %Y}, and a live product cannot be "
            "hidden, moved or deleted before then. You can still change its stock, down to 0."
        )

    # ------------------------------------------------------------------
    # Expiry
    # ------------------------------------------------------------------

    @staticmethod
    def due(products=None):
        """Published products whose period has ended, of `products` or of all."""
        products = Product.objects.all() if products is None else products
        return products.filter(status=Product.STATUS_PUBLISHED, live_until__lte=timezone.now())

    @classmethod
    def expire_due(cls, products=None) -> int:
        """
        Moves each due product (see due()) to EXPIRED with one
        PRODUCT_LISTING_EXPIRED audit row and a listing.expired notice to the
        seller. Each product commits on its own, so one failure loses no
        other's work. Returns how many moved.
        """
        moved = 0
        policy = None
        for pk in list(cls.due(products).values_list("pk", flat=True)):
            with transaction.atomic():
                product = (
                    cls.due(Product.objects.select_for_update())
                    .select_related("shop", "shop__owner")
                    .filter(pk=pk)
                    .first()
                )
                if product is None:
                    continue
                product.status = Product.STATUS_EXPIRED
                product.save(update_fields=["status", "updated_at"])
                AuditService.log(
                    action="PRODUCT_LISTING_EXPIRED",
                    target=product,
                    shop=product.shop,
                    seller=product.shop.owner if product.shop else None,
                    reason="The listing period ended.",
                    previous_state={"status": Product.STATUS_PUBLISHED},
                    new_state={"status": Product.STATUS_EXPIRED, "live_until": product.live_until.isoformat()},
                )
                policy = policy or ProductListingPolicy.current()
                publish(
                    events.LISTING_EXPIRED,
                    payload={
                        "product_id": product.pk,
                        "product_name": product.name,
                        "ended_on": end_date_text(product.live_until),
                        "renewal_points": policy.renewal_points,
                        "renewal_period_months": policy.renewal_period_months,
                    },
                    aggregate=product,
                    idempotency_key=f"listing_expired:{_period_key(product)}",
                )
                moved += 1
        if moved:
            logger.info("[LISTINGS] Expired %s product listing(s).", moved)
        return moved

    @staticmethod
    def ending_soon(policy: ProductListingPolicy, products=None):
        """Published products, of `products` or of all, whose period ends within policy.ending_soon_days."""
        products = Product.objects.all() if products is None else products
        now = timezone.now()
        return products.filter(
            status=Product.STATUS_PUBLISHED,
            live_until__gt=now,
            live_until__lte=now + timedelta(days=policy.ending_soon_days),
        )

    @classmethod
    def announce_ending_soon(cls, products=None) -> int:
        """
        Sends listing.ending_soon to the seller of each product, of
        `products` or of all, in the ending-soon window. The notice is keyed
        on the product and its end date, so a product hears once per period
        however often this runs, and a renewal starts a period with a notice
        of its own. Returns how many products are in the window.
        """
        policy = ProductListingPolicy.current()
        count = 0
        for product in cls.ending_soon(policy, products).order_by("pk").iterator():
            days_left = max(1, math.ceil((product.live_until - timezone.now()) / timedelta(days=1)))
            with transaction.atomic():
                publish(
                    events.LISTING_ENDING_SOON,
                    payload={
                        "product_id": product.pk,
                        "product_name": product.name,
                        "ends_on": end_date_text(product.live_until),
                        "days_left": days_left,
                        "renewal_points": policy.renewal_points,
                        "renewal_period_months": policy.renewal_period_months,
                    },
                    aggregate=product,
                    idempotency_key=f"listing_ending:{_period_key(product)}",
                )
            count += 1
        return count

    # ------------------------------------------------------------------
    # Renewal
    # ------------------------------------------------------------------

    @classmethod
    def renew(cls, product: Product, seller: SellerProfile, actor=None, ip_address: Optional[str] = None) -> Product:
        """
        Adds renewal_period_months to a product's listing, debiting
        renewal_points from the seller's wallet (PointService raises
        InsufficientPointsError). A live product is renewed early: the months
        go on after its current end date, so no paid day is lost. An expired
        one goes back on the storefront from now. No new review: staff
        approved the product before. Writes PRODUCT_LISTING_RENEWED.
        """
        if not product.shop or product.shop.owner_id != seller.pk:
            raise ListingError("You do not own the shop this product belongs to.")
        if not seller.is_operational:
            raise ListingError("Suspended or unapproved sellers cannot renew products.")
        if not cls.has_end_date(seller):
            raise ListingError("Your products have no end date, so there is nothing to renew.")

        policy = ProductListingPolicy.current()
        with transaction.atomic():
            product = Product.objects.select_for_update().select_related("shop", "shop__owner").get(pk=product.pk)
            # A period that ended moments ago may not have been swept yet.
            early = product.listing_locked
            if not (early or product.status == Product.STATUS_EXPIRED or (
                product.status == Product.STATUS_PUBLISHED and cls.has_ended(product)
            )):
                raise ListingError(
                    "Only a live or expired product can be renewed; "
                    f"this one is {product.get_status_display().lower()}."
                )
            if product.shop.status not in (Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE):
                raise ListingError(
                    f"Shop '{product.shop.name}' is {product.shop.get_status_display().lower()}, "
                    "so its products cannot go live."
                )

            PointService.debit(
                seller=seller,
                amount=policy.renewal_points,
                transaction_type=PointTransaction.TYPE_LISTING_RENEWAL,
                reason=f"Listing renewal for '{product.name}'",
                actor=actor,
                reference_type="PRODUCT",
                reference_id=str(product.pk),
            )
            previous = {"status": product.status, "live_until": product.live_until.isoformat()}
            product.status = Product.STATUS_PUBLISHED
            product.is_active = True
            product.live_until = policy.renewal_period_end(product.live_until if early else timezone.now())
            product.renewal_count += 1
            product.save(update_fields=["status", "is_active", "live_until", "renewal_count", "updated_at"])
            AuditService.log(
                action="PRODUCT_LISTING_RENEWED",
                target=product,
                actor=actor,
                shop=product.shop,
                seller=seller,
                previous_state=previous,
                new_state={"status": product.status, "live_until": product.live_until.isoformat()},
                metadata={
                    "points_debited": policy.renewal_points,
                    "renewal_count": product.renewal_count,
                    "early": early,
                },
                ip_address=ip_address,
            )
        logger.info("[LISTINGS] Renewed product %s until %s.", product.pk, product.live_until)
        return product

    # ------------------------------------------------------------------
    # Seller type and summary
    # ------------------------------------------------------------------

    @classmethod
    def seller_type_changed(cls, seller: SellerProfile, actor=None) -> int:
        """
        Called in the transaction that saves a seller's new type (the Django
        admin). Made Limited: published products without an end date get a
        full first period from now, so nothing leaves the storefront at once.
        Made Full: end dates are cleared and expired products go back to
        published. Returns how many products changed; audited on the seller.
        """
        products = Product.objects.filter(shop__owner=seller)
        if cls.has_end_date(seller):
            changed = products.filter(status=Product.STATUS_PUBLISHED, live_until__isnull=True).update(
                live_until=ProductListingPolicy.current().first_period_end(timezone.now())
            )
            restored = 0
        else:
            restored = products.filter(status=Product.STATUS_EXPIRED).update(status=Product.STATUS_PUBLISHED)
            changed = products.filter(live_until__isnull=False).update(live_until=None)
        if changed or restored:
            AuditService.log(
                action="SELLER_LISTING_PERIODS_CHANGED",
                target=seller,
                actor=actor,
                seller=seller,
                reason=f"Seller type changed to {seller.get_seller_type_display()}.",
                metadata={"products_redated": changed, "products_restored": restored},
            )
        return changed

    @classmethod
    def seller_summary(cls, seller: SellerProfile) -> dict:
        """The seller dashboard's counts, after expiring the seller's due products."""
        products = Product.objects.filter(shop__owner=seller)
        cls.expire_due(products)
        now = timezone.now()
        policy = ProductListingPolicy.current()
        published = Q(status=Product.STATUS_PUBLISHED)
        counts = products.aggregate(
            total=Count("pk"),
            live=Count("pk", filter=published & listing_running_q()),
            ending_soon=Count(
                "pk",
                filter=published & Q(live_until__gt=now, live_until__lte=now + timedelta(days=policy.ending_soon_days)),
            ),
            expired=Count("pk", filter=Q(status=Product.STATUS_EXPIRED)),
            in_review=Count("pk", filter=Q(status__in=(Product.STATUS_SUBMITTED, Product.STATUS_APPROVED))),
            not_live=Count(
                "pk", filter=Q(status__in=(Product.STATUS_DRAFT, Product.STATUS_REJECTED, Product.STATUS_UNPUBLISHED))
            ),
        )
        return {
            **counts,
            "has_end_date": cls.has_end_date(seller),
            "ending_soon_days": policy.ending_soon_days,
            "first_period_months": policy.first_period_months,
            "renewal_period_months": policy.renewal_period_months,
            "renewal_points": policy.renewal_points,
        }

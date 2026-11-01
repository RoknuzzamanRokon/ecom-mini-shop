"""
Who hears about products, stock, reviews and points (docs/NOTIFICATION_SYSTEM.md
§5): always the seller responsible.

- product.moderated: the product's shop owner (CATALOG); email for rejections only.
- listing.ending_soon and listing.expired: the product's shop owner
  (CATALOG), in-app and email.
- inventory.low_stock: the product's shop owner (INVENTORY), in-app only.
- review.created: the owner of the reviewed product's shop, or of the reviewed
  shop (REVIEWS), in-app only.
- points.adjusted: the seller whose wallet changed (WALLET), in-app only.
"""
from ..events import (
    INVENTORY_LOW_STOCK,
    LISTING_ENDING_SOON,
    LISTING_EXPIRED,
    POINTS_ADJUSTED,
    PRODUCT_MODERATED,
    REVIEW_CREATED,
)
from ..models import Audience
from .base import Recipient, handles

IN_APP_ONLY = frozenset()


def _product_owner(product_id):
    from shop.models import Product

    product = Product.objects.select_related("shop__owner__user").filter(pk=product_id).first()
    if product and product.shop and product.shop.owner:
        return product.shop.owner.user
    return None


@handles(PRODUCT_MODERATED)
def tell_owner_product_moderated(event):
    owner = _product_owner(event.payload["product_id"])
    if owner:
        email = event.payload["action"] == "reject"
        yield Recipient(owner, Audience.SELLER, channels=None if email else IN_APP_ONLY)


@handles(LISTING_ENDING_SOON)
def tell_owner_listing_ending(event):
    owner = _product_owner(event.payload["product_id"])
    if owner:
        yield Recipient(owner, Audience.SELLER)


@handles(LISTING_EXPIRED)
def tell_owner_listing_expired(event):
    owner = _product_owner(event.payload["product_id"])
    if owner:
        yield Recipient(owner, Audience.SELLER)


@handles(INVENTORY_LOW_STOCK)
def tell_owner_low_stock(event):
    owner = _product_owner(event.payload["product_id"])
    if owner:
        yield Recipient(owner, Audience.SELLER)


@handles(REVIEW_CREATED)
def tell_owner_new_review(event):
    from customers.models import Review, ShopReview

    payload = event.payload
    if payload["kind"] == "product":
        review = Review.objects.select_related("product__shop__owner__user").filter(pk=payload["review_id"]).first()
        shop = review.product.shop if review and review.product else None
    else:
        review = ShopReview.objects.select_related("shop__owner__user").filter(pk=payload["review_id"]).first()
        shop = review.shop if review else None
    if shop and shop.owner:
        yield Recipient(shop.owner.user, Audience.SELLER)


@handles(POINTS_ADJUSTED)
def tell_seller_points_adjusted(event):
    from sellers.models import SellerProfile

    seller = SellerProfile.objects.select_related("user").filter(pk=event.payload["seller_id"]).first()
    if seller:
        yield Recipient(seller.user, Audience.SELLER)

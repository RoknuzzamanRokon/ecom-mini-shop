"""
Who hears about seller accounts and shops (docs/NOTIFICATION_SYSTEM.md §5).

- seller.status_changed: the seller's own account (ACCOUNT, always emailed).
- shop.status_changed: the shop's owner (SHOPS).
- shop.submitted: the staff who can review shops, i.e. holders of
  'shops.approve' at routing time (D5), in-app only.
"""
from ..events import SELLER_STATUS_CHANGED, SHOP_STATUS_CHANGED, SHOP_SUBMITTED
from ..models import Audience
from .base import Recipient, handles


@handles(SELLER_STATUS_CHANGED)
def tell_seller_account_status(event):
    from sellers.models import SellerProfile

    seller = SellerProfile.objects.select_related("user").filter(pk=event.payload["seller_id"]).first()
    if seller:
        yield Recipient(seller.user, Audience.SELLER)


@handles(SHOP_STATUS_CHANGED)
def tell_shop_owner_status(event):
    from shops.models import Shop

    shop = Shop.objects.select_related("owner__user").filter(pk=event.payload["shop_id"]).first()
    if shop and shop.owner:
        yield Recipient(shop.owner.user, Audience.SELLER)


@handles(SHOP_SUBMITTED)
def tell_shop_reviewers(event):
    from rbac.services import users_with_permission

    for reviewer in users_with_permission("shops.approve").order_by("pk"):
        yield Recipient(reviewer, Audience.STAFF)

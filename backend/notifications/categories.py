"""
Notification categories (docs/NOTIFICATION_SYSTEM.md §3 D8 and §5).

People choose channels per category. `default_channels` are the channels a
category uses, all on until the person switches one off; a channel outside the
set is never used for that category. `locked_channels` can't be switched off:
in-app for every category, and email for ACCOUNT and PAYMENTS.

A leaf module: it imports only `notifications.models`.
"""
from dataclasses import dataclass

from .models import Channel


@dataclass(frozen=True)
class Category:
    code: str
    label: str
    default_channels: frozenset
    locked_channels: frozenset


IN_APP_ONLY = frozenset({Channel.IN_APP})
IN_APP_AND_EMAIL = frozenset({Channel.IN_APP, Channel.EMAIL})

ORDERS = "ORDERS"
SELLER_ORDERS = "SELLER_ORDERS"
PAYMENTS = "PAYMENTS"
SUPPORT = "SUPPORT"
ACCOUNT = "ACCOUNT"
SHOPS = "SHOPS"
CATALOG = "CATALOG"
INVENTORY = "INVENTORY"
REVIEWS = "REVIEWS"
WALLET = "WALLET"
STAFF_QUEUE = "STAFF_QUEUE"

CATEGORIES = {
    category.code: category
    for category in (
        Category(ORDERS, "Your orders", IN_APP_AND_EMAIL, IN_APP_ONLY),
        Category(SELLER_ORDERS, "Orders for your shop", IN_APP_AND_EMAIL, IN_APP_ONLY),
        Category(PAYMENTS, "Payments and refunds", IN_APP_AND_EMAIL, IN_APP_AND_EMAIL),
        Category(SUPPORT, "Support replies", IN_APP_AND_EMAIL, IN_APP_ONLY),
        Category(ACCOUNT, "Seller account decisions", IN_APP_AND_EMAIL, IN_APP_AND_EMAIL),
        Category(SHOPS, "Shop reviews and status", IN_APP_AND_EMAIL, IN_APP_ONLY),
        Category(CATALOG, "Product moderation", IN_APP_AND_EMAIL, IN_APP_ONLY),
        Category(INVENTORY, "Low stock", IN_APP_ONLY, IN_APP_ONLY),
        Category(REVIEWS, "New reviews", IN_APP_ONLY, IN_APP_ONLY),
        Category(WALLET, "Points and wallet", IN_APP_ONLY, IN_APP_ONLY),
        Category(STAFF_QUEUE, "Work waiting for you", IN_APP_AND_EMAIL, IN_APP_ONLY),
    )
}

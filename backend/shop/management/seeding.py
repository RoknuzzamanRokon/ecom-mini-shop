"""
Rules every seed command follows (BUG-068).

The dev settings point at a shared database, and the seeders match rows by
slug or username, so they used to rewrite real rows that happened to share
one. Now a seed command:

- runs only with DEBUG on and an explicit --i-know-this-is-a-dev-db flag;
- changes only rows it owns: accounts with a SEED_EMAIL_DOMAIN address, the
  shops those accounts own, and the products in those shops. A real row that
  shares a slug or username is reported and left alone;
- never resets the password of an account that already exists;
- moves stock through InventoryService, so every change has a ledger row.
"""

from django.conf import settings
from django.core.management.base import CommandError

#: Seed accounts are created with an address here, which marks them (and
#: their shops and products) as the seeders' own.
SEED_EMAIL_DOMAIN = "@minishop.demo"
CONFIRM_FLAG = "--i-know-this-is-a-dev-db"


def add_dev_db_argument(parser):
    parser.add_argument(
        CONFIRM_FLAG,
        action="store_true",
        dest="dev_db_confirmed",
        help="Required: confirms this database holds development data the seeder may add to.",
    )


def require_dev_database(options):
    """Refuses to seed unless DEBUG is on and the caller passed CONFIRM_FLAG."""
    if not settings.DEBUG:
        raise CommandError("Seeding is for development databases only, and DEBUG is off.")
    if not options.get("dev_db_confirmed"):
        raise CommandError(f"Seeding writes demo rows. Pass {CONFIRM_FLAG} to confirm this is a development database.")


def is_seed_account(user):
    return bool(user and user.email) and user.email.lower().endswith(SEED_EMAIL_DOMAIN)


def is_seed_shop(shop):
    return bool(shop and shop.owner_id) and is_seed_account(shop.owner.user)


def is_seed_product(product):
    return is_seed_shop(product.shop) if product.shop_id else False

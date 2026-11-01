"""
Every business rule MiniShop runs on, in one place (docs/BUSINESS_RULES_PLAN.md).

Each editable rule names the singleton row and field that store it. The
services keep reading those rows, so this file holds no second copy of any
value, and a rule's default is its model field's default. Each group also
lists the rules fixed in code, so the Console Rules page and the generated
docs/BUSINESS_RULES.md show them next to the values they shape.

To add a rule: add a field to a singleton policy model (with its migration),
add one Rule here, then run `python manage.py rules_doc`.
"""
from dataclasses import dataclass
from typing import Callable

from onboarding.models import OnboardingSettings
from points.models import PointExpiryPolicy, ProductCreationCost, SellerPointPolicy
from sellers.models import LimitedShopOwnerProductLimit
from shop.models import InventoryPolicy, ProductListingPolicy
from support.models import SupportPolicy


@dataclass(frozen=True)
class Rule:
    key: str
    model: type
    field: str
    label: str
    help: str
    unit: str
    minimum: int
    maximum: int
    applies_to: str
    takes_effect: str

    @property
    def default(self) -> int:
        return self.model._meta.get_field(self.field).default


@dataclass(frozen=True)
class Group:
    key: str
    title: str
    rules: tuple
    #: Rules fixed in code, shown with the group but not editable.
    fixed: tuple = ()


@dataclass(frozen=True)
class Check:
    """A rule about rules: `find(values)` returns {rule key: why} for what it refuses."""
    description: str
    find: Callable[[dict], dict]


LIMITED = "Limited Shop Owners"

GROUPS = (
    Group(
        key="products",
        title="Products",
        rules=(
            Rule(
                key="product.creation_cost",
                model=ProductCreationCost,
                field="required_points",
                label="Product creation cost",
                help="Points taken from the seller's wallet for each new product.",
                unit="points",
                minimum=1,
                maximum=1_000,
                applies_to="Every seller",
                takes_effect="The next product created",
            ),
            Rule(
                key="product.first_period_months",
                model=ProductListingPolicy,
                field="first_period_months",
                label="First listing period",
                help="Months a product stays live from its first publication.",
                unit="months",
                minimum=1,
                maximum=24,
                applies_to=LIMITED,
                takes_effect="Periods started afterwards; running periods keep their end date",
            ),
            Rule(
                key="product.renewal_period_months",
                model=ProductListingPolicy,
                field="renewal_period_months",
                label="Renewal period",
                help="Months each renewal adds: after the current end date while live, from the renewal once expired.",
                unit="months",
                minimum=1,
                maximum=24,
                applies_to=LIMITED,
                takes_effect="Renewals afterwards",
            ),
            Rule(
                key="product.renewal_points",
                model=ProductListingPolicy,
                field="renewal_points",
                label="Renewal cost",
                help="Points the seller pays for each renewal.",
                unit="points",
                minimum=1,
                maximum=1_000,
                applies_to=LIMITED,
                takes_effect="The next renewal",
            ),
            Rule(
                key="product.ending_soon_days",
                model=ProductListingPolicy,
                field="ending_soon_days",
                label="Ending soon window",
                help=(
                    "Days before its end date a live product shows as ending soon on the seller dashboard, "
                    "and its seller is notified."
                ),
                unit="days",
                minimum=1,
                maximum=30,
                applies_to=LIMITED,
                takes_effect="At once; notices go out with the next daily expire_listings run",
            ),
            Rule(
                key="product.limited_max_products",
                model=LimitedShopOwnerProductLimit,
                field="max_products",
                label="Limited Shop Owner product limit",
                help=(
                    "Products a Limited Shop Owner may hold, expired ones included until deleted. Products they "
                    "already hold above it stay."
                ),
                unit="products",
                minimum=0,
                maximum=1_000,
                applies_to=LIMITED,
                takes_effect="The next product created",
            ),
        ),
        fixed=(
            "A Full Shop Owner's products have no end date.",
            "While a product is live, its seller cannot hide it, delete it or move it to another shop.",
            (
                "An expired product leaves the storefront. Its seller renews it or deletes it; staff cannot "
                "publish it again. Nothing is refunded on delete."
            ),
            "A product with units held for open orders cannot be deleted.",
            "A renewal needs no new review, and a seller may renew a live product early.",
            "The seller is notified when a product enters the ending-soon window and when it expires.",
        ),
    ),
    Group(
        key="stock",
        title="Stock",
        rules=(
            Rule(
                key="stock.low_stock_threshold",
                model=InventoryPolicy,
                field="low_stock_threshold",
                label="Low stock threshold",
                help=(
                    "Available units at or below which a product counts as low on stock: the admin filter and "
                    "badge, the dashboard metrics and the seller's low-stock notification."
                ),
                unit="units",
                minimum=1,
                maximum=1_000,
                applies_to="Every seller",
                takes_effect="At once; the next stock change below it notifies the seller",
            ),
        ),
        fixed=(
            "Sellers change stock at any time for free, also while a product is live.",
            "At 0 available units the storefront shows Out of stock and Add to Cart is disabled.",
        ),
    ),
    Group(
        key="points",
        title="Points",
        rules=(
            Rule(
                key="points.seller_validity_days",
                model=SellerPointPolicy,
                field="validity_days",
                label="Seller point validity",
                help="Days each purchase adds to the expiry date of a seller's points.",
                unit="days",
                minimum=1,
                maximum=365,
                applies_to=LIMITED,
                takes_effect="The next purchase; points already held keep their date",
            ),
            Rule(
                key="points.minimum_purchase",
                model=SellerPointPolicy,
                field="minimum_purchase",
                label="Minimum point sale",
                help="The fewest points staff may give a seller at once.",
                unit="points",
                minimum=1,
                maximum=100_000,
                applies_to="Every seller",
                takes_effect="The next sale",
            ),
            Rule(
                key="points.staff_expiry_months",
                model=PointExpiryPolicy,
                field="expiry_months",
                label="Staff point validity",
                help="Months a batch of points received into a staff wallet lasts.",
                unit="months",
                minimum=1,
                maximum=24,
                applies_to="Staff wallets",
                takes_effect="Points received afterwards",
            ),
        ),
        fixed=(
            "A Full Shop Owner's points never expire.",
            "Sellers pay staff outside MiniShop (cash, bKash); staff give the points from their own wallet.",
            (
                "A purchase moves the seller's whole unspent balance to one date: the later of now and the "
                "current date, plus the validity days. A refunded product fee joins the current date."
            ),
            "Points are spent soonest-expiring first.",
            "Taking points back has no minimum.",
        ),
    ),
    Group(
        key="onboarding",
        title="Onboarding",
        rules=(
            Rule(
                key="onboarding.starting_points",
                model=OnboardingSettings,
                field="starting_points",
                label="Starting points",
                help="Points that move from the onboarder's wallet to each new seller they open. 0 gives none.",
                unit="points",
                minimum=0,
                maximum=100_000,
                applies_to="Onboarded sellers",
                takes_effect="Sellers onboarded afterwards",
            ),
            Rule(
                key="onboarding.tokens_per_seller",
                model=OnboardingSettings,
                field="tokens_per_seller",
                label="Tokens per seller",
                help="Tokens the onboarder earns for each seller they open. 0 gives none.",
                unit="tokens",
                minimum=0,
                maximum=100_000,
                applies_to="Sales Team onboarders",
                takes_effect="Sellers onboarded afterwards",
            ),
            Rule(
                key="onboarding.taka_per_token",
                model=OnboardingSettings,
                field="taka_per_token",
                label="Token value",
                help="What one token is worth in ৳ when an onboarder hands tokens in for payment.",
                unit="৳ per token",
                minimum=1,
                maximum=1_000,
                applies_to="Sales Team onboarders",
                takes_effect="Payout requests made afterwards; a pending request keeps its value",
            ),
            Rule(
                key="onboarding.edit_code_minutes",
                model=OnboardingSettings,
                field="edit_code_minutes",
                label="Edit code valid for",
                help="Minutes the code sent to the seller can be used to open an edit session.",
                unit="minutes",
                minimum=2,
                maximum=30,
                applies_to="Sales Team onboarders",
                takes_effect="The next code sent",
            ),
            Rule(
                key="onboarding.edit_window_minutes",
                model=OnboardingSettings,
                field="edit_window_minutes",
                label="Edit window",
                help=(
                    "Minutes the onboarder may correct the seller, its shops and their products once the code "
                    "is accepted."
                ),
                unit="minutes",
                minimum=5,
                maximum=120,
                applies_to="Sales Team onboarders",
                takes_effect="The next session opened",
            ),
        ),
        fixed=(
            "A Sales Team member sells points only to the sellers they onboarded, once those are approved.",
            (
                "Rejecting an onboarded seller returns its starting points to the onboarder (up to what is "
                "left) and takes back the tokens it earned."
            ),
            (
                "An onboarded seller chooses their own password at first sign-in, since the onboarder set the "
                "first one."
            ),
            (
                "Edits need the seller's code: 5 wrong tries void it, and a new code can be asked for once a "
                "minute. The seller type and the login account cannot be changed this way."
            ),
            (
                "A Sales Team member sees only the products they added, and only with "
                "'onboarding.products.view', which an admin can turn off for the team or for one person."
            ),
            (
                "Handing tokens in holds them until an admin decides, one request at a time; accepted tokens "
                "move to that admin, rejected or cancelled ones come back. Nobody settles their own request."
            ),
        ),
    ),
    Group(
        key="support",
        title="Support",
        rules=(
            Rule(
                key="support.max_unresolved_tickets",
                model=SupportPolicy,
                field="max_unresolved_tickets",
                label="Open tickets per person",
                help=(
                    "Unresolved tickets one person may have at once, counted separately as a customer and as "
                    "a seller."
                ),
                unit="tickets",
                minimum=1,
                maximum=50,
                applies_to="Customers and sellers",
                takes_effect="The next ticket opened; tickets already open stay",
            ),
            Rule(
                key="support.auto_close_after_days",
                model=SupportPolicy,
                field="auto_close_after_days",
                label="Auto-close after",
                help="Days a resolved ticket may go without a customer reply before it closes on its own.",
                unit="days",
                minimum=1,
                maximum=90,
                applies_to="Resolved tickets",
                takes_effect="The next daily close_resolved_tickets run",
            ),
        ),
        fixed=(
            "A customer reply reopens a resolved ticket, so it does not close on its own.",
            "Subjects are 5 to 150 characters and messages up to 5,000.",
            "Each message takes up to 5 attachments of 5 MB each: JPG, PNG, WebP or PDF.",
        ),
    ),
)

RULES = {rule.key: rule for group in GROUPS for rule in group.rules}


def _starting_points_reach_minimum(values: dict) -> dict:
    # Starting points are a staff credit, which is a sale of at least the
    # minimum (PointService.adjust_points); fewer would fail every onboarding.
    starting = values["onboarding.starting_points"]
    minimum = values["points.minimum_purchase"]
    if 0 < starting < minimum:
        return {
            "onboarding.starting_points": (
                f"Starting points must be 0 or at least the minimum point sale ({minimum}). "
                "To raise the minimum above the starting points, raise both in one save."
            )
        }
    return {}


CHECKS = (
    Check(
        description="Onboarding starting points are 0 or at least the minimum point sale.",
        find=_starting_points_reach_minimum,
    ),
)

# Business rules

Generated from `backend/rules/registry.py` by `python manage.py rules_doc`;
do not edit by hand. The values below are the defaults. The current
values, and who changed them last, are on the Console Rules page
(`/admin/rules`), the only place they change. Every change there needs a
reason and writes a `RULE_CHANGED` audit row.

A change never rewrites what already happened: point lots keep their
dates, running listing periods keep their end dates, and each onboarding
keeps what its seller was given.

## Products

| Key | Rule | Default | Range | Applies to | Takes effect |
|---|---|---|---|---|---|
| `product.creation_cost` | **Product creation cost.** Points taken from the seller's wallet for each new product. | 5 points | 1–1,000 | Every seller | The next product created |
| `product.first_period_months` | **First listing period.** Months a product stays live from its first publication. | 4 months | 1–24 | Limited Shop Owners | Periods started afterwards; running periods keep their end date |
| `product.renewal_period_months` | **Renewal period.** Months each renewal keeps an expired product live again. | 2 months | 1–24 | Limited Shop Owners | Renewals afterwards |
| `product.renewal_points` | **Renewal cost.** Points the seller pays to renew an expired product. | 5 points | 1–1,000 | Limited Shop Owners | The next renewal |
| `product.ending_soon_days` | **Ending soon window.** Days before its end date a live product shows as ending soon on the seller dashboard. | 7 days | 1–30 | Limited Shop Owners | At once |
| `product.limited_max_products` | **Limited Shop Owner product limit.** Products a Limited Shop Owner may hold. Products they already hold above it stay. | 10 products | 0–1,000 | Limited Shop Owners | The next product created |

Fixed in code:

- A Full Shop Owner's products have no end date.
- While a product is live, its seller cannot hide it, delete it or move it to another shop.
- An expired product leaves the storefront. Its seller renews it; staff cannot publish it again.
- A renewal needs no new review.

## Stock

| Key | Rule | Default | Range | Applies to | Takes effect |
|---|---|---|---|---|---|
| `stock.low_stock_threshold` | **Low stock threshold.** Available units at or below which a product counts as low on stock: the admin filter and badge, the dashboard metrics and the seller's low-stock notification. | 10 units | 1–1,000 | Every seller | At once; the next stock change below it notifies the seller |

Fixed in code:

- Sellers change stock at any time for free, also while a product is live.
- At 0 available units the storefront shows Out of stock and Add to Cart is disabled.

## Points

| Key | Rule | Default | Range | Applies to | Takes effect |
|---|---|---|---|---|---|
| `points.seller_validity_days` | **Seller point validity.** Days each purchase adds to the expiry date of a seller's points. | 30 days | 1–365 | Limited Shop Owners | The next purchase; points already held keep their date |
| `points.minimum_purchase` | **Minimum point sale.** The fewest points staff may give a seller at once. | 100 points | 1–100,000 | Every seller | The next sale |
| `points.staff_expiry_months` | **Staff point validity.** Months a batch of points received into a staff wallet lasts. | 2 months | 1–24 | Staff wallets | Points received afterwards |

Fixed in code:

- A Full Shop Owner's points never expire.
- Sellers pay staff outside MiniShop (cash, bKash); staff give the points from their own wallet.
- A purchase moves the seller's whole unspent balance to one date: the later of now and the current date, plus the validity days. A refunded product fee joins the current date.
- Points are spent soonest-expiring first.
- Taking points back has no minimum.

## Onboarding

| Key | Rule | Default | Range | Applies to | Takes effect |
|---|---|---|---|---|---|
| `onboarding.starting_points` | **Starting points.** Points that move from the onboarder's wallet to each new seller they open. 0 gives none. | 200 points | 0–100,000 | Onboarded sellers | Sellers onboarded afterwards |
| `onboarding.tokens_per_seller` | **Tokens per seller.** Tokens the onboarder earns for each seller they open. 0 gives none. | 51 tokens | 0–100,000 | Sales Team onboarders | Sellers onboarded afterwards |

Fixed in code:

- A Sales Team member sells points only to the sellers they onboarded, once those are approved.
- Rejecting an onboarded seller returns its starting points to the onboarder (up to what is left) and takes back the tokens it earned.

## Checks between rules

- Onboarding starting points are 0 or at least the minimum point sale.

# Point validity and product listing periods

Decided 2026-11-01. New feature work, outside the fixes-only roadmap in
`FUTURE_PLAN.md`. Branch: `feature/listing-validity`.

## Rules

1. **Seller points last 30 days.** Points a seller receives expire 30 days
   later if they are not spent (`SellerPointPolicy.validity_days`). Staff
   wallets keep their own period (`PointExpiryPolicy`, 2 months).
2. **A new purchase stacks the validity.** When a seller gets new points, the
   whole unspent balance gets one date: the later of now and the current
   expiry date, plus 30 days. Example: 90 points with 5 days left, plus 100
   bought, gives 190 points with 35 days left. A refund (a product fee given
   back) joins the current date and does not extend it.
3. **Points are sold, at least 100 at a time.** The seller pays staff outside
   the system (cash, bKash), and the staff member gives the points from their
   own wallet. Every staff credit to a seller must be at least
   `SellerPointPolicy.minimum_purchase` (100). Onboarding starting points
   (200) obey the same minimum. Taking points back has no minimum.
4. **Who sells.** Staff who can credit sellers (Administrator, Finance) sell
   to any seller, as today. A Sales Team member sells only to the sellers they
   onboarded, once those are approved, from their own wallet:
   `POST /api/onboarding/sellers/<pk>/points/`.
5. **A product is live for 4 months the first time.** The period starts when
   the product is first published (`ProductListingPolicy.first_period_months`).
   When it ends, the product becomes `EXPIRED` and leaves the storefront.
6. **Renewal.** The seller renews an expired product for 5 points
   (`renewal_points`), with no new review. A renewal lasts 2 months
   (`renewal_period_months`), every time.
7. **No removal while live.** While a product's period runs, the seller cannot
   hide it, delete it, or move it to another shop. Stock can change at any
   time, for free, down to 0; at 0 the storefront shows "Out of stock".
   Other edits (name, price, description, images) work as today. Staff
   moderation (unpublish, delete) is unchanged.
8. **Full Shop Owners are exempt from both.** Their points never expire (as
   today) and their products have no end date. Rules 1, 2, 5, 6 and 7 apply to
   Limited Shop Owners; rule 3's minimum applies to everyone.
9. **Seller dashboard.** The seller sees how many products are live, ending
   soon, expired and in review, each product's end date (or the date it
   expired), a Renew button on expired ones, and when their points expire.

## How expiry happens

As for points: lazily and by a daily command. The public catalog hides a
product whose period has ended even before its status changes. Seller reads
and `python manage.py expire_listings` (cron, daily) move such products to
`EXPIRED` and write one `PRODUCT_LISTING_EXPIRED` audit row each.

## Edge cases, decided here

- **Existing data.** Published products of Limited Shop Owners get 4 months
  from the migration date. Existing seller point lots keep their dates; the new
  30-day period applies to points received afterwards.
- **Staff publish.** Publishing starts the first period when the product has
  none. Re-publishing an unpublished product keeps its clock. Staff cannot
  publish a product whose period has ended; the seller renews it.
- **Seller type change** (Django admin only). Full to Limited: published
  products without an end date get a full first period from now, and point
  lots a full 30 days, so nothing vanishes at once. Limited to Full: end dates
  are cleared and expired products go back to published.
- **Sales to sellers awaiting approval** are refused: rejecting an onboarded
  seller returns only its starting points.
- **Credit and take-back.** A staff credit followed by a take-back still
  extends the seller's other points by 30 days. Accepted: it needs a staff
  member who holds both point permissions.

## Scope boundary

Not in this work: a payment gateway or a ৳ price per point, a seller "buy
points" request flow, renewing before the period ends, notifications about
expiring products, seller deletion of products (sellers still lack
`products.delete`), and the Sales Team Android app.

Early renewal, the expiry notices and deleting expired products came later,
in `docs/FOLLOW_UPS_PLAN.md`.

## Tasks

### Phase A: seller points (backend)

- A1. `SellerPointPolicy` singleton (`validity_days` 30, `minimum_purchase`
  100), its admin and migration. `PointExpiryPolicy` now covers staff wallets.
- A2. Stacking in `PointService.credit`; refunds join the current date;
  `restart_expiry_clock` uses the seller period for seller wallets.
- A3. The minimum in `adjust_points` (CREDIT); `OnboardingSettings` validates
  `starting_points` against it.
- A4. The Sales Team sale endpoint (own, approved sellers), audited as
  `ONBOARDING_POINTS_SOLD`.
- A5. Seller wallet payload: `validity_days`, `minimum_purchase`.
- A6. Tests.

### Phase B: product listing periods (backend)

- B1. `Product.live_until`, `Product.renewal_count`, status `EXPIRED`,
  `PointTransaction.TYPE_LISTING_RENEWAL`, `ProductListingPolicy` (4, 2, 5),
  and the backfill migration.
- B2. `ListingService`: start the period on publish (Limited only), refuse
  publishing an ended listing, `expire_due` plus the `expire_listings`
  command, `renew`.
- B3. Visibility: `Product.objects.public()`, `is_publicly_visible`, category
  counts, the cart check, the Django admin storefront checklist.
- B4. The lock while live: hide, shop move and delete refused.
- B5. Seller type changes in the Django admin.
- B6. Seller API: listing fields on seller products,
  `GET /api/products/mine/listings/`, `POST /api/products/mine/<pk>/renew/`.
- B7. Tests.

### Phase C: frontend

- C1. Seller dashboard: listing summary and table, Renew, points expiry and
  the minimum purchase.
- C2. Seller products page: end date, Renew, hide and delete disabled while
  live. (The page has no status filter; the dashboard's tabs list live,
  ending-soon and expired products.)
- C3. Storefront product card: "Out of stock", Add to Cart disabled.
- C4. Console: `EXPIRED` in product filters and badges, the end date on the
  product page, the 100-point minimum in the credit forms.
- C5. Vitest tests, lint, build.

### Phase D: verification and docs

- D1. Full backend suite and frontend build.
- D2. A live check in headless Chrome, throwaway data cleaned up.
- D3. `MINISHOP_REVIEW_STATE.md` and `FUTURE_PLAN.md` updated.

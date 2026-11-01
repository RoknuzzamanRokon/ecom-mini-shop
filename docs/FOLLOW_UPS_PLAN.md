# Follow-ups to listing validity and the Rules page

Decided 2026-11-01, after `feature/listing-validity` and `feature/business-rules`
reached master. The user answered the five open points:

1. Sellers can delete expired products.
2. Sellers can renew before the end date, and are notified before it.
3. A cron file for the daily commands, to install on the server later.
4. The support limits join the Console Rules page.
5. A screen for the Sales Team to sell points to their sellers.

Branch: `feature/listing-followups`.

## 1. Deleting expired products

- The shop owner deletes their own **expired** product without `products.delete`.
  A published product whose period has ended counts as expired. Other statuses
  keep today's rule: `products.delete`, which sellers do not hold.
- Refused while units of the product are reserved for open orders.
- Nothing is refunded (neither the creation fee nor renewals).
- Deleting frees its place under the Limited Shop Owner product limit. Expired
  products keep counting until they are deleted.
- Orders keep their lines: `OrderItem.product` is `SET_NULL` and the line holds
  its own snapshot.
- The `PRODUCT_DELETED` audit row records the status it was deleted from.
- Seller products page: Delete is enabled on expired products only, with a
  hint on the others.

## 2. Early renewal and notices

- **Renewal** works while the period runs as well as after it ends:
  - early: the new end date is the current end date plus
    `renewal_period_months`, so no paid day is lost;
  - expired: now plus `renewal_period_months`, as today.
  - The cost is the same `renewal_points`. The audit row says `early`.
  - A product staff unpublished stays out of reach, as today.
- **Notices**, two new seller events in the CATALOG category (renamed
  "Products and listings"), in-app and email, one per product per period:
  - `listing.ending_soon`: the product entered the ending-soon window
    (`product.ending_soon_days` on the Rules page). Sent by the daily
    `expire_listings` run. Keyed on product + end date, so a renewal starts a
    new period that gets its own notice.
  - `listing.expired`: the product moved to EXPIRED, by the daily run or a
    seller read.
- Seller dashboard and products page: Renew on live products with an end date,
  showing the new end date before confirming.

## 3. Cron

`deploy/cron/`:

- `minishop.crontab`: the daily commands (`expire_points`, `expire_listings`,
  `close_resolved_tickets`, `purge_notifications`) plus
  `run_notification_worker --once` every minute, for email (skip it when the
  worker runs as a service).
- `run-manage.sh`: runs one `manage.py` command with the venv and
  `config.settings.prod`, holds a lock so a slow run never overlaps the next,
  and appends to a log file.
- `README.md`: how to install and check it.

## 4. Support limits on the Rules page

- New singleton `support.SupportPolicy`:
  - `max_unresolved_tickets`, default 5, range 1–50: unresolved tickets one
    person may have per channel (customer, seller);
  - `auto_close_after_days`, default 7, range 1–90: quiet days before a
    resolved ticket closes.
- The services and `close_resolved_tickets` read it. Its Django admin page is
  read-only with the Console link, like the other rule pages.
- A "Support" group in `rules/registry.py`; `docs/BUSINESS_RULES.md`
  regenerated. Text lengths and attachment limits stay in code.

## 5. Sales Team point sales

- Console page `/admin/my-sellers` ("My Sellers") for `sellers.onboard`:
  - my points, my tokens and the minimum point sale;
  - the sellers I onboarded, with status, shops and products;
  - **Sell points** on approved sellers: amount (at least the minimum, at most
    my points), confirm, then the seller's new balance and expiry date and my
    remaining points.
- Uses the existing `/api/onboarding/me/`, `/api/onboarding/sellers/` and
  `/api/onboarding/sellers/<pk>/points/`. No backend change.
- Administrators and Finance keep selling from Users → the points panel.

## Not in this work

- Sellers deleting drafts or rejected products.
- Point expiry notices.
- A digest instead of one notice per product.
- Onboarding sellers from the Console (that is the Android app's job).

## Tasks

- A. Backend: expired deletes; early renewal; the two events, templates,
  handler and the `expire_listings` warnings; `SupportPolicy`, registry group,
  migration, read-only admin; tests.
- B. Frontend: seller Delete and early Renew; the My Sellers page and nav item;
  tests, lint, build.
- C. `deploy/cron/`.
- D. Full backend suite, migrate the dev DB and the 16 test clones, a live
  check in headless Chrome, docs.

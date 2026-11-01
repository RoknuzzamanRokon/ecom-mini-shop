# Business rules in one place

Decided 2026-11-01. New feature work, outside the fixes-only roadmap in
`FUTURE_PLAN.md`. Branch: `feature/business-rules`, started from
`feature/listing-validity` (not merged yet), which adds two of the rule tables.

## Goal

Every business rule (what a product costs, how long points and listings last,
what onboarding gives and earns) is written down in one file and changed from
one Console page. Today the 10 values sit in 6 singleton tables across 4 apps,
each with its own Django admin page, and two more are constants in code. Nobody
can see them side by side. A change writes no audit row, and the rules are not
checked against each other: raising the minimum point sale above the onboarding
starting points goes through and then makes every onboarding fail.

## The rules

Editable values. "Limited" means Limited Shop Owners only; Full Shop Owners
are exempt.

| Key | Rule | Default | Range | Applies to | Takes effect |
|---|---|---|---|---|---|
| `product.creation_cost` | Points a new product costs | 5 | 1–1,000 | Every seller | The next product created |
| `product.first_period_months` | Months a product is live from its first publication | 4 | 1–24 | Limited | Periods started afterwards |
| `product.renewal_period_months` | Months each renewal adds | 2 | 1–24 | Limited | Renewals afterwards |
| `product.renewal_points` | Points a renewal costs | 5 | 1–1,000 | Limited | The next renewal |
| `product.ending_soon_days` | Days before the end date a product counts as "ending soon" | 7 | 1–30 | Limited | At once (dashboard window) |
| `product.limited_max_products` | Products a Limited Shop Owner may hold | 10 | 0–1,000 | Limited | The next product created |
| `stock.low_stock_threshold` | Units at or below which stock is "low" | 10 | 1–1,000 | Every seller | At once (filters, metrics); the next stock change notifies |
| `points.seller_validity_days` | Days each purchase adds to a seller's point expiry | 30 | 1–365 | Limited | The next purchase |
| `points.minimum_purchase` | Fewest points staff may give a seller at once | 100 | 1–100,000 | Every seller | The next sale |
| `points.staff_expiry_months` | Months points last in a staff wallet | 2 | 1–24 | Staff | Points received afterwards |
| `onboarding.starting_points` | Points each new onboarded seller gets | 200 | 0, or minimum purchase–100,000 | Sales Team sellers | Sellers onboarded afterwards |
| `onboarding.tokens_per_seller` | Tokens the onboarder earns per seller | 51 | 0–100,000 | Sales Team | Sellers onboarded afterwards |

A change never rewrites what already happened. Point lots keep their dates,
running listing periods keep their end dates, and each `SellerOnboarding` row
keeps what that seller was given. The page says this next to the save button.

Fixed rules, shown on the page under their group but not editable:

- **Products:** a Full Shop Owner's products have no end date. A live product
  cannot be hidden, deleted or moved to another shop. Stock changes are free.
  An expired product is renewed by its seller; staff cannot re-publish it.
- **Points:** a Full Shop Owner's points never expire. A purchase moves the
  whole unspent balance to one date: the later of now and the current date,
  plus the validity days. A refunded product fee joins the current date.
  Points are spent soonest-expiring first. Taking points back has no minimum.
- **Onboarding:** rejecting an onboarded seller returns its starting points to
  the onboarder (up to what is left) and takes back the tokens it earned.

## Design

1. **One registry file, `backend/rules/registry.py`.** It lists every editable
   rule: key, group, label, help text, unit, range, who it applies to, when
   it takes effect, and where it is stored (model and field). Each group also
   carries its fixed rules. The default is the model field's default, so it
   is defined in exactly one place. Adding a rule later means adding a field
   and one registry entry.
2. **Storage stays where it is.** The 6 singleton tables keep their rows, and
   every service keeps reading them as today, so nothing moves and no caller
   changes. The two values in code get stored too:
   `ProductListingPolicy.ending_soon_days` and a new singleton
   `shop.InventoryPolicy` (`low_stock_threshold`). Merging all of it into one
   key-value table was rejected: it touches some 20 call sites and many tests
   across 4 apps, and the person using the page would see no difference.
3. **One service, `RuleService`.** `snapshot()` returns every group with
   current values, defaults and the last change. `update(changes, reason,
   actor, ip)` checks everything first, then saves all the changes in one
   transaction (rows locked, pk=1 created when missing). It writes one
   `RULE_CHANGED` audit row per changed rule, with the old value, the new value
   and the reason.
4. **One API: `GET` / `PATCH /api/admin/rules/`.** The PATCH body is
   `{changes: {key: {from, to}}, reason}`. If `from` no longer matches the
   stored value, the request is refused with 409 ("changed by someone else,
   reload"), so two people cannot silently overwrite each other.
5. **One Console page: `/admin/rules`** ("Rules", in the Administration
   section). It shows one card per group (Products, Stock, Points,
   Onboarding). Each rule row shows its label, help text, a number input with
   the unit and range, its default, and who changed it last and when. The
   fixed rules are listed under each card. A bar at the bottom counts the
   pending changes and asks for a reason. A confirmation step lists every
   change as old → new before saving. Without `rules.manage`, the page is
   read-only.
6. **The Django admin pages become read-only.** The 7 singleton admin pages
   keep showing their values with a link to the Console page, so every change
   goes through the checks and the audit log.
7. **The written copy is generated.** `python manage.py rules_doc` writes
   `docs/BUSINESS_RULES.md` from the registry. A test runs
   `rules_doc --check` and fails when the committed file is stale, so the doc
   cannot drift from the code.
8. **Settings fallbacks go.** `PRODUCT_CREATION_POINT_COST` (in
   `config/settings/base.py`) and the `getattr` fallbacks to
   `POINT_EXPIRY_MONTHS`, `LIMITED_SHOP_OWNER_PRODUCT_LIMIT` and
   `LOW_STOCK_THRESHOLD` are removed. They are second defaults that nobody
   sets.

## Checks on a save

- Every value must be a whole number inside its range.
- `onboarding.starting_points` must be 0 or at least `points.minimum_purchase`,
  checked against the values after the save. Raising the minimum therefore
  needs the starting points raised in the same save, and the error says so.
- A value equal to the stored one is not a change. A save with no real change
  is refused.
- The reason is required (at most 500 characters).

## Who can see and change

New permissions, seeded and added by an rbac migration:

- `rules.view`: Administrator, Finance, Operation Manager.
- `rules.manage`: Administrator.

Super Administrator holds both, as with every permission.

## Edge cases, decided here

- **No saved row** (the dev DB today): the page shows the defaults; the first
  save creates the row.
- **Lowering the product limit** below what a seller holds: their products
  stay; they cannot add more until they are under the limit.
- **Changing period lengths:** running periods keep their end date; the new
  length applies from the next publication or renewal.
- **Lowering the validity days:** existing point dates stay; the next purchase
  uses the new length.

## Scope boundary

Not in this work:

- Switching the fixed rules on or off (for example the Full Shop Owner
  exemptions).
- Support limits (5 unresolved tickets per customer, auto-close after 7 days).
  They could be added later as registry entries.
- Technical and security limits (upload sizes, login throttles, token
  lifetimes, text lengths). These stay in code.
- Notifying anyone when a rule changes.
- Scheduling future changes.
- Open point from `feature/listing-validity`: expired products still count
  towards the Limited product limit, and sellers cannot delete them.

## Tasks

### Phase A: backend

- A1. Store the two values that live in code:
  - `ProductListingPolicy.ending_soon_days`;
  - a new `shop.InventoryPolicy` singleton for the low-stock threshold;
  - the migration;
  - every use of `ENDING_SOON_DAYS` and `LOW_STOCK_THRESHOLD` (seller API,
    listing summary, admin filters and badges, metrics, the low-stock
    notification) reads the policy instead;
  - remove the settings fallbacks.
- A2. The `rules` app: `registry.py`, plus `RuleService` (snapshot, update,
  range and cross-rule checks, the 409 on a stale value, `RULE_CHANGED` audit
  rows).
- A3. `rules.view` and `rules.manage`: `seed_rbac` and an rbac migration.
- A4. `GET` / `PATCH /api/admin/rules/`.
- A5. Django admin: the 7 singleton pages read-only, with the Console link.
- A6. `rules_doc` (`--check`) and the generated `docs/BUSINESS_RULES.md`.
- A7. Tests:
  - registry entries match model fields and ranges;
  - snapshot;
  - update, ranges, cross-rule check, 409;
  - the audit rows;
  - permissions;
  - the read-only Django admin;
  - that the services follow a saved value;
  - doc freshness.

### Phase B: frontend

- B1. Types, `admin-api.ts` calls, `ADMIN_PERMISSIONS.rulesView` /
  `rulesManage`, the "Rules" nav item.
- B2. The `/admin/rules` page: group cards, inputs, defaults, last change,
  fixed rules, the save bar with reason, confirm, the read-only mode, and the
  409 and validation errors.
- B3. Vitest tests, lint, build.

### Phase C: verification and docs

- C1. Run the full backend suite and migrate the dev DB and the 16 test clones.
- C2. A live check in headless Chrome:
  - change a value with a reason;
  - see the audit row;
  - see the seller side follow (the product creation cost);
  - restore the defaults and remove the throwaway rows.
- C3. Update `MINISHOP_REVIEW_STATE.md` and `FUTURE_PLAN.md`.

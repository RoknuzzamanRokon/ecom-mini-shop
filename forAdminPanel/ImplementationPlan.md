# Django Superuser Admin — Professional Platform Control Panel

Turn `http://127.0.0.1:8001/admin/` into a powerful, professional, secure, and highly usable internal administration control center for MiniShop superusers.

> **Status:** Phases 1–5 complete. See [task_list.md](./task_list.md) for the per-item tracker.
>
> **Scope:** Django admin only. The Next.js management console at `frontend/src/app/admin` is a separate surface and is **not** covered here — see [Out of scope](#out-of-scope).

---

## What this revision corrects

The first draft of this plan was written against a stale reading of the codebase. Three things were wrong:

1. **It missed that the admin was broken.** `manage.py check` failed with **7 `admin.E108`/`E116` errors**, which makes `runserver` refuse to start — the admin *and* the `/api/` endpoints the storefront depends on were both down.
2. **It planned work that was already done.** Model registration, `select_related`, annotated counts, lifecycle actions and the User admin were all already built and committed.
3. **It described the dashboard as existing.** `index.html`'s "4 KPI cards" were static `<a>` navigation links containing zero numbers.

It also used absolute Linux paths (`/mnt/Project/Python/MiniShop/...`) that do not exist in this repo. All paths below are repo-relative.

---

## Current state

### Registered models — all 25

| App | Models | Notes |
|-----|--------|-------|
| **audit** | `AuditLog` | Read-only; all three permissions blocked |
| **cart** | `Cart` + `CartItem` (inline) | `select_related` on both |
| **customers** | `CustomerProfile`, `Address`, `Favorite` | Annotated order/address counts |
| **points** | `SellerWallet`, `PointTransaction`, `ProductCreationCost` | Ledger immutable; cost model is a pk=1 singleton |
| **rbac** | `Role` (inline), `Permission`, `UserRole`, `RolePermission`, + re-registered `auth.User` | `User` carries a `UserRole` inline |
| **sellers** | `SellerProfile` | Fieldsets + lifecycle actions |
| **shop** | `Category`, `Product`, `Order`, `OrderItem`, `ProductInventory`, `InventoryTransaction`, `Payment`, `Refund` | Order has status-transition actions |
| **shops** | `Shop` | Fieldsets + lifecycle actions |

`shop.ProductImage` is deliberately inline-only (via `ProductImageInline`), with no standalone ModelAdmin.

### Admin chrome

- `backend/templates/admin/base_site.html` — branding, Google Fonts, theme CSS
- `backend/templates/admin/index.html` — dashboard, now with 8 live metric cards
- `backend/templates/admin/login.html` — glassmorphism login
- `backend/templates/admin/nav_sidebar.html` — grouped navigation
- `backend/templates/admin/admin_actions.html` — reason-capture form
- `backend/static/css/japanese_admin.css` — 28.6 KB theme, `--jp-*` custom properties with dark variants

### Domain services (always reused, never bypassed)

- `sellers.services` → `approve_seller()`, `reject_seller()`, `suspend_seller()`, `reactivate_seller()`
- `shops.services.ShopService` → `approve_shop()`, `reject_shop()`, `suspend_shop()`, `reactivate_shop()`
- `shop.services.OrderService` → `transition_order_status()`, `cancel_customer_order()`
- `shop.inventory_service.InventoryService` → stock operations
- `shop.payment_service.PaymentService` → payment operations
- `audit.services.AuditService` → `log()` for the immutable audit trail

---

## Completed work

### Phase 0 — Unbreak the admin

Two admin classes referenced model fields that do not exist:

| File | Declared | Model actually has |
|---|---|---|
| `backend/customers/admin.py` | `'title'` | `Address.label` |
| `backend/points/admin.py` | `cost_amount`, `is_active`, `effective_from`, `created_at` | `ProductCreationCost.required_points`, `updated_at` |

Both now point at real fields. `ProductCreationCost` also blocks delete and only allows an add when no row exists, matching its pk=1 singleton `save()`.

**Gate:** `manage.py check` reports 0 issues.

### Phase 1 — Correctness of the list displays

Three divergent copies of the status-badge helper lived in `shop/`, `sellers/` and `shops/`. They are now one `StatusBadgeMixin` in `backend/audit/admin_mixins.py` — `audit` is the project's only leaf app (its models use string FK refs, its services import no siblings), so every other app can import from it without a cycle. Importing from `shop/` instead would have created a mutual dependency, since `shop` already imports `shops` and `sellers`.

The merged colour map covers **every** status choice across `Product`, `Order`, `SellerProfile`, `Shop`, `Payment` and `Refund`; `SHIPPED` and `REFUNDED` previously fell through to grey.

Two display helpers branched on constants that do not exist:

- `InventoryTransactionAdmin.quantity_display` tested `RESTOCK`/`RETURN`/`ADJUST_UP`/`RESERVE`/`ADJUST_DOWN`. The real choices are `INITIAL_STOCK`, `STOCK_IN`, `STOCK_OUT`, `RESERVATION`, `RELEASE`, `SALE`, `ADJUSTMENT` — so six of seven types rendered uncoloured. Now uses the `TYPE_*` constants, with `ADJUSTMENT` taking its sign from the stored value.
- `PointTransactionAdmin.amount_display` compared `transaction_type` to `'CREDIT'`, which is not a valid choice, so **every** amount rendered red. Direction now comes from the balance delta, which is authoritative even for `ADJUSTMENT`.

The points ledger stores **points, not money**, so amounts are labelled `pts` rather than carrying the Taka sign. (The `৳` rule applies to prices and revenue, which the dashboard honours.)

Also tightened: `Payment` change view blocked (matching `Refund` and `InventoryTransaction`), `OrderItem` add/delete blocked, and list filters added for `Category`, `Refund`, and a `StockLevelFilter` for `ProductInventory`.

### Phase 2 — Real dashboard metrics

`backend/shop/metrics.py` is the single source of truth. One `.aggregate()` per table using `Count(filter=Q(...))` — one query per model, not one per status — with `Coalesce` guarding the only `Sum`. Safe on an empty database, since `Count` is never `NULL`.

It exposes two entry points:

- `get_platform_metrics()` — nested payload for the Django dashboard
- `get_console_metrics()` — the flat seven-key payload the Next.js console consumes

`AdminMetricsAPIView` now calls `get_console_metrics()` and returns **byte-identical** output; its four tests still pass. `pending` stays strictly `PENDING` for both shops and sellers because that is the published contract — `UNDER_REVIEW` and `DRAFT` are separate keys.

The dashboard is fed by `MiniShopAdminSite.index()` in `backend/config/admin_site.py`, wired through `config/apps.py` → `AdminConfig.default_site` and one line in `INSTALLED_APPS`. This is Django's supported hook and is transparent to the existing `@admin.register(...)` decorators, because `admin.site` is a `LazyObject` resolving to whatever `default_site` names. `app_list`, `{% get_admin_log %}`, `each_context()` and the `admin:` URL namespace are all untouched — so `config/urls.py` needed no change at all.

Eight cards, each still linking to its changelist and carrying status breakdown pills: Users, Sellers, Shops, Products, Orders, Revenue (`৳`), Payments, Low stock.

### Phase 3 — Navigation and theme

`nav_sidebar.html` is grouped into **Main**, **Commerce** (Products, Categories, Orders, Payments, Refunds, Inventory, Stock Movements), **Merchants** (Sellers, Shops, Wallets, Point Ledger), **Customers** (Profiles, Addresses, Favorites, Carts), **Access Control** (Users, Roles, Permissions, Role Assignments) and **Governance** (Audit Logs) — every registered model, versus the four links it had before.

`MiniShopAdminSite.each_context()` now supplies `nav_categories` and `storefront_url` directly. The sidebar previously only worked because `shop.context_processors.shop_context` is registered globally and leaked storefront values into every admin page; it no longer depends on that.

The storefront host moved to a `STOREFRONT_URL` setting (env-overridable), replacing the hardcoded `http://localhost:3000` in four templates.

### Phase 4 — Reason capture for suspend/reject

Previously these actions passed a hardcoded `'Suspended via admin action'` / `'Rejected via admin action'`, so every suspension recorded a meaningless reason.

`ReasonRequiredActionMixin` (`backend/audit/admin_mixins.py`) implements Django's intermediate-confirmation-page pattern. Returning a `TemplateResponse` from an action makes `ModelAdmin.response_action` render it; returning `None` falls through to the normal changelist redirect. Re-entry needs no custom plumbing — Django re-resolves the action and rebuilds the queryset from the `ACTION_CHECKBOX_NAME` values the form re-posts, and `select_across` is carried through so select-all-pages keeps its meaning.

`backend/templates/admin/admin_actions.html` is one reusable themed form, styled entirely with existing `--jp-*` custom properties so both light and dark themes work with no extra CSS.

**Audit logging was a real gap, not a duplication risk.** Verified: neither `sellers/models.py` nor `shops/models.py` imports `audit`, and neither `sellers.services` nor `ShopService` logs. Seller and shop approvals, suspensions and rejections were **invisible to the audit trail** — only `OrderService.transition_order_status` audited. The mixin now logs each one with the operator-typed reason and the before/after status. Action codes match the DRF console's convention (`ADMIN_SELLER_SUSPEND`, `ADMIN_SHOP_APPROVE`, …) so both admin surfaces feed one queryable stream.

Validation is enforced twice: the mixin requires ≥10 characters, and `SellerProfile.suspend`/`reject` and the `ShopService` equivalents raise `ValidationError` on a blank reason regardless.

> If `sellers.services` or `shops.services` is ever changed to audit internally, remove `audit_action` from these call sites or entries will double up. It is a required keyword argument precisely so that coupling stays visible.

### Phase 5 — Admin test coverage

`backend/shop/test_admin_site.py` — 11 tests. The suite previously exercised only the DRF API (`APITestCase`), which is exactly why the two `list_display` errors shipped undetected.

- `manage.py check` reports no issues
- every registered changelist returns 200 (walks `admin.site._registry`, so new models are covered automatically)
- every permitted add form returns 200
- the dashboard exposes all seven metric groups and renders `৳`, never `$`
- the reason form renders; blank and short reasons are rejected with the record unchanged; a valid reason suspends the record, stores the real text, and writes exactly one audit row
- the same for shop suspension

---

## Security rules

> [!CAUTION]
> - **Never** weaken existing authentication / RBAC / lifecycle rules
> - **Never** expose sensitive payment credentials (card numbers, gateway secrets)
> - **Never** allow direct status editing that bypasses services for lifecycle-critical models
> - **Financial and audit records** — `PointTransaction`, `InventoryTransaction`, `Payment`, `Refund`, `AuditLog` — stay immutable: no add, no change, no delete
> - Admin actions **always** go through the domain service layer, never raw `save()`
> - Destructive batch actions require a typed reason, recorded to the audit log

## Performance rules

- Every `list_display` FK must be covered by `select_related()` in `get_queryset()`
- Computed columns use `Count()` annotations, not per-row queries
- Dashboard metrics are one `.aggregate()` per table, not one query per status
- Pagination stays at the Django default

---

## Out of scope

The Next.js management console at `frontend/src/app/admin`. Its six modules (`shops`, `sellers`, `orders`, `payments`, `categories`, `audit-logs`) are placeholder cards today, and the backend exposes no `/api/admin/` endpoints for **orders, payments, refunds or inventory**. Recorded here only so the gap is visible; Master Prompt §26 is explicit that Django Admin is not the primary management UI, so that console is the larger separate effort.

---

## Verification

Run from the repo root. The documented venv is `backend/venv` (`backend/venv/Scripts/python.exe` on Windows).

```bash
# 1. The blocking gate
backend/venv/Scripts/python.exe backend/manage.py check

# 2. Tests. The DB is a remote MySQL, and a test_minishop database already
#    exists there -- use --keepdb so the runner reuses it instead of prompting
#    to drop a database other people may be using.
backend/venv/Scripts/python.exe backend/manage.py test shop --keepdb
backend/venv/Scripts/python.exe backend/manage.py test \
  shop customers points sellers shops rbac audit cart --keepdb

# 3. Frontend build (untouched by this work, but AGENTS.md requires it)
cd frontend && npm run build
```

Manual pass — `runserver 127.0.0.1:8001`, log in at `/admin/`, then confirm:

- every changelist loads, especially `Address` and `ProductCreationCost` (the two that were broken)
- the dashboard shows real counts and `৳` revenue
- every sidebar section resolves
- selecting sellers → **Suspend** reaches the reason form; a blank reason is rejected; a real reason is stored and appears in the audit log
- `Payment`, `Refund`, `InventoryTransaction`, `PointTransaction` and `AuditLog` remain non-editable

# Django Superuser Admin — Task Tracker

Scope: Django admin at `127.0.0.1:8001/admin/` only. See [ImplementationPlan.md](./ImplementationPlan.md).

## Phase 0: Unbreak the admin (was blocking everything)
- [x] `customers/admin.py` — `AddressAdmin.list_display` used `'title'`; the field is `label`
- [x] `points/admin.py` — `ProductCreationCostAdmin` referenced 4 non-existent fields; model has `required_points`, `updated_at`
- [x] `ProductCreationCost` — block delete, allow add only when no row exists (pk=1 singleton)
- [x] `manage.py check` back to 0 issues (was 7 `admin.E108`/`E116`, which stopped `runserver`)

## Phase 1: Register models + correct the list displays
- [x] All 25 models registered — `ProductInventory`, `InventoryTransaction`, `Payment`, `Refund`, `Favorite` included *(was already done before this pass)*
- [x] `select_related` / annotated counts across all 8 `admin.py` files *(already done)*
- [x] Consolidate 3 divergent badge helpers into one `StatusBadgeMixin` in `audit/admin_mixins.py`
- [x] Badge map now covers every status choice — `SHIPPED` and `REFUNDED` were falling through to grey
- [x] Fix `InventoryTransactionAdmin.quantity_display` — tested 5 constants that do not exist; 6 of 7 real types rendered uncoloured
- [x] Fix `PointTransactionAdmin.amount_display` — compared against `'CREDIT'`, not a valid choice, so every row rendered red
- [x] Label the points ledger in `pts`, not `৳` — it stores points, not money
- [x] `PaymentAdmin` — block the change view (matching `Refund` / `InventoryTransaction`)
- [x] `OrderItemAdmin` — block top-level add/delete
- [x] Add `list_filter` to `Category`, `Refund`, and a `StockLevelFilter` for `ProductInventory`

## Phase 2: Dashboard metrics
- [x] Create `shop/metrics.py` — one `.aggregate()` per table via `Count(filter=Q(...))`, `Coalesce` on the only `Sum`
- [x] Repoint `AdminMetricsAPIView` at the shared helper; output byte-identical, 4 tests still green
- [x] Create `config/admin_site.py` — `MiniShopAdminSite.index()` injects metrics
- [x] Create `config/apps.py` + swap one `INSTALLED_APPS` line — `AdminConfig.default_site`
- [x] `config/urls.py` — **no change needed** (the old plan wrongly assumed a new route)
- [x] `templates/admin/index.html` — 8 live metric cards with breakdown pills, replacing 4 static links
- [x] Revenue renders `৳`, never `$`

## Phase 3: Navigation + theme
- [x] `nav_sidebar.html` — Main / Commerce / Merchants / Customers / Access Control / Governance, covering every registered model
- [x] `each_context()` supplies `nav_categories` — sidebar no longer relies on the storefront context processor leaking into admin
- [x] Add `STOREFRONT_URL` setting; remove the hardcoded `localhost:3000` from all 4 templates
- [x] Metric/pill styles built on the existing `--jp-*` custom properties, dark theme included

## Phase 4: Reason capture for suspend/reject
- [x] `ReasonRequiredActionMixin` — Django's intermediate-confirmation-page pattern, `select_across` preserved
- [x] `templates/admin/admin_actions.html` — one reusable themed form
- [x] Seller suspend/reject now capture a typed reason (were hardcoded `'Suspended via admin action'`)
- [x] Shop suspend/reject likewise
- [x] `AuditService.log()` on all 8 seller/shop lifecycle actions — these were **not audited at all** before
- [x] Approve/reactivate keep their no-reason shape but are now audited too
- [x] All actions still route through `sellers.services` / `ShopService`; never raw `save()`

## Phase 5: Admin test coverage
- [x] `shop/test_admin_site.py` — 11 tests (the suite previously covered only the DRF API)
- [x] `manage.py check` asserted clean as a test
- [x] Every registered changelist + add form returns 200 (walks `admin.site._registry`)
- [x] Dashboard exposes all 7 metric groups; renders `৳`, never `$`
- [x] Reason flow: form renders, blank/short rejected with no state change, valid reason stores text + exactly 1 audit row

## Phase 6: Docs
- [x] Rewrite `ImplementationPlan.md` against the verified codebase; drop the `/mnt/Project/...` paths
- [x] Rewrite this tracker with accurate state

## Verification
- [x] `manage.py check` — 0 issues
- [x] `manage.py test shop.test_admin_site --keepdb` — 11/11
- [x] `manage.py test shop.test_admin_metrics --keepdb` — 4/4
- [ ] Full suite: `test shop customers points sellers shops rbac audit cart --keepdb`
- [ ] `cd frontend && npm run build`
- [ ] Manual pass at `http://127.0.0.1:8001/admin/`
- [x] Commits (`AGENTS.md` §9)

## Not in scope
The Next.js console at `frontend/src/app/admin` — 6 placeholder modules, and no `/api/admin/` endpoints exist for orders, payments, refunds or inventory. Separate effort.

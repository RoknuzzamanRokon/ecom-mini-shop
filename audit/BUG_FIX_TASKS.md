# MiniShop — Bug Fix Task List

Built from [`BUG_AUDIT_REPORT.md`](BUG_AUDIT_REPORT.md), which audited commit `ebd71c5` on 2026-10-22. Every BUG ID maps to exactly one task. Tasks for *Probable* findings say "verify first". The single *Unverified* finding (BUG-093) is filed as an **investigation task**.

**Conventions**
- **Effort:** XS < 30 min · S < 2 h · M ≈ 1 day · L ≈ 3 days · XL > 3 days.
- **Priority** is the highest severity among the task's bugs.
- **Done for every task** means all of the following:
  - The regression tests named here are added and pass.
  - `python manage.py test --settings=config.settings.test --parallel --keepdb --noinput` passes against an isolated MySQL; prefer `TEST_DATABASE_URL` pointing at a local server.
  - `npm run typecheck` and `npm run build` pass.
  - The change is committed with a descriptive subject (project rule).

**Suggested execution order:**
1. Group 1, plus TASK-042/043 harnesses and the TASK-048 decisions, in parallel.
2. Group 2.
3. Group 3.
4. Group 4.
5. TASK-044 any time after TASK-042/043.

---

## Group 1 — Critical security and data-integrity fixes

### TASK-001 — Production settings and secret hygiene
- **Bugs:** BUG-001 · **Priority:** P1 (P0 at first deployment) · **Effort:** S
- **Scope:**
  - Read `SECRET_KEY` and a separate `SIMPLE_JWT["SIGNING_KEY"]` from the environment; fail fast outside dev if they are missing.
  - Rotate the key: the committed value stays in git history, so treat it as public.
  - Add `config/settings/prod.py` with:
    - DEBUG False and `ALLOWED_HOSTS` from the environment;
    - HSTS, `SECURE_SSL_REDIRECT` and `SECURE_PROXY_SSL_HEADER` (if behind a proxy);
    - `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE`;
    - `CSRF_TRUSTED_ORIGINS`, and `CORS_ALLOWED_ORIGINS` from the environment;
    - Django's full `AUTH_PASSWORD_VALIDATORS`.
  - Make `wsgi.py` and `asgi.py` require an explicit `DJANGO_SETTINGS_MODULE`, with no silent dev default.
- **Files:** `backend/config/settings/base.py`, `dev.py`, new `prod.py`, `backend/config/wsgi.py`, `backend/config/asgi.py`, `backend/README.md`
- **Acceptance criteria:**
  - No secret literal remains in tracked files.
  - `manage.py check --deploy --settings=config.settings.prod` reports no warnings.
  - The dev workflow still works with `backend/.env`.
- **Tests:** a settings test that imports prod with the environment set and asserts DEBUG is False and the cookie flags are True; a CI deploy check (TASK-044).
- **Dependencies / order:** first; independent.

### TASK-002 — Token revocation, throttling and password policy
- **Bugs:** BUG-013, BUG-014 · **Priority:** P2 · **Effort:** S–M
- **Scope:**
  - Add `rest_framework_simplejwt.token_blacklist` to `INSTALLED_APPS` and migrate.
  - Set `BLACKLIST_AFTER_ROTATION=True`, and `CHECK_REVOKE_TOKEN=True` (SimpleJWT 5.5.1), or blacklist a user's outstanding tokens on password change.
  - Add `POST /api/auth/logout/` to blacklist the refresh token, and call it from the frontend logout.
  - Add `ScopedRateThrottle` on token, refresh, register and change-password, plus lockout or backoff for `/admin/login/`.
  - Restore Django's default password validators, with a minimum length of at least 8.
- **Files:** `backend/config/settings/base.py`, `backend/rbac/views.py`, `backend/rbac/urls.py`, `backend/rbac/serializers.py`, `frontend/src/lib/auth.ts`, `frontend/src/context/AuthContext.tsx`
- **Acceptance criteria:**
  - After a password change, the old access and refresh tokens are rejected.
  - A rotated refresh token is rejected on reuse.
  - The (N+1)th failed login gets 429.
  - Logout invalidates the refresh token server-side.
- **Tests:** API tests for each criterion; a throttle test using an overridden low rate.
- **Dependencies / order:** after TASK-001 (the signing key change invalidates every token anyway, so ship them together).

### TASK-003 — Close Django-admin RBAC escalation paths
- **Bugs:** BUG-002, BUG-039 · **Priority:** P1 · **Effort:** M
- **Scope:**
  - `Role.code` and `Permission.code` / `resource` / `action` become read-only after creation, and `*` is refused.
  - Protected roles (SUPER_ADMINISTRATOR, ADMINISTRATOR) cannot be edited or deactivated by non-wildcard actors.
  - `PermissionAdmin`, `UserPermissionAdmin`, `RolePermissionAdmin`, `UserRoleAdmin` and the UserRole inline apply the same delegation, protected-role and no-self rules as the Console API (or are limited to wildcard holders).
  - `is_superuser`, `is_staff`, `user_permissions` and `groups` are read-only for non-superusers in `UserAdmin`.
  - `UserAdmin.save_related` diffs only editable (non-locked) direct grants.
- **Files:** `backend/rbac/admin.py`, `backend/rbac/services.py`, `backend/rbac/widgets.py`
- **Acceptance criteria:** a non-wildcard staff user holding any single rbac/auth model permission cannot change their own effective permission set through any admin page; saving a user form unchanged preserves every direct grant.
- **Tests:** one crafted-POST test per escalation path (a)–(f) in BUG-002, asserting `get_user_permissions(actor)` is unchanged; a locked-grant preservation test.
- **Dependencies / order:** Group 1, early. Shares a helper with TASK-004.

### TASK-004 — Delegation boundary on Console user role assignment
- **Bugs:** BUG-003 · **Priority:** P1 · **Effort:** S
- **Scope:** add `rbac.services.assert_can_assign_roles(actor, target, desired_roles)` with two rules:
  - The permissions of the added roles must be delegatable by the actor.
  - A non-wildcard actor may only modify (activate, deactivate or change roles of) a target whose effective permissions are a subset of the actor's and who holds no protected role.
  
  Use it in `AdminUserListAPIView.post` and `AdminUserDetailAPIView.patch`.
- **Files:** `backend/rbac/services.py`, `backend/shop/admin_views.py`
- **Acceptance criteria:**
  - A custom `users.admin.*` holder gets 403 when assigning FINANCE or when deactivating an ADMINISTRATOR.
  - An ADMINISTRATOR assigning FINANCE still gets 200.
- **Tests:** API tests for the cases above in `shop/test_admin_governance.py`.
- **Dependencies / order:** with TASK-003.

### TASK-005 — Separate seller permissions from staff permissions
- **Bugs:** BUG-004 · **Priority:** P1 (verify first: confirm which role production sellers hold) · **Effort:** M
- **Scope:**
  - Introduce a seller-scoped role, or make seller product creation depend on `IsEligibleProductSeller` alone.
  - Gate Console read endpoints on staff-only codes such as `sellers.admin.view` and `products.admin.view`.
  - Update `seed_rbac`, `seed_showcase` and `frontend/src/lib/admin-auth.ts` so SALES_TEAM is no longer how sellers get product rights.
  - Add a data migration or script to move existing seller accounts to the new role.
- **Files:** `backend/rbac/management/commands/seed_rbac.py`, `backend/shop/admin_permissions.py`, `backend/shop/permissions.py`, `backend/shop/management/commands/seed_showcase.py`, `frontend/src/lib/admin-auth.ts`, `frontend/src/lib/admin-navigation.ts`
- **Acceptance criteria:**
  - A seller account can create products and gets 403 on every `/api/admin/*` endpoint.
  - Staff roles keep their current access.
- **Tests:** a seller gets 403 on `/api/admin/sellers/` and `/api/admin/products/` and 201 on seller product create; SALES_MANAGER still gets 200.
- **Dependencies / order:** after the TASK-048 decision on the seller permission model; relates to Known #27.

### TASK-006 — Lock down Django-admin change forms that bypass services
- **Bugs:** BUG-006, BUG-021, BUG-046 · **Priority:** P1 · **Effort:** M
- **Scope:**
  - `OrderAdmin`: make `status` and `shipping_address` read-only (or use raw_id) and disable delete.
  - `ProductAdmin`: make the lifecycle and moderation fields (`status`, `submitted_at`, `reviewed_*`, `rejection_reason`) and `shop` read-only on change. Remove `stock` from `list_editable`, or route it through `InventoryService.adjust_stock` in `save_model`. Apply the Limited-owner product cap on add and move, and decide on charging points.
  - `ProductInventoryAdmin`: make the counters read-only and add an "Adjust stock" action that uses `InventoryService`.
  - `ShopAdminForm.clean_owner` and `SellerProfileAdmin.clean_seller_type`: add the product cap and lock the owner row.
  - Make `SellerProfile.user` read-only on change, or audit the change.
- **Files:** `backend/shop/admin.py`, `backend/shops/admin.py`, `backend/sellers/admin.py`
- **Acceptance criteria:**
  - Crafted change-form POSTs cannot change order or product status, inventory counters or ownership outside the services.
  - Every allowed change writes an audit row.
- **Tests:** extend the `AdminChangeFormStatusLockdownTests` pattern (from Known #22) to Order, Product, ProductInventory, and to Shop/Seller ownership and caps.
- **Dependencies / order:** before TASK-008, because it closes the BUG-006 inflow.

### TASK-007 — Seller cancellation must cancel or refund the payment
- **Bugs:** BUG-005 · **Priority:** P1 · **Effort:** XS–S
- **Scope:** call `PaymentService.handle_order_cancellation` in the seller CANCELLED branch. Preferably extract a single post-transition helper used by both `transition_order_status` and `transition_seller_order_status`.
- **Files:** `backend/shop/services.py`
- **Acceptance criteria:**
  - A seller cancelling a PAID order refunds it: a COMPLETED Refund row and a REFUND_PROCESSED event.
  - A seller cancelling a PENDING payment cancels it.
- **Tests:** `shop/test_seller_orders.py`, one test for each case.
- **Dependencies / order:** independent; pairs with TASK-015.

### TASK-008 — Bound delivery (SALE) by the order's own reservation
- **Bugs:** BUG-007 · **Priority:** P1 · **Effort:** XS (code) + investigation (TASK-047)
- **Scope:**
  - In `finalize_order_delivery`, cap `qty` with `_order_reserved_quantity(order, product)`.
  - Define the shortfall behaviour: sell from available stock with a ledger note, or refuse delivery.
- **Files:** `backend/shop/inventory_service.py`
- **Acceptance criteria:** delivering an order never reduces another order's reservation.
- **Tests:** `shop/test_inventory.py`, delivering a reservation-less order leaves a concurrent order's reservation intact.
- **Dependencies / order:** after TASK-006. Pair with TASK-047 to reconcile historical drift (Known #30).

### TASK-009 — Trustworthy audit trail
- **Bugs:** BUG-015, BUG-041, BUG-049 · **Priority:** P2 · **Effort:** M
- **Scope:**
  - One `get_client_ip` helper: use `REMOTE_ADDR` unless a trusted-proxy count is configured, validate with `ipaddress`, and fall back to None. Replace the copies in `shop/admin_views.py` and `shop/api_views.py`.
  - Wrap perform + log per object in `transaction.atomic()` inside `ReasonRequiredActionMixin`.
  - Snapshot the actor's username and id on `AuditLog`, so attribution survives user deletion.
  - Make `/api/shops/staff/*` lock the row and write `ADMIN_SHOP_*` audit rows, mirroring `AdminShopStatusAPIView`, or retire those routes.
- **Files:** `backend/audit/utils.py`, `backend/audit/models.py` (+ migration), `backend/audit/services.py`, `backend/audit/admin_mixins.py`, `backend/shop/admin_views.py`, `backend/shop/api_views.py`, `backend/shops/views.py`, `backend/shops/urls.py`
- **Acceptance criteria:**
  - A spoofed XFF is not recorded.
  - An over-long XFF never yields a state change without an audit row.
  - Deleting a user keeps their audit attribution.
  - Each staff shop transition writes exactly one audit row.
- **Tests:** a unit test for the IP helper; an admin action test with a 60-character XFF; an actor-deletion test; shop staff endpoint audit tests.
- **Dependencies / order:** Group 1. Needs a migration: run the 16 test DB clones in place, as noted in project memory.

### TASK-010 — Invoice escaping and balance
- **Bugs:** BUG-019, BUG-020 · **Priority:** P2 · **Effort:** S
- **Scope:**
  - Escape every dynamic value passed to `Paragraph`.
  - Fix balance due: 0 for CANCELLED, otherwise `max(0, total − (paid − refunded))`.
  - Write down the refund semantics.
- **Files:** `backend/shop/invoice.py`
- **Acceptance criteria:**
  - Invoices for names or products containing `<`, `&` and tags build and show the literal text.
  - Cancelled and refunded orders show ৳0.00 due.
- **Tests:** a new `shop/test_invoice.py` that builds PDFs in-memory and asserts on the extracted text.
- **Dependencies / order:** independent.

---

## Group 2 — High-priority functional bugs

### TASK-011 — Stock edits by delta, not stale absolute values
- **Bugs:** BUG-008 · **Priority:** P1 · **Effort:** S
- **Scope:**
  - The seller edit form sends `stock` only when it changed.
  - Stock changes go through `adjustSellerProductStock` (`POST /api/seller/inventory/<id>/adjust/`), or the PATCH gains an `expected_stock` precondition (409 on mismatch).
  - Relabel the "Initial Stock" field in the edit modal (see BUG-096).
- **Files:** `frontend/src/app/seller/products/page.tsx`, `frontend/src/lib/api.ts`, `backend/shop/services.py` (if adding the precondition), `backend/shop/serializers.py`
- **Acceptance criteria:** editing a description never changes availability; a concurrent reservation is never undone by a seller save.
- **Tests:** a backend reserve-then-stale-PATCH test; a frontend test that untouched stock is not sent (needs TASK-042).
- **Dependencies / order:** Group 2, first.

### TASK-012 — Seller order detail and data minimisation
- **Bugs:** BUG-009, BUG-055 · **Priority:** P1 · **Effort:** S
- **Scope:**
  - "View Details" fetches `getSellerOrderDetail(order_number)`, with loading and error states.
  - Remove `total_amount` from the seller serializers (use `seller_subtotal`).
  - Mask customer names on seller-visible inventory transactions, and add `select_related`.
- **Files:** `frontend/src/app/seller/orders/page.tsx`, `frontend/src/app/seller/page.tsx`, `frontend/src/lib/types.ts`, `backend/shop/serializers.py`, `backend/shop/api_views.py`
- **Acceptance criteria:**
  - The modal shows recipient, phone and address.
  - The list payload has no PII and no whole-order total.
- **Tests:** a backend contract test (list vs detail fields); a component test for the modal fetch.
- **Dependencies / order:** with TASK-021 (same page).

### TASK-013 — Cart integrity in CartContext
- **Bugs:** BUG-010, BUG-084, BUG-087 · **Priority:** P1 · **Effort:** M
- **Scope:**
  - Use the local fallback only when there is no token. On API failure, call `refreshCart()` and expose `error`.
  - Disable the steppers while a call is pending, and compute the next quantity from the latest state.
  - Checkout re-reads the server cart before rendering totals.
  - Guest merge removes items one by one as they succeed, keeps failures and shows a notice.
  - Buy Now awaits the add, does not open the drawer, and shows a spinner while `cartLoading`. Clamp the stepper to `min(stock, 99)`.
- **Files:** `frontend/src/context/CartContext.tsx`, `frontend/src/components/cart/CartDrawer.tsx`, `frontend/src/app/checkout/page.tsx`, `frontend/src/app/product/[slug]/page.tsx`
- **Acceptance criteria:**
  - The displayed cart always equals the server cart for signed-in users.
  - No silent loss of the guest cart.
  - Buy Now lands on checkout with the item.
- **Tests:** CartContext unit tests with mocked API failures (needs TASK-042).
- **Dependencies / order:** after TASK-042.

### TASK-014 — Product publication workflow
- **Bugs:** BUG-011 · **Priority:** P1 · **Effort:** S–M
- **Scope:**
  - Decide the flow (TASK-048).
  - Either add `POST /api/products/<id>/submit/` (DRAFT→SUBMITTED, owner-only, audited) with a "Submit for review" button in Seller Center, or let the Console offer approve/publish on DRAFT.
  - Update the Console copy at `products/[id]/page.tsx:218-221`.
- **Files:** `backend/shop/services.py`, `backend/shop/api_views.py`, `backend/shop/urls.py`, `frontend/src/app/seller/products/page.tsx`, `frontend/src/lib/api.ts`, `frontend/src/app/admin/products/productGovernance.tsx`, `frontend/src/app/admin/products/[id]/page.tsx`
- **Acceptance criteria:** a new product can go from DRAFT to PUBLISHED using only Seller Center and the Console, with audit rows.
- **Tests:** a backend end-to-end test (create → submit → approve → publish); a `getAvailableProductActions` unit test.
- **Dependencies / order:** after the TASK-048 decision; resolves Known #8.

### TASK-015 — COD payment record at checkout
- **Bugs:** BUG-012, BUG-052 · **Priority:** P2 · **Effort:** S
- **Scope:**
  - Create a PENDING `CASH_ON_DELIVERY` Payment in `create_order_from_cart` (same transaction).
  - Optionally mark it PAID on DELIVERED.
  - Treat PAID, PARTIALLY_REFUNDED and REFUNDED as already paid in `create_or_get_payment`.
  - Decide whether to backfill historical orders (TASK-047).
- **Files:** `backend/shop/services.py`, `backend/shop/payment_service.py`, possibly `frontend/src/lib/api.ts` (remove the unused `initiateOrderPayment` or wire it up)
- **Acceptance criteria:**
  - Every new order has exactly one PENDING COD payment equal to `total_amount`.
  - No second payment can be started after a refund.
- **Tests:** order create → payment exists; refund then POST payment → 400.
- **Dependencies / order:** after the TASK-048 decision; before relying on revenue metrics; pairs with TASK-007.

### TASK-016 — Seller lifecycle state guards
- **Bugs:** BUG-017, BUG-050 · **Priority:** P2 · **Effort:** S
- **Scope:**
  - Allowed source states per transition in `SellerProfile`: approve from PENDING/UNDER_REVIEW/REJECTED; reject from PENDING/UNDER_REVIEW; suspend from APPROVED/ACTIVE; reactivate from SUSPENDED.
  - Raise a typed error and map it to 400 in `sellers/views.py`, `AdminSellerStatusAPIView` and the admin actions.
- **Files:** `backend/sellers/models.py`, `backend/sellers/services.py`, `backend/sellers/views.py`, `backend/sellers/admin.py`, `backend/shop/admin_views.py`
- **Acceptance criteria:** approve on SUSPENDED returns 400 with the status unchanged and no audit row; no lifecycle call can return 500.
- **Tests:** a table-driven (action × status) test on all three surfaces.
- **Dependencies / order:** independent.

### TASK-017 — Checkout gate and server-side address validation
- **Bugs:** BUG-034, BUG-053, BUG-088 · **Priority:** P2 · **Effort:** S
- **Scope:**
  - Checkout requires sign-in once auth has loaded (`/login?next=/checkout`); remove the guest copy.
  - The server requires `address_id`, or a non-blank recipient, phone, line 1 and city; drop the placeholder address.
  - Save "remember this address" only after the order succeeds.
  - Block Place Order while `hasUnavailableItems`.
- **Files:** `frontend/src/app/checkout/page.tsx`, `backend/shop/serializers.py`, `backend/shop/services.py`
- **Acceptance criteria:**
  - A guest never sees the form.
  - An empty or blank address gets 400.
  - A failed order saves no address.
- **Tests:** a backend serializer/service test; a checkout component test (TASK-042).
- **Dependencies / order:** independent.

### TASK-018 — Refund UI safety
- **Bugs:** BUG-036, BUG-076 · **Priority:** P2 · **Effort:** S
- **Scope:**
  - Split the refund POST from the refetch, closing the modal on POST success.
  - Use a text amount input with regex validation and an explicit "Full refund" choice.
  - Optionally add an idempotency key on `POST /api/staff/payments/<id>/refund/`.
- **Files:** `frontend/src/app/admin/payments/paymentGovernance.tsx`, `frontend/src/app/admin/payments/[id]/page.tsx`, optionally `backend/shop/api_views.py` and `backend/shop/payment_service.py`
- **Acceptance criteria:** a successful refund is never reported as failed; invalid input never becomes a full refund.
- **Tests:** component tests (TASK-042).
- **Dependencies / order:** before TASK-035 (which enables multiple partial refunds).

---

## Group 3 — Medium-priority bugs and performance

### TASK-019 — Fix shop location editing in the Django admin
- **Bugs:** BUG-016 · **Priority:** P2 · **Effort:** S
- **Scope:**
  - Give `MySQLPointField` a `formfield()` whose `prepare_value` emits `to_wkt()`.
  - `to_python` and `from_wkt` raise `ValidationError`.
  - Validate coordinate ranges.
- **Files:** `backend/shops/fields.py`, `backend/shops/admin.py`
- **Acceptance criteria:** opening and re-saving an existing shop gives 302; malformed WKT gives 200 with a form error.
- **Tests:** an admin client GET, then re-POST of the rendered form.
- **Dependencies / order:** independent.

### TASK-020 — Public shop visibility follows seller status
- **Bugs:** BUG-018 · **Priority:** P2 · **Effort:** XS
- **Scope:** add `owner__status__in=[APPROVED, ACTIVE]` to `get_public_shops_queryset` and to the shop review lookup.
- **Files:** `backend/shops/services.py`, `backend/shops/views.py`
- **Acceptance criteria:** a suspended seller's shops disappear from the list, nearby, detail and review endpoints.
- **Tests:** `shops/tests.py`.
- **Dependencies / order:** independent.

### TASK-021 — Pagination contract fixes
- **Bugs:** BUG-024, BUG-025, BUG-026, BUG-079 · **Priority:** P2 · **Effort:** M
- **Scope:**
  - Derive page counts from `next`/`previous`, or pass `page_size` explicitly, on the seller products and profile orders pages.
  - Add a pager and server-side debounced `q` to seller orders, resetting the page on filter changes.
  - Return paginated envelopes plus "load more" for the seller wallet history.
  - Set `pagination_class=None` (or page through) for seller shops.
  - Add a backend status filter for "Current Orders".
  - Reset to page 1 on a 404 for an out-of-range page in `AdminDataTable` pages.
- **Files:**
  - Frontend: `frontend/src/app/seller/products/page.tsx`, `seller/orders/page.tsx`, `seller/wallet/page.tsx`, `profile/orders/page.tsx`, `profile/track/page.tsx`, `frontend/src/lib/api.ts`, `frontend/src/components/admin/shared/AdminDataTable.tsx`
  - Backend: `backend/shops/views.py`, `backend/shop/api_views.py`
- **Acceptance criteria:**
  - Every list can reach every row.
  - No page button leads to "Invalid page.".
- **Tests:** component tests with count 11/12/24/30; backend tests for the status filter.
- **Dependencies / order:** with TASK-012 (same seller orders page).

### TASK-022 — One API error parser; valid seller status transitions
- **Bugs:** BUG-028, BUG-029 · **Priority:** P2 · **Effort:** S
- **Scope:**
  - Add a shared `extractApiError(body)` (detail → error → first field message; lists joined) and use it in every `api.ts` function, including createOrder, the seller product functions and seller order status.
  - Add `min` / `maxLength` client-side checks to the seller product form.
  - Expose `allowed_transitions` on seller orders, or mirror `VALID_TRANSITIONS`; initialise the select to the first allowed state; hide the action on multi-merchant orders.
- **Files:** `frontend/src/lib/api.ts`, `frontend/src/app/seller/orders/page.tsx`, `frontend/src/app/seller/products/page.tsx`, optionally `backend/shop/serializers.py`
- **Acceptance criteria:** users see the server's field message; no raw JSON is shown; a PENDING order offers only CONFIRMED and CANCELLED.
- **Tests:** parser unit tests; a status modal component test.
- **Dependencies / order:** after TASK-042.

### TASK-023 — Seller Center robustness
- **Bugs:** BUG-027, BUG-030, BUG-069, BUG-070, BUG-071, BUG-072, BUG-096 · **Priority:** P2 · **Effort:** M
- **Scope:**
  - Only APPROVED/ACTIVE shops are eligible for product creation, with an explanation.
  - SellerGuard renders an error state with Retry and uses `router.replace` with the current path.
  - Separate the `loading` and `refreshing` flags.
  - Map `category_id`→`category` and `shop_id`→`shop` in the product update.
  - Multipart edit sends an empty `old_price` to clear it.
  - Use `is_operational` for the "no shop" message; never use demo categories in seller forms.
  - Fix the status dot, labels and count filters.
- **Files:** `frontend/src/components/seller/SellerGuard.tsx`, `SellerSidebar.tsx`, `frontend/src/app/seller/products/page.tsx`, `frontend/src/app/seller/page.tsx`, `frontend/src/app/seller/profile/page.tsx`, `frontend/src/lib/api.ts`, `backend/shop/serializers.py`, `backend/shop/services.py`
- **Acceptance criteria:** each bug's expected behaviour holds (see the register).
- **Tests:** a backend PATCH `category_id` test; component tests for the guard error state and eligibility.
- **Dependencies / order:** after TASK-022.

### TASK-024 — Session resilience
- **Bugs:** BUG-031, BUG-092 · **Priority:** P2 · **Effort:** S
- **Scope:**
  - Only a 400/401 from the refresh endpoint ends the session; transport and 5xx errors keep the tokens and show a retry state.
  - `initialize` uses `refreshTokenOnce()`.
  - `login` clears the tokens if `getCurrentUser` fails.
- **Files:** `frontend/src/context/AuthContext.tsx`, `frontend/src/lib/auth.ts`, `frontend/src/lib/api.ts`
- **Acceptance criteria:** a backend restart during reload does not log the user out; there is no half-logged-in state.
- **Tests:** unit tests with fetch mocked to reject or return 502 (TASK-042).
- **Dependencies / order:** after TASK-002 (logout endpoint).

### TASK-025 — Storefront navigation URL contract
- **Bugs:** BUG-032, BUG-033 · **Priority:** P2 · **Effort:** S
- **Scope:**
  - Home reads and writes `?category=` and `?q=` via `useSearchParams` (in Suspense).
  - Header submit falls back to `router.push('/?q=…')`.
  - Add a mobile search entry and debounce the search.
- **Files:** `frontend/src/app/page.tsx`, `frontend/src/components/layout/Header.tsx`, `frontend/src/components/layout/Navbar.tsx`
- **Acceptance criteria:** category and search work from every page and on phones.
- **Tests:** component or route tests.
- **Dependencies / order:** independent.

### TASK-026 — Fetch error propagation and the demo fallback policy
- **Bugs:** BUG-035 (and the error-state parts of BUG-090) · **Priority:** P2 (verify first) · **Effort:** M
- **Scope:**
  - Implement the documented "Fetch Error Propagation / Demo Fallback Policy": public readers throw (or return typed errors) so route `error.tsx` boundaries render.
  - Demo data is either removed from production builds or marked non-purchasable.
  - `getOrderDetail` distinguishes 404 from other errors, and FavoritesContext exposes `error`.
- **Files:** `frontend/src/lib/api.ts`, `frontend/src/app/shop/[slug]/page.tsx`, `frontend/src/context/FavoritesContext.tsx`, `frontend/src/context/CartContext.tsx`, `frontend/src/app/profile/**`
- **Acceptance criteria:**
  - With the backend down, users see error states with retry, never demo products.
  - Demo ids can never reach the cart API.
- **Tests:** component tests with fetch rejected.
- **Dependencies / order:** after the TASK-048 policy decision; BUG-090 is fixed together here, though it is tracked under TASK-040.

### TASK-027 — Query performance
- **Bugs:** BUG-022, BUG-023, BUG-067 · **Priority:** P2 · **Effort:** M
- **Scope:**
  - Replace `current_payment` per-row queries with an annotated Subquery or an ordered Prefetch.
  - Compute refundable amounts from prefetched data.
  - Cart `select_related("product__inventory")`.
  - Checkout `select_for_update(of=("self",))`, after verifying on MySQL.
  - Console lists: annotate counts, `select_related` profiles, Prefetch active roles; avoid prefetching all products just to count them.
- **Files:** `backend/shop/models.py`, `backend/shop/serializers.py`, `backend/shop/api_views.py`, `backend/cart/services.py`, `backend/cart/serializers.py`, `backend/shop/services.py`, `backend/shop/admin_views.py`, `backend/shop/admin_serializers.py`
- **Acceptance criteria:** constant query counts per page on the staff orders, staff payments, customer orders, cart and Console users/customers/shops lists.
- **Tests:** `assertNumQueries` for each endpoint; a MySQL concurrency test for the lock scope.
- **Dependencies / order:** independent.

### TASK-028 — Theme and icon correctness
- **Bugs:** BUG-037, BUG-095, BUG-099 · **Priority:** P2 · **Effort:** M
- **Scope:**
  - Define `--c-on-nav` for every theme and dark block.
  - Load the Material Symbols CSS so Tailwind size utilities win (CSS layer), then review icon sizes across surfaces.
  - Add one sticky Header+Navbar chrome component used by every route boundary and loading branch.
- **Files:** `frontend/src/app/globals.css`, `frontend/src/app/layout.tsx`, `frontend/src/components/layout/*`, `frontend/src/app/product/[slug]/*`, `frontend/src/app/shop/[slug]/*`
- **Acceptance criteria:**
  - Header contrast meets WCAG AA in every theme and mode.
  - `text-[Npx]` on icons changes their computed size.
  - Boundaries render sticky chrome.
- **Tests:** a screenshot comparison with headless Chrome (see project memory: Playwright's Chromium does not hydrate; use system `google-chrome --headless=new`).
- **Dependencies / order:** independent.

### TASK-029 — Concurrency failures that surface as 500
- **Bugs:** BUG-058, BUG-059 · **Priority:** P3 (BUG-058: verify first) · **Effort:** M
- **Scope:**
  - Lock the parent `User` row (or evaluate the queryset) in AddressService; re-read inside the transaction.
  - Use `get_or_create` / IntegrityError → 409 for the first cart add and the shop slug.
  - Canonical lock order: Order before Payment; inventory sorted by `product_id`. Retry, or return 409, on MySQL error 1213.
- **Files:** `backend/customers/services.py`, `backend/cart/services.py`, `backend/shops/models.py`, `backend/shop/payment_service.py`, `backend/shop/inventory_service.py`
- **Acceptance criteria:** the races in BUG-058/059 produce 2xx or 409, never 500.
- **Tests:** `TransactionTestCase` thread tests on MySQL.
- **Dependencies / order:** after TASK-027 (shares the checkout lock code).

---

## Group 4 — Low-priority issues

### TASK-030 — Django admin chrome fixes
- **Bugs:** BUG-038, BUG-042 · **Priority:** P3 · **Effort:** XS
- **Scope:**
  - Pass the revenue and payment blocks to `admin/index.html` only with `payments.view`.
  - Add a hidden `#nav-filter`, or stop loading `nav_sidebar.js`.
- **Files:** `backend/config/admin_site.py`, `backend/templates/admin/index.html`, `backend/templates/admin/nav_sidebar.html`
- **Acceptance criteria:** staff without `payments.view` see no revenue; no JS error on admin pages.
- **Tests:** admin client render tests.
- **Dependencies / order:** independent.

### TASK-031 — Input validation: usernames, uploads, query params
- **Bugs:** BUG-040, BUG-060, BUG-066 · **Priority:** P3 · **Effort:** M
- **Scope:**
  - Add `UnicodeUsernameValidator` in registration and Console account creation.
  - Shared upload validators (size cap, format allow-list) for the customer avatar API, product images and shop logo/cover; phone and DOB validators shared with the admin profile form.
  - Validate the `category` / `shop` / `shop_id` / `start_date` / `end_date` / `assigned` params (400 on bad input).
  - Add max values on integer inputs.
  - Build audit-log date ranges in Asia/Dhaka.
- **Files:** `backend/rbac/serializers.py`, `backend/shop/admin_serializers.py`, `backend/customers/serializers.py`, `backend/config/admin_profile.py`, `backend/shop/serializers.py`, `backend/shops/serializers.py`, `backend/shop/admin_views.py`, `backend/shop/api_views.py`, `backend/support/views.py`, `backend/points/serializers.py`
- **Acceptance criteria:** every BUG-040/060/066 repro returns 400.
- **Tests:** an API test per input.
- **Dependencies / order:** independent.

### TASK-032 — Repository hygiene for uploads and logs
- **Bugs:** BUG-043 · **Priority:** P3 · **Effort:** S
- **Scope:**
  - Ignore `backend/media/` and `*.log`.
  - Move seed images to a fixtures directory; `git rm --cached` the customer avatars and the log files.
  - Fix the ineffective ignore line and `README.md:145`.
  - Decide whether to purge the avatars from history; this rewrites history, so it is the owner's call.
- **Files:** `backend/.gitignore`, `backend/README.md`, `backend/shop/management/commands/seed_*.py` (image paths)
- **Acceptance criteria:** runtime uploads never show up in `git status`.
- **Tests:** a CI check that nothing under `backend/media/customers` is tracked.
- **Dependencies / order:** independent.

### TASK-033 — Seller shop API fixes
- **Bugs:** BUG-044, BUG-045 · **Priority:** P3 · **Effort:** XS
- **Scope:**
  - Only update coordinates when they are non-null; map Django `ValidationError` to 400.
  - Return the updated instance.
  - Remove the staff bypass from `IsShopOwner` on seller-only views.
- **Files:** `backend/shops/views.py`, `backend/shops/services.py`, `backend/shops/serializers.py`, `backend/shops/permissions.py`
- **Acceptance criteria:** no 500 on PUT or null coordinates; the PATCH response shows new values; staff get 403.
- **Tests:** `shops/tests.py`.
- **Dependencies / order:** independent.

### TASK-034 — Points expiry edge cases
- **Bugs:** BUG-047, BUG-048 · **Priority:** P3 (BUG-048: verify the policy first) · **Effort:** S
- **Scope:**
  - On a superuser→non-superuser change, call `restart_expiry_clock` under the wallet lock and audit it.
  - On take-back, carry the consumed lots' `expires_at` into the returning lot, if the policy (TASK-048) says renewal is not allowed.
- **Files:** `backend/rbac/admin.py` (UserAdmin.save_model), `backend/points/services.py`
- **Acceptance criteria:** demotion never expires points instantly; a credit/debit bounce never extends expiry.
- **Tests:** `points/test_expiry.py`.
- **Dependencies / order:** after the TASK-048 decision.

### TASK-035 — Payments small fixes
- **Bugs:** BUG-051, BUG-054, BUG-056, BUG-057 · **Priority:** P3 · **Effort:** S
- **Scope:**
  - Persist `failure_reason` and `metadata`.
  - Customer payment POST requires ownership or a write permission.
  - The cancel service uses the same RBAC check as the view.
  - Allow PARTIALLY_REFUNDED → PARTIALLY_REFUNDED.
- **Files:** `backend/shop/payment_service.py`, `backend/shop/models.py`, `backend/shop/api_views.py`, `backend/shop/services.py`
- **Acceptance criteria:** each bug's expected behaviour holds.
- **Tests:** `shop/test_payments.py` with `refresh_from_db`; SUPPORT_TEAM cancel and POST tests; a two-partial-refunds test.
- **Dependencies / order:** after TASK-018 (refund UI safety) because of BUG-057.

### TASK-036 — Customers, support and notifications small fixes
- **Bugs:** BUG-061, BUG-062, BUG-063, BUG-064, BUG-065 · **Priority:** P3 (BUG-063/065: verify first) · **Effort:** S
- **Scope:**
  - Annotate favorites with visible-review ratings.
  - Use customer wording in public status notes.
  - Map MPO to `image/jpeg`.
  - Preferences: `isinstance` check and `update_or_create`.
  - Notification lease ≥ worst-case SMTP time, or a heartbeat renewal, or document the case under D4.
- **Files:** `backend/customers/views.py`, `backend/support/services.py`, `backend/support/serializers.py`, `backend/support/validators.py`, `backend/notifications/preferences.py`, `backend/notifications/worker.py`, `backend/config/settings/base.py`, `docs/NOTIFICATION_SYSTEM.md`
- **Acceptance criteria:** each bug's expected behaviour holds.
- **Tests:** the tests named in each bug entry.
- **Dependencies / order:** independent.

### TASK-037 — Guard the seed commands
- **Bugs:** BUG-068 · **Priority:** P3 · **Effort:** S
- **Scope:**
  - Refuse to run unless DEBUG and an explicit `--i-know-this-is-a-dev-db` flag (or similar).
  - Touch only rows created by the seeder (for example, a marker field or a slug prefix).
  - Use `InventoryService` for stock.
  - Never reset passwords of pre-existing accounts.
  - Stop granting SALES_TEAM (see TASK-005).
- **Files:** `backend/shop/management/commands/seed_demo_data.py`, `seed_showcase.py`
- **Acceptance criteria:** running against a database with real rows changes nothing outside the seeder's own rows.
- **Tests:** command tests with pre-existing matching slugs.
- **Dependencies / order:** after TASK-005.

### TASK-038 — Frontend list races and debounce
- **Bugs:** BUG-073, BUG-074, BUG-075 · **Priority:** P3 · **Effort:** M
- **Scope:**
  - Add a shared `useLatestRequest` hook (request key or AbortController) and apply it to every list page named in BUG-073.
  - Fix the debounce effect dependencies (pattern: `admin/reviews/page.tsx:96-101`).
  - Drop the explicit `fetchHistory()` after a points adjustment.
- **Files:** `frontend/src/app/admin/*/page.tsx`, `frontend/src/app/seller/*/page.tsx`, `frontend/src/components/notifications/NotificationInbox.tsx`, a new hook under `frontend/src/hooks/`
- **Acceptance criteria:** the latest request always wins; filters are never dropped.
- **Tests:** hook unit tests with out-of-order promises; fake-timer debounce tests.
- **Dependencies / order:** after TASK-042.

### TASK-039 — Console small fixes
- **Bugs:** BUG-077, BUG-078, BUG-080, BUG-081, BUG-082, BUG-083, BUG-097, BUG-098, BUG-100 · **Priority:** P3 · **Effort:** M
- **Scope:**
  - A confirm modal for category deactivation.
  - A functional state update for "Use current location".
  - EXPIRY in the points-type filter.
  - An owner-id filter for the shop list, linked from seller detail (backend param plus link).
  - `notFound()` in the catch-all route.
  - Gate the dashboard KPIs on `reports.view` and render "—" for missing values.
  - English empty-state copy.
  - UTC-safe date-only formatting.
  - Merge the full order response (or refetch the row) after list actions.
- **Files:** `frontend/src/app/admin/categories/page.tsx`, `shops/[id]/page.tsx`, `sellers/sellerGovernance.tsx`, `sellers/[id]/page.tsx`, `[...slug]/page.tsx`, `admin/page.tsx`, `orders/page.tsx`, `frontend/src/components/admin/shared/AdminStatCard.tsx`, `frontend/src/lib/admin-format.ts`, `backend/shop/admin_views.py` (shop owner filter)
- **Acceptance criteria:** each bug's expected behaviour holds.
- **Tests:** component tests for the modal, the KPI gating and the formatter.
- **Dependencies / order:** after TASK-042.

### TASK-040 — Storefront small fixes
- **Bugs:** BUG-085, BUG-086, BUG-089, BUG-090, BUG-091 · **Priority:** P3 · **Effort:** M
- **Scope:**
  - Hot Deals: badge only when there is a real discount, timer driven by the API, chevrons wired or removed.
  - Profile Settings disabled until the profile loads; send changed fields only.
  - Order-success loading, not-found and error states.
  - Error states instead of empty states (with TASK-026).
  - Review delete confirmation and visible errors.
- **Files:** `frontend/src/components/home/HotDealWidget.tsx`, `frontend/src/app/profile/settings/page.tsx`, `frontend/src/context/ProfileContext.tsx`, `frontend/src/app/order-success/[orderNumber]/page.tsx`, `frontend/src/context/FavoritesContext.tsx`, `frontend/src/app/profile/**`, `frontend/src/components/reviews/ReviewSection.tsx`
- **Acceptance criteria:** each bug's expected behaviour holds.
- **Tests:** component tests.
- **Dependencies / order:** after TASK-026 and TASK-042.

### TASK-041 — Accessibility pass on dialogs and menus
- **Bugs:** BUG-094 · **Priority:** P3 · **Effort:** M
- **Scope:**
  - A shared accessible Dialog (label, Escape, focus trap and return) used by CartDrawer, the cancel-order modals and the Console modals.
  - Disclosure ARIA plus Escape/outside-click on the Console header menu.
  - `inert` on the closed mobile sidebar.
  - Names for the thumbnail buttons and Hot Deals chevrons.
- **Files:** `frontend/src/components/cart/CartDrawer.tsx`, `frontend/src/components/profile/OrderCard.tsx`, `frontend/src/app/profile/orders/[orderNumber]/page.tsx`, `frontend/src/app/product/[slug]/page.tsx`, `frontend/src/components/admin/AdminHeader.tsx`, `frontend/src/components/admin/AdminSidebar.tsx`
- **Acceptance criteria:** keyboard-only users can open, use and close every dialog and menu; axe reports no critical issues on these components.
- **Tests:** axe plus Testing Library keyboard tests.
- **Dependencies / order:** after TASK-042.

---

## Group 5 — Test coverage, prevention and investigations

### TASK-042 — Frontend test harness
- **Bugs:** enables regression tests for the frontend bugs · **Priority:** P2 (prevention) · **Effort:** M
- **Scope:**
  - Add Vitest, React Testing Library and jsdom, with a `test` script in `package.json`.
  - Seed the suite with unit tests for `safeNextPath`, `refreshTokenOnce` single-flight, the API error parser and the CartContext failure paths.
  - Add the suite to CI.
- **Files:** `frontend/package.json`, `frontend/vitest.config.ts`, `frontend/src/**/*.test.ts(x)`, `.github/workflows/ci.yml`
- **Acceptance criteria:** `npm test` runs in CI and the seed tests pass.
- **Tests:** —
- **Dependencies / order:** start immediately; it unblocks TASK-013, 022, 024, 038, 039, 040 and 041.

### TASK-043 — Backend regression suites
- **Bugs:** cross-cutting (BUG-002, 005, 006, 007, 017, 019, 020, 021, 022, 057, 058, 059) · **Priority:** P2 (prevention) · **Effort:** M
- **Scope:**
  - A reusable change-form lockdown test mixin.
  - `assertNumQueries` baselines for the list endpoints.
  - MySQL `TransactionTestCase` concurrency helpers.
  - Invoice text-extraction helpers.
  - Table-driven state-machine tests (orders, payments, sellers, shops).
- **Files:** `backend/*/tests*`, a new `backend/utils/testing.py`
- **Acceptance criteria:** the helpers exist and are used by the Group 1–2 tasks.
- **Tests:** —
- **Dependencies / order:** in parallel with Group 1.

### TASK-044 — CI hardening
- **Bugs:** prevention for BUG-001/014 and lint drift · **Priority:** P3 · **Effort:** S
- **Scope:**
  - Add `check --deploy --fail-level WARNING --settings=config.settings.prod`.
  - Add an `npm run lint` step, initially with an agreed baseline (47 known `set-state-in-effect` errors).
  - Add `permissions: contents: read`.
  - Optionally add a secret scanner (for example gitleaks) and a dependency audit job.
- **Files:** `.github/workflows/ci.yml`
- **Acceptance criteria:** CI fails on new deploy warnings, new lint errors and committed secrets.
- **Tests:** —
- **Dependencies / order:** after TASK-001 and TASK-042.

### TASK-045 — INVESTIGATION: route params in API paths (BUG-093)
- **Bugs:** BUG-093 (Unverified) · **Priority:** P3 · **Effort:** XS
- **Investigate:** in Next 16, what does `useParams()` return for an encoded slash (`%2F`) in `/order-success/[orderNumber]` and `/admin/*/[id]`? If the value is decoded, confirm the traversal in a local dev environment only.
- **Outcome:**
  - If decoded: open an implementation task to apply `encodeURIComponent` in every path builder (`lib/api.ts`, `lib/admin-api.ts`).
  - Otherwise: close BUG-093 as not reproducible, and still encode for defence in depth.
- **Files to read:** `frontend/src/lib/api.ts:531`, `frontend/src/lib/admin-api.ts` path builders, the route pages.

### TASK-046 — INVESTIGATION: follow-up pass on partially read files
- **Bugs:** none yet · **Priority:** P3 · **Effort:** M
- **Investigate:** read line by line the files listed in report §7 that were only scanned with grep. These include the Django templates `profile.html`, `index.html` and `auth/user/change_form.html`; `rbac/widgets.py` lines 121-229; the admin JS; the support ticket page lines 420-880; role and category governance; customer directory; admin profile; and `types.ts` lines 520-946.
- **Outcome:** new BUG entries (same format) or a note that the area is clear.

### TASK-047 — INVESTIGATION: data reconciliation (read-only first)
- **Bugs:** supports BUG-007, BUG-012 · **Priority:** P2 · **Effort:** M
- **Investigate**, using read-only SQL on a snapshot of the database, never the live shared instance:
  - inventory drift (`available + reserved + sold` versus the ledger) per product (Known #30);
  - delivered orders without reservations;
  - orders without payments;
  - sellers holding SALES_TEAM (BUG-004 reach).
- **Outcome:** a reconciliation report and, if needed, a reviewed repair migration or script, with a backup first.
- **Dependencies:** run after TASK-006 and TASK-008, so no new drift is produced.

### TASK-048 — DECISIONS: business rules that gate fixes
- **Bugs:** gates BUG-004, 011, 012, 035, 048 · **Priority:** P1 (blocking) · **Effort:** S (meeting plus write-up)
- **Decide, and record in `docs/FUTURE_PLAN.md`:**
  1. The seller permission model (seller role versus RBAC `products.create`), and whether a platform inventory permission is needed (Known #27).
  2. The product publication flow (seller submit versus staff publishing from DRAFT; Known #8).
  3. The COD payment lifecycle (create at checkout? mark PAID on delivery? backfill?).
  4. The demo-data fallback policy for production.
  5. Whether staff take-back may renew point expiry.
  6. Whether product rejection or deletion refunds the creation fee (`PointTransaction.TYPE_REFUND` has no producer).
  7. Whether staff may credit their own seller wallet.
  8. Whether `users.admin.view` / `roles.admin.view` should see the full audit log, including payment metadata.
  9. Whether the CUSTOMER role is protected from deactivation and edits.
- **Outcome:** a short decision record per item; unblocks TASK-005, 014, 015, 026 and 034.

---

## Bug → task cross-reference

| Task | Bugs |
|---|---|
| TASK-001 | 001 |
| TASK-002 | 013, 014 |
| TASK-003 | 002, 039 |
| TASK-004 | 003 |
| TASK-005 | 004 |
| TASK-006 | 006, 021, 046 |
| TASK-007 | 005 |
| TASK-008 | 007 |
| TASK-009 | 015, 041, 049 |
| TASK-010 | 019, 020 |
| TASK-011 | 008 |
| TASK-012 | 009, 055 |
| TASK-013 | 010, 084, 087 |
| TASK-014 | 011 |
| TASK-015 | 012, 052 |
| TASK-016 | 017, 050 |
| TASK-017 | 034, 053, 088 |
| TASK-018 | 036, 076 |
| TASK-019 | 016 |
| TASK-020 | 018 |
| TASK-021 | 024, 025, 026, 079 |
| TASK-022 | 028, 029 |
| TASK-023 | 027, 030, 069, 070, 071, 072, 096 |
| TASK-024 | 031, 092 |
| TASK-025 | 032, 033 |
| TASK-026 | 035 |
| TASK-027 | 022, 023, 067 |
| TASK-028 | 037, 095, 099 |
| TASK-029 | 058, 059 |
| TASK-030 | 038, 042 |
| TASK-031 | 040, 060, 066 |
| TASK-032 | 043 |
| TASK-033 | 044, 045 |
| TASK-034 | 047, 048 |
| TASK-035 | 051, 054, 056, 057 |
| TASK-036 | 061, 062, 063, 064, 065 |
| TASK-037 | 068 |
| TASK-038 | 073, 074, 075 |
| TASK-039 | 077, 078, 080, 081, 082, 083, 097, 098, 100 |
| TASK-040 | 085, 086, 089, 090, 091 |
| TASK-041 | 094 |
| TASK-042 … TASK-044 | prevention (no bug owned) |
| TASK-045 | 093 (investigation) |
| TASK-046 … TASK-048 | investigations / decisions |

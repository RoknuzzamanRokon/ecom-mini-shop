# MiniShop — Future Plan

**Created:** 2026-09-18 · **Baseline commit:** `fe347ef` · **Status:** Phases 2A, 2B and 2C done 
(2026-09-18/19); everything after them still proposed

This is a **roadmap**, not a spec. Each phase below is sized to become one spec
and one commit, written in the same format as `task/task*.md`.

Three rules carried over from `docs/MINISHOP_REVIEW_STATE.md`:

1. **Source is the only source of truth.** This file, like the review cache, goes
   stale. Every `file:line` below was verified against source on 2026-09-18 — but
   re-check before you act on one.
2. **`docs/MINISHOP_REVIEW_STATE.md` remains the review cache.** It records what
   *is*; this file records what *should happen next*. Known Issue numbers (`#n`)
   below refer to its §16 table.
3. **Architecture invariants (§18 of the review cache) are not up for
   negotiation.** Where a phase below brushes against one, its scope boundary
   says so explicitly.

## Ordering rationale

The review cache's last roadmap note (§20) left `/admin/audit-logs` as the sole
remaining console module and asked whether Known Issue #23 outranked it. Having
made that comparison with fresh evidence, the answer is that **both are outranked**
— first by the test suite itself, then by a revenue-reporting defect that was not
previously recorded.

The suite comes first for a blunt reason: a ~92-minute run means fixes ship on
targeted test runs and partial evidence. Every phase after 2A is cheaper and
better-verified because 2A happened.

---


2A ✅ → 2B ✅ → 2C ✅ → 2D ← NEXT → 2F → 2G → 2H → 2E → 2L → 2I → 2J → 2K → 2M → 2N


## Phase 2A — Make the test suite fast

**Objective.** Split `backend/config/settings.py` into `base` / `dev` / `test`, and
make the test settings cheap to run.

**Evidence.** 512 test methods across 25 modules take roughly 92 minutes (~4
tests/min) per §15 of the review cache. There is **no `PASSWORD_HASHERS` override**
anywhere in `config/settings.py`, and there are **176 `create_user` /
`create_superuser` call sites** across those 25 modules — so most of the wall clock
is PBKDF2 at Django's default iteration count, plus 21 migrations replayed against
a fresh MySQL test database on every run. This is misconfiguration, not scale.

**Scope boundary — do NOT:**
- Move the test database to SQLite. `select_for_update()` is a silent no-op there,
  which would blind Phase 2G and weaken every existing concurrency test.
- Change any application behavior. This phase touches settings and test
  configuration only.
- Add production settings hardening — that is Phase 2N.

**Done when.** The full suite runs in under 10 minutes with `--parallel --keepdb`,
and produces the same pass/fail set as before (one pre-existing failure, #14, still
failing — 2B fixes it). Record the before/after timing in the final report.

**Status: DONE 2026-09-18 — with the timing target missed and the reason measured.**
`config/settings.py` → `config/settings/{__init__,base,dev,test,hashers}.py`; `dev` is
value-for-value identical to the pre-split module (verified by diffing every upper-case
attribute). **`Ran 462 tests in 5509s` (91.8 min) → `Ran 512 tests in 785.179s` (13.1 min)**
at the default worker count, **610.4 s (10.2 min)** at `--parallel 32`; same pass/fail set
(one failure, always #14) across three full runs. See §15/§21 of the review cache.

Two corrections to the evidence above, both measured:

1. **PBKDF2 was not "most of the wall clock".** It is worth ~13.6% on a serial control
   subset. CPU utilisation during a test run is **5%** — the suite is round-trip-bound on
   the *remote* MySQL in `backend/.env` (54–167 ms per query), not CPU-bound.
2. **`--parallel` did not work at all on this suite**, independent of settings. Django
   pickles worker failures back to the parent, tracebacks are not picklable without
   `tblib`, and #14 fails on every run — so a parallel run aborted with
   `TypeError: cannot pickle 'traceback' object` and reported nothing. `tblib` is now a
   requirement. **Phase 2B's CI must install it**, or CI's parallel job will abort rather
   than report the failure 2B is fixing.

**Under 10 minutes is not reachable on the remote database.** Django partitions parallel
work by `TestCase` class, so the longest class is an unsplittable floor. Measured directly:
run alone with `--parallel`, `shop.tests` takes **551 s** and `sellers` **546 s** — those are
single-class costs, ~60 s per individual test, i.e. hundreds of round-trips each. The floor
is therefore **~9.2 min**, and the 32-worker whole-suite run (610 s) is already within a
minute of it. No worker count clears 10 minutes here.

`config.settings.test` honours `TEST_DATABASE_URL` (MySQL only) so test runs can point at a
local server — the one lever that would clear the target comfortably. It could not be used
here: the local MariaDB account has no `CREATE DATABASE` privilege. **Give Phase 2B's CI job
a local MySQL service and this target is met for free.** Alternatively, trimming the query
volume in `shop.tests` / `sellers`' slowest classes would lower the floor itself — but that
is a test change, which Phase 2A explicitly excludes.

---

## Phase 2B — Green suite, then the first CI

**Objective.** Fix the one permanently-failing test, add the missing npm scripts,
and add the repository's first CI workflow.

**Evidence.**
- Known Issue #14: `shop/test_admin_site.py:94` asserts `assertIn("৳", body)`, but
  `templates/admin/index.html:80` emits the numeric character reference `&#2547;`.
  The test as written can never pass. Note the second assertion —
  `assertNotIn("$", body)` at `:95` — has never been exercised and may also fail
  once the first is fixed.
- `frontend/package.json` has only `dev`/`build`/`start`/`lint`. There is no
  `typecheck` script; `tsc --noEmit` is run by hand.
- There is no `.github/` directory anywhere in the repository.

**Scope boundary — do NOT:**
- Add a deploy pipeline, Docker, or any publish step. Build-and-test only.
- Add frontend component or E2E tests (see *Not in this roadmap*).
- Fix any other failing or flaky test discovered along the way — record it as a new
  Known Issue instead.

**Done when.** CI runs backend tests + `tsc --noEmit` + `next build` on push, and
the backend job is green with zero failures.

**Status: DONE 2026-09-19.**

- **#14 fixed on the template side, with no test modified.** `templates/admin/index.html:80`
  now emits the literal `৳` instead of `&#2547;` — the direction AGENTS.md commandment 1
  asks for, and the one that lets the assertion pass exactly as written. **The open question
  above is answered: the second assertion passes.** The rendered dashboard contains zero `$`
  characters (checked against the full body, then confirmed by running the test).
- **Suite is green: `Ran 512 tests in 923.766s … OK` — 512 passed, 0 failed, 0 errors.**
  First fully green full-suite run on record. No other test changed status, so no new Known
  Issue was raised.
- **`npm run typecheck`** (`tsc --noEmit`) added to `frontend/package.json`; exit 0.
  `npm run build` exit 0, 42/42 static pages.
- **`.github/workflows/ci.yml`** — backend job against a **MySQL 8 service container**
  (not SQLite: `select_for_update()` must stay real), which installs `requirements.txt`,
  asserts `tblib` imports, runs both `manage.py check` variants plus `makemigrations
  --check`, then the suite with `--parallel 4 --noinput`; frontend job runs `npm ci`,
  `npm run typecheck`, `npm run build` on Node 20. Verification only — no deploy, Docker,
  publish or release step.
- **Caveat, stated plainly: the workflow has never been executed.** GitHub Actions cannot
  run in this environment. It was validated by parsing the YAML and by confirming every
  command it invokes is green locally. Its first real run will be on the next push.

---

## Phase 2C — Refund-aware revenue

**Objective.** Make `total_revenue` reflect money actually kept.

**Evidence.** `backend/shop/metrics.py:30` defines
`PAID_PAYMENT_STATUSES = (Payment.STATUS_PAID, "COMPLETED")`, and `:119-123` sums
`Payment.amount` filtered on it. But `PaymentService.process_refund`
(`shop/payment_service.py:321-323`) transitions a payment to `REFUNDED` or
`PARTIALLY_REFUNDED`. **A ৳1 partial refund therefore erases the entire ৳10,000
payment from `total_revenue`** — on both the Django admin dashboard and the console
KPI card. Revenue is also cast `Decimal → float` at `metrics.py:165`.

This is not in the Known Issues table; it was found during the 2026-09-18 review.

**The fix is not a status-list edit.** Adding `PARTIALLY_REFUNDED` to the tuple
would count the *full original amount* of a partly-refunded payment. Correct
revenue is `Sum(Payment.amount)` over paid-ish statuses **minus** `Sum(Refund.amount)`
over succeeded refunds.

**Scope boundary — do NOT:**
- Change the `paid` **count** at `metrics.py:109`, which reads the same tuple.
  Whether a partly-refunded payment still counts as "paid" is a separate product
  question — leave it, and say so in the report.
- Rename or re-scope the seven `get_console_metrics` keys. The docstring at
  `metrics.py:156-161` marks them a published API contract consumed by
  `frontend/src/lib/admin-api.ts`.
- Add a new metrics endpoint, a date-range filter, or any dashboard UI change.

**Done when.** A test proves a ৳10,000 payment with a ৳1 partial refund reports
৳9,999 revenue, not ৳0 and not ৳10,000; and revenue stays `Decimal` end to end.

**Status: DONE 2026-09-19.** Recorded as Known Issue #25 (now fixed).

Revenue is `Sum(Payment.amount)` over captured statuses — the paid pair widened with
`PARTIALLY_REFUNDED` and `REFUNDED`, all of which genuinely captured money, since
`Payment.VALID_TRANSITIONS` reaches either only from `PAID` — **minus**
`Sum(Refund.amount)` over `COMPLETED` refunds on those same payments. Scoping the
refund side to the same status set is what keeps a fully-refunded payment at exactly
0 rather than negative. Only `COMPLETED` counts, because that is what
`PaymentService.process_refund` itself treats as money gone; no refund status was
invented and no refund logic duplicated.

The refund total is a **separate** aggregate on `Refund`, not a join into the payment
aggregate, which would have fanned out one payment row per refund row and silently
inflated every `Count()` beside it.

`Decimal` end to end — both sides `Coalesce` to `Decimal("0.00")`, and the `float()`
cast is gone. The wire format is unchanged: DRF's JSON encoder renders a `Decimal` as
a JSON number, so `admin-api.ts`'s `total_revenue: number` still holds. **No frontend
file changed.** The `paid` count was left alone, as instructed, and that asymmetry is
now pinned by a test.

14 tests added; the key one was proven to fail against the pre-fix code with
`Decimal('0.00') != Decimal('9999.00')`. Full suite `Ran 538 tests in 799.683s … OK`,
`tsc` and `next build` both exit 0.

**Found along the way, recorded not fixed — Known Issue #26:** a payment accepts only
one partial refund that leaves a balance, because
`Payment.VALID_TRANSITIONS[PARTIALLY_REFUNDED]` has no self-edge, so a second partial
refund raises `ValidationError`. That contradicts `process_refund`'s cumulative
`remaining_refundable` design, but it is payment-lifecycle behaviour, outside this
phase's metrics-only scope.

---

## Phase 2D — One authorization system

**Objective.** Replace the hand-rolled role-code checks with RBAC permission
classes, and stop serving revenue to operators who should not see it.

**Evidence.**
- `shop/api_views.py` builds an inline `is_staff_override` tuple at **six** sites —
  `:422, 778, 822, 874, 912, 958` — each re-listing `user.is_staff` plus
  `ROLE_SUPER_ADMINISTRATOR` / `ROLE_ADMINISTRATOR` / `ROLE_OPERATION_MANAGER` by
  hand, instead of using an RBAC permission class. (The review cache lists five;
  `:422` is a sixth.)
- `AdminMetricsAPIView` (`shop/admin_views.py:1277-1300`) declares
  `permission_classes = [IsAuthenticated]` and enforces management access inline in
  `get()` via the same hardcoded role-code pattern. **This is a consistency problem,
  not an open hole** — access *is* enforced. Do not report it as a vulnerability.
- The real exposure is narrower: that endpoint returns the whole payload including
  `total_revenue` to any of seven management roles, and hiding the KPI card is a
  purely client-side decision (`frontend/src/app/admin/page.tsx:60-71`). A
  finance-less operator can read revenue from the network tab.

**Scope boundary — do NOT:**
- Build a second permission system or use Django `auth.Permission` to authorize an
  API (invariant 2).
- Touch the client-side console-access heuristic at
  `frontend/src/lib/admin-auth.ts:70` — it is a separate decision.
- Change which roles hold which permissions. This phase changes *how* the check is
  expressed, plus one server-side field gate.

**Done when.** No `is_staff_override` tuple remains in `shop/api_views.py`; a test
proves a management user without the finance permission receives a metrics payload
with no `total_revenue` key; and every existing authorization test still passes.

**Status: DONE 2026-09-19 — with one done-when condition deliberately not met.**

- **Order sites converted (2 of 6).** `:422` (cancel) now uses `orders.staff.update`
  via `CanUpdateStaffOrders`; the payment-lookup helper uses `orders.staff.view` via
  `CanViewStaffOrders`. Both are the permissions written for exactly this check
  ("view all customer orders across the platform (Staff)").
- **Inventory sites NOT converted (4 of 6) — "no `is_staff_override` remains" is
  therefore unmet, by decision.** There is no platform-wide inventory permission to
  convert them to: the catalogue holds only `inventory.view`/`inventory.adjust`, and
  a seller must already hold `inventory.view` to clear `CanViewInventory` and reach
  the endpoint, so either one used as the override would hand every seller every
  shop's stock. Adding a permission and granting it to roles was out of scope.
  Recorded as **Known Issue #27**; each site carries a comment pointing at it.
- **Metrics authorization** moved to `CanViewPlatformMetrics` (`reports.view`),
  replacing an inline seven-role-code list plus an `is_staff` test and a check for
  `"admin:access"` — a code that is not in `PERMISSIONS_DATA` and so never matched.
- **Revenue gated server-side** on `payments.view` (reusing `CanViewPayment`): the
  key is *removed* from the payload, not zeroed. Proven against the serialized HTTP
  body, not the UI.
- **No role grant changed.** `seed_rbac` is untouched.

**Follow-up this created — Known Issue #28.** The console draws the revenue card on
`payments.view` **or** `reports.view`, and `AdminStatCard` renders a missing value as
`formatTaka(0)`. So a finance-less operator now sees a confident **৳0.00** rather than
no card. The leak is genuinely closed — the value is absent from the response — but the
display is misleading. The fix is one line in the frontend, which this phase was
explicitly forbidden from touching.

Verification: full suite `Ran 556 tests in 787.872s … OK` (0 failures);
`makemigrations --check` clean; `npm run typecheck` and `npm run build` exit 0.

---

## Phase 2E — Retire the legacy template storefront

**Objective.** Delete the server-rendered cart/checkout/order-success flow.

**Evidence.** `shop/views.py:111-146` `checkout()` creates `Order` and `OrderItem`
rows directly — no `OrderService`, no inventory reservation, no audit entry, no
product-eligibility re-validation (`shop/cart.py:68-94` filters on `is_active` only,
so a DRAFT product or one from a suspended shop can still be ordered this way), and
none of the `shipping_*` / `subtotal` snapshot fields populated. Known Issue #1b,
open since 2026-09-17. The Next.js app is the real storefront.

**Removal set:** `cart_view` (`:106`), `checkout` (`:111`), `order_success` (`:149`)
and their helpers `_remember_placed_order` (`:159`) / `_can_view_order` (`:176`);
the `cart_add` / `cart_increase` / `cart_decrease` / `cart_remove` POST views
(`:68-104`); the corresponding `templates/shop/` pages; the matching `shop/urls.py`
routes; and `shop/tests.py`'s `CheckoutTests` + `LegacyOrderAccessTests`.

**Decided 2026-09-18: guest checkout ends with this phase.** This is the only path
producing `user=NULL` orders, and there is no guest order-lookup API. A real guest
flow, if wanted, is a future spec built on `OrderService` — not a reason to keep
this one.

**Scope boundary — do NOT:**
- Touch the Django `/admin/` site. Invariant 10 keeps it; this removes the legacy
  *storefront*, a different surface.
- Change the Next.js checkout in any way.
- Delete `LegacyOrderAccessTests` in a separate commit from the code it guards — it
  is the regression proof for the #1 IDOR fix. Same commit, or not at all.
- Migrate or delete existing legacy orders from the database.

**Done when.** No route renders a `templates/shop/` checkout page, the suite is
green, and the report names every deleted file and the guest-checkout consequence
explicitly.

---

## Phase 2F — Guard inventory release against reservation-less orders

**Objective.** Stop a cancellation from releasing stock it never reserved.

**Evidence.** `InventoryService.release_order_reservation` releases
`qty = min(inventory.reserved_quantity, item.quantity)`
(`shop/inventory_service.py:258`). An order with no RESERVE ledger row — every
order the legacy flow ever created — therefore releases stock **reserved by other
orders**, producing phantom availability and a real oversell path.

**This phase stands alone from 2E.** Retiring `checkout()` stops new bad orders; it
does nothing about the ones already in the database. This is the actual safety fix
and is needed regardless of what happens to 2E.

**Scope boundary — do NOT:**
- Redesign the inventory model, the ledger, or the reservation lifecycle.
- Change `reserve_stock_for_cart` or the SALE path.
- Backfill or repair existing inventory rows — if the audit surfaces drift, report
  it as a new Known Issue with numbers.

**Done when.** A test creates an order with no RESERVE row against a product with
stock reserved by a *different* order, cancels it, and proves the other order's
reservation is untouched.

---

## Phase 2G — Row-lock the seller lifecycle (#23)

**Objective.** Close the TOCTOU window on audited seller status transitions.

**Evidence.** Known Issue #23: none of the four lifecycle endpoints in
`sellers/views.py` (`SellerApproveView` / `RejectView` / `SuspendView` /
`ReactivateView`) nor the bulk actions in `sellers/admin.py` take
`select_for_update()` when reading the seller row. Each captures
`previous_state = {"status": seller.status}` from an unlocked read, so under two
concurrent requests on the same seller the audit trail can record a `previous_state`
that never preceded the write. The sibling `AdminSellerStatusAPIView._update_status`
(`shop/admin_views.py:744`) already does this correctly — copy that pattern verbatim.

Fold in Known Issue #24 while here: `SellerApproveView.post`
(`sellers/views.py:152-154`) fetches inside its atomic block while the other three
fetch before. Cosmetic, same file, same lines being edited.

**Scope boundary — do NOT:**
- Change any lifecycle rule, state machine, or permission.
- Change what is written to `AuditLog`, only when the row is read.
- Extend locking to shops, orders, or products in this phase.

**Done when.** All four views and both admin helpers hold a row lock across the
read-then-write, and a concurrency test proves `previous_state` matches the
last-committed value. Note in the report that MySQL is required for this test to be
meaningful (see 2A's boundary).

---

## Phase 2H — Stop the seller UI reporting things that are not true

**Objective.** Fix three seller-facing contract lies. Bundled deliberately: each is
a few lines, and splitting them would be three specs of ceremony around one theme.

**Evidence.**
- **#3** — `frontend/src/app/seller/wallet/page.tsx:96,111` read
  `wallet.total_earned` / `wallet.total_spent`, and `:204` reads `txn.description`.
  `SellerWalletSerializer` returns neither total (only `balance`), and
  `PointTransactionSerializer` exposes `reason`, not `description`. The tiles show
  `+0` / `-0` forever and every row reads "Point transaction". The TypeScript types
  declare the missing fields, which is precisely why `tsc` cannot catch it.
- **#4** — `get_seller_capabilities` sets `can_create_shop = True`
  (`sellers/services.py:52,56`) for FULL/LIMITED shop owners, contradicting the
  enforced hard 403.
- **#11** — `frontend/src/app/seller/products/page.tsx:19` hardcodes
  `PRODUCT_CREATION_COST = 5` instead of reading the configurable
  `ProductCreationCost`. If an admin changes the cost, the UI lies; the backend
  still charges correctly.

**Scope boundary — do NOT:**
- Store totals as new columns on `SellerWallet`. They must be **aggregated from the
  existing `PointTransaction` ledger** — invariant 8 forbids a second balance source.
- Fix #4 by enabling shop creation. Sellers never create shops (invariant 4); the
  fix is to report `false`.
- Redesign the wallet page. Correct the data contract, including the lying TS types.

**Done when.** The wallet tiles show real ledger-derived totals and real transaction
reasons, `can_create_shop` is `false` everywhere, the creation cost is read from the
backend, and the TS types match what the serializers actually return.

---

## Phase 2I — `/admin/audit-logs`, the last console module

**Objective.** Build the final missing management-console module.

**Evidence.** `/admin/audit-logs` appears in `ADMIN_NAV_ITEMS` but has no route
directory, so `frontend/src/app/admin/[...slug]/page.tsx` renders the "Foundation
Ready / Awaiting Implementation" card. The read-only backend API
`GET /api/admin/audit-logs/` already exists, and `getAdminAuditLogs()`
(`frontend/src/lib/admin-api.ts:168`) is already written and called by nothing.
This is the most shovel-ready item on the list.

Follow the established colocated pattern — an `auditLogGovernance.tsx` beside the
route — and reuse `AdminDataTable`, `AdminFilterBar`, `AdminStatusBadge` and
`AdminPagination` from `frontend/src/components/admin/shared/`.

**Scope boundary — do NOT:**
- Ship all 13 filter parameters `getAdminAuditLogs` already types. Pick 4–5
  (actor, action, target type, date range) and defer the rest, or this becomes the
  largest console module yet built.
- Add any mutation. Audit logs are immutable — no edit, no delete, no annotation.
- Add CSV/PDF export, a retention policy, or log-pruning tooling.
- Change the backend. This module is frontend-only, like Phases 1J and 1K.

**Done when.** The module lists and filters audit entries with permission gating
matching every other console module, and `ADMIN_NAV_ITEMS` no longer routes to the
placeholder.

---

## Phase 2J — Auth resilience on the client

**Objective.** Stop a mid-session token expiry from looking like a random error.

**Evidence.** Neither `frontend/src/lib/api.ts` nor `frontend/src/lib/admin-api.ts`
has a 401 interceptor. `AuthContext.initialize()`
(`frontend/src/context/AuthContext.tsx:64-98`) attempts a refresh exactly once, on
mount. After that, an expired access token surfaces as a generic error toast and the
user must reload the page. The three legacy token-key fallbacks are also re-read
independently in `lib/auth.ts:5` and `context/CartContext.tsx:34` instead of through
one accessor.

Fold in Known Issue #9: `checkout/page.tsx:282` links to `/login?redirect=/checkout`
but `login/page.tsx:48,70` reads `?next=`, so the return-to-checkout redirect
silently does nothing.

**Scope boundary — do NOT:**
- Move tokens out of `localStorage`. Migrating to httpOnly cookies is a real
  improvement and its own phase with its own backend work.
- Add a logout or token-revocation endpoint (not in this roadmap — see below).
- Refactor either API module beyond the interceptor and the shared accessor.

**Done when.** A request that 401s refreshes once and retries transparently; a
failed refresh logs out cleanly instead of erroring; and the login redirect returns
the user to checkout.

---

## Phase 2K — Route-level error, loading and not-found boundaries

**Objective.** Stop failed fetches from rendering a silently empty page.

**Evidence.** There is no `loading.tsx`, `error.tsx` or `not-found.tsx` anywhere
under `frontend/src/app/`. Several storefront pages — `page.tsx`,
`product/[slug]`, `shops`, `shop/[slug]`, `seller/page.tsx`, `admin/profile` — have
a loading branch but **no error branch**, so a rejected fetch just renders nothing.

Kept separate from 2J on purpose: this is mechanical boilerplate, and bundling it
would bury 2J's auth logic — the part that actually needs review.

**Scope boundary — do NOT:**
- Change any data-fetching logic or add a data-fetching library.
- Convert client components to server components or restructure routes.
- Use anything but the existing design tokens (invariant 13).

**Done when.** Every route segment has appropriate boundaries and a forced fetch
failure renders a real error state with a retry affordance.

**Status: DONE 2026-09-23 — scope delivered, "Done when" corrected rather than
met as originally worded.** Every route segment now has `loading.tsx`, `error.tsx`
and `not-found.tsx` (root-level `global-error.tsx`/`error.tsx`/`loading.tsx`/
`not-found.tsx`, plus segment-level boundaries for `product/[slug]`, `shop/[slug]`,
`shops`, `seller`, `admin` and `profile`), a shared `RouteErrorState` presentation
component, and the existing `notFound()` calls in `product/[slug]/page.tsx` and
`shop/[slug]/page.tsx` are now backed by real `not-found.tsx` pages instead of an
inline branch. A render-phase throw now reaches these boundaries with a working
retry affordance. No data-fetching logic or library was touched, no client
component was converted, and no route was restructured — the scope boundary held
exactly as written.

**The literal second half of "Done when" is not met, and cannot be met inside this
phase's own scope boundary.** A reconciliation audit (2026-09-23) found that every
`frontend/src/lib/api.ts` function the storefront actually fetches through
(`getCategories`, `getProducts`, `getProductDetail`, `getProductById`,
`getHotDeal`, `getShopDetail`, `getShops`, `getOrderDetail`) already caught its own
fetch failure and resolved to demo data or `null` before this phase started — that
is the "Change any data-fetching logic" this phase was told not to touch. A
`useEffect` fetch that never rejects gives a route `error.tsx` nothing to catch, so
a **forced network-level fetch failure still renders demo data or a `not-found.tsx`
page, never `error.tsx`**, on the pages the original Evidence paragraph named. The
boundaries built here are real and load-bearing for what they do catch — a genuine
render-phase crash — just not for that specific failure mode. See the deferred
follow-up under "Not in this roadmap" below.

---

## Phase 2L — Decide seller self-registration (#5)

**Objective.** Resolve a standing contradiction between an endpoint and an
architecture invariant.

**Evidence.** `POST /api/sellers/register/` (`sellers/views.py:30-42`) allows
self-service `SellerProfile` creation with only `IsAuthenticated`, contradicting
invariant 4 ("admins create and configure sellers"). Mitigated today: the profile
lands in `PENDING`, has no shop and no RBAC role, so it can do nothing until an
admin acts — and no frontend code calls it.

**Default to removal.** Nothing consumes it and it contradicts a stated invariant.
Keeping it requires documenting an explicit exception in §18 of the review cache,
which is more work than deleting it.

**Scope boundary — do NOT:**
- Build an admin-side seller-creation UI as a replacement — that already exists.
- Touch the seller lifecycle, RBAC roles, or `SellerProfile` itself.

**Done when.** The endpoint is gone (or documented as a deliberate exception), and
`docs/MINISHOP_REVIEW_STATE.md` records the decision either way.

---

## Phase 2M — Deletion-only sweep

**Objective.** One trivially reviewable commit that removes dead code.

**Evidence.**
- `CanCreatePayment` (`shop/permissions.py:349-361`) — referenced by zero views
  (#20). Customer payment initiation is by ownership, by design.
- `IsInventoryProductOwner`, `IsOrderOwner` (`shop/api_views.py:44-45`) and
  `rbac.permissions.HasAnyPermission` — imported or defined, never used.
- `Product.STATUS_SUBMITTED` and `submitted_at` — nothing can set them; there is no
  seller submit endpoint (#8).
- `SellerProfile.submit_for_review()` (`sellers/models.py:121-124`) — zero callers
  outside migrations and tests. A *different* unreachable path from #8; do not
  conflate the two.
- Duplicate `/api/orders/` registration (`shop/urls.py:29-30`) — inert, Django takes
  the first match. Hygiene only.
- `DEMO_CATEGORIES` / `DEMO_PRODUCTS` (`frontend/src/lib/api.ts:36-290`) — ~250
  lines of mock data with hardcoded external image URLs, exported and imported
  nowhere.
- `ProtectedRoute` (`frontend/src/components/auth/ProtectedRoute.tsx`) — zero
  usages; `profile/layout.tsx:29` reimplements it (#10).
- The five `/account/*` redirect shims — duplicating the `redirects()` block at
  `frontend/next.config.ts:46-78`.

**Scope boundary — do NOT:**
- Refactor anything. Deletions only. No renames, no signature changes, no "while
  I'm here."
- Delete `#13` (`/api/admin/roles/` unpaginated) or `#21` (`StaffRefundListAPIView`
  has no filters) — those are *missing* behavior, not dead code.
- Remove anything a grep cannot prove unused. If in doubt, leave it and say so.

**Done when.** Every deletion is justified by a zero-usage grep quoted in the report,
and the full suite plus `next build` are green.

---

## Phase 2N — Production readiness gate (not scheduled)

**Not a next task.** No deployment is planned as of 2026-09-18. This is the
checklist that must be cleared **before the first deploy to any shared
environment**, recorded here so the decision is easy later. Phase 2A's settings
split is its natural foundation.

| Blocker | Evidence |
|---|---|
| `DEBUG = True` | `backend/config/settings.py:40` |
| Hardcoded `SECRET_KEY` committed to git | `config/settings.py:37` |
| `ALLOWED_HOSTS` localhost-only | `config/settings.py:42` |
| CORS origins hardcoded to `localhost:3000` | `config/settings.py:175` |
| Password minimum of 4 characters, no other validators | `config/settings.py:137-138` |
| **No `LOGGING` config beyond the `notifications` logger** (added 2026-09-29) — while 8 other non-test modules call `logging.getLogger` |
 `audit/services.py`, `cart/services.py`, `customers/services.py`, `points/services.py`, 
 `shop/{admin_views,inventory_service,payment_service,services}.py` |
| No `SECURE_*` / HSTS / secure-cookie settings | absent from `config/settings.py` |
| `.env` hand-parsed, no `python-dotenv` | `config/settings.py` |
| Stale `backend/db.sqlite3` tracked, though settings require MySQL | repo root of `backend/` |
| JWTs in `localStorage`, no revocation on logout | `frontend/src/context/AuthContext.tsx` |

---

## Decisions from the 2026-10-22 audit (TASK-048)

`audit/BUG_FIX_TASKS.md` TASK-048 lists business rules that gate fixes. They
are recorded here as they are made.

1. **Seller permission model** — decided 2026-10-23, implemented in TASK-005.
   - Sellers hold no staff role. The Seller Center (product create and edit,
     seller orders, seller inventory) admits a user by an APPROVED or ACTIVE
     seller profile, then scopes them to their own shops. No RBAC code is
     involved.
   - Product delete still needs `products.delete`, which sellers do not hold,
     the same as before.
   - SALES_TEAM stays a staff role. Migration
     `sellers/0003_sellers_leave_sales_team` deactivated it on plain seller
     accounts, and `seed_showcase` no longer assigns it.
   - Staff access is unchanged. Known #27 (the inventory role-code override) is
     still open: staff who hold `inventory.*` outside the override list are
     still scoped as sellers.
2. **Product publication flow** — decided 2026-10-23, implemented in TASK-014
   (resolves Known #8).
   - The seller submits: "Submit for review" in the Seller Center calls
     `POST /api/products/mine/<id>/submit/`, which moves a DRAFT, or a
     REJECTED product the seller has corrected, to SUBMITTED. It is
     owner-only, and writes a `PRODUCT_SUBMITTED` audit row.
   - Staff review in the Console: approve or reject a SUBMITTED product, then
     publish an approved one. These are the existing audited moderation
     actions.
   - The Console offers no action on a DRAFT. The staff status endpoint still
     has no from-state guard, so staff could act on one through the API.
3. **COD payment lifecycle** — decided 2026-10-23, implemented in TASK-015.
   - Cash on delivery is the only payment method for now. Online and
     mobile-banking methods (bKash, Nagad, card) come later, together with a
     gateway.
   - Checkout opens one PENDING `CASH_ON_DELIVERY` payment for the order
     total, inside the order transaction.
   - Delivering the order marks that payment PAID, because the cash is
     collected at the door. Cancelling cancels it. A refund never reopens an
     order for a second payment.
   - The customer payment endpoint accepts only `CASH_ON_DELIVERY` until
     the gateway exists.
   - Historical orders are not backfilled now. An order placed before this
     change gets its payment when it is delivered, and TASK-047 reports any
     remaining gaps.
4. **Demo-data fallback** — decided 2026-10-23, applied in TASK-026.
   - The demo catalogue fallback stays for now, during development.
   - **Before the first production release it is removed.** That means
     `DEMO_PRODUCTS`, `DEMO_CATEGORIES`, and the fallbacks in `getProducts`,
     `getProductDetail`, `getHotDeal` and `getCategories` in
     `frontend/src/lib/api.ts`.
   - Until then BUG-035's risk stands. While the API is down the storefront
     shows eight demo products as real ones, and a guest who adds one to the
     cart gets the real product with the same id after logging in.
   - Outages unrelated to demo data now show as errors, not as "not found" or
     "empty": the order page, the shop page (its `error.tsx`), favorites and
     addresses. Seller forms never use demo categories (TASK-023).
5. **Point expiry on a take-back** — decided 2026-10-24, implemented in
   TASK-034.
   - Points a staff member takes back from a seller keep the expiry they had
     in the staff wallet; they do not start a fresh period. Crediting a
     seller and debiting the points straight back can no longer renew them.
   - Giving is unchanged: a seller's credit always starts a full expiry
     period. The seller's lot records when the staff points it came from
     would have expired (`SellerPointLot.origin_expires_at`), and a
     take-back returns the points with the earliest such date among the
     lots it takes from.
   - Points from a wallet whose points never expire (a superuser's, or a
     staff member with expiry switched off) carry no date, and come back
     with a full period, as before.
   - Unticking `is_superuser` in the Django admin restarts the expiry clock
     on what the user holds, with a `STAFF_POINTS_EXPIRY_RESTARTED` audit
     row, instead of letting every dated lot expire at once (BUG-047).

6. **Creation-fee refund** — decided 2026-10-25, implemented in TASK-048.
   - When staff delete a product that never went live, the seller gets its
     creation fee back as a REFUND point transaction, once. "Never went
     live" means it is not PUBLISHED or UNPUBLISHED and no
     `ADMIN_PRODUCT_PUBLISH` audit row exists for it.
   - A rejection keeps the fee: the seller can correct and resubmit the same
     product. A seller deleting their own product gets no refund.
   - Staff delete products in the Django admin (single or bulk). Each
     deletion writes `PRODUCT_DELETED` with the refunded amount. That delete
     used to be refused for everyone, because the product's inventory and
     ledger admins refuse deletes; those rows now go with the product.
7. **Staff and their own seller wallet** — decided 2026-10-25, implemented
   in TASK-048. A staff member who also sells cannot credit or debit their
   own seller wallet: `PointService.adjust_points` raises
   `SelfAdjustmentError` (the API answers 403). The Console hides the
   buttons on one's own seller page. Another staff member has to do it.
8. **Who reads the full audit log** — decided 2026-10-25, implemented in
   TASK-048. Only `audit.view` or `audit.admin.view` (and Super
   Administrators) open `/api/admin/audit-logs/`, since it carries payment
   and refund details. `users.admin.view` and `roles.admin.view` no longer
   do. `audit.view` is now seeded and given to ADMINISTRATOR, also by
   migration `rbac/0003_audit_view_permission` for existing databases. A
   custom role that held only the user or role codes loses access.
9. **The CUSTOMER role is locked** — decided 2026-10-25, implemented in
   TASK-048. `LOCKED_ROLE_CODES` (the protected roles plus CUSTOMER):
   - the Console API can neither change nor delete it;
   - in the Django admin only a Super Administrator can change it, and
     nobody deletes it.

   Holding or assigning CUSTOMER is unchanged: it is not in
   `PROTECTED_ROLE_CODES`, so administrators still create customers.

## Sales Team field onboarding (decided 2026-10-31)

New feature work, outside the fixes-only roadmap above. It is the backend
for a planned Android app for the Sales Team; the app itself comes later.
The code is in the `onboarding` app, and the API is under `/api/onboarding/`.

1. **Permission.** The Sales Team gets the new code `sellers.onboard`, not
   `sellers.create` / `shops.create` / `shops.view`. Those three would open
   the Console's free creation path and every seller's shops, which breaks
   decisions 2 and 3. SALES_TEAM also loses `sellers.view` (migration
   `rbac/0005_sellers_onboard_permission`). The Console paths are unchanged.
2. **Points and tokens.** A superuser gives a Sales Team member points
   through the existing staff transfer: `sellers.onboard` now counts as a
   reason to hold points. Each seller they open moves
   `OnboardingSettings.starting_points` (200) from their wallet to the new
   seller's wallet. With 500 points, that is two sellers. Each seller also
   earns them `tokens_per_seller` (51) tokens, which they can see
   (`/api/onboarding/me/`, `/api/onboarding/tokens/`). How tokens are spent
   is not decided yet. Product creation fees come out of the seller's
   wallet, as for any product.
3. **Scope.** `SellerProfile.created_by` records who created every seller
   (Console, Django admin or onboarding). An onboarder reaches only the
   sellers they onboarded, and sees how many those are.
4. **Approval.** The onboarder adds the seller, its shop and its products,
   and nothing is public until staff approve. One approval
   (`/api/onboarding/review/<pk>/approve/`) puts the seller, its waiting
   shops and its submitted products live together. It needs every code the
   separate Console actions take: seller, shop and product approval, and
   product publishing. Today only Administrators (and Super Administrators)
   hold them all. The separate Console actions still work too. In the
   Console, the Onboarding page (`/admin/onboarding`, shown only to those
   reviewers) lists the queue; each row and each detail page has Approve all
   and Reject.
5. **Rejection.** Rejecting an onboarded seller, by any path, first refunds
   its products' creation fees (none ever went live). It then returns up to
   the starting points it was given to the onboarder, and takes back the
   onboarder's tokens. This happens once per onboarding. Points the seller
   got from anyone else stay with the seller.

## Point validity and listing periods (decided 2026-11-01)

New feature work, outside the fixes-only roadmap. The rules, edge cases and
tasks are in `docs/LISTING_VALIDITY_PLAN.md`. In short: a seller's points
last 30 days and each purchase adds 30 days to all of them; a product is live
4 months, then the seller renews it for 5 points, 2 months at a time, and
cannot take it down while it is live. Three choices the user made:

1. **Buying points.** The seller pays staff outside the system and the staff
   member gives the points (at least 100) from their own wallet. There is no
   payment gateway and no request flow.
2. **Who sells.** Administrators and Finance sell to any seller, as before.
   A Sales Team member sells only to the sellers they onboarded.
3. **Full Shop Owners are exempt from both.** Their points never expire and
   their products have no end date. The 100-point minimum applies to
   everyone.

## Business rules in one place (decided 2026-11-01)

New feature work, outside the fixes-only roadmap; the plan is
`docs/BUSINESS_RULES_PLAN.md`. Every value the platform runs on (product
cost, listing periods, point validity, the minimum sale, onboarding points
and tokens, the product limit, the low-stock threshold) is listed in
`backend/rules/registry.py`. It changes only on the Console Rules page
(`/admin/rules`), with a reason, an audit row per rule and checks between
rules. `docs/BUSINESS_RULES.md` is generated from the registry. The user
chose a page over a config file, so a change needs no deploy. Viewing is for
Administrators, Finance and Operation Managers; changing is for
Administrators.

## Follow-ups to listing validity and the Rules page (decided 2026-11-01)

The plan is `docs/FOLLOW_UPS_PLAN.md`. The user answered the five open
points:

1. **Deleting.** A seller deletes their own expired product with no RBAC
   code, which frees its place under the product limit. Nothing is refunded,
   and units held for open orders block the delete.
2. **Renewing early, and notices.** A live product can be renewed at any time;
   the months go on after its current end date. The seller gets a
   `listing.ending_soon` notice when a product enters the ending-soon window
   and a `listing.expired` notice when it expires, in-app and email, once per
   product per period.
3. **Cron.** `deploy/cron/` holds the crontab, a wrapper script and a README,
   to install on the server later.
4. **Support limits** (open tickets per person, auto-close days) moved to
   `support.SupportPolicy` and the Rules page.
5. **Sales Team point sales.** The Console page `/admin/my-sellers` lists an
   onboarder's sellers and sells them points.

## Sales Team edits, token payouts and product visibility (decided 2026-11-01)

The plan is `docs/SALES_TEAM_EDITS_PAYOUTS_PLAN.md`, done before the Android
app so the app can be built on this API. The user decided:

1. **Edits with the seller's code.** An onboarder corrects the seller, its
   shops and the products they added only inside an edit session. A 6-digit
   code goes to the seller's account; once the onboarder enters it, they can
   edit for 30 minutes (Rules page: code 10 minutes, window 30). The seller
   type and the login account stay with the seller.
2. **Token payouts.** An onboarder hands tokens to an admin with a request for
   real payment. Accepting moves the tokens to that admin; rejecting or
   cancelling gives them back. 1 token = ৳1 (Rules page "Token value").
3. **Products.** The Sales Team sees only the products it added, through the
   new `onboarding.products.view`, which an admin can turn off for the whole
   team (Roles) or for one person (Users → Turn off). It lost `products.view`
   and `inventory.*`.
4. **Starting password.** An onboarded seller chooses their own password at
   first sign-in, since the onboarder set the first one; later changes go
   through Settings.

Follow-ups the user asked for on 2026-11-02: Administrators hold the Sales
Team's codes (`rbac/0009`), so they can change a Sales Team member's roles or
deactivate them in the Console (and can onboard sellers themselves); and the
Console product edit can replace the photo.

## Not in this roadmap

A short honest roadmap beats an exhaustive wish list. These are known and
deliberately excluded — with reasons, so nobody re-discovers them as new.

**Recorded as preconditions on a future spec, not as phases:**
- **#18** — `Payment.metadata` / `Refund.metadata` are serialized verbatim with no
  allowlist (`shop/serializers.py:752`) and rendered as raw JSON in the payments
  detail page. Harmless today: a repo-wide grep finds no caller that ever passes
  `metadata=`, so it is always `{}`. **Any future payment-gateway integration spec
  must add redaction before writing to this field.**
- **#19** — `RefundCreateSerializer.amount` has no upper bound at the serializer
  layer; the real ceiling is enforced in `PaymentService.process_refund:300-303`.
  Same condition applies: any new refund caller that bypasses the service needs its
  own boundary check.

**Deferred pending a fetch-error / demo-fallback policy decision:**
- **Follow-up — Fetch Error Propagation / Demo Fallback Policy.** Phase 2K
  (above) built route-level `error.tsx`/`loading.tsx`/`not-found.tsx` boundaries
  but, by design, left `frontend/src/lib/api.ts` untouched — and that module
  already converts most public-read fetch failures into demo data or `null`
  before those boundaries can ever see them. Closing that gap is a page-by-page
  product decision, not mechanical boilerplate: for each of `getCategories`,
  `getProducts`, `getProductDetail`, `getProductById`, `getHotDeal`,
  `getShopDetail`, `getShops`, `getOrderDetail`, decide whether a network failure
  should (a) keep the demo fallback — an intentional offline/dev-mode experience
  for the public catalogue, (b) surface a local inline error state (the pattern
  `admin/products/page.tsx` already uses), or (c) propagate to the route's
  `error.tsx` (needs a targeted `api.ts` change plus the calling page's
  `useEffect`). Candidate files if approved: the eight `api.ts` functions above,
  `frontend/src/app/page.tsx`, `product/[slug]/page.tsx`, `shop/[slug]/page.tsx`,
  `shops/page.tsx`. Separately, authenticated dashboard pages that fetch through
  `Promise.allSettled` (e.g. `seller/page.tsx`) currently discard a partial-fetch
  failure with no error state at all, local or route-level, and may need its own
  pass under the same policy. Not scheduled as a numbered phase until that policy
  decision is made.
- **#17** — `/admin/orders` list merges only `{id, status}` after an action, so
  `payment_status` goes stale until refetch. Fold into whoever next touches that page.
- Accessibility sweep — roughly 250 decorative Material Symbols glyphs without
  `aria-hidden`, plus unlabeled icon-only buttons on the seller sidebar. Admin
  surfaces are already markedly better than storefront and seller ones. One late
  mechanical pass.
- Missing pagination on `/admin/roles` (#13), `/seller/orders`, `/seller/shops`,
  `/seller/wallet`; `/seller/products` hand-rolls Previous/Next instead of reusing
  the shared `AdminPagination`.
- **#21** — `StaffRefundListAPIView` supports zero query filters. Nothing consumes
  it yet.

**Dropped:**
- Wiring the checkout payment-method radio (`checkout/page.tsx:499-515`) — binding
  state to a single `defaultChecked` COD option is theatre until a second payment
  method exists.
- Frontend component and E2E tests — headless Chromium does not hydrate this app in
  this environment, so browser automation is not a realistic gate. `tsc --noEmit` in
  CI (Phase 2B) is the practical frontend check. If unit tests are wanted later,
  scope them to pure logic (`admin-auth.ts`, the token accessor) only.

**Never-built features, out of scope for this roadmap** (all listed in §17 of the
review cache): logout / token revocation, password reset, guest-cart merge on login,
guest order-lookup API, seller product submission, seller-facing inventory page,
support ticketing, reports and analytics, notifications.

**Exceptions: built anyway, because the owner asked.** Three items on that list now
exist. Each was the owner's explicit request, not a change to this roadmap's rule:

- **Support ticketing** (2026-09-24/25): plan and task log in `docs/SUPPORT_SYSTEM.md`.
- **Guest-cart merge on login** (2026-09-25): on login, the localStorage cart is merged
  into the account cart (`frontend/src/context/CartContext.tsx`).
- **Notifications** (2026-09-29): an in-app inbox with a bell on all three surfaces,
  email for selected events, per-category email preferences, and a MySQL outbox with a
  worker. The plan, decisions D1–D11, the runbook and a per-task log are in
  `docs/NOTIFICATION_SYSTEM.md`.

Of these, **logout / token revocation** is the one worth promoting first when
feature work resumes — Phase 2J makes its absence more visible, not less.

**"Refunds do not restore inventory" is a product policy decision, not a bug.** It
should not be roadmapped until someone decides what the policy ought to be.

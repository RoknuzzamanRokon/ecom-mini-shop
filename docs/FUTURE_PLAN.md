# MiniShop — Future Plan

**Created:** 2026-09-18 · **Baseline commit:** `fe347ef` · **Status:** Phase 2A done (2026-09-18); everything after it still proposed

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
| **No `LOGGING` config at all** — while 8 non-test modules call `logging.getLogger` | `audit/services.py`, `cart/services.py`, `customers/services.py`, `points/services.py`, `shop/{admin_views,inventory_service,payment_service,services}.py` |
| No `SECURE_*` / HSTS / secure-cookie settings | absent from `config/settings.py` |
| `.env` hand-parsed, no `python-dotenv` | `config/settings.py` |
| Stale `backend/db.sqlite3` tracked, though settings require MySQL | repo root of `backend/` |
| JWTs in `localStorage`, no revocation on logout | `frontend/src/context/AuthContext.tsx` |

---

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

**Deferred as cosmetic or mechanical:**
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

Of these, **logout / token revocation** is the one worth promoting first when
feature work resumes — Phase 2J makes its absence more visible, not less.

**"Refunds do not restore inventory" is a product policy decision, not a bug.** It
should not be roadmapped until someone decides what the policy ought to be.

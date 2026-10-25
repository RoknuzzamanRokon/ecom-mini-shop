# MiniShop — Bug Audit Report

| | |
|---|---|
| Audit date | 2026-10-22 |
| Commit audited | `ebd71c5` on `master`; working tree clean at the start |
| Method | Static, read-only. No code changes, no servers, no tests against a database, no HTTP requests, no dependency installs. |
| Companion file | [`BUG_FIX_TASKS.md`](BUG_FIX_TASKS.md) — the prioritized task list built from this register |

**How to read the register**

- **Severity** follows the anchors in the audit brief: P0 Critical, P1 High, P2 Medium, P3 Low. P4 (maintenance) items are in §5 and are not counted as bugs.
- **Status**:
  - *Confirmed* means the defect is visible in source and the path was traced.
  - *Probable* means the defect depends on runtime data, configuration or library behaviour.
  - *Unverified* means the code path is suspected but not traced; it becomes an investigation task.
- **Verified** says who traced the code:
  - `C` means the audit coordinator re-read the cited lines.
  - `A` means a slice auditor traced the path. About 170 cited line references were printed from the files during consolidation. The four that did not match were replaced with verified lines or marked `approximate`.
- Nothing in this report was executed at runtime. Every finding comes from static analysis.
- Secrets, credentials, hostnames and personal data are never reproduced. Only path, variable and risk class are given.

---

## 1. Executive summary

MiniShop has two deployables:

- **Backend:** a Django 5.2 / DRF / SimpleJWT API on MySQL 8 (`backend/`, 12 apps).
- **Frontend:** a Next.js 16 / React 19 app (`frontend/`) serving the storefront, Seller Center and Management Console.

All 651 tracked files were in scope except 92 media uploads and the npm lockfile. The audit used static reading, Django checks, `tsc` and ESLint.

**Findings: 100 bugs.** P0 0, P1 11, P2 26, P3 63. 88 Confirmed, 11 Probable, 1 Unverified. P4 items are listed separately and not counted.

**Main risks**

- **Authorization.**
  - The committed `SECRET_KEY` also signs JWTs, and there are no production settings (BUG-001).
  - Staff with ordinary Django-admin permissions can escalate to the RBAC wildcard (BUG-002).
  - Console user managers can assign roles above their own permissions (BUG-003).
  - The role sellers need to create products also opens the staff seller directory (BUG-004).
- **Money and stock.**
  - Seller cancellation never refunds (BUG-005).
  - Order status is editable raw in the Django admin (BUG-006).
  - Delivery can consume other orders' reservations (BUG-007).
  - Seller product edits overwrite live stock (BUG-008).
  - The cart can show a different total from the one ordered (BUG-010).
- **Broken workflows.**
  - Sellers cannot see shipping addresses (BUG-009).
  - New products cannot be published through any UI (BUG-011).

**Not inspected or not tested**

- The backend test suite (it writes databases on the MySQL server).
- `npm run build` (it overwrites `.next`).
- Database contents (Known Issue #30).
- MySQL locking behaviour.
- The render-only parts of some pages and templates, which were scanned with grep only (§7).

---

## 2. Repository and architecture overview

### 2.1 Scope (Phase 0)

| Item | Value |
|---|---|
| `git status --porcelain=v1` at start | *(empty — clean tree)* |
| Tracked files | 651 (`git ls-files \| wc -l`) |
| Deployables (M = 2) | `backend/` (Django; `backend/requirements.txt`) and `frontend/` (Next.js; `frontend/package.json`). There is no Dockerfile, compose file, Procfile or reverse-proxy config in the repo. |
| Excluded (K = 5 directories + 1 file) | `backend/media/` (92 tracked binary uploads), plus the untracked `frontend/node_modules/`, `frontend/.next/`, `backend/venv/` and `__pycache__/`; the file `frontend/package-lock.json` |
| Read for context only | `docs/`, `task/`, `report.md`, `GEMINI.md`, `forAdminPanel/` (requirements, prior review cache, prompt-injection scan) |
| Source in scope | About 250 backend Python modules (about 60 of them test modules), 25 Django templates, 4 admin JS files, and about 180 frontend TS/TSX files |

### 2.2 Layers and evidence

| Layer | What it is | Evidence |
|---|---|---|
| Frontend entry | Next.js 16.3.4 App Router, React 19.2.8, Tailwind 4. Three surfaces: storefront `/`, Seller Center `/seller`, Management Console `/admin`. | `frontend/package.json:15-16`, `frontend/src/app/layout.tsx`, `frontend/src/app/seller/layout.tsx`, `frontend/src/app/admin/layout.tsx` |
| Frontend → API | Browser calls Django directly at `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8001`). `/media/*` is rewritten to the backend. Tokens are kept in `localStorage`. | `frontend/src/lib/api.ts:5-6`, `frontend/src/lib/admin-api.ts:12`, `frontend/next.config.ts:37-45`, `frontend/src/lib/auth.ts` |
| Backend entry | Django 5.2.17, DRF 3.18.1, SimpleJWT 5.5.1. URLconf mounts `rbac`, `sellers`, `points`, `shops`, `cart`, `support`, `notifications`, `customers` and `shop`. | `backend/config/urls.py:26-37`, `backend/config/settings/base.py:51-71`, `backend/requirements.txt` |
| Settings | `base` / `dev` / `test`. **No production module.** `wsgi.py` / `asgi.py` / `manage.py` default to `dev` (DEBUG=True). | `backend/config/settings/__init__.py`, `dev.py:12`, `config/wsgi.py:14`, `config/asgi.py:14` |
| AuthN | JWT (access 60 min, refresh 7 days, rotation on, no blacklist) plus Session auth. | `backend/config/settings/base.py:207-223` |
| AuthZ | Custom RBAC: Role, Permission, UserRole and UserPermission. Permissions are resolved by role code, with a `*` wildcard. Roles and permissions are seeded by `seed_rbac`. | `backend/rbac/services.py:25-83`, `backend/rbac/management/commands/seed_rbac.py:145-230` |
| Database | MySQL 8 only (enforced). Strict mode. Default READ COMMITTED isolation. Spatial `POINT` field for shops. | `backend/config/settings/base.py:107-148`, `:133`, `backend/shops/fields.py:90-164` |
| Domain apps | `shop` (catalog, orders, payments, refunds, inventory, invoices, staff Console API), `cart`, `customers` (profile, addresses, favorites, reviews), `sellers`, `shops` (including nearby search), `points` (wallet ledger with expiring lots), `support` (tickets, private attachments), `notifications` (outbox, worker, email), `audit`, `rbac` | `backend/shop/admin_views.py`, `backend/shop/services.py`, `backend/points/services.py`, `backend/support/services.py`, `backend/notifications/worker.py` |
| File storage | Public uploads in `MEDIA_ROOT`, served by Django only when DEBUG. Support attachments in `PRIVATE_MEDIA_ROOT`, outside `MEDIA_ROOT`, served by authenticated views. | `backend/config/settings/base.py:180-187`, `backend/support/storage.py`, `backend/support/views.py:75` |
| Integrations | SMTP email (notifications channel). OpenStreetMap tiles (map). Google Fonts. Image downloads in the seed commands. An IP geolocation dev script. | `backend/notifications/channels/email.py`, `base.py:232-240`, `frontend/src/components/shops/NearbyShopsMap.tsx:23`, `frontend/src/app/layout.tsx:26-30`, `backend/shop/management/commands/seed_showcase.py:17-18`, `backend/tools/my_location.py` |
| Background jobs | Management commands only, with no scheduler config in the repo: `run_notification_worker`, `purge_notifications`, `notification_health`, `expire_points`, `close_resolved_tickets`. | `backend/notifications/management/commands/`, `backend/points/management/commands/expire_points.py`, `backend/support/management/commands/close_resolved_tickets.py` |
| CI | GitHub Actions: Django checks plus the backend suite on a MySQL 8 service; frontend `typecheck` plus `build`. No deploy. | `.github/workflows/ci.yml:82-96` |
| Tests | About 60 backend test modules (Django `TestCase` on MySQL). **The frontend has no test runner or tests.** | `git ls-files backend \| grep test`, `frontend/package.json:5-11` |

---

## 3. Detailed bug register

### 3.1 Index

`Ver` = verified by the coordinator (C) or by a slice auditor (A). `Task` = the task in `BUG_FIX_TASKS.md`.

| ID | Title | Sev | Conf | Status | Area | Ver | Task |
|---|---|---|---|---|---|---|---|
| BUG-001 | Committed SECRET_KEY doubles as JWT signing key; DEBUG on; no prod settings | P1 | High | Confirmed | Config/Security | C | TASK-001 |
| BUG-002 | Django-admin RBAC surfaces allow escalation to the `*` wildcard | P1 | High | Confirmed | Security | C | TASK-003 |
| BUG-003 | Console user API assigns roles beyond the actor's own permissions; can lock out administrators | P1 | High | Confirmed | Security | C | TASK-004 |
| BUG-004 | SALES_TEAM (the seller product role) opens the staff seller directory and product list | P1 | Medium | Probable | Security | C | TASK-005 |
| BUG-005 | Seller cancellation never cancels or refunds the payment | P1 | High | Confirmed | Orders/Payments | C | TASK-007 |
| BUG-006 | Django admin Order form edits `status` raw, bypassing OrderService | P1 | High | Confirmed | Integrity | C | TASK-006 |
| BUG-007 | Delivery (SALE) not bounded by the order's own reservation (Known #29) | P1 | High | Confirmed | Inventory | C | TASK-008 |
| BUG-008 | Seller product edit re-sends stale absolute stock (lost update) | P1 | High | Confirmed | Inventory/Frontend | C | TASK-011 |
| BUG-009 | Seller order "View Details" shows a blank delivery address | P1 | High | Confirmed | Seller UI | C | TASK-012 |
| BUG-010 | Cart applies failed server mutations locally; shown total ≠ ordered cart | P1 | High | Confirmed | Storefront | C | TASK-013 |
| BUG-011 | New products can never be published through a UI (DRAFT dead end) | P1 | High | Confirmed | Catalog workflow | C | TASK-014 |
| BUG-012 | Checkout never creates a Payment record (COD orders unpaid forever) | P2 | High | Confirmed | Payments | C | TASK-015 |
| BUG-013 | Refresh tokens renew indefinitely and survive logout and password change | P2 | High | Confirmed | Security | C | TASK-002 |
| BUG-014 | No rate limiting on auth endpoints; 4-character minimum password | P2 | High | Confirmed | Security | C | TASK-002 |
| BUG-015 | Audit IP taken from client X-Forwarded-For; long values drop audit rows | P2 | High | Confirmed | Security/Audit | C | TASK-009 |
| BUG-016 | Saving any existing shop in the Django admin returns 500 | P2 | High | Confirmed | Admin | C | TASK-019 |
| BUG-017 | Seller lifecycle transitions have no source-state guards (approve lifts a suspension) | P2 | High | Confirmed | Security/Workflow | C | TASK-016 |
| BUG-018 | Suspended or rejected seller's shops stay publicly listed | P2 | Medium | Confirmed | Catalog | C | TASK-020 |
| BUG-019 | Invoice PDF interprets user text as ReportLab markup | P2 | High | Confirmed | Security/Invoices | C | TASK-010 |
| BUG-020 | Invoice "Balance due" wrong for cancelled and refunded orders | P2 | High | Confirmed | Invoices | C | TASK-010 |
| BUG-021 | Django ProductAdmin/ProductInventoryAdmin edit stock, status and counters directly | P2 | High | Confirmed | Integrity | C | TASK-006 |
| BUG-022 | N+1 queries on staff order/payment lists, customer orders and cart | P2 | High | Confirmed | Performance | C | TASK-027 |
| BUG-023 | Checkout `select_for_update` also locks Category/Shop/Seller rows | P2 | Medium | Probable | Performance/DB | A | TASK-027 |
| BUG-024 | Frontend assumes 10 per page; backend serves 12 (phantom page, then 404) | P2 | High | Confirmed | Integration | C | TASK-021 |
| BUG-025 | Seller Orders page cannot paginate; search only filters the first 12 | P2 | High | Confirmed | Seller UI | C | TASK-021 |
| BUG-026 | Lists silently truncated to the first page (wallet history, seller shops, current orders) | P2 | High | Confirmed | Integration | C | TASK-021 |
| BUG-027 | "Add product" offered for shops that are not yet approved; refusal shown as a generic error | P2 | High | Confirmed | Seller UI | C | TASK-023 |
| BUG-028 | API clients drop DRF error bodies or show raw JSON | P2 | High | Confirmed | Integration | C | TASK-022 |
| BUG-029 | Seller status modal offers invalid transitions; PENDING orders send PENDING | P2 | High | Confirmed | Seller UI | C | TASK-022 |
| BUG-030 | SellerGuard swallows non-404 failures; portal shows "Not Operational" | P2 | High | Confirmed | Seller UI | A | TASK-023 |
| BUG-031 | A transient network or 5xx error during session restore or refresh logs the user out | P2 | High | Confirmed | Auth/Frontend | C | TASK-024 |
| BUG-032 | Category links off the home page do nothing (home ignores `?category=`) | P2 | High | Confirmed | Storefront | C | TASK-025 |
| BUG-033 | Header search is a no-op on most pages and absent on phones | P2 | High | Confirmed | Storefront | C | TASK-025 |
| BUG-034 | Checkout still shows the retired guest-checkout form; submit always fails | P2 | High | Confirmed | Storefront | C | TASK-017 |
| BUG-035 | Demo-data fallback leaks into real flows (cart ids, shop pages, false 404s) | P2 | Medium | Probable | Storefront | A | TASK-026 |
| BUG-036 | Console refund reported as failed when the refetch fails; modal stays armed | P2 | Medium | Confirmed | Console/Payments | C | TASK-018 |
| BUG-037 | Dark-mode storefront header icons and text near-invisible (Known #34) | P2 | High | Confirmed | Storefront UI | A | TASK-028 |
| BUG-038 | Django admin dashboard shows revenue to every staff account | P3 | High | Confirmed | Security | C | TASK-030 |
| BUG-039 | Saving a user's change form deactivates their locked direct grants | P3 | High | Confirmed | RBAC | C | TASK-003 |
| BUG-040 | Registration and Console account creation skip Django's username validator | P3 | High | Confirmed | Validation | C | TASK-031 |
| BUG-041 | Deleting a user erases the actor on all their audit rows | P3 | High | Confirmed | Audit | C | TASK-009 |
| BUG-042 | `nav_sidebar.js` throws on every Django admin page (Known #36) | P3 | High | Confirmed | Admin UI | A | TASK-030 |
| BUG-043 | User uploads, including customer avatars, are committed to git; ignore rules ineffective | P3 | High | Confirmed | Config/Privacy | C | TASK-032 |
| BUG-044 | Seller shop update: PUT or null coordinates give 500; response shows stale data | P3 | High | Confirmed | Shops API | C | TASK-033 |
| BUG-045 | `IsShopOwner` lets `shops.update` staff through; views then 500 | P3 | High | Confirmed | Shops API | C | TASK-033 |
| BUG-046 | Django admin seller/shop/product edits bypass tier caps, product cost and audit | P3 | Medium | Confirmed | Integrity | C | TASK-006 |
| BUG-047 | Clearing `is_superuser` makes the user's held points expire at once | P3 | Medium | Confirmed | Points | A | TASK-034 |
| BUG-048 | Staff can renew point expiry by bouncing points through a seller wallet | P3 | Medium | Probable | Points | A | TASK-034 |
| BUG-049 | `/api/shops/staff/*` status endpoints write no AuditLog and take no lock | P3 | High | Confirmed | Audit | C | TASK-009 |
| BUG-050 | Console seller status view lets Django ValidationError escape (500) | P3 | High | Confirmed | Console API | C | TASK-016 |
| BUG-051 | Payment `failure_reason` / `metadata` never persisted | P3 | High | Confirmed | Payments | C | TASK-035 |
| BUG-052 | A second full-amount payment can be started after a refund | P3 | Medium | Confirmed | Payments | C | TASK-015 |
| BUG-053 | Orders accepted with blank or placeholder shipping addresses | P3 | High | Confirmed | Orders | A | TASK-017 |
| BUG-054 | Read-only `orders.staff.view` can create or modify payments on any order | P3 | High | Confirmed | Security | C | TASK-035 |
| BUG-055 | Seller order payloads expose the whole-order total and customer names | P3 | High | Confirmed | Data exposure | C | TASK-012 |
| BUG-056 | Staff cancel: the view and the service use different staff rules (SUPPORT_TEAM gets 403) | P3 | High | Confirmed | Orders | C | TASK-035 |
| BUG-057 | Only one partial refund per payment (Known #26) | P3 | High | Confirmed | Payments | C | TASK-035 |
| BUG-058 | Inconsistent lock ordering leads to deadlocks surfacing as 500 | P3 | Medium | Probable | DB/Concurrency | A | TASK-029 |
| BUG-059 | Check-then-insert races return 500 (address default, first cart add, shop slug) | P3 | High | Confirmed | DB/Concurrency | C | TASK-029 |
| BUG-060 | Upload and profile validation gaps (avatar API, product and shop images unbounded) | P3 | High | Confirmed | Validation/Security | C | TASK-031 |
| BUG-061 | Favorites always report rating 0 (Known #7) | P3 | High | Confirmed | Customers | A | TASK-036 |
| BUG-062 | Support public status lines use staff wording (Known #33) | P3 | High | Confirmed | Support | C | TASK-036 |
| BUG-063 | Support attachments reject multi-picture (MPO) JPEGs | P3 | Medium | Probable | Support | A | TASK-036 |
| BUG-064 | Notification preferences PUT gives 500 on malformed or concurrent input | P3 | High | Confirmed | Notifications | A | TASK-036 |
| BUG-065 | Email delivered twice when an SMTP send outlasts the 60 s lease | P3 | Medium | Probable | Notifications | A | TASK-036 |
| BUG-066 | Unvalidated inputs raise 500 instead of 400; audit dates bucket by UTC | P3 | High | Confirmed | API | C | TASK-031 |
| BUG-067 | N+1 queries in Console list serializers | P3 | High | Confirmed | Performance | A | TASK-027 |
| BUG-068 | Seed commands mutate non-demo rows with no environment guard | P3 | High | Confirmed | Tooling/Integrity | C | TASK-037 |
| BUG-069 | Product PATCH accepts `category_id` / `shop_id` but ignores them | P3 | High | Confirmed | Seller API | C | TASK-023 |
| BUG-070 | Multipart product edit cannot clear `old_price` | P3 | High | Confirmed | Seller UI | C | TASK-023 |
| BUG-071 | Seller products page claims "no shop assigned" when the call failed; demo categories used | P3 | High | Confirmed | Seller UI | C | TASK-023 |
| BUG-072 | `refreshDashboard()` unmounts the whole Seller Center | P3 | High | Confirmed | Seller UI | A | TASK-023 |
| BUG-073 | List pages accept stale, out-of-order responses | P3 | High | Confirmed | Frontend | A | TASK-038 |
| BUG-074 | Console debounced search drops filters changed within 350 ms | P3 | High | Confirmed | Console UI | C | TASK-038 |
| BUG-075 | Console seller points-history refresh races after an adjustment | P3 | High | Confirmed | Console UI | C | TASK-038 |
| BUG-076 | Console refund: blank or unparseable amount becomes a full refund | P3 | Medium | Probable | Console/Payments | C | TASK-018 |
| BUG-077 | Category deactivation is one click with no confirmation | P3 | High | Confirmed | Console UI | C | TASK-039 |
| BUG-078 | Shop edit "Use current location" writes a stale form snapshot | P3 | High | Confirmed | Console UI | C | TASK-039 |
| BUG-079 | Out-of-range `?page=` leaves a dead-end error with no pager | P3 | Medium | Probable | Console UI | A | TASK-021 |
| BUG-080 | Seller points-history filter cannot select EXPIRY | P3 | High | Confirmed | Console UI | A | TASK-039 |
| BUG-081 | "View this seller's shops" uses a substring search (lists other sellers' shops) | P3 | High | Confirmed | Console UI | C | TASK-039 |
| BUG-082 | Catch-all admin route shows "Awaiting Implementation" instead of 404 | P3 | High | Confirmed | Console UI | C | TASK-039 |
| BUG-083 | Dashboard shows a 403 banner and fake "0"/"৳0.00" KPIs without `reports.view` (Known #28) | P3 | High | Confirmed | Console UI | C | TASK-039 |
| BUG-084 | Guest-cart merge clears the saved cart even when every POST failed | P3 | High | Confirmed | Storefront | C | TASK-013 |
| BUG-085 | Hot Deals widget invents "49% OFF" and a 120-day countdown | P3 | High | Confirmed | Storefront | C | TASK-040 |
| BUG-086 | Profile Settings can save blanks over real data; avatar upload wipes edits | P3 | Medium | Probable | Storefront | C | TASK-040 |
| BUG-087 | Buy Now: not awaited, drawer opens over checkout, empty-cart flash, unbounded stepper | P3 | High | Confirmed | Storefront | C | TASK-013 |
| BUG-088 | Checkout retries save duplicate addresses; unavailable items not blocked | P3 | High | Confirmed | Storefront | A | TASK-017 |
| BUG-089 | Order-success page says "Order Confirmed" for any order number | P3 | High | Confirmed | Storefront | C | TASK-040 |
| BUG-090 | Profile pages show empty states when loading actually failed | P3 | High | Confirmed | Storefront | C | TASK-040 |
| BUG-091 | Review delete: no confirmation, and a failure is invisible | P3 | High | Confirmed | Storefront | C | TASK-040 |
| BUG-092 | Login leaves tokens stored if `/auth/me` fails (half-logged-in state) | P3 | Medium | Confirmed | Auth/Frontend | C | TASK-024 |
| BUG-093 | Route params interpolated into API paths without encoding | P3 | Low | Not reproducible (TASK-045); encoded anyway | Frontend/Security | C | TASK-045 |
| BUG-094 | Accessibility gaps in dialogs, menus and the off-screen sidebar | P3 | High | Confirmed | Accessibility | C | TASK-041 |
| BUG-095 | Material Symbols ignore Tailwind size classes (Known #35) | P3 | High | Confirmed | Frontend UI | A | TASK-028 |
| BUG-096 | Seller Center minor UI defects (status dot, labels, counts) | P3 | High | Confirmed | Seller UI | C | TASK-023 |
| BUG-097 | Console empty state in Bengali on an English UI | P3 | High | Confirmed | Console UI | C | TASK-039 |
| BUG-098 | Date-only values (customer DOB) shift a day for viewers west of UTC | P3 | Low | Probable | Console UI | C | TASK-039 |
| BUG-099 | Header/Navbar sticky rule broken on product/shop loading, error and 404 states | P3 | High | Confirmed | Storefront UI | A | TASK-028 |
| BUG-100 | Console orders list merges only `{id,status}` after an action (Known #17) | P3 | High | Confirmed | Console UI | C | TASK-039 |
| BUG-101 | Console role API can reactivate a role whose permissions the actor does not hold | P2 | High | Confirmed | Security | C | TASK-049 |
| BUG-102 | Support status confirm dialog closes on a refresh and reopens on its own later | P3 | High | Confirmed | Console UI | C | TASK-049 |
| BUG-103 | Support status dialog quotes the staff label, not the customer's wording | P3 | High | Confirmed | Console UI | C | TASK-049 |
| BUG-104 | Support assignee list: a failed load looks empty and “Assign to me” announces “Unassigned” | P3 | Medium | Confirmed | Console UI | C | TASK-049 |
| BUG-105 | New category: every name edit overwrites a slug the operator typed | P3 | High | Confirmed | Console UI | C | TASK-049 |
| BUG-106 | Category detail edit deactivates without the confirmation the list requires | P3 | High | Confirmed | Console UI | C | TASK-049 |
| BUG-107 | Category PATCH audit rows do not record slug, icon or description changes | P3 | High | Confirmed | Backend audit | C | TASK-049 |
| BUG-108 | Category delete counts products outside a lock, then deletes with CASCADE | P3 | Medium | Confirmed | Backend | C | TASK-049 |
| BUG-109 | Support ticket writes can be applied out of order | P3 | Low | Probable | Console UI | A | TASK-049 |
| BUG-110 | `dark:` utilities follow the OS preference, not the app's dark mode | P3 | High | Confirmed | Storefront UI | C | TASK-049 |
| BUG-111 | Dark themes do not set `color-scheme: dark` | P3 | Medium | Confirmed | Storefront UI | C | TASK-049 |
| BUG-112 | Console profile hides a failed profile load and offers an edit link that cannot work | P3 | High | Confirmed | Console UI | C | TASK-049 |
| BUG-113 | Console profile wallet figures omit expired points | P3 | High | Confirmed | Console UI | C | TASK-049 |
| BUG-114 | “No points yet” shown for any zero balance, even after activity | P3 | Medium | Confirmed | Console UI | C | TASK-049 |
| BUG-115 | Console customer directory lists staff and superuser accounts | P3 | Medium | Confirmed | Backend/Console | C | TASK-049 |
| BUG-116 | Customer search placeholder promises name search the backend does not do | P3 | Medium | Confirmed | Console UI | C | TASK-049 |
| BUG-117 | Debounced Console search can drop a keystroke typed while the URL updates | P3 | Low | Probable | Console UI | A | TASK-049 |
| BUG-118 | A negative or fractional ?page= leaves the Console customers list stuck on an error | P3 | High | Confirmed | Console UI | A | TASK-049 |
| BUG-119 | Demo category counts contradict the demo products | P3 | High | Confirmed | Storefront (demo only) | A | TASK-049 |
| BUG-120 | Django admin direct-grant board: the filter blanks every section until reload | P3 | High | Confirmed | Django admin UI | C | TASK-049 |
| BUG-121 | Django admin direct-grant board: counters rewritten to direct grants only on load | P3 | High | Confirmed | Django admin UI | C | TASK-049 |
| BUG-122 | Django admin direct-grant board: Enter in the filter saves the form for full-access accounts | P3 | High | Confirmed | Django admin UI | C | TASK-049 |
| BUG-123 | Role permission board: section and Select-all boxes cannot clear when locked rows are unticked | P3 | High | Confirmed | Django admin UI | A | TASK-049 |
| BUG-124 | Locked grants show as not granted after a validation error re-render | P3 | High | Confirmed | Django admin UI | A | TASK-049 |
| BUG-125 | User change form hero gauge shows 0 / 0 to non-superuser operators | P3 | High | Confirmed | Django admin UI | A | TASK-049 |
| BUG-126 | Deactivated roles shown as active on the user change form | P3 | High | Confirmed | Django admin UI | C | TASK-049 |
| BUG-127 | Access-board copy contradicts what the boards do | P3 | High | Confirmed | Django admin UI | A | TASK-049 |
| BUG-128 | Saved role cards keep a hidden but focusable role select | P3 | Medium | Confirmed | Django admin UI | A | TASK-049 |
| BUG-129 | Wide permission-matrix checkboxes have no readable accessible name | P3 | Low | Probable | Django admin UI | A | TASK-049 |
| BUG-130 | Django admin dashboard shows create links without add permission | P3 | High | Confirmed | Django admin UI | A | TASK-049 |
| BUG-131 | Admin templates: external-link hint on a non-link; panes unreachable without JavaScript | P3 | High | Confirmed | Django admin UI | A | TASK-049 |

Counts: P1 11 · P2 26 · P3 63. Confirmed 88 · Probable 11 · Unverified 1.

### 3.2 P1 — High

```yaml
- id: BUG-001
  title: Committed SECRET_KEY doubles as the JWT signing key; DEBUG on by default; no production settings
  severity: P1   # becomes P0 the moment any instance is reachable by anyone other than the developer
  confidence: High
  status: Confirmed
  category: [E Security, H Config]
  verified: C
  location:
    - backend/config/settings/base.py:44            # SECRET_KEY literal (value not reproduced)
    - backend/config/settings/base.py:217-223       # SIMPLE_JWT sets no SIGNING_KEY
    - backend/config/settings/base.py:154-159       # only MinimumLengthValidator, min_length 4
    - backend/config/settings/dev.py:12             # DEBUG = True
    - backend/config/wsgi.py:14                     # defaults to config.settings.dev
    - backend/config/asgi.py:14
    - backend/config/urls.py:39-40                  # media served whenever DEBUG
    - backend/venv/.../rest_framework_simplejwt/settings.py:20  # "SIGNING_KEY": settings.SECRET_KEY
  symbol: settings module; SimpleJWT defaults
  explanation: >
    The only secret key is a literal in a tracked file, and git history keeps it permanently.
    SimpleJWT signs HS256 tokens with SECRET_KEY by default, so anyone with repository read access
    can mint a valid access token for any user_id, superusers included. There is no production
    settings module, and wsgi/asgi default to dev. Any deployment therefore runs with DEBUG=True
    (technical 500 pages, public media) and with the committed key.
  repro: "`manage.py check --deploy` reports security.W004, W008, W009 (SECRET_KEY), W012, W016 and W018 (DEBUG); see §6. No token was forged."
  expected: The secret comes from the environment and is rotated; a production module sets DEBUG off, secure cookies and HSTS.
  actual: One committed key for every environment; DEBUG on wherever wsgi.py is used.
  impact: Full API authentication bypass on any shared or deployed instance, plus information disclosure through debug pages.
  fix: >
    - Read SECRET_KEY, and a separate SIMPLE_JWT["SIGNING_KEY"], from the environment and refuse to start without them outside dev.
    - Rotate the key.
    - Add config/settings/prod.py with DEBUG False, HSTS, secure session/CSRF cookies, CSRF_TRUSTED_ORIGINS, a CORS allow-list from the environment and the full Django password validators.
    - Make wsgi/asgi require an explicit DJANGO_SETTINGS_MODULE.
  regression_test: A settings test asserting the prod module's values; a CI step running `check --deploy --fail-level WARNING --settings=config.settings.prod`.
  effort: S
  release_blocking: yes   # blocks any deployment
  dependencies: none
  related: ["Known #12", BUG-014]

- id: BUG-002
  title: Django-admin RBAC surfaces allow escalation to the "*" wildcard
  severity: P1
  confidence: High
  status: Confirmed
  category: [E Security]
  verified: C
  location:
    - backend/rbac/admin.py:101-103     # RoleAdminForm Meta fields = "__all__"
    - backend/rbac/admin.py:130         # RoleAdmin list_editable = ("is_active",)
    - backend/rbac/admin.py:139-142     # Role.code editable on change
    - backend/rbac/admin.py:232-236     # PermissionAdmin: plain ModelAdmin
    - backend/rbac/admin.py:239-249     # UserRoleAdmin: plain ModelAdmin, list_editable is_active
    - backend/rbac/admin.py:252-276     # UserPermissionAdmin: plain ModelAdmin
    - backend/rbac/admin.py:279-288     # RolePermissionAdmin: plain ModelAdmin
    - backend/rbac/admin.py:374-376     # UserAdmin exposes is_active / is_staff / is_superuser
    - backend/rbac/services.py:16-22, 45-48, 80-81   # resolution keys on role *code*; "*" grants everything
  symbol: RoleAdmin, PermissionAdmin, UserRoleAdmin, UserPermissionAdmin, RolePermissionAdmin, UserAdmin
  explanation: >
    The "you may only give away what you hold" rule is enforced only in RoleAdmin.save_related
    (rbac/admin.py:166-195) and UserAdmin.save_related (:476). The sibling admin surfaces check
    nothing beyond Django model permissions:
      (a) change_role: rename SUPER_ADMINISTRATOR's code, then rename your own role's code to
          SUPER_ADMINISTRATOR. get_user_permissions() keys on the code and returns the wildcard.
          The protected role can also be deactivated from the changelist.
      (b) change_permission: rename a permission you hold to "*". has_user_permission() then
          returns True for every code.
      (c) add_userpermission, (d) add_rolepermission, (e) add/change_userrole: grant anything to
          anyone, including yourself.
      (f) auth.change_user: the stock is_superuser checkbox.
    Precondition: a non-superuser staff account holds one of these Django model permissions. The
    project explicitly supports this (the role-board delegation tests and the "Admin panel
    permissions" board).
  repro: Operator with rbac.change_role sets the SUPER_ADMINISTRATOR role code to X, sets their own role code to SUPER_ADMINISTRATOR, then calls any /api/admin/* endpoint and is authorized.
  expected: The same delegation and protected-role boundary as the Console API.
  actual: Any of the paths above yields the full platform wildcard.
  impact: A semi-trusted staff account can take over users, roles, payments and points.
  fix: >
    - Make Role.code and Permission.code/resource/action read-only after creation, and refuse "*".
    - Restrict add/change/delete on PermissionAdmin, UserPermissionAdmin, RolePermissionAdmin and UserRoleAdmin (and the UserRole inline) to wildcard holders, or apply the delegation, protected-role and no-self rules used by the API.
    - Make is_superuser, is_staff, user_permissions and groups read-only for non-superusers.
  regression_test: One test per path (a)–(f) — a crafted admin POST by non-wildcard staff holding only the cited Django permission leaves get_user_permissions(actor) unchanged.
  effort: M
  release_blocking: yes   # before any non-superuser is given rbac.* or auth.change_user
  dependencies: none
  related: ["Known #15, #16, #22 (same class on other admins)", BUG-039]

- id: BUG-003
  title: Console user API assigns roles beyond the actor's own permissions and can lock out administrators
  severity: P1
  confidence: High
  status: Confirmed
  category: [E Security]
  verified: C
  location:
    - backend/shop/admin_views.py:198-215      # AdminUserListAPIView.post: only protected roles refused
    - backend/shop/admin_views.py:232-233      # assign_user_role for every requested role
    - backend/shop/admin_views.py:291-345      # AdminUserDetailAPIView.patch: checks 1-4
    - backend/shop/admin_serializers.py:21     # PROTECTED_ROLE_CODES = {SUPER_ADMINISTRATOR, ADMINISTRATOR}
    - backend/shop/admin_views.py:412          # contrast: role create/edit applies get_undelegatable_permission_codes
  symbol: AdminUserListAPIView.post, AdminUserDetailAPIView.patch
  explanation: >
    User create and PATCH refuse only the two protected roles. Any other active role is assigned
    whether or not the actor holds its permissions. Self role edits are blocked (:299-300), but the
    actor can create a new account with a password they choose and any role, then sign in as it.
    PATCH protects only Super Administrator targets (:295). A non-super users.admin.manage holder can
    therefore deactivate ADMINISTRATOR accounts (:309-324) or revoke their ADMINISTRATOR role (check 4
    at :336-339 only guards assigning a protected role).
  repro: >
    A holder of a custom role with users.admin.view and users.admin.manage (custom roles and direct
    grants are both supported) POSTs /api/admin/users/ with roles=["FINANCE"] and gets 201. The new
    account holds payments.refund and points.adjust (seed_rbac.py:214-220).
  expected: 403 when the added roles carry permissions outside the actor's set, or when the target outranks the actor.
  actual: 201/200.
  impact: Privilege escalation through a sock-puppet account; denial of service against administrators.
  fix: >
    Add one helper in rbac.services:
    - The permissions of (desired_roles − current_roles) must be delegatable by the actor.
    - A non-wildcard actor may only modify a target whose effective permissions are a subset of the actor's and who holds no protected role.
    Use it in both POST and PATCH.
  regression_test: A custom users.admin.* holder adding FINANCE gets 403, and deactivating an ADMINISTRATOR gets 403; an ADMINISTRATOR assigning FINANCE still gets 200 (ADMINISTRATOR holds payments.*, seed_rbac.py:156).
  effort: S
  release_blocking: yes
  dependencies: none
  related: [BUG-002]

- id: BUG-004
  title: SALES_TEAM — the only non-admin role that lets sellers create products — opens the staff seller directory and product list
  severity: P1
  confidence: Medium
  status: Probable   # depends on how real sellers are provisioned (not observable without DB access)
  category: [E Security]
  verified: C
  location:
    - backend/shop/api_views.py:483-486 and backend/shop/permissions.py:45   # seller product create needs RBAC products.create
    - backend/rbac/management/commands/seed_rbac.py:207-213                 # SALES_TEAM: sellers.view, products.view, products.create, …
    - backend/shop/admin_permissions.py:70-75                                # CanViewAdminSellers: sellers.admin.manage OR sellers.view
    - backend/shop/admin_permissions.py:254-258                              # CanViewAdminProducts: products.admin.manage OR products.view
    - backend/shop/admin_views.py:633-636, 765-768                           # seller list/detail GET use CanViewAdminSellers
    - backend/shop/admin_serializers.py:368-372                              # business_email … tax_id in the seller payload
    - backend/shop/admin_views.py:681-684                                    # Console seller creation assigns no role
    - backend/shop/management/commands/seed_showcase.py:20                   # SELLER_ROLE_CODE = "SALES_TEAM"
    - frontend/src/lib/admin-auth.ts:8                                       # SALES_TEAM treated as a management role
  symbol: CanViewAdminSellers, CanViewAdminProducts, CanCreateProduct
  explanation: >
    A seller can create products only with RBAC products.create. Console seller creation assigns no
    role, and the only non-administrator role carrying products.create is SALES_TEAM, which is
    exactly what the seed command assigns to sellers. SALES_TEAM also carries sellers.view and
    products.view, which satisfy the staff Console read gates.
  repro: A seller holding SALES_TEAM calls GET /api/admin/sellers/?page_size=100 and gets 200, including other sellers' business email and phone, tax_id and rejection/suspension reasons. GET /api/admin/products/ lists every shop's drafts.
  expected: Seller accounts get 403 on /api/admin/*.
  actual: 200 (if sellers hold SALES_TEAM).
  impact: Cross-tenant exposure of business PII and unpublished catalog data.
  fix: >
    - Split seller from staff permissions: add a seller role without platform-wide *.view codes, or gate the Console reads on staff-only codes (sellers.admin.view, products.admin.view).
    - Reconsider whether seller product creation should require RBAC at all; IsEligibleProductSeller already scopes it.
  regression_test: A seller with the seller role gets 403 on /api/admin/sellers/ and /api/admin/products/; SALES_MANAGER still gets 200.
  effort: M
  release_blocking: yes   # if production sellers hold SALES_TEAM
  dependencies: TASK-048 (decide the seller permission model)
  related: ["Known #27"]

- id: BUG-005
  title: Seller cancellation never cancels or refunds the payment
  severity: P1
  confidence: High
  status: Confirmed
  category: [A Functional, I Integrity]
  verified: C
  location:
    - backend/shop/services.py:1040-1055   # transition_seller_order_status: CANCELLED → release_order_reservation only
    - backend/shop/services.py:797-809     # transition_order_status: release + PaymentService.handle_order_cancellation
    - backend/shop/serializers.py:611      # seller status ChoiceField accepts CANCELLED
    - frontend/src/app/seller/orders/page.tsx:385   # CANCELLED offered in the seller UI
  symbol: OrderService.transition_seller_order_status
  explanation: The staff/customer path releases stock and calls handle_order_cancellation, which cancels pending payments and auto-refunds paid ones. The seller path releases stock only.
  repro: A paid (or pending) order; the seller PATCHes /api/seller/orders/<n>/status/ with {"status":"CANCELLED"}. The order is CANCELLED, the payment stays PAID or PENDING, and no Refund row is created.
  expected: The payment is refunded, or cancelled if pending, exactly as on the staff path.
  actual: Money is kept on a cancelled order.
  impact: Customer funds are not returned, and order and payment states disagree. Exposure is limited today only because checkout creates no payments (BUG-012).
  fix: Call PaymentService.handle_order_cancellation in the seller CANCELLED branch. Better, move both paths onto one post-transition helper.
  regression_test: Seller cancels a paid order → payment REFUNDED, one COMPLETED Refund, REFUND_PROCESSED event; pending payment → CANCELLED.
  effort: XS
  release_blocking: yes
  dependencies: none
  related: [BUG-012]

- id: BUG-006
  title: Django admin Order change form edits status raw, bypassing OrderService
  severity: P1
  confidence: High
  status: Confirmed
  category: [I Integrity, E Security]
  verified: C
  location:
    - backend/shop/admin.py:350-383   # OrderAdmin; readonly_fields at :364-373 has no "status"; no fields/fieldsets/save_model/has_delete_permission
  symbol: OrderAdmin
  explanation: >
    The generated ModelForm includes status, plus shipping_address as a select over every Address
    in the database. Saving writes them straight to the row and skips everything OrderService does:
    VALID_TRANSITIONS, reservation release, the refund, delivery finalisation, the audit row and the
    notification. A stale form can also write an old status back over a newer one (resurrecting a
    cancelled order). Deleting an order cascades its payments.
  repro: Staff with shop.change_order set a paid PENDING order to Cancelled → no refund, stock stays reserved. DELIVERED → PENDING is also accepted.
  expected: status is read-only, and transitions go only through the five guarded actions.
  actual: status is free-form.
  impact: Unrefunded payments, inventory drift (it also creates new reservation-less orders for BUG-007), and no forensic trail.
  fix: Add status and shipping_address (or use raw_id_fields) to readonly_fields; override has_delete_permission to return False; mirror the Known #22 fix and its AdminChangeFormStatusLockdownTests.
  regression_test: A crafted change-form POST with status=CANCELLED leaves the status unchanged and causes no inventory movement.
  effort: XS
  release_blocking: yes
  dependencies: none
  related: ["Known #15", "Known #22", BUG-007, BUG-021]
  note: Reported independently by two slice auditors; consolidated here.

- id: BUG-007
  title: Delivery (SALE) is not bounded by the order's own reservation (Known Issue #29, still open)
  severity: P1
  confidence: High
  status: Confirmed
  category: [D Database, I Integrity]
  verified: C
  location:
    - backend/shop/inventory_service.py:420-435   # finalize_order_delivery: qty = min(inventory.reserved_quantity, item.quantity) at :430
    - backend/shop/inventory_service.py:329       # contrast: release path is bounded by _order_reserved_quantity
  symbol: InventoryService.finalize_order_delivery
  explanation: >
    Delivering an order that has no reservation of its own, or a smaller one, moves units reserved
    by other orders into "sold". Two inflows exist: historical reservation-less orders (the legacy
    checkout and the pre-Phase-2F release bug) and raw status edits (BUG-006).
  repro: Order A reserves 2 of P. Order B, with no reservation, is delivered for 2 of P. A's reservation is consumed, so A's later delivery or cancellation moves nothing.
  expected: The sale draws only on the order's own reservation; any shortfall is handled explicitly.
  actual: Other customers' reservations are consumed.
  impact: Inventory counts corrupted across orders; oversell.
  fix: Use qty = min(inventory.reserved_quantity, item.quantity, _order_reserved_quantity(order, product)) and decide how to handle a shortfall (sell from available stock or flag it).
  regression_test: Delivering a reservation-less order leaves another order's reservation intact.
  effort: XS   # plus a data reconciliation investigation (TASK-047)
  release_blocking: yes
  dependencies: TASK-006 (closes the BUG-006 inflow)
  related: ["Known #29", "Known #30", BUG-006]

- id: BUG-008
  title: Seller product edit always re-sends a stale absolute stock value (lost update)
  severity: P1
  confidence: High
  status: Confirmed
  category: [A Functional, I Integrity]
  verified: C
  location:
    - frontend/src/app/seller/products/page.tsx:182   # edit form seeded from the list row: stock: (p.stock ?? 0).toString()
    - frontend/src/app/seller/products/page.tsx:280   # stock: parseInt(formData.stock) || 0 sent on every edit
    - backend/shop/services.py:289-304                # absolute stock → delta against the *current* available_quantity
  symbol: handleOpenEdit / handleEditSubmit; ProductService.update_product
  explanation: The edit form always PATCHes an absolute stock value taken from a possibly hours-old list. The backend turns it into a delta against current availability, so units reserved since the page loaded are added back.
  repro: The list loads with stock 10. Checkouts reserve 5, so 5 are available. The seller fixes a typo and saves; the PATCH sends stock=10, the delta is +5, and 10 are available again.
  expected: Stock changes only when the seller edits it, and only relative to what they saw.
  actual: Stock is reset to the stale value.
  impact: Inflated inventory and overselling; the audit log attributes the change to the seller.
  fix: >
    Use one of:
    - Send stock only when the field is dirty.
    - Use the existing delta endpoint (POST /api/seller/inventory/<id>/adjust/, adjustSellerProductStock — currently unused).
    - Add an expected_stock / updated_at precondition and return 409 on mismatch.
  regression_test: Backend — reserve units, then PATCH a non-stock field with the stale stock; availability must be unchanged (or the request rejected). Frontend — an untouched stock field is not sent.
  effort: S
  release_blocking: yes
  dependencies: none
  related: ["Known #2"]

- id: BUG-009
  title: Seller order "View Details" shows a blank delivery address
  severity: P1
  confidence: High
  status: Confirmed
  category: [G Integration, B Frontend]
  verified: C
  location:
    - frontend/src/app/seller/orders/page.tsx:223      # setViewingOrder(order) — the list row
    - frontend/src/app/seller/orders/page.tsx:297-311  # reads shipping_recipient_name / shipping_phone / shipping_address_line_1 / shipping_city
    - backend/shop/serializers.py:505-517              # SellerOrderListSerializer fields: no shipping or contact fields
    - frontend/src/lib/api.ts:821                      # getSellerOrderDetail exists but is never called
  symbol: SellerOrdersPage modal; SellerOrderListSerializer
  explanation: The list payload deliberately omits PII. The modal renders the list row, so every line of "Delivery Address Snapshot" is undefined. The dashboard's "Ships to …" line has the same gap.
  repro: A seller opens Orders and clicks "View Details" on any order.
  expected: Recipient, phone and address are shown (from the detail endpoint).
  actual: An empty card.
  impact: Fulfilment is broken in the UI; sellers must ask staff for addresses.
  fix: On open, fetch /api/seller/orders/<n>/ (with loading and error states) and keep PII out of the list payload.
  regression_test: A component test that the modal fetches the detail endpoint and renders shipping_address_line_1; a backend contract test that the list omits PII and the detail includes it.
  effort: S
  release_blocking: yes
  dependencies: none

- id: BUG-010
  title: Cart applies failed server mutations to local state for signed-in users; displayed total ≠ ordered cart
  severity: P1
  confidence: High
  status: Confirmed
  category: [A Functional, G Integration]
  verified: C
  location:
    - frontend/src/context/CartContext.tsx:165-211   # addToCart: catch → falls through to the guest/local branch
    - frontend/src/context/CartContext.tsx:213-232   # removeFromCart: same pattern
    - frontend/src/context/CartContext.tsx:234-269   # increaseQuantity (also decreaseQuantity / clearCart)
    - frontend/src/app/checkout/page.tsx:519         # Place Order (৳{totalAmount}) uses local state
    - backend/shop/api_views.py:286-341              # the order is built from the *server* cart; client items ignored
  symbol: CartProvider
  explanation: >
    For an authenticated user, every API error is logged with console.warn and then the same local
    mutation as guest mode is applied. Nothing persists it, because localStorage is only written
    when there is no token. The drawer and checkout display local totals, while createOrder orders
    the unchanged server cart. In addition, increaseQuantity sends item.quantity + 1 from a stale
    render closure, so rapid clicks lose increments, and the server's 99-unit cap
    (cart/models.py:53) is not reflected in the UI.
  repro: Remove item X while the API fails; the UI drops X, but Place Order still orders it. Or press "+" past 99.
  expected: Show the error, re-fetch the server cart and leave local state alone.
  actual: The UI shows a cart the server does not have.
  impact: The customer is charged for a different cart than the one shown.
  fix: Use the local fallback only when there is no token; on failure call refreshCart() and expose an error; disable the steppers while a call is pending; have checkout re-read the server cart total before rendering.
  regression_test: Mock removeCartItemApi to reject → items unchanged and an error is shown (repeat for add and increase).
  effort: S
  release_blocking: yes
  dependencies: TASK-042 (frontend test harness) for the regression test
  related: [BUG-084, BUG-087]

- id: BUG-011
  title: New products can never be published through a UI (DRAFT dead end)
  severity: P1
  confidence: High
  status: Confirmed
  category: [A Functional, G Integration]
  verified: C
  location:
    - backend/shop/services.py:182                                  # create_product → status=Product.STATUS_DRAFT
    - frontend/src/app/admin/products/productGovernance.tsx:132-135 # DRAFT → no actions offered
    - backend/shop/services.py:354                                  # backend moderation accepts any status
    - backend/shop/admin.py:213                                     # the only UI path: raw status edit in Django admin (see BUG-021)
  symbol: ProductService.create_product; getStatusRelevantActions
  explanation: >
    Sellers pay points to create a product, which is stored as DRAFT. No endpoint moves it to
    SUBMITTED (Known #8; STATUS_SUBMITTED is referenced only by shop/models.py and shop/metrics.py).
    The Console offers no action for DRAFT and says no moderation decision is needed yet. The only
    way to publish is a raw status edit in the Django admin, which skips the audited ProductService.
  repro: A seller creates a product; staff open /admin/products/<id> and see no Approve/Publish action.
  expected: A defined path from DRAFT to PUBLISHED.
  actual: The listing stays DRAFT unless the audit-bypassing Django admin is used.
  impact: The core listing workflow is broken.
  fix: >
    Product decision, then one of:
    (a) a seller "submit for review" endpoint and button (DRAFT→SUBMITTED), or
    (b) the Console offers approve/publish for DRAFT.
    Update the Console copy either way.
  regression_test: End to end — seller create → submit → staff approve → publish; a DRAFT product with products.approve offers approve.
  effort: S (Console) – M (submit endpoint)
  release_blocking: yes
  dependencies: TASK-048 decision
  related: ["Known #8", BUG-021]
```

### 3.3 P2 — Medium

```yaml
- id: BUG-012
  title: Checkout never creates a Payment record, so the payments/refund subsystem is unreachable for real orders
  severity: P2
  confidence: High
  status: Confirmed   # code fact; intended COD design needs a decision
  category: [G Integration, A Functional]
  verified: C
  location:
    - backend/shop/api_views.py:1012-1028   # the only caller of PaymentService.create_or_get_payment (customer POST /api/orders/<n>/payment/)
    - frontend/src/lib/api.ts:929           # initiateOrderPayment — defined, never called
    - backend/shop/services.py (create_order_from_cart, steps 9-12)   # approximate; creates no Payment
  symbol: OrderService.create_order_from_cart
  explanation: Checkout is cash-on-delivery only and creates no Payment. Consequences — is_paid is always False, staff verify/refund have nothing to act on, cancellation never touches money, and payment-based revenue stays at ৳0.
  repro: Place any order through the UI; GET /api/orders/<n>/payment/ returns 404 "No payment record found".
  expected: Each order carries a PENDING COD payment (for example, paid on delivery or verified by staff).
  actual: No payment exists.
  impact: Payments, refunds and revenue reporting are wrong or empty.
  fix: Create a PENDING CASH_ON_DELIVERY Payment for total_amount inside the order transaction (or call initiateOrderPayment after createOrder); optionally mark it PAID on DELIVERED; decide on a backfill.
  regression_test: POST /api/orders/ creates exactly one PENDING COD Payment equal to total_amount.
  effort: S
  release_blocking: yes   # for any money reporting
  dependencies: TASK-048 decision on the COD payment lifecycle
  related: [BUG-005, BUG-052, BUG-083]

- id: BUG-013
  title: Refresh tokens renew indefinitely and survive logout and password change
  severity: P2
  confidence: High
  status: Confirmed
  category: [E Security]
  verified: C
  location:
    - backend/config/settings/base.py:217-223   # ROTATE_REFRESH_TOKENS True, BLACKLIST_AFTER_ROTATION False
    - backend/config/settings/base.py:51-71     # token_blacklist app not installed
    - backend/rbac/serializers.py:179-180       # password change: set_password + save; no revocation
    - backend/venv/.../rest_framework_simplejwt/settings.py:45   # CHECK_REVOKE_TOKEN False
    - frontend/src/lib/auth.ts:16-17            # "no logout or token revocation endpoint"
  symbol: SIMPLE_JWT, PasswordChangeSerializer
  explanation: Each refresh returns a new refresh token with a fresh 7-day expiry, and the old one is never blacklisted, so a stolen refresh token can be chained forever. A password change does not invalidate existing tokens. Only is_active=False stops them.
  repro: Obtain a token pair, change the password, and refresh with the old refresh token; the refresh succeeds (expected from the library defaults; not executed).
  expected: Logout and password change end other sessions.
  actual: Sessions persist without limit.
  impact: A compromised session cannot be remediated by the user. Tokens live in localStorage, so any future XSS becomes persistent access.
  fix: Install token_blacklist and set BLACKLIST_AFTER_ROTATION=True; set CHECK_REVOKE_TOKEN=True (SimpleJWT 5.5.1) or blacklist outstanding tokens on password change; add a logout endpoint; optionally cap absolute session age.
  regression_test: After a password change, the old access and refresh tokens get 401; reusing a rotated refresh token gets 401.
  effort: S
  release_blocking: yes
  dependencies: none
  related: ["review-state §17 'No logout / token revocation'"]

- id: BUG-014
  title: No rate limiting on any authentication surface; minimum password length 4
  severity: P2
  confidence: High
  status: Confirmed
  category: [E Security]
  verified: C
  location:
    - backend/config/settings/base.py:207-214   # REST_FRAMEWORK: no DEFAULT_THROTTLE_CLASSES/RATES
    - backend/rbac/views.py:16-20               # CustomTokenObtainPairView: no throttle
    - backend/rbac/urls.py:15-19                # token / refresh / register / change-password routes
    - backend/config/settings/base.py:154-159   # MinimumLengthValidator(min_length=4) only
  symbol: REST_FRAMEWORK, AUTH_PASSWORD_VALIDATORS
  explanation: /api/auth/token/, /api/auth/register/, /api/auth/change-password/ and /admin/login/ accept unlimited attempts. The only throttle in the codebase is the notifications unread-count throttle. Registration also reveals whether a username or email exists.
  repro: A scripted POST loop against /api/auth/token/ is never refused (static).
  expected: 429 after N failures per IP or username; real password policy.
  actual: Unlimited attempts.
  impact: Credential stuffing and brute force against customers and staff; mass account creation.
  fix: Add ScopedRateThrottle on the auth views, lockout or backoff on the admin login, and restore Django's default validators with a sensible minimum length.
  regression_test: The (N+1)th failed token request returns 429.
  effort: S
  release_blocking: yes
  dependencies: none
  related: [BUG-001]

- id: BUG-015
  title: Audit IP taken from client-controlled X-Forwarded-For; long values make ShopAdmin actions commit without an audit row
  severity: P2
  confidence: High
  status: Confirmed   # spoofing; the "no audit row" path is Probable (depends on MySQL strict mode, which base.py:133 sets)
  category: [E Security, I Integrity]
  verified: C
  location:
    - backend/audit/utils.py:4-9                 # first XFF hop trusted
    - backend/shop/admin_views.py:120-124        # duplicate helper
    - backend/shop/api_views.py:1019-1020        # inline copy (more at other call sites)
    - backend/audit/models.py:59                 # GenericIPAddressField → char(39) on MySQL
    - backend/audit/admin_mixins.py:113-120      # perform(obj) then AuditService.log, no enclosing atomic
    - backend/shops/admin.py:143                 # ShopAdmin actions call run_simple_action without transaction.atomic
    - backend/shops/services.py:390              # approve_shop commits in its own @transaction.atomic
  symbol: get_client_ip, ReasonRequiredActionMixin.run_simple_action
  explanation: >
    No trusted proxy is configured, yet the first X-Forwarded-For hop is trusted, so any requester
    can write an arbitrary value of up to 39 characters as the audit IP. The same value is shown as
    "last IP" on /admin/profile/. A longer value raises a DataError under STRICT_TRANS_TABLES:
    - At atomic call sites this means a 500 and a rollback.
    - In ShopAdmin actions the shop service has already committed, so the status changes with no audit row.
  repro: Staff with change_shop runs "Approve and activate" with an X-Forwarded-For header longer than 39 characters.
  expected: Every lifecycle change is audited with the real client IP.
  actual: A forged IP, or a status change with no audit row.
  impact: The audit trail's forensic value is compromised, and staff can evade auditing.
  fix: Use REMOTE_ADDR unless a trusted-proxy count is configured; validate with ipaddress and fall back to None; keep one helper; wrap perform + log per object in transaction.atomic inside the mixin.
  regression_test: A spoofed XFF records REMOTE_ADDR; a 60-character XFF on the ShopAdmin approve action results in either a change with an audit row or no change.
  effort: S
  release_blocking: no
  dependencies: none
  related: ["Known #23 (shop side)", BUG-049]
  note: Reported independently by two slice auditors; consolidated here.

- id: BUG-016
  title: Saving any existing shop in the Django admin returns 500
  severity: P2
  confidence: High
  status: Confirmed   # static trace through Django 5.2 form/field code; not executed
  category: [A Functional, C Backend]
  verified: C
  location:
    - backend/shops/fields.py:10-11     # Point: @dataclass(frozen=True), no __str__
    - backend/shops/fields.py:78-87     # Point.from_wkt raises ValueError when the regex fails
    - backend/shops/fields.py:147-164   # MySQLPointField.to_python: any string starting "POINT" (case-insensitive) → from_wkt
    - backend/shops/admin.py:40-43, 53-54   # location is editable (not in readonly_fields) and in the fieldset
  symbol: MySQLPointField (no formfield() override → forms.CharField)
  explanation: >
    The change form renders str(Point), which is the dataclass repr
    "Point(longitude=…, latitude=…)". On save, full_clean calls to_python. "Point(" matches the
    "POINT" prefix, from_wkt's regex fails, and ValueError (not ValidationError) escapes
    clean_fields, so the request ends in a 500. The Add form works only because the default is the
    string 'POINT(0 0)'. (The original auditor cited non-existent line numbers; the lines above were
    re-read.)
  repro: Open /admin/shops/shop/<id>/change/, change the name, and save.
  expected: 302 and the change saved.
  actual: 500, nothing saved.
  impact: Shops cannot be edited in the Django admin, including the owner reassignment secured in 61ff971. The Console PATCH still works.
  fix: Give MySQLPointField a formfield whose prepare_value emits to_wkt() (or make Point.__str__ return to_wkt()); raise ValidationError from to_python/from_wkt; validate coordinate ranges. Alternatively, make location read-only and edit latitude/longitude as separate fields.
  regression_test: GET the change page and re-POST the rendered values → 302; malformed WKT → 200 with a form error.
  effort: S
  release_blocking: no
  dependencies: none

- id: BUG-017
  title: Seller lifecycle transitions have no source-state guards (sellers.approve can lift a suspension)
  severity: P2
  confidence: High
  status: Confirmed
  category: [E Security, A Functional]
  verified: C
  location:
    - backend/sellers/models.py:122-128   # approve(): no status check
    - backend/sellers/models.py:137-143   # suspend(): only checks the reason
    - backend/sellers/models.py:145-152   # reject(): only checks the reason
    - backend/sellers/models.py:130-132   # activate(): the only guarded transition
    - backend/shop/admin_permissions.py:126-131                    # approve/reject → sellers.approve; suspend/reactivate → sellers.suspend
    - backend/rbac/management/commands/seed_rbac.py:199-200        # SALES_MANAGER holds sellers.approve, not sellers.suspend
    - backend/shops/services.py:397        # contrast: ShopService guards source states
  symbol: SellerProfile.approve / suspend / reject; sellers.services.approve_seller
  explanation: >
    The permission map treats suspend/reactivate as a separate authority from approve/reject, but
    the transitions accept any source state:
    - approve on SUSPENDED goes to APPROVED, then ACTIVE.
    - reject works on ACTIVE.
    - suspend then reactivate on PENDING activates an applicant without approval.
    The same holes exist on every path: DRF views, the Console status view and the Django admin actions.
  repro: A SALES_MANAGER POSTs {"action":"approve"} to /api/admin/sellers/<suspended id>/status/ (or /api/sellers/<id>/approve/); the seller becomes ACTIVE.
  expected: 400 for an illegal transition.
  actual: 200; the suspension is lifted.
  impact: Separation of duties is bypassed with a default role.
  fix: Allowed source states per transition (approve from PENDING/UNDER_REVIEW/REJECTED, reject from PENDING/UNDER_REVIEW, suspend from APPROVED/ACTIVE, reactivate from SUSPENDED), raising a typed error mapped to 400 everywhere.
  regression_test: Table-driven tests over (action × source status); approve on SUSPENDED leaves the seller SUSPENDED and writes no audit row.
  effort: S
  release_blocking: no
  dependencies: none
  related: ["Known #23", BUG-050]
  note: Reported independently by two slice auditors; consolidated here.

- id: BUG-018
  title: Suspended or rejected seller's shops stay publicly listed
  severity: P2
  confidence: Medium   # a test comment calls such a shop "(otherwise public)", so the gap may be known
  status: Confirmed
  category: [A Functional, E Security]
  verified: C
  location:
    - backend/shops/services.py:266-280   # get_public_shops_queryset filters shop status only
    - backend/shop/models.py:61-68        # contrast: Product.objects.public() also requires shop__owner__status APPROVED/ACTIVE
    - backend/sellers/admin.py:173        # help text: "Suspending a seller blocks their shops and products from the storefront."
  symbol: ShopService.get_public_shops_queryset
  explanation: After a seller is suspended, their shops (with phone and address) stay in /api/shops/, the shop detail, nearby (without q) and the shop review list, each with an empty product list.
  repro: Suspend an ACTIVE seller, then GET /api/shops/<their-shop-slug>/ → 200.
  expected: 404, and the shop excluded from lists.
  actual: 200 and listed.
  impact: Suspended merchants stay visible, contradicting the admin's stated behaviour.
  fix: Add owner__status__in=[APPROVED, ACTIVE] to the public queryset and to the review lookup.
  regression_test: With a suspended owner, the shop is absent from list/nearby/detail and its reviews return 404.
  effort: XS
  release_blocking: no
  dependencies: none

- id: BUG-019
  title: Invoice PDF interprets customer/seller text as ReportLab markup
  severity: P2
  confidence: High
  status: Confirmed
  category: [E Security, A Functional]
  verified: C
  location:
    - backend/shop/invoice.py:391-409   # _party_block: Paragraph(order.customer_name …), Paragraph(order.shipping_phone …)
    - backend/shop/invoice.py:446       # _items_table: Paragraph(item.product_name …)
    - backend/shop/invoice.py:576       # _refunds_section: Paragraph(refund.reason …)
  symbol: _party_block, _items_table, _refunds_section
  explanation: >
    Strings the customer controls (recipient, phone, address lines — OrderCreateSerializer has no
    character validation), product names set by sellers and refund reasons set by staff are passed
    raw to Paragraph, which parses an XML-like markup.
    - With ReportLab's default crashOnError, an unclosed tag raises ValueError, so the invoice download returns 500.
    - <a href>, <font> and <img src="/local/path"> are honoured: clickable links can be injected into an official document, and local server files can be embedded.
  repro: An order whose recipient is "<b>Rahim" → the invoice download fails; a product name containing <a href="…"> → a clickable link in the PDF.
  expected: Text rendered literally.
  actual: Interpreted as markup.
  impact: Failed invoices, forged links, embedding of local files.
  fix: Escape every dynamic value (xml.sax.saxutils.escape) before building each Paragraph.
  regression_test: An invoice for the inputs above builds without error, and the extracted text contains the literal characters.
  effort: S
  release_blocking: no
  dependencies: none

- id: BUG-020
  title: Invoice "Balance due" is wrong for cancelled and refunded orders
  severity: P2
  confidence: High
  status: Confirmed
  category: [A Functional]
  verified: C
  location:
    - backend/shop/invoice.py:482-501   # balance = total − paid + refunded
    - backend/shop/models.py:437-448    # total_paid_amount includes REFUNDED / PARTIALLY_REFUNDED payments; total_refunded_amount = completed refunds
  symbol: _totals_table
  explanation: A cancelled, fully refunded ৳1,000 order gives 1000 − 1000 + 1000 = ৳1,000 due. A cancelled unpaid order shows the full total due. A partial refund is billed back to the customer.
  repro: Build the invoice for a cancelled and refunded order.
  expected: ৳0.00 due on cancelled orders; refunds are not re-billed.
  actual: The refunded amount is shown as owed.
  impact: A wrong money figure on a customer-facing document.
  fix: Use 0 for CANCELLED; otherwise max(0, total − (paid − refunded)). Document the semantics.
  regression_test: Cancelled+refunded and cancelled+unpaid invoices both show "Balance due ৳0.00".
  effort: XS
  release_blocking: no
  dependencies: none

- id: BUG-021
  title: Django ProductAdmin and ProductInventoryAdmin edit stock, status and counters directly
  severity: P2
  confidence: High
  status: Confirmed
  category: [I Integrity, D Database]
  verified: C
  location:
    - backend/shop/admin.py:172       # list_editable includes "stock"
    - backend/shop/admin.py:176       # readonly_fields only current_image, storefront_checklist
    - backend/shop/admin.py:195       # "shop" editable
    - backend/shop/admin.py:209       # submitted_at, reviewed_at, reviewed_by, rejection_reason editable
    - backend/shop/admin.py:213       # status editable
    - backend/shop/admin.py:530-535   # ProductInventoryAdmin: available/reserved/sold editable; add/delete allowed
  symbol: ProductAdmin (no save_model), ProductInventoryAdmin
  explanation: >
    - Product.stock edits desync from ProductInventory (Known #2, fixed only on the API path).
    - Status and reviewer edits skip ProductService and the audit log, and allow attribution to another staff member.
    - Saving an inventory row from a stale form overwrites concurrent reservations; no InventoryTransaction ledger row is written.
  repro: Load the inventory change form; a checkout reserves units; save the form → the reservation is overwritten.
  expected: Stock goes through InventoryService.adjust_stock under a lock; moderation goes through ProductService.
  actual: Raw ModelForm saves.
  impact: Oversell, ledger drift, forged audit attribution.
  fix: Make lifecycle/moderation fields, shop and the inventory counters read-only on change; route stock through InventoryService in save_model (or drop it from list_editable); add an admin action for adjustments.
  regression_test: A crafted POST with status, stock and counters leaves the database unchanged (the #22 test pattern).
  effort: S
  release_blocking: no
  dependencies: none
  related: ["Known #2", "Known #22", BUG-006, BUG-011, BUG-046]
  note: Reported independently by two slice auditors; consolidated here.

- id: BUG-022
  title: N+1 queries on staff order/payment lists, customer orders and cart
  severity: P2
  confidence: High
  status: Confirmed
  category: [F Performance]
  verified: C
  location:
    - backend/shop/models.py:426-429      # current_payment: self.payments.order_by(...).first() bypasses the prefetch
    - backend/shop/api_views.py:1182-1191 # prefetch_related("payments") that current_payment ignores
    - backend/shop/serializers.py:960-966 # get_payment_status / get_payment_method each call current_payment
    - backend/shop/serializers.py:415-416 # OrderDetailSerializer.get_payment
    - backend/shop/serializers.py:772-774 # refundable amount re-queries refunds per payment
    - backend/cart/serializers.py:18 and backend/shop/models.py:198   # in_stock → hasattr(self, "inventory") per item
  symbol: Order.current_payment, StaffOrderListSerializer, PaymentSerializer, CartProductSummarySerializer
  explanation: Up to about 200 extra queries per staff order page at page_size=100. A round trip to the remote dev database costs 54–167 ms (measured in config/settings/test.py), so these pages are slow.
  repro: "`assertNumQueries` on /api/staff/orders/?page_size=50 (not run)."
  expected: A constant number of queries per page.
  actual: Linear in rows.
  impact: Slow staff lists and cart.
  fix: Annotate the latest payment with a Subquery, or use an ordered Prefetch and read [0]; compute refundable amounts from the prefetched lists; select_related("product__inventory") in the cart query.
  regression_test: assertNumQueries on /api/staff/orders/, /api/staff/payments/, /api/orders/ and /api/cart/.
  effort: S
  release_blocking: no
  dependencies: none

- id: BUG-023
  title: Checkout select_for_update also locks the joined Product/Category/Shop/SellerProfile rows
  severity: P2
  confidence: Medium
  status: Probable   # depends on MySQL locking-read behaviour; not observed
  category: [F Performance, D Database]
  verified: A
  location:
    - backend/shop/services.py:545-554   # CartItem.objects.select_for_update().filter(cart=cart).select_related("product", "product__category", …) without of=
  symbol: OrderService.create_order_from_cart
  explanation: MySQL's SELECT … FOR UPDATE over a join locks the scanned rows of every joined table. Each checkout would hold X locks on the category, shop and seller rows of every cart product for the whole order transaction, serializing concurrent checkouts in the same category and blocking admin edits.
  repro: Two concurrent checkouts in one category on MySQL; observe lock waits (not run).
  expected: Only the cart and inventory rows are locked.
  actual: Catalog rows are locked too (per MySQL semantics).
  impact: Throughput collapse and deadlock exposure under load.
  fix: select_for_update(of=("self",)); inventory rows are locked separately.
  regression_test: A MySQL concurrency test showing the second checkout does not wait on the category row.
  effort: XS
  release_blocking: no
  dependencies: verify on MySQL first

- id: BUG-024
  title: Frontend pages assume 10 items per page while the backend serves 12 (phantom page, then 404)
  severity: P2
  confidence: High
  status: Confirmed
  category: [G Integration]
  verified: C
  location:
    - frontend/src/app/seller/products/page.tsx:101    # Math.ceil(res.count / 10)
    - frontend/src/app/profile/orders/page.tsx:11, 29  # PAGE_SIZE = 10
    - backend/shop/api_views.py:82-85                  # StandardResultsSetPagination page_size = 12
  symbol: fetchProductsList; OrderHistoryPage
  explanation: >
    For counts of 11–12, 21–24, 31–36 and so on, the UI offers a page that does not exist. DRF then
    returns 404 "Invalid page.".
    - The seller page shows a sticky error over the previous page's rows.
    - Order History shows "We could not load your orders".
  repro: A seller with 11 products clicks Next; a customer with 12 orders clicks page 2.
  expected: 1 page.
  actual: 2 pages, the second fails.
  impact: Broken pagination on two pages.
  fix: Derive the page count from next/previous, or send page_size explicitly; clear errors on a successful fetch.
  regression_test: Mocked count=11 and count=24 give 1 and 2 pages.
  effort: XS
  release_blocking: no
  dependencies: none
  related: [BUG-025, BUG-026]

- id: BUG-025
  title: Seller Orders page cannot paginate; search filters only the first 12 orders client-side
  severity: P2   # borderline P1: older orders are unreachable for fulfilment
  confidence: High
  status: Confirmed
  category: [B Frontend, G Integration]
  verified: C
  location:
    - frontend/src/app/seller/orders/page.tsx:20-22   # totalCount / setPage / totalPages unused (ESLint no-unused-vars)
    - frontend/src/app/seller/orders/page.tsx:42-77   # always page 1; client-side search over res.results; refetch on each keystroke (deps :77)
    - backend/shop/api_views.py:681, 692-693          # paginated (12) and supports ?q= — unused
  symbol: SellerOrdersPage
  explanation: There are no pager controls, so only the newest 12 orders, per status filter, are reachable. Search runs client-side over those 12 and matches only order_number, because name fields are absent from the list payload (BUG-009).
  repro: A seller with 13 or more orders.
  expected: Page through all orders and search them all.
  actual: Only the newest 12 are reachable.
  impact: Sellers cannot fulfil older orders from the UI.
  fix: Add pager controls driven by next/previous; send a debounced q to the server; reset page on filter change.
  regression_test: With count=30, clicking Next requests page=2; search sends q.
  effort: S
  release_blocking: no
  dependencies: none

- id: BUG-026
  title: Lists silently truncated to the first page (seller wallet history, seller shops, "Current Orders")
  severity: P2
  confidence: High
  status: Confirmed
  category: [G Integration]
  verified: C
  location:
    - frontend/src/lib/api.ts:1578-1579   # getSellerPointHistory: Array.isArray(data) ? data : data.results — count/next discarded
    - frontend/src/lib/api.ts:1445-1446   # getSellerShops: same
    - backend/points/views.py:53          # SellerTransactionHistoryView uses the default PAGE_SIZE 12
    - frontend/src/app/profile/track/page.tsx:22-26   # active orders filtered from page 1 only
  symbol: getSellerPointHistory, getSellerShops, Track page
  explanation: >
    - The wallet "itemized audit ledger" shows only the newest 12 entries.
    - A Full Shop Owner (who may now hold several shops) loses shops beyond 12 in every selector.
    - An older order that is still active is hidden behind 12 newer ones, and the page says "No active orders".
  repro: A seller with 13 or more ledger rows; a customer with 13 orders where only the oldest is SHIPPED.
  expected: Full lists, or paging.
  actual: Silent truncation.
  impact: Missing financial history and missing shops/orders.
  fix: Return the paginated envelope and add paging or "load more"; set pagination_class=None on the small seller-shop list; add a backend status filter for active orders.
  regression_test: A component test with next set shows a "load more" control; 13 orders with the oldest SHIPPED → it is listed.
  effort: S
  release_blocking: no
  dependencies: none

- id: BUG-027
  title: '"Add product" is offered for shops that are not approved; the refusal is shown as "Failed to create product"'
  severity: P2
  confidence: High
  status: Confirmed
  category: [A Functional, B Frontend]
  verified: C
  location:
    - frontend/src/app/seller/products/page.tsx:332   # disabled={!hasShop || atProductLimit} — shop status ignored
    - frontend/src/app/seller/products/page.tsx:167   # defaults to the first shop regardless of status
    - backend/shops/services.py:183                   # Console-created shops start DRAFT
    - backend/shop/serializers.py:263-266             # create requires an APPROVED/ACTIVE shop
  symbol: SellerProductsPage
  explanation: Every newly provisioned seller fills in the whole form, then gets a generic failure, because the 400 body is dropped (BUG-028).
  repro: Staff create a seller and a shop (DRAFT); the seller submits a product.
  expected: The button is disabled with "your shop must be approved".
  actual: The form is submitted, followed by a generic error.
  impact: A confusing first run for every seller (no points are lost).
  fix: Eligible shops = APPROVED/ACTIVE; disable creation or filter the selector and explain why.
  regression_test: With one DRAFT shop, the button is disabled and the message shown.
  effort: S
  release_blocking: no
  dependencies: none

- id: BUG-028
  title: Frontend API clients drop DRF error bodies or show raw JSON
  severity: P2
  confidence: High
  status: Confirmed
  category: [G Integration, B Frontend]
  verified: C
  location:
    - frontend/src/lib/api.ts:557-560     # getSellerProducts: errorData.error only
    - frontend/src/lib/api.ts:617-628     # createSellerProduct: errorData.error only (:627)
    - frontend/src/lib/api.ts:1538-1541   # updateSellerProduct: err.error || err.detail
    - frontend/src/lib/api.ts:851-854     # seller order status: JSON.stringify of list-valued errors (:854)
    - frontend/src/lib/api.ts:500-503     # createOrder: detail || cart, then JSON.stringify (:502)
  symbol: several api.ts functions
  explanation: >
    DRF returns {"detail": …} and per-field errors such as {"price": ["…"]}. The clients read
    .error, or stringify lists. Users therefore see "Failed to create product" or
    '["Your shopping cart is empty."]' instead of the actual field message. Negative prices, badges
    over 20 characters, a non-approved shop and a suspended seller (403 detail) are all hidden.
  repro: Create a product with price -1 → "Failed to create product".
  expected: The server's message, per field.
  actual: A generic message or raw JSON.
  impact: Users cannot correct their input.
  fix: One shared parser (detail → error → first field message, joining lists), reusing the admin-api.ts extractErrorMessage pattern; add client-side min and maxLength.
  regression_test: Unit tests for {detail}, {error}, {field:[msg]} and {error:{field:[msg]}}.
  effort: S
  release_blocking: no
  dependencies: TASK-042
  related: [BUG-029, BUG-088]

- id: BUG-029
  title: Seller order status modal offers invalid transitions and sends PENDING for PENDING orders
  severity: P2
  confidence: High
  status: Confirmed
  category: [B Frontend]
  verified: C
  location:
    - frontend/src/app/seller/orders/page.tsx:85        # setNewStatus(order.status)
    - frontend/src/app/seller/orders/page.tsx:376-386   # options lack PENDING; SHIPPED/DELIVERED offered from PENDING
    - backend/shop/services.py:1029-1033                # multi-merchant orders always refused
  symbol: SellerOrdersPage status modal
  explanation: For a PENDING order the select shows CONFIRMED while state holds "PENDING", so Confirm sends PENDING → 400, shown as a raw JSON array. Multi-merchant orders show an "Update Status" button that can never succeed.
  repro: Open "Update Status" on a PENDING order and click Confirm without touching the select.
  expected: Only the allowed next states, initialised to the first one.
  actual: 400 with raw JSON.
  impact: Fulfilment errors that sellers misread.
  fix: Expose allowed_transitions from the API (or mirror VALID_TRANSITIONS); hide the action for multi-merchant orders.
  regression_test: A PENDING order offers only CONFIRMED and CANCELLED.
  effort: S
  release_blocking: no
  dependencies: none
  related: [BUG-028]

- id: BUG-030
  title: SellerGuard swallows non-404 failures and renders the portal as "Not Operational"
  severity: P2
  confidence: High
  status: Confirmed
  category: [B Frontend]
  verified: A
  location:
    - frontend/src/components/seller/SellerGuard.tsx:53-64   # non-404 → setError (:63), never rendered
    - frontend/src/components/seller/SellerGuard.tsx:99-112  # renders children with null data
    - frontend/src/app/seller/page.tsx:56-66                 # "Not Operational" badge
  symbol: SellerGuard
  explanation: On a network error, 5xx or 429, an operational seller sees "Welcome, Seller!" with a red "Not Operational" badge and no retry. Metrics silently show 0. The login redirect uses push and drops the deep link.
  repro: Mock /api/sellers/dashboard/ → 500.
  expected: An error state with Retry.
  actual: A misleading portal.
  impact: Sellers think their account has been suspended.
  fix: Render the error state when error is set and there is no data; use router.replace with the current path as next.
  regression_test: A mocked 500 renders the error state, not the children.
  effort: S
  release_blocking: no
  dependencies: none

- id: BUG-031
  title: A transient network or 5xx failure during session restore or token refresh logs the user out
  severity: P2
  confidence: High
  status: Confirmed
  category: [A Functional, E Security]
  verified: C
  location:
    - frontend/src/context/AuthContext.tsx:53-77   # any getCurrentUser error → refresh → any failure → clearTokens()
    - frontend/src/lib/auth.ts:164-182             # performRefresh catch → failRefresh → clearTokens + notifyAuthCleared
    - frontend/src/lib/api.ts:1097-1099            # refreshAccessToken throws on any non-OK status
  symbol: AuthProvider.initialize, performRefresh
  explanation: A network TypeError, 502 or 429 is treated as an invalid token, so a still-valid 7-day refresh token is deleted.
  repro: Reload the app while Django is restarting.
  expected: Only 400/401 from the refresh endpoint ends the session.
  actual: Any failure logs the user out.
  impact: Unexpected logouts mid-checkout (the cart becomes a guest cart).
  fix: Distinguish auth failures from transport/5xx failures in both callers; on a transient failure keep the tokens and show a retry state.
  regression_test: Fetch rejected (network) during initialize → tokens remain in localStorage.
  effort: S
  release_blocking: no
  dependencies: TASK-042
  related: [BUG-092]

- id: BUG-032
  title: Category links from every page except home do nothing (home ignores ?category=)
  severity: P2
  confidence: High
  status: Confirmed
  category: [B Frontend]
  verified: C
  location:
    - frontend/src/components/layout/Navbar.tsx:41-48   # router.push(`/?category=${slug}`) when no onSelectCategory
    - frontend/src/app/product/[slug]/page.tsx:99       # breadcrumb link /?category=…
    - frontend/src/app/page.tsx:19                      # selectedCategory starts "all"; no useSearchParams in the file
  symbol: Navbar.handleSelect; HomePage
  explanation: Product, checkout, profile, shops and other pages render Navbar without onSelectCategory. Navigation goes to /?category=x, and home always shows "all". The mobile category toggler (project rule 5) is ineffective off the home page.
  repro: On a product page, choose "Electronics" in the Navbar.
  expected: The Electronics listing.
  actual: All products, with "Home" highlighted.
  impact: Main category navigation is broken outside home.
  fix: Home reads and writes ?category via useSearchParams (inside Suspense).
  regression_test: Visiting /?category=electronics requests category=electronics and activates that tab.
  effort: S
  release_blocking: no
  dependencies: none
  related: [BUG-033]

- id: BUG-033
  title: Header search does nothing on most pages and is absent on phones
  severity: P2
  confidence: High
  status: Confirmed
  category: [B Frontend]
  verified: C
  location:
    - frontend/src/components/layout/Header.tsx:26-31   # submit only calls onSearch if provided (:28)
    - frontend/src/components/layout/Header.tsx:81      # form is "hidden md:flex"
  symbol: Header.handleSubmit
  explanation: Only home, shop/[slug] and shops pass onSearch. Everywhere else, submitting does nothing. Below md there is no search at all. On pages that do search, every keystroke fires a fetch with no debounce.
  repro: Search from /product/<slug>.
  expected: Navigate to /?q=….
  actual: No-op.
  impact: Catalogue search is unusable on mobile and on most pages.
  fix: Fall back to router.push('/?q=' + encodeURIComponent(q)); home reads q; add a mobile search entry; debounce.
  regression_test: Submitting on /product/x navigates to /?q=….
  effort: S
  release_blocking: no
  dependencies: BUG-032 fix (same URL contract)

- id: BUG-034
  title: Checkout still shows the retired guest-checkout form; submitting always fails with 401
  severity: P2
  confidence: High
  status: Confirmed
  category: [A Functional, G Integration]
  verified: C
  location:
    - frontend/src/app/checkout/page.tsx:264-282   # "Guest checkout below"
    - frontend/src/app/checkout/page.tsx:383       # manual shipping form shown when !isAuthenticated
    - backend/shop/api_views.py:294-296            # POST requires IsAuthenticated + CanCreateOrder
  symbol: CheckoutPage
  explanation: Guest checkout was retired on purpose (decision of 2026-09-18), but this page was not walked back. A guest fills in the whole form and then gets "Authentication credentials were not provided."
  repro: Log out, add an item, open /checkout and submit.
  expected: A sign-in gate (/login?next=/checkout); the guest cart merges on login.
  actual: A dead end at the end of the funnel.
  impact: Every guest checkout attempt fails after full data entry.
  fix: Gate checkout on isAuthenticated once auth has loaded; remove the guest copy.
  regression_test: Checkout rendered with a guest context shows the login gate, not the form.
  effort: XS
  release_blocking: yes
  dependencies: none

- id: BUG-035
  title: Demo-data fallback leaks into real flows (demo ids reach real carts; outages look like 404 or an empty catalogue)
  severity: P2
  confidence: Medium
  status: Probable   # depends on runtime failures and which real product ids exist
  category: [G Integration]
  verified: A
  location:
    - frontend/src/lib/api.ts:283-305   # getProducts fallback (ignores the shop filter)
    - frontend/src/lib/api.ts:316-323   # getProductDetail fallback
    - frontend/src/lib/api.ts:471-472   # getHotDeal → DEMO_PRODUCTS[7]
    - frontend/src/lib/api.ts:536-538   # getOrderDetail → null on any error
    - frontend/src/app/shop/[slug]/page.tsx:60-67
    - frontend/src/context/CartContext.tsx:91   # guest merge posts item.product.id (demo ids 1-8)
  symbol: lib/api.ts public readers
  explanation: >
    On any fetch failure, demo products with ids 1–8 are shown as real.
    - A guest can add them to the cart; on login they are posted by id, so whatever real product has that id is added.
    - A shop page shows the whole demo catalogue.
    - Outages render as "Product Not Found", "no active shops" or "Order Not Found".
  repro: Stop the backend and browse; add a demo product as a guest, restart, log in.
  expected: Error states; demo data never purchasable.
  actual: Demo data mixed into commerce flows.
  impact: Wrong products added to carts; outages disguised as missing data.
  fix: Apply the documented "Fetch Error Propagation / Demo Fallback Policy" follow-up — propagate errors to route boundaries, and at minimum mark demo items non-purchasable.
  regression_test: With fetch mocked to reject, add-to-cart is disabled or absent for fallback products.
  effort: M
  release_blocking: no
  dependencies: policy decision (TASK-048)
  related: [review-state Phase 2K note, BUG-071]

- id: BUG-036
  title: A successful Console refund is reported as failed if the follow-up refetch fails; the modal stays armed
  severity: P2
  confidence: Medium   # needs a transient failure to trigger
  status: Confirmed
  category: [A Functional]
  verified: C
  location:
    - frontend/src/app/admin/payments/paymentGovernance.tsx:270-284   # refund POST and detail GET share one try/catch (:278, :282)
  symbol: useRefundPaymentAction.confirm
  explanation: If the GET after a successful refund fails, the operator sees "Failed to process refund" with the modal still open and the same amount filled in. Clicking again can issue a second refund when the amount fits the remaining balance.
  repro: Refund POST returns 201, then the payment GET fails.
  expected: 'The UI reports "Refund issued; refresh failed" and closes the modal.'
  actual: An error and a re-submittable modal.
  impact: Money operations mis-reported; possible duplicate refund.
  fix: Split the two steps, close the modal on POST success, and add an idempotency key on the refund endpoint.
  regression_test: Mock POST ok and GET failing → modal closes and success is shown.
  effort: S
  release_blocking: no
  dependencies: none
  related: [BUG-057, BUG-076]

- id: BUG-037
  title: Dark-mode storefront header icons and text are near-invisible (Known #34, still open)
  severity: P2
  confidence: High
  status: Confirmed
  category: [B Frontend]
  verified: A
  location:
    - frontend/src/app/globals.css:31   # --color-on-nav falls back to --c-on-primary unless --c-on-nav is set
    - frontend/src/app/globals.css:91, 105, 109   # default dark theme: on-primary #0C151C on nav #0F1A24 (per auditor)
    - frontend/src/components/layout/Header.tsx:58   # bg-nav text-on-nav
  symbol: theme tokens
  explanation: Only the kolapata theme defines --c-on-nav. In the default, sumi and matsu dark modes, header icons, the account name and the bell render dark-on-dark.
  repro: Switch to dark mode in the default theme.
  expected: Readable header.
  actual: Near-invisible header row.
  impact: The header is unusable in dark mode.
  fix: Define --c-on-nav in every theme and dark block.
  regression_test: A contrast check for each theme (manual, or a Playwright/Chrome screenshot).
  effort: S
  release_blocking: no
  dependencies: none
  related: ["Known #34"]
```

### 3.4 P3 — Low

Each P3 entry keeps every required field on one line.

```yaml
- {id: BUG-038, title: "Django admin dashboard shows revenue and payment mix to every staff account", severity: P3, confidence: High, status: Confirmed, category: "E Security", verified: C,
   location: ["backend/config/admin_site.py:69-77 (index passes get_platform_metrics())", "backend/templates/admin/index.html:80 (revenue tile)", "contrast backend/shop/admin_views.py:1466-1467 (API pops total_revenue without payments.view)"],
   symbol: "MiniShopAdminSite.index", explanation: "The template has no permission checks; any is_staff account sees finance figures that the API deliberately gates.",
   repro: "A staff user without payments.view opens /admin/.", expected: "Revenue hidden.", actual: "Revenue shown.", impact: "Finance data disclosed to non-finance staff.",
   fix: "Compute and pass gated blocks only when has_user_permission(user, 'payments.view').", regression_test: "Staff without payments.view → response lacks the revenue figure.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-039, title: "Saving a user's change form deactivates their direct grants that render as locked", severity: P3, confidence: High, status: Confirmed, category: "I Integrity", verified: C,
   location: ["backend/rbac/widgets.py:446 (locked = inherited or full_access)", "backend/templates/admin/widgets/minishop_permission_matrix.html:126 (disabled → not submitted)", "backend/rbac/admin.py:482-493, 513-516 (missing ids → is_active=False)"],
   symbol: "UserAdmin.save_related", explanation: "Disabled checkboxes post nothing, so any save deactivates every direct grant of a superuser or SUPER_ADMINISTRATOR target, plus grants a role also provides. They are lost if the role is later removed. RoleAdmin already guards this pitfall (:170-175).",
   repro: "A superuser edits only the email of a user with a direct grant and the SUPER_ADMINISTRATOR role; the role is later removed and the grant is gone.", expected: "Untouched grants preserved.", actual: "Silently revoked.", impact: "Silent loss of access configuration.",
   fix: "Diff only the editable (non-locked) permission ids.", regression_test: "Unchanged form post keeps the grant active.", effort: XS, release_blocking: no, dependencies: none, related: [BUG-002]}

- {id: BUG-040, title: "Registration and Console account creation skip Django's username validator", severity: P3, confidence: High, status: Confirmed, category: "A Functional / C Backend", verified: C,
   location: ["backend/rbac/serializers.py:48 (plain CharField)", "backend/shop/admin_serializers.py:149 (Console account username, per auditor)"],
   symbol: "CustomerRegistrationSerializer", explanation: "Usernames with spaces or other disallowed characters are accepted. Django admin's UserChangeForm later refuses to save those users. The iexact duplicate pre-check is check-then-act, so a race gives IntegrityError → 500.",
   repro: "Register 'john doe' → 201; then edit that user in Django admin → 'Enter a valid username'.", expected: "400 at registration.", actual: "Accepted.", impact: "Unmanageable accounts; sporadic 500s.",
   fix: "validators=[UnicodeUsernameValidator()]; map IntegrityError to 400.", regression_test: "Register 'john doe' → 400.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-041, title: "Deleting a user erases attribution on all their audit rows", severity: P3, confidence: High, status: Confirmed, category: "I Integrity", verified: C,
   location: ["backend/audit/models.py:10-12 (actor FK on_delete=SET_NULL)", "backend/audit/models.py:84 (renders 'System')"],
   symbol: "AuditLog.actor", explanation: "No actor snapshot is stored. Deleting a staff account turns their audit history into 'System'.",
   repro: "Log an action, delete the actor, view the audit log.", expected: "The actor is still identified.", actual: "'System'.", impact: "Audit attribution is not immutable.",
   fix: "Snapshot actor_username/actor_id at write time, or PROTECT plus deactivate instead of delete.", regression_test: "Row still names the actor after deletion.", effort: S, release_blocking: no, dependencies: none}

- {id: BUG-042, title: "Django's nav_sidebar.js throws a TypeError on every Django admin page (Known #36)", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: A,
   location: ["backend/templates/admin/nav_sidebar.html (no #nav-filter element)", "django/contrib/admin/static/admin/js/nav_sidebar.js:66-67 (getElementById('nav-filter').addEventListener)"],
   symbol: "admin nav sidebar", explanation: "The custom sidebar removed the filter input that Django's script dereferences.",
   repro: "Open any /admin/ page with the browser console open.", expected: "No JS error.", actual: "TypeError.", impact: "Console noise; later admin scripts on the page may not run.",
   fix: "Add a hidden #nav-filter input or stop loading nav_sidebar.js.", regression_test: "Render contains id=\"nav-filter\" or no nav_sidebar.js.", effort: XS, release_blocking: no, dependencies: none, related: ["Known #36"]}

- {id: BUG-043, title: "User uploads, including customer avatars, are committed to git; media and log ignore rules missing or ineffective", severity: P3, confidence: High, status: Confirmed, category: "H Config / E Privacy", verified: C,
   location: ["git ls-files backend/media → 92 files incl. 3 under backend/media/customers/avatars/ (names withheld)", "backend/.gitignore (no media/ or *.log rule)", "backend/.gitignore:19 (rule for a file that is tracked anyway)", "backend/server-8000.out.log, backend/server-8000.err.log (tracked)", "backend/README.md:145 (claims media/ is gitignored)"],
   symbol: "repository hygiene", explanation: "MEDIA_ROOT is inside the repo and not ignored, so runtime uploads land in unrelated commits. For example, commit d35cc9d ('feat(theme)…') added two customer avatars.",
   repro: "git show --stat d35cc9d.", expected: "Uploads never tracked.", actual: "Personal photos in history.", impact: "Personal data in the repository and its history.",
   fix: "Ignore media/ and *.log; git rm --cached user uploads (move seed images to a fixtures dir); consider purging history; fix the README.", regression_test: "CI check that no file under backend/media/customers is tracked.", effort: S, release_blocking: no, dependencies: none}

- {id: BUG-044, title: "Seller shop update: PUT or explicit null coordinates give 500; responses carry pre-update data", severity: P3, confidence: High, status: Confirmed, category: "C Backend", verified: C,
   location: ["backend/shops/serializers.py:166-167 (FloatField default=None)", "backend/shops/services.py:221-222 and :58-59 (validate_coordinates(None, None) raises Django ValidationError)", "backend/shops/views.py:234-240 (perform_update re-fetches the shop; only IneligibleSellerError caught)"],
   symbol: "SellerShopUpdateView", explanation: "A Django ValidationError is not handled by DRF, so the response is 500. The update runs on a second instance while the response is built from the first.",
   repro: "PUT /api/shops/mine/<pk>/update/ with name only, or PATCH {latitude:null, longitude:null}.", expected: "400, or 200 with new values.", actual: "500, or stale 200.", impact: "API-only today (the UI PATCHes without coordinates and refetches).",
   fix: "Only take the coordinate branch when values are not None; map ValidationError to 400; update serializer.instance.", regression_test: "PUT name-only → 200/400, never 500; PATCH response shows the new name.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-045, title: "IsShopOwner lets shops.update staff through; the views then dereference request.user.seller_profile (500)", severity: P3, confidence: High, status: Confirmed, category: "C Backend", verified: C,
   location: ["backend/shops/permissions.py:70-74 (superuser / shops.update → True)", "backend/shops/views.py:236, 254, 289 (request.user.seller_profile)"],
   symbol: "IsShopOwner", explanation: "Staff without a seller profile raise RelatedObjectDoesNotExist; staff with one get a PermissionDenied from the service. The bypass is never useful.",
   repro: "An Administrator without a seller profile PATCHes /api/shops/mine/<pk>/update/.", expected: "403.", actual: "500.", impact: "Spurious 500s.",
   fix: "Drop the staff bypass on seller-only views (staff use the Console).", regression_test: "Staff PATCH → 403.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-046, title: "Django admin seller/shop/product edits bypass the Limited-owner product cap, the product points cost and auditing", severity: P3, confidence: Medium, status: Confirmed, category: "A Functional / I Integrity", verified: C,
   location: ["backend/shop/admin.py:195 (ProductAdmin can add products or move them between shops; no save_model)", "backend/shops/admin.py:16-27 (clean_owner checks only the shop cap, without a lock)", "backend/sellers/admin.py:33-44 (clean_seller_type checks only the shop count)", "backend/sellers/admin.py:86 (SellerProfile.user editable: re-homes wallet and shops with no AuditLog)"],
   symbol: "ProductAdmin, ShopAdminForm.clean_owner, SellerProfileAdmin", explanation: "The cap (698fa84) and the always-charge rule (ebd71c5) are enforced only in ProductService.create_product.",
   repro: "Admin adds an 11th product to a Limited owner's shop (limit 10), or reassigns a shop full of products to a Limited owner.", expected: "Refused.", actual: "Accepted; no points debited; no audit.", impact: "Over-quota sellers; free listings; unaudited ownership moves.",
   fix: "ProductAdmin form clean applying the product limit; decide on charging for admin-created products; extend clean_owner/clean_seller_type with the product cap; lock the owner row; audit ownership edits.", regression_test: "Admin POSTs over the cap return 200 with a form error.", effort: S, release_blocking: no, dependencies: none, related: [BUG-021]}

- {id: BUG-047, title: "Clearing is_superuser makes the user's held points expire at once", severity: P3, confidence: Medium, status: Confirmed, category: "I Integrity", verified: A,
   location: ["backend/points/services.py:58-60 (staff_points_expire: points_expire and not is_superuser)", "backend/points/services.py:711-721 (restart_expiry_clock — callers are only sellers/admin.py:74 and set_staff_points_expire)", "backend/rbac/admin.py:374-376 (is_superuser editable)"],
   symbol: "PointService", explanation: "A superuser's lots are dated at receipt but never expire. Demotion makes every lot older than the policy due immediately.",
   repro: "Mint points, age the lots 90 days, untick is_superuser.", expected: "Balance unchanged and the expiry clock restarted.", actual: "Points expire on the next read.", impact: "Unintended loss of points.",
   fix: "In UserAdmin.save_model, on a True→False superuser change, lock the wallet, call restart_expiry_clock and audit it.", regression_test: "As in repro → balance unchanged.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-048, title: "Staff can renew point expiry indefinitely by crediting then debiting a seller", severity: P3, confidence: Medium, status: Probable, category: "I Integrity", verified: A,
   location: ["backend/points/services.py:264-266 (debit path)", "backend/points/services.py:538-541 (every inflow becomes a fresh lot)", "backend/points/services.py:561-571 (expires_at = expiry_for(now))"],
   symbol: "PointService.adjust_points / _add_lot", explanation: "Take-back mints a new lot with a full period, defeating superuser-controlled expiry. Probable because the design intent is unclear (test_expiry gives fresh clocks on purpose for giving).",
   repro: "A staff lot expiring tomorrow: credit 10 to a seller, then debit 10 back → the staff lot now expires in about 2 months.", expected: "The original expiry is carried back.", actual: "Renewed.", impact: "The expiry policy can be bypassed (visible in the ledger).",
   fix: "Carry the consumed lots' expires_at into the returning lot.", regression_test: "As in repro → still about 1 day.", effort: S, release_blocking: no, dependencies: "policy decision (TASK-048)"}

- {id: BUG-049, title: "/api/shops/staff/* status endpoints write no AuditLog and take no row lock", severity: P3, confidence: High, status: Confirmed, category: "E Security / I Integrity", verified: C,
   location: ["backend/shops/views.py:350-435 (e.g. :358 get_object_or_404 then ShopService.approve_shop; no AuditService.log)", "backend/shops/urls.py:38-41 (routes live)"],
   symbol: "StaffShopApproveView / RejectView / SuspendView / ReactivateView", explanation: "Same gap as Known #23 (fixed for sellers): unlocked read-check-write and no governance audit row. No frontend caller, but the API is live.",
   repro: "POST /api/shops/staff/<pk>/approve/ → no ADMIN_SHOP_* AuditLog.", expected: "Audited and locked, like AdminShopStatusAPIView.", actual: "Neither.", impact: "Unaudited shop lifecycle changes; racing approve/reject.",
   fix: "Mirror AdminShopStatusAPIView (atomic + select_for_update + AuditService.log), or retire the routes.", regression_test: "Each action writes exactly one audit row.", effort: S, release_blocking: no, dependencies: none, related: ["Known #23", BUG-015]}

- {id: BUG-050, title: "Console seller status view lets Django ValidationError escape (500)", severity: P3, confidence: High, status: Confirmed, category: "C Backend", verified: C,
   location: ["backend/shop/admin_views.py:860-875 (no try/except around the lifecycle calls)", "backend/sellers/models.py:130-132 (activate raises ValidationError)", "contrast backend/shop/admin_views.py:1134-1135 (shop view maps it to 400)"],
   symbol: "AdminSellerStatusAPIView", explanation: "Reactivating an ACTIVE, PENDING or REJECTED seller raises a Django ValidationError, which DRF does not handle.",
   repro: "{\"action\":\"reactivate\"} on an ACTIVE seller.", expected: "400.", actual: "500.", impact: "Spurious 500s; worsens once BUG-017 adds more guards.",
   fix: "Wrap the calls the way the shop view does.", regression_test: "Reactivate ACTIVE → 400.", effort: XS, release_blocking: no, dependencies: "do with BUG-017", related: [BUG-017]}

- {id: BUG-051, title: "Payment failure_reason and metadata are never persisted", severity: P3, confidence: High, status: Confirmed, category: "A Functional", verified: C,
   location: ["backend/shop/payment_service.py:239-243 (fields set, then transition_to)", "backend/shop/models.py:752-763 (transition_to saves only status/updated_at/paid_at)"],
   symbol: "PaymentService.process_payment_failure", explanation: "The values exist only on the in-memory instance; the existing test asserts res.data, not refresh_from_db().",
   repro: "Mark a payment failed with a reason, then reload it.", expected: "Reason stored.", actual: "Blank.", impact: "Staff console shows no failure reason.",
   fix: "Include failure_reason and metadata in the save.", regression_test: "refresh_from_db() shows the reason.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-052, title: "A second full-amount payment can be started after a refund", severity: P3, confidence: Medium, status: Confirmed, category: "A Functional", verified: C,
   location: ["backend/shop/payment_service.py:66-97 (only STATUS_PAID counts as already paid; payable = full total)"],
   symbol: "PaymentService.create_or_get_payment", explanation: "PARTIALLY_REFUNDED and REFUNDED payments are not treated as paid, so a new PENDING payment for the full total is created. current_payment then reports PENDING.",
   repro: "Partially refund a payment, then POST /api/orders/<n>/payment/.", expected: "Refused, or a deliberate re-payment flow.", actual: "New full-amount payment.", impact: "Possible double charge if staff verify it.",
   fix: "Treat PAID, PARTIALLY_REFUNDED and REFUNDED as already paid.", regression_test: "As in repro → 400.", effort: XS, release_blocking: no, dependencies: "TASK-015", related: [BUG-012]}

- {id: BUG-053, title: "Orders are accepted with blank or placeholder shipping addresses", severity: P3, confidence: High, status: Confirmed, category: "C Backend", verified: A,
   location: ["backend/shop/services.py:601-640 (address_data branch accepts blanks; fallback line_1 'Standard Delivery Address', city 'Dhaka')"],
   symbol: "OrderService.create_order_from_cart", explanation: "Only the frontend validates the address. Any non-empty body, or no address at all, creates an order.",
   repro: "POST /api/orders/ with {\"phone\":\"\"}.", expected: "400.", actual: "Order with a blank or invented address.", impact: "Undeliverable orders.",
   fix: "Require address_id or a non-blank recipient, phone, line 1 and city; drop the placeholder.", regression_test: "Empty address → 400.", effort: S, release_blocking: no, dependencies: none}

- {id: BUG-054, title: "Read-only orders.staff.view lets the holder create or modify payments on any customer's order", severity: P3, confidence: High, status: Confirmed, category: "E Security", verified: C,
   location: ["backend/shop/api_views.py:984-989 (staff override = CanViewStaffOrders)", "backend/shop/api_views.py:1001, 1012-1028 (POST creates a payment or changes its method)"],
   symbol: "CustomerOrderPaymentAPIView.post", explanation: "FINANCE and SUPPORT_TEAM hold orders.staff.view and pass the ownership check on the write path.",
   repro: "SUPPORT_TEAM user POSTs /api/orders/<someone's order>/payment/.", expected: "403/404.", actual: "Payment created or changed.", impact: "Writes through a read permission.",
   fix: "Require ownership, or a write permission, on POST.", regression_test: "SUPPORT_TEAM POST → 404.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-055, title: "Seller order payloads expose the whole-order total and customer account names", severity: P3, confidence: High, status: Confirmed, category: "E Security", verified: C,
   location: ["backend/shop/serializers.py:513, 575 (total_amount in the seller list and detail serializers)", "backend/shop/serializers.py:702-705 (InventoryTransactionSerializer.get_actor_name → customer name on RESERVATION rows)"],
   symbol: "SellerOrderListSerializer, SellerOrderDetailSerializer, InventoryTransactionSerializer", explanation: "On multi-seller orders, total_amount reveals other merchants' item values, contradicting the seller-scoped design (seller_subtotal exists). The transactions query also has no select_related.",
   repro: "Seller A views a mixed order.", expected: "Seller-scoped figures only.", actual: "Whole-order total.", impact: "Cross-merchant data leak.",
   fix: "Drop total_amount for sellers; mask non-staff actors; add select_related.", regression_test: "Seller payload has no total_amount.", effort: XS, release_blocking: no, dependencies: "TASK-012"}

- {id: BUG-056, title: "Staff cancel via the customer endpoint: the view and the service disagree on who is staff", severity: P3, confidence: High, status: Confirmed, category: "C Backend", verified: C,
   location: ["backend/shop/api_views.py:443 (view: CanUpdateStaffOrders)", "backend/shop/services.py:894-903 (service: is_superuser / is_staff / role codes)"],
   symbol: "CustomerOrderCancelAPIView / OrderService.cancel_order", explanation: "SUPPORT_TEAM holds orders.staff.update, passes the view, then gets 403 from the service.",
   repro: "A SUPPORT_TEAM user cancels a customer order.", expected: "One consistent rule.", actual: "403.", impact: "Support staff cannot cancel orders.",
   fix: "Use the RBAC check in the service.", regression_test: "SUPPORT_TEAM cancel → 200.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-057, title: "Only one partial refund per payment (Known #26, still open)", severity: P3, confidence: High, status: Confirmed, category: "A Functional", verified: C,
   location: ["backend/shop/models.py:659-667 (PARTIALLY_REFUNDED → [REFUNDED] only)"],
   symbol: "Payment.VALID_TRANSITIONS", explanation: "A second partial refund that still leaves a balance needs PARTIALLY_REFUNDED → PARTIALLY_REFUNDED.",
   repro: "Refund ৳100 of ৳1,000, then ৳100 again.", expected: "Second refund accepted.", actual: "Validation error.", impact: "Staff cannot issue staged refunds.",
   fix: "Allow the self-transition.", regression_test: "Two partial refunds succeed.", effort: XS, release_blocking: no, dependencies: "check BUG-036 (duplicate-refund risk grows after this fix)", related: ["Known #26"]}

- {id: BUG-058, title: "Inconsistent lock ordering leads to MySQL deadlocks surfacing as 500", severity: P3, confidence: Medium, status: Probable, category: "D Database / I Reliability", verified: A,
   location: ["backend/shop/payment_service.py:151, 165 (Payment then Order)", "backend/shop/payment_service.py:404 with the services.py cancel path (Order then Payments)", "backend/cart/models.py:72 (inventory locked in cart created_at order)"],
   symbol: "PaymentService, InventoryService.reserve_stock_for_cart", explanation: "Opposite acquisition orders deadlock. MySQL rolls one transaction back, which keeps the data consistent, but the user gets a raw 500.",
   repro: "Concurrent verify and cancel on one order; two carts locking P1,P2 vs P2,P1.", expected: "No deadlock, or a 409 retry.", actual: "500.", impact: "Sporadic checkout/payment failures.",
   fix: "Canonical order (Order before Payment; inventory sorted by product_id); retry or 409 on MySQL error 1213.", regression_test: "MySQL concurrency test.", effort: S, release_blocking: no, dependencies: "verify on MySQL"}

- {id: BUG-059, title: "Check-then-insert races return 500 (address default switching, first cart add, shop slug)", severity: P3, confidence: High, status: Confirmed, category: "D Database", verified: C,
   location: ["backend/customers/services.py:214, 276, 318 (select_for_update querysets built but never evaluated → no lock)", "backend/customers/services.py:165-166 (first address: no rows to lock under READ COMMITTED)", "backend/customers/models.py:123-128 (unique default constraint)", "backend/cart/services.py:104-123 (first add of a product, per auditor)", "backend/shops/models.py:152-159 (slug generation, per auditor)"],
   symbol: "AddressService, CartService.add_item, Shop.save", explanation: "Lazy querysets never run, so the documented locks do nothing. Concurrent requests hit unique constraints and the IntegrityError is not caught.",
   repro: "Two tabs calling set-default on different addresses; a double-submitted first address.", expected: "Serialized requests, 2xx.", actual: "One 500.", impact: "Sporadic 500s on address, cart and shop creation (no corruption — the constraints hold).",
   fix: "Lock the parent User row, or list() the queryset; re-read inside the transaction; map IntegrityError to 409; use get_or_create.", regression_test: "TransactionTestCase with two threads → both 2xx, one default.", effort: S, release_blocking: no, dependencies: none}

- {id: BUG-060, title: "Upload and profile validation gaps: avatar API, product and shop images unbounded", severity: P3, confidence: High, status: Confirmed, category: "E Security / C Backend", verified: C,
   location: ["backend/customers/serializers.py:46-48 (phone free text, avatar ImageField only, DOB unbounded)", "contrast backend/config/admin_profile.py:62-63, 162-189 (admin form: 2 MB, JPEG/PNG/WEBP, phone and DOB checks)", "backend/shop/serializers.py:224 and frontend/src/app/seller/products/page.tsx:193-201 (product image: no size or type limit)", "backend/shops/models.py:40-41 (shop logo/cover: no size limit, per auditor)"],
   symbol: "CustomerProfileUpdateSerializer, product/shop image fields", explanation: "Any Pillow-readable format and any size is written to public MEDIA_ROOT. No FILE_UPLOAD_* / DATA_UPLOAD_* limits are configured.",
   repro: "PATCH /api/profile/me/ with a very large PNG, a GIF/TIFF avatar, or date_of_birth 2099-01-01.", expected: "400, as in the admin form.", actual: "Accepted.", impact: "Disk exhaustion; formats browsers don't render; junk profile data.",
   fix: "Shared validators (size, format allow-list, phone, DOB range) used by the API and admin; a proxy body limit in production.", regression_test: "Each case → 400.", effort: S, release_blocking: no, dependencies: none}

- {id: BUG-061, title: "Favorites always report average_rating 0 and review_count 0 (Known #7)", severity: P3, confidence: High, status: Confirmed, category: "A Functional", verified: A,
   location: ["backend/customers/views.py:188-195 (no annotations)", "backend/shop/serializers.py:88-89, 124-126 (serializer defaults)"],
   symbol: "FavoriteListCreateView", explanation: "ProductListSerializer relies on annotations that the favorites queryset does not add.",
   repro: "Favorite a reviewed product; GET /api/favorites/.", expected: "Real rating.", actual: "0.0 / 0.", impact: "Wrong ratings on wishlist cards.",
   fix: "Prefetch products annotated with the visible-review Avg/Count.", regression_test: "2 visible + 1 hidden review → count 2.", effort: XS, release_blocking: no, dependencies: none, related: ["Known #7"]}

- {id: BUG-062, title: "Support public status lines use staff wording (Known #33)", severity: P3, confidence: High, status: Confirmed, category: "A Functional", verified: C,
   location: ["backend/support/services.py:58, 465, 495 (STATUS_LABELS from STATUS_CHOICES)", "backend/support/serializers.py:15-21 (customer labels used only for the badge)"],
   symbol: "SupportTicketService._set_status callers", explanation: "Public notes say 'Waiting on customer' while the badge says 'Waiting on you'.",
   repro: "Staff move a ticket to WAITING_ON_CUSTOMER.", expected: "Customer wording.", actual: "Staff wording.", impact: "Confusing copy.",
   fix: "Build public notes from the customer label map.", regression_test: "The note uses 'Waiting on you'.", effort: XS, release_blocking: no, dependencies: none, related: ["Known #33"]}

- {id: BUG-063, title: "Support attachments reject multi-picture (MPO) JPEGs", severity: P3, confidence: Medium, status: Probable, category: "A Functional", verified: C,
   location: ["backend/support/validators.py:24-27 (_IMAGE_TYPES has no MPO)", "backend/support/validators.py:119-136 (_detect_type returns _IMAGE_TYPES.get(image.format))"],
   symbol: "_detect_type", explanation: "Pillow reports format 'MPO' for JPEGs that embed an MPF secondary image (depth or gain maps from some phones), so a valid .jpg is refused. How common this is cannot be known from source.",
   repro: "Attach an MPO JPEG.", expected: "Accepted as image/jpeg.", actual: "'not a JPG, PNG, WebP or PDF file'.", impact: "Some real photos cannot be attached.",
   fix: "Map 'MPO' to ('image/jpeg', 'jpg').", regression_test: "Pillow-generated MPO accepted.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-064, title: "Notification preferences PUT returns 500 on malformed or concurrent input", severity: P3, confidence: High, status: Confirmed, category: "C Backend", verified: A,
   location: ["backend/notifications/preferences.py:100-107 (code not in allowed → TypeError for a list/dict category)", "backend/notifications/preferences.py:145 (create without upsert)", "backend/notifications/models.py:199 (unique constraint)"],
   symbol: "parse_preference_changes, apply_preference_changes", explanation: "A non-string category raises TypeError rather than PreferenceError; two concurrent PUTs raise IntegrityError.",
   repro: "PUT [{\"category\":[\"ORDERS\"],\"channels\":{}}].", expected: "400 / idempotent success.", actual: "500.", impact: "Spurious 500s.",
   fix: "isinstance check; update_or_create.", regression_test: "List-valued category → 400.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-065, title: "A notification email can be sent twice when one SMTP send outlasts the 60 s lease", severity: P3, confidence: Medium, status: Probable, category: "I Reliability", verified: A,
   location: ["backend/notifications/worker.py:110-116 (expired PROCESSING rows are re-claimable)", "backend/notifications/worker.py:156-167 (lease renewed once, before the send)", "backend/notifications/worker.py:273-302 (_deliver)", "backend/config/settings/base.py:251 (LEASE_SECONDS 60; EMAIL_TIMEOUT 10 s per socket operation)"],
   symbol: "NotificationWorker._deliver", explanation: "A full SMTP exchange can exceed 60 s even though each step times out at 10 s. A second worker then reclaims the row and sends again. Design decision D4 accepts duplicates only on a crash.",
   repro: "A slow or tarpitting SMTP relay with two workers.", expected: "One email.", actual: "Two.", impact: "Duplicate customer emails.",
   fix: "Make the per-channel lease exceed the worst-case send, or heartbeat-renew during the send, or document the case under D4.", regression_test: "Adapter sleeping past a short lease → one send.", effort: S, release_blocking: no, dependencies: none}

- {id: BUG-066, title: "Unvalidated inputs raise 500 instead of 400; audit-log date filters bucket by UTC", severity: P3, confidence: High, status: Confirmed, category: "C Backend", verified: C,
   location: ["backend/shop/admin_views.py:1179-1185 (category / shop query params passed straight to filter)", "backend/shop/admin_views.py:1536-1542 (start_date / end_date; __date in UTC, TIME_ZONE base.py:167)", "backend/shop/api_views.py:498-500 (seller shop_id)", "backend/support/views.py:418 (isdigit() accepts Unicode digits; int() then fails)", "unbounded integers (inventory adjust quantity, seller stock, point amounts) → DataError (per auditors)"],
   symbol: "Console and seller list views", explanation: "ValueError and ValidationError raised inside filter(), and DataError on overflow, are not mapped to 400. Events between 00:00 and 05:59 Bangladesh time fall on the previous date.",
   repro: "?category=abc or ?start_date=2026-13-40.", expected: "400; local-day ranges.", actual: "500; UTC days.", impact: "Spurious 500s; off-by-one-day audit filtering.",
   fix: "Parse and validate params explicitly; add max values; build aware Asia/Dhaka [start, end+1) ranges.", regression_test: "Bad params → 400; a log at 02:00 BST is included in that BST day.", effort: S, release_blocking: no, dependencies: none}

- {id: BUG-067, title: "N+1 queries in Console list serializers", severity: P3, confidence: High, status: Confirmed, category: "F Performance", verified: A,
   location: ["backend/shop/admin_views.py:144 (users queryset without select_related/prefetch)", "backend/shop/admin_serializers.py (approximate: per-row role codes and profile checks in the user serializer)", "backend/shop/admin_serializers.py:831 (get_orders_count per customer)", "backend/shop/admin_views.py:908 (prefetches every product just to count)"],
   symbol: "Admin list serializers", explanation: "About 3 queries per row on the users list (300+ at page_size=100), plus similar per-row counts elsewhere.",
   repro: "assertNumQueries on /api/admin/users/?page_size=100 (not run).", expected: "Constant number of queries.", actual: "Linear.", impact: "Slow Console lists against the remote database.",
   fix: "annotate(Count), select_related profiles, Prefetch active roles.", regression_test: "assertNumQueries on each list.", effort: S, release_blocking: no, dependencies: none}

- {id: BUG-068, title: "Seed commands mutate non-demo rows with no environment guard", severity: P3, confidence: High, status: Confirmed, category: "I Integrity", verified: C,
   location: ["backend/shop/management/commands/seed_demo_data.py:301-305 (re-homes and publishes any product whose slug matches)", "backend/shop/management/commands/seed_showcase.py:281-283 (resets an existing account's password when --password is given)", "seed_showcase.py:302-306 (takes over a matching shop's owner)", "seed_showcase.py:354-358 (takes over a matching product)", "seed_showcase.py:372-375 (sets inventory without a ledger row)", "seed_showcase.py:285-286 (grants SALES_TEAM)"],
   symbol: "seed_demo_data, seed_showcase", explanation: "Matching is by slug or username, so real rows are overwritten. backend/.env points the dev settings at a shared remote MySQL database. No hardcoded password (the default is an unusable password).",
   repro: "Run seed_showcase against a database with a real product whose slug matches.", expected: "Only rows owned by the seeder are touched.", actual: "Real rows rewritten.", impact: "Data damage on a shared database.",
   fix: "Refuse to run unless DEBUG and an explicit flag; touch only seeder-owned rows; use InventoryService.", regression_test: "Command refuses without the flag.", effort: S, release_blocking: no, dependencies: none, related: [BUG-004]}

- {id: BUG-069, title: "Product PATCH accepts category_id / shop_id but silently ignores them", severity: P3, confidence: High, status: Confirmed, category: "A Functional / G Integration", verified: C,
   location: ["backend/shop/serializers.py:277-278 (category_id field)", "backend/shop/services.py:259 (checks 'shop', not 'shop_id')", "backend/shop/services.py:267-269 (updatable_fields lists 'category', not 'category_id')"],
   symbol: "SellerProductUpdateSerializer / ProductService.update_product", explanation: "The keys never match, so the API returns 200 without change. Sellers can fix a wrong category only by deleting and recreating the product, which costs points again.",
   repro: "PATCH {category_id: <other>} → 200, category unchanged.", expected: "Category changed.", actual: "Ignored.", impact: "Silent no-op; extra points spent.",
   fix: "Map category_id→category and shop_id→shop; expose Category in the edit form.", regression_test: "PATCH category_id changes product.category.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-070, title: "Multipart product edit cannot clear old_price (FormData drops nulls)", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/lib/api.ts:1521-1526 (null/undefined skipped)", "frontend/src/app/seller/products/page.tsx:279, 284"],
   symbol: "updateSellerProduct", explanation: "The JSON path sends old_price:null; the multipart path (used when a new image is chosen) omits it.",
   repro: "Clear Old Price and change the image in one save.", expected: "Strike-through price removed.", actual: "Remains.", impact: "Stale discount display.",
   fix: "Send an empty string for null and treat blank as null server-side.", regression_test: "Multipart save clears old_price.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-071, title: "Seller products page says 'no shop assigned' when the shops call failed; demo categories used in the seller form", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/app/seller/products/page.tsx:118 (getSellerShops(...).catch(() => {}))", "frontend/src/app/seller/products/page.tsx:359-367 (no-shop message)", "backend/shops/permissions.py:47-50 (non-operational seller → 403)", "frontend/src/lib/api.ts:258-259 (DEMO_CATEGORIES fallback)"],
   symbol: "SellerProductsPage", explanation: "Suspended, pending and rejected sellers get a 403 and are told they have no shop. A failed categories fetch offers demo ids that may not exist.",
   repro: "Suspended seller opens Products.", expected: "The real reason.", actual: "'You have not been assigned a Shop yet'.", impact: "Misleading guidance.",
   fix: "Use useSeller().seller.is_operational; surface errors; never use demo categories here.", regression_test: "Non-operational seller sees the status message.", effort: S, release_blocking: no, dependencies: none, related: [BUG-035]}

- {id: BUG-072, title: "refreshDashboard() unmounts the whole Seller Center (the profile success message is lost)", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: A,
   location: ["frontend/src/components/seller/SellerGuard.tsx:47-49, 81-92, 107 (setLoading(true) → full-screen spinner replaces the tree)", "frontend/src/app/seller/profile/page.tsx:133-135"],
   symbol: "SellerGuard.fetchDashboard", explanation: "A background refresh re-uses the initial loading flag.",
   repro: "Save the seller profile.", expected: "Success message stays.", actual: "Page remounts; message gone.", impact: "Users can't tell the save worked.",
   fix: "Separate the initial loading flag from a refreshing flag.", regression_test: "Message present after refresh.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-073, title: "List pages accept stale, out-of-order responses (no request key or abort)", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: A,
   location: ["frontend/src/app/seller/products/page.tsx:86-111", "frontend/src/app/seller/orders/page.tsx:42-81", "frontend/src/app/seller/wallet/page.tsx:27-49", "frontend/src/app/admin/users/page.tsx:119-150, plus the sellers, shops, products, categories, customers, orders, payments and audit-logs pages, and sellers/[id] history", "frontend/src/components/notifications/NotificationInbox.tsx:109-124 (loadMore)"],
   symbol: "list fetch effects", explanation: "A slower earlier response can overwrite results for newer filters. The correct pattern already exists in admin/reviews/page.tsx:107-131.",
   repro: "Change a filter while the previous request is in flight.", expected: "Latest request wins.", actual: "Earlier response may win.", impact: "Operators act on rows that don't match the visible filters.",
   fix: "Request key or AbortController in effect cleanup.", regression_test: "Two deferred promises resolved out of order → latest shown.", effort: S, release_blocking: no, dependencies: "TASK-042"}

- {id: BUG-074, title: "Console debounced search commits a stale URL snapshot and drops filters changed within 350 ms", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/app/admin/users/page.tsx:102-110 (deps [searchInput] only, eslint-disable)", "same pattern on sellers, shops, products, categories, customers, orders, payments, roles and audit-logs (:99-117)"],
   symbol: "debounced search effects", explanation: "The timer calls updateParams captured from an old render.",
   repro: "Type a search, then change Status within 350 ms.", expected: "Both params kept.", actual: "Status reverts.", impact: "Lost filter selections.",
   fix: "Full dependencies, as in admin/reviews/page.tsx:96-101.", regression_test: "Fake timers keep both params.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-075, title: "Console seller points history: post-adjustment refresh fetches the old page and races page 1", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/app/admin/sellers/[id]/page.tsx:346-348 (fetchWallet; setHistoryPage(1); fetchHistory())", "frontend/src/app/admin/sellers/[id]/page.tsx:281 (fetchHistory deps include historyPage)"],
   symbol: "confirmAdjustment", explanation: "The explicit call uses the stale page, while the effect fetches page 1.",
   repro: "Adjust points while on history page 3.", expected: "Page 1 with the new row.", actual: "Sometimes page-3 rows under a page-1 pager.", impact: "New transaction not visible.",
   fix: "Drop the explicit fetchHistory() call.", regression_test: "One request, for page 1.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-076, title: "Console refund: a blank or unparseable amount silently becomes a full refund", severity: P3, confidence: Medium, status: Probable, category: "A Functional", verified: C,
   location: ["frontend/src/app/admin/payments/[id]/page.tsx:325-339 (type=number input)", "frontend/src/app/admin/payments/paymentGovernance.tsx:245-246, 259-268 (blank → omit amount → full refund)"],
   symbol: "refund modal", explanation: "Number inputs report invalid text ('1,500' in Firefox, '12.5.0') as an empty string, and blank means 'full remaining amount'. The confirm text does show the full amount.",
   repro: "Type '1,500' in Firefox.", expected: "Submit disabled.", actual: "Full refund requested.", impact: "An intended partial refund becomes full.",
   fix: "Text input with regex validation; an explicit 'Full refund' toggle.", regression_test: "'1,500' keeps Process Refund disabled.", effort: S, release_blocking: no, dependencies: none, related: [BUG-036]}

- {id: BUG-077, title: "Category deactivation is one click with no confirmation; all its products leave the storefront", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/app/admin/categories/page.tsx:195-219 (toggleActive → updateAdminCategory at :205)", "frontend/src/app/admin/categories/page.tsx:276-286 (row action)"],
   symbol: "toggleActive", explanation: "Every other governance action uses AdminConfirmModal.",
   repro: "Misclick Deactivate.", expected: "Confirm modal showing the product count.", actual: "Immediate PATCH.", impact: "A whole catalogue section hidden by accident.",
   fix: "Route through AdminConfirmModal.", regression_test: "Click opens the modal; no PATCH until confirmed.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-078, title: "Shop edit 'Use current location' writes back a stale form snapshot", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/app/admin/shops/[id]/page.tsx:447-455 (setEditValues({...editValues, …}))", "frontend/src/components/location/UseCurrentLocationButton.tsx:44-45"],
   symbol: "onLocated callback", explanation: "The callback captures editValues at click time; edits made while the GPS prompt is open are overwritten.",
   repro: "Click the button, type a new name, then allow location.", expected: "Name kept.", actual: "Name reverted.", impact: "Lost edits.",
   fix: "Functional state update.", regression_test: "Edits during the pending fix survive.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-079, title: "Out-of-range ?page= leaves a dead-end 'Invalid page.' error with no pager", severity: P3, confidence: Medium, status: Probable, category: "B Frontend", verified: A,
   location: ["frontend/src/components/admin/shared/AdminDataTable.tsx:182-212 (error branch returns before the pager)", "frontend/src/app/admin/users/page.tsx:77 (page taken from the URL)"],
   symbol: "AdminDataTable", explanation: "DRF answers a page beyond the last with 404, and 'Try Again' repeats the same request.",
   repro: "Bookmark page 5, then delete rows.", expected: "Reset to page 1.", actual: "Stuck.", impact: "Users must edit the URL.",
   fix: "On 404 for page > 1, reset to 1, or render the pager in the error state.", regression_test: "Mock 404 at page 3 → page 1 requested.", effort: S, release_blocking: no, dependencies: none, related: [BUG-024]}

- {id: BUG-080, title: "Seller points-history type filter cannot select EXPIRY", severity: P3, confidence: High, status: Confirmed, category: "G Integration", verified: A,
   location: ["frontend/src/app/admin/sellers/sellerGovernance.tsx:255-262 (no EXPIRY)", "backend/points/models.py:79 (TYPE_EXPIRY, per auditor)"],
   symbol: "POINT_TRANSACTION_TYPE_LABELS", explanation: "Expiry rows added by ebd71c5 cannot be filtered.",
   repro: "Open the type filter.", expected: "EXPIRY listed.", actual: "Missing.", impact: "Expiries cannot be reviewed in isolation.",
   fix: "Add EXPIRY, or derive the list from the API type.", regression_test: "EXPIRY option present.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-081, title: "'View this seller's shops' uses a substring search and can list other sellers' shops", severity: P3, confidence: High, status: Confirmed, category: "G Integration", verified: C,
   location: ["frontend/src/app/admin/sellers/[id]/page.tsx:511-512 (comment claims exact)", "frontend/src/app/admin/sellers/[id]/page.tsx:771 (?search=business_name)", "backend/shop/admin_views.py:910-915 (icontains OR filter, per auditor)"],
   symbol: "seller detail link", explanation: "Seller 'Rahim' also matches 'Rahim Store' owned by someone else.",
   repro: "Two sellers with overlapping names.", expected: "Only this seller's shops.", actual: "Both.", impact: "Operators may act on the wrong shop.",
   fix: "Add an owner id filter to the admin shop list and link by id.", regression_test: "Link lists only owned shops.", effort: S, release_blocking: no, dependencies: none}

- {id: BUG-082, title: "Catch-all admin route shows 'Foundation Ready / Awaiting Implementation' instead of a 404", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/app/admin/[...slug]/page.tsx:26-34, 83, 101"],
   symbol: "AdminCatchAllPage", explanation: "Every navigation item is now implemented, so this route only catches typos and nested paths.",
   repro: "/admin/order or /admin/users/5/edit.", expected: "404.", actual: "A placeholder 'module'.", impact: "Broken links are never noticed.",
   fix: "Call notFound() for unknown or nested slugs.", regression_test: "/admin/does-not-exist → 404.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-083, title: "Dashboard shows a 403 banner and fake '0' / '৳0.00' KPIs for operators without reports.view (Known #28)", severity: P3, confidence: High, status: Confirmed, category: "B Frontend / G Integration", verified: C,
   location: ["frontend/src/app/admin/page.tsx:28-58, 148-193", "frontend/src/components/admin/shared/AdminStatCard.tsx:83 (missing → formatTaka(0) / '0')", "frontend/src/lib/admin-navigation.ts:161-167 (cards gated on other codes)"],
   symbol: "AdminDashboard", explanation: "The metrics endpoint requires reports.view; the cards are gated on different permissions, and missing values render as zero.",
   repro: "A SALES_TEAM user opens /admin.", expected: "Cards hidden or '—'.", actual: "Error banner plus zeros.", impact: "Misleading numbers on the landing page.",
   fix: "Gate the KPI grid and fetch on reports.view; render '—' for missing values.", regression_test: "No metrics request and no '0' for SALES_TEAM.", effort: S, release_blocking: no, dependencies: none, related: ["Known #28", BUG-012]}

- {id: BUG-084, title: "Guest-cart merge clears the saved cart even when every POST failed; a partial run re-merges and doubles quantities", severity: P3, confidence: High, status: Confirmed, category: "A Functional", verified: C,
   location: ["frontend/src/context/CartContext.tsx:82-100 (failures only console.warn at :94; key removed unconditionally at :97-98)"],
   symbol: "mergeGuestCart", explanation: "The merge itself is an intended feature (decision of 2026-09-25); these failure edges are not handled. The server adds quantities, so a reload mid-merge doubles the items already merged.",
   repro: "Log in while the backend returns 5xx.", expected: "Failed items kept and reported.", actual: "Guest cart silently lost.", impact: "Lost carts or doubled quantities.",
   fix: "Remove merged items one by one; keep the failures; show a notice.", regression_test: "One item rejected → it remains in localStorage and a message is shown.", effort: S, release_blocking: no, dependencies: "TASK-042"}

- {id: BUG-085, title: "Hot Deals widget invents a '49% OFF' badge and a 120-day countdown", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/components/home/HotDealWidget.tsx:31-36 (days: 120)", "frontend/src/components/home/HotDealWidget.tsx:59-67 (fallback 49)", "frontend/src/components/home/HotDealWidget.tsx:103-108 (chevrons with no handler or label)", "backend/shop/api_views.py:266-274 (falls back to the newest product; deal_ends_in_hours ignored by the UI)"],
   symbol: "HotDealWidget", explanation: "With no real discount the widget still advertises one.",
   repro: "No product has old_price.", expected: "No badge.", actual: "'49% OFF'.", impact: "False discount claim to customers.",
   fix: "Show the badge only when discount_percent > 0; drive the timer from the API; wire or remove the chevrons.", regression_test: "discount 0 → no badge.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-086, title: "Profile Settings can save blanks over the user's real data; avatar upload wipes unsaved edits", severity: P3, confidence: Medium, status: Probable, category: "A Functional", verified: C,
   location: ["frontend/src/context/ProfileContext.tsx:38-39 (fetch failure → profile null)", "frontend/src/app/profile/settings/page.tsx:50-61 (effect resets details on every profile change)", "frontend/src/app/profile/settings/page.tsx:71-74 (payload sends every field)"],
   symbol: "ProfileSettingsPage", explanation: "If the profile fails to load, the form is enabled with empty fields and saving PATCHes blanks. Probable because backend acceptance of blank names was not executed.",
   repro: "Profile fetch fails; edit the phone and save.", expected: "Form disabled until loaded.", actual: "Names blanked.", impact: "Data loss on the profile.",
   fix: "Disable until loaded; send only changed fields; sync once per profile id.", regression_test: "Fetch failing → Save disabled.", effort: S, release_blocking: no, dependencies: none}

- {id: BUG-087, title: "Buy Now isn't awaited, opens the cart drawer over checkout; checkout flashes 'cart is empty'; stepper unbounded", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/app/product/[slug]/page.tsx:30-34 (addToCart not awaited, then router.push)", "frontend/src/context/CartContext.tsx:172 (setIsCartOpen(true))", "frontend/src/app/checkout/page.tsx:213 (empty state ignores cartLoading)"],
   symbol: "handleBuyNow", explanation: "A race between the add and navigation, plus a drawer opening on top of checkout. The quantity stepper is not clamped to stock or the 99 cap.",
   repro: "Click Buy Now on an empty cart.", expected: "Checkout with the item.", actual: "Drawer over checkout; brief empty-cart page.", impact: "Confusing purchase flow.",
   fix: "Await the add with a no-drawer option; spinner while cartLoading; clamp the stepper.", regression_test: "Buy Now lands on checkout with the item and no drawer.", effort: XS, release_blocking: no, dependencies: "TASK-013"}

- {id: BUG-088, title: "Checkout retries save duplicate addresses; unavailable items not blocked before Place Order", severity: P3, confidence: High, status: Confirmed, category: "A Functional", verified: A,
   location: ["frontend/src/app/checkout/page.tsx:159-178 (address saved before the order; repeated on every retry)"],
   symbol: "CheckoutPage.handleSubmit", explanation: "With 'Save this address' ticked, each failed attempt saves another copy. hasUnavailableItems is not used to block submission. Error-message parsing is covered by BUG-028.",
   repro: "Tick save, submit with a failing cart three times.", expected: "One address.", actual: "Three.", impact: "Address book clutter; avoidable failures.",
   fix: "Save the address after the order succeeds (or dedupe); block while items are unavailable.", regression_test: "Failed order creates no address.", effort: XS, release_blocking: no, dependencies: none, related: [BUG-028]}

- {id: BUG-089, title: "Order-success page says 'Order Confirmed' for any order number", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/app/order-success/[orderNumber]/page.tsx:18-27 (null result ignored)", "frontend/src/app/order-success/[orderNumber]/page.tsx:42-63 (:43 'Order Confirmed')"],
   symbol: "OrderSuccessPage", explanation: "A 404, someone else's order or a network error still renders a confirmation. No data is exposed — the backend checks ownership.",
   repro: "/order-success/NOPE.", expected: "Not-found or error state.", actual: "Confirmation.", impact: "Misleading UI.",
   fix: "Loading, not-found and error states.", regression_test: "Unknown number shows not-found.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-090, title: "Profile pages show empty states when loading actually failed", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/context/FavoritesContext.tsx:41-42 (catch → setFavorites([]))", "frontend/src/lib/api.ts:536-538 (getOrderDetail → null on any error)", "frontend/src/app/profile/addresses/page.tsx:49-50, 333 (error banner plus empty state)"],
   symbol: "FavoritesContext, getOrderDetail, AddressesPage", explanation: "Failures render as 'No favorites yet' or 'Order Not Found …belongs to another customer'; the page-level error branches are dead code.",
   repro: "Backend down; open favorites or an order.", expected: "Error with retry.", actual: "Empty or not-found.", impact: "Users think their data is gone.",
   fix: "Expose an error from the contexts; throw on non-404 errors.", regression_test: "Mocked 500 → error state.", effort: S, release_blocking: no, dependencies: "TASK-026 (same policy)"}

- {id: BUG-091, title: "Review delete has no confirmation, and a failed delete shows nothing", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/components/reviews/ReviewSection.tsx:195-212 (:208 setFormError)", "frontend/src/components/reviews/ReviewSection.tsx:243-272, 289 (formError rendered only in the edit form)"],
   symbol: "ReviewSection", explanation: "Delete lives in the read-only view, but the error renders only in edit mode. The same no-confirm pattern exists on profile/reviews and address delete.",
   repro: "Delete while the API fails.", expected: "Confirm, then a visible error.", actual: "One click, silent failure.", impact: "Accidental deletes; invisible failures.",
   fix: "Confirm step; render the error in the view branch.", regression_test: "Failed delete shows the message.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-092, title: "Login leaves tokens stored if /auth/me fails right after a successful token call", severity: P3, confidence: Medium, status: Confirmed, category: "A Functional", verified: C,
   location: ["frontend/src/context/AuthContext.tsx:87-93 (setTokens, then getCurrentUser at :91)"],
   symbol: "AuthProvider.login", explanation: "The UI shows 'Login' while CartContext sees a token and sends cart calls to the server; guest cart persistence is off.",
   repro: "/api/auth/me/ fails once after login.", expected: "Tokens cleared, or retried.", actual: "Half-logged-in state.", impact: "Lost cart changes.",
   fix: "Clear tokens when getCurrentUser fails inside login.", regression_test: "me() rejects → no tokens stored.", effort: XS, release_blocking: no, dependencies: none, related: [BUG-031]}

- {id: BUG-093, title: "Route params are interpolated into authenticated API paths without encoding", severity: P3, confidence: Low, status: Unverified, category: "E Security", verified: C,
   location: ["frontend/src/lib/api.ts:531 (`/api/orders/${orderNumber}/`)", "frontend/src/lib/admin-api.ts id interpolation (e.g. :1259, per auditor)", "callers use useParams() values"],
   symbol: "order/admin path builders", explanation: "If Next 16's useParams returns decoded segments, a crafted link (e.g. ..%2F..%2Fapi%2F…) makes the victim's browser send a bearer-authenticated GET to another backend path. Support paths already use encodeURIComponent.",
   repro: "Investigation needed — check what useParams returns for encoded slashes.", expected: "Encoded path segments.", actual: "Raw interpolation.", impact: "Low (GET only, response shown to the victim); one side effect — a ticket GET marks it read.",
   fix: "encodeURIComponent in every path builder.", regression_test: "Unit test: builder output for '../x' is encoded.", effort: XS, release_blocking: no, dependencies: "TASK-045 investigation",
   resolution: "TASK-045 (2026-10-25), checked in Next 16.3.4 dev + headless Chrome: useParams() keeps %2F (and %20) encoded, decoding only escapes like %2E, so 'a%2Fb' arrives as 'a%2Fb' and the API URL keeps the slash encoded; Django decodes it once and routes '1/../../users/' to no view (404). A param can only become a dot segment through %2E%2E, which the browser itself resolves in the page URL before the route matches ('/admin/shops/%2E%2E' opens /admin). Not reproducible. For defence in depth every API path builder now encodes its values through lib/paths.ts pathSegment(), which also refuses '', '.' and '..' (frontend/src/lib/paths.test.ts)."}

- {id: BUG-094, title: "Accessibility gaps in dialogs, menus and the off-screen sidebar", severity: P3, confidence: High, status: Confirmed, category: "B Frontend (a11y)", verified: C,
   location: ["frontend/src/components/cart/CartDrawer.tsx:26 (role=dialog without label, Escape or focus management)", "frontend/src/components/profile/OrderCard.tsx:236-238 and frontend/src/app/profile/orders/[orderNumber]/page.tsx:462-464 (cancel modals)", "frontend/src/app/product/[slug]/page.tsx:125-135 (thumbnail buttons unnamed)", "frontend/src/components/admin/AdminHeader.tsx:62-66, 85-89 (no aria-expanded; dismissed only on mouse leave)", "frontend/src/components/admin/AdminSidebar.tsx:52-56 (closed sidebar still focusable)"],
   symbol: "dialogs and menus", explanation: "Keyboard and screen-reader users cannot dismiss or identify these controls. NotificationBell already implements the right pattern.",
   repro: "Keyboard-only navigation.", expected: "Escape closes; focus is trapped; controls are named.", actual: "Not the case.", impact: "Usability barrier.",
   fix: "A shared accessible dialog/menu; inert on the closed sidebar.", regression_test: "axe checks plus keyboard tests.", effort: S, release_blocking: no, dependencies: none}

- {id: BUG-095, title: "Material Symbols ignore Tailwind size classes app-wide (Known #35)", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: A,
   location: ["frontend/src/app/layout.tsx:25-28 (unlayered Google Fonts stylesheet)", "frontend/src/app/globals.css:955-957 (no font-size rule, per auditor)"],
   symbol: "icon styling", explanation: "Google's CSS outranks Tailwind's layered utilities, so every icon renders at 24px; some components work around it with inline styles.",
   repro: "text-[16px] on an icon has no effect.", expected: "Sizes applied.", actual: "24px everywhere.", impact: "Layout and visual inconsistencies.",
   fix: "Import the font CSS inside a layer, or set size via a token utility.", regression_test: "Computed font-size matches the class.", effort: M, release_blocking: no, dependencies: none, related: ["Known #35"]}

- {id: BUG-096, title: "Seller Center minor UI defects (status dot, labels, counts)", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/components/seller/SellerSidebar.tsx:114 (status dot always bg-success)", "frontend/src/app/seller/products/page.tsx:759 ('Initial Stock' label in the edit modal)", "frontend/src/app/seller/page.tsx:109-116 ('Active' count includes DRAFT/REJECTED, per auditor)", "frontend/src/app/seller/products/page.tsx:467 (flex on a td)"],
   symbol: "Seller Center", explanation: "Cosmetic misstatements of status and counts.",
   repro: "A suspended seller still sees a green dot.", expected: "Accurate indicators.", actual: "Misleading.", impact: "Minor confusion.",
   fix: "Bind to real status; fix labels and count filters.", regression_test: "Snapshot per status.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-097, title: "Console empty state shown in Bengali on an English UI", severity: P3, confidence: High, status: Confirmed, category: "B Frontend (copy)", verified: C,
   location: ["frontend/src/app/admin/sellers/[id]/page.tsx:962"],
   symbol: "seller points history", explanation: "A mixed-language string in an otherwise English console.",
   repro: "A seller with no point transactions.", expected: "English copy.", actual: "Bengali sentence.", impact: "Inconsistent copy.",
   fix: "'No point transactions for this seller yet.'", regression_test: "n/a (copy).", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-098, title: "Date-only values (customer date of birth) shift by a day for viewers west of UTC", severity: P3, confidence: Low, status: Probable, category: "B Frontend", verified: C,
   location: ["frontend/src/app/admin/customers/[id]/page.tsx:198", "frontend/src/lib/admin-format.ts:53-61 (new Date(iso) with no timeZone)"],
   symbol: "formatDate", explanation: "'1990-05-14' parses as UTC midnight and is formatted in local time. Correct in Dhaka; wrong in UTC− zones.",
   repro: "View in a UTC−5 browser.", expected: "14 May.", actual: "13 May.", impact: "Wrong DOB for some viewers.",
   fix: "Format date-only strings without Date, or with timeZone: 'UTC'.", regression_test: "TZ=America/New_York unit test.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-099, title: "Header/Navbar sticky rule broken on product and shop loading, error and 404 states", severity: P3, confidence: High, status: Confirmed, category: "B Frontend (project rule 4)", verified: A,
   location: ["frontend/src/app/product/[slug]/loading.tsx:9, not-found.tsx:13, error.tsx:25 and the shop/[slug] equivalents", "frontend/src/app/product/[slug]/page.tsx:60 and frontend/src/app/shop/[slug]/page.tsx:115 (in-page loading branches)"],
   symbol: "route boundary files", explanation: "These render <Header /> alone — not sticky, with no Navbar.",
   repro: "Open a slow product page.", expected: "Sticky Header+Navbar.", actual: "Header only.", impact: "Layout jump; project rule violated.",
   fix: "Shared sticky chrome component used by every boundary.", regression_test: "Snapshot includes the Navbar.", effort: XS, release_blocking: no, dependencies: none}

- {id: BUG-100, title: "Console orders list merges only {id, status} after an action (Known #17)", severity: P3, confidence: High, status: Confirmed, category: "B Frontend", verified: C,
   location: ["frontend/src/app/admin/orders/page.tsx:153-157 (:155 merges only status)"],
   symbol: "handleActionSuccess", explanation: "Other fields that changed (updated_at, payment status) stay stale until a refetch.",
   repro: "Confirm an order from the list.", expected: "Row fully refreshed.", actual: "Only status updated.", impact: "Cosmetic staleness.",
   fix: "Merge the full response or refetch the row.", regression_test: "Row shows the new updated_at.", effort: XS, release_blocking: no, dependencies: none, related: ["Known #17"]}
```

### 3.5 TASK-046 follow-up pass (2026-10-25)

The files §7 listed as only grep-scanned were read line by line against the current code (after TASK-001 to TASK-045). Each finding below was checked against the source: `verified: C` by the coordinator, `A` as reported by the slice reader with the quoted code. BUG-101 is the only P2. No XSS, CSRF gap, `$` sign or 500 was found in these files, and the frontend types in `lib/types.ts` 506-964 match their serializers.

**Status (2026-10-26):** fixed in TASK-049, except BUG-119, which goes with the demo-data removal before production (TASK-048 decision 4). BUG-115 follows the decision to list only CUSTOMER-role accounts.

```yaml
- {id: BUG-101, title: "Console role API can reactivate a role whose permissions the actor does not hold", severity: P2, confidence: High, status: Confirmed, category: "Security", verified: C,
   location: ["backend/shop/admin_views.py:525-533 (AdminRoleDetailAPIView.patch sets is_active without a delegation check)", "frontend/src/app/admin/roles/roleGovernance.tsx:548-566 (Active checkbox editable under the permission lock)", "frontend/src/app/admin/roles/[id]/page.tsx:198-204 (always sends is_active)"],
   explanation: "The delegation check runs only when `permissions` is sent. The Django admin refuses the same reactivation (rbac/admin.py:226-235, test_admin_escalation.py:152); the API has no such check.",
   repro: "An operator with roles.admin.manage but not payments.staff.refund holds a deactivated FINANCE role; they tick Active on it in the Console and save.", expected: "403, as in the Django admin.", actual: "200; every FINANCE holder, the actor included, regains payments.staff.refund.", impact: "Privilege escalation for role managers; the reverse (deactivating a role above the actor) silently locks its holders out.",
   fix: "Refuse an is_active change for actors without the wildcard when the role grants codes they cannot delegate; disable the checkbox under that lock; warn in the confirm dialog; API test.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-102, title: "Support status confirm dialog closes on a refresh and reopens on its own later", severity: P3, confidence: High, status: Confirmed, category: "Console UI", verified: C,
   location: ["frontend/src/app/admin/support/[ticketNumber]/page.tsx:233-245, 361-386 (open = pendingStatus && allowed_transitions.includes(pendingStatus))"],
   explanation: "pendingStatus survives a failed confirm; the dialog's visibility follows allowed_transitions, which the refresh changes.",
   repro: "A colleague moves the ticket first; A's confirm fails and the re-read hides the dialog; when the status later allows it again, the dialog pops up and takes focus.", expected: "The refusal shown, then the dialog closed for good.", actual: "Dialog vanishes with its error and reappears minutes later.", impact: "Confusing; a reflex confirm changes the status against intent.",
   fix: "Clear pendingStatus when it leaves allowed_transitions, or drive `open` from pendingStatus alone and show the refusal inside.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-103, title: "Support status dialog quotes the staff label, not the customer's wording", severity: P3, confidence: High, status: Confirmed, category: "Console UI", verified: C,
   location: ["frontend/src/app/admin/support/[ticketNumber]/page.tsx:370-373 (STAFF_STATUS_LABELS)", "backend/support/services.py change_status (CUSTOMER_STATUS_LABELS, BUG-062)"],
   explanation: "TASK-036 made the customer note use customer wording; the confirm text still promises the staff label.",
   repro: "Choose “Wait on customer”.", expected: "“Status changed to Waiting on you”.", actual: "Dialog says the customer will see “Waiting on customer”.", impact: "Misleading copy.",
   fix: "Mirror the customer labels in the frontend for this sentence.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-104, title: "Support assignee list: a failed load looks empty and “Assign to me” announces “Unassigned”", severity: P3, confidence: Medium, status: Confirmed, category: "Console UI", verified: C,
   location: ["frontend/src/app/admin/support/[ticketNumber]/page.tsx:166-179 (.catch(() => undefined))", "page.tsx:704-708 (announcement built from the loaded names)"],
   explanation: "The error is swallowed with no retry; the live-region text looks the name up in the empty list.",
   repro: "Make GET /api/support/staff/assignees/ fail; open a ticket as a manager; click “Assign to me”.", expected: "A load error with retry; “Assigned to you.”", actual: "Only “Unassigned” in the picker; the assignment succeeds but is announced as “Unassigned.”", impact: "Wrong feedback for screen-reader users.",
   fix: "Show the load error with a retry; announce from the chosen value.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-105, title: "New category: every name edit overwrites a slug the operator typed", severity: P3, confidence: High, status: Confirmed, category: "Console UI", verified: C,
   location: ["frontend/src/app/admin/categories/categoryGovernance.tsx:162-166 (autoSlug rewrites slug on each name change)"],
   explanation: "The help text invites editing the slug, but the next name keystroke replaces it; a Bangla name slugifies to empty and disables Create with no reason given.",
   repro: "Type “Mens Wear”, set slug “men”, then edit the name.", expected: "Slug kept.", actual: "Slug reset to the name's slug.", impact: "Wrong public URL.",
   fix: "Stop auto-filling once the slug has been edited by hand.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-106, title: "Category detail edit deactivates without the confirmation the list requires", severity: P3, confidence: High, status: Confirmed, category: "Console UI", verified: C,
   location: ["frontend/src/app/admin/categories/categoryGovernance.tsx:234-251 (Active checkbox in edit mode)", "frontend/src/app/admin/categories/[id]/page.tsx:114-142 (submitEdit PATCHes is_active)"],
   explanation: "BUG-077 put deactivation behind a confirm on the list page only.",
   repro: "Untick Active on the detail page and save.", expected: "The same confirmation, with the product count.", actual: "Products leave the storefront silently.", impact: "Accidental catalogue loss.",
   fix: "Route a true→false change through the same confirm step, or drop the checkbox from the edit form.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-107, title: "Category PATCH audit rows do not record slug, icon or description changes", severity: P3, confidence: High, status: Confirmed, category: "Backend audit", verified: C,
   location: ["backend/shop/admin_views.py:1396-1398 (prev_state/new_state = name, is_active only)"],
   explanation: "A slug change, which breaks public category links, is logged with identical before and after states.",
   repro: "Change only the slug.", expected: "The audit row shows the old and new slug.", actual: "Before == after.", impact: "Untraceable URL changes.",
   fix: "Include slug, icon and description in both states.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-108, title: "Category delete counts products outside a lock, then deletes with CASCADE", severity: P3, confidence: Medium, status: Confirmed, category: "Backend", verified: C,
   location: ["backend/shop/admin_views.py:1418-1434", "backend/shop/models.py:104-106 (Product.category on_delete=CASCADE)"],
   explanation: "A product created between the count and the delete is deleted with the category.",
   repro: "A seller saves a product in the category while staff delete it.", expected: "Delete refused.", actual: "The new product is deleted.", impact: "Rare data loss.",
   fix: "select_for_update the category and recount inside the transaction, or on_delete=PROTECT.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-109, title: "Support ticket writes can be applied out of order", severity: P3, confidence: Low, status: Probable, category: "Console UI", verified: A,
   location: ["frontend/src/app/admin/support/[ticketNumber]/page.tsx:186-199 (every write sets the ticket unconditionally)"],
   explanation: "Reads are sequenced (generation counter); writes are not.",
   repro: "Change priority, then reassign at once; the responses arrive reversed.", expected: "The newest state shown.", actual: "The assignee card reverts until the 60 s poll.", impact: "Brief stale view.",
   fix: "Sequence writes and ignore older responses.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-110, title: "`dark:` utilities follow the OS preference, not the app's dark mode", severity: P3, confidence: High, status: Confirmed, category: "Storefront UI", verified: C,
   location: ["frontend/src/app/globals.css (no @custom-variant dark)", "frontend/src/components/cart/CartDrawer.tsx:86", "frontend/src/app/register/page.tsx:175"],
   explanation: "Tailwind v4's default `dark:` uses prefers-color-scheme; the app toggles a .dark class (ThemeContext).",
   repro: "OS dark, app light; open the cart with an unavailable item, or fail registration.", expected: "Readable warning colours.", actual: "amber-400 / red-300 text on light tints (≈1.3–1.5:1).", impact: "Unreadable warnings.",
   fix: "Add `@custom-variant dark (&:where(.dark, .dark *));` or use the design tokens.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-111, title: "Dark themes do not set `color-scheme: dark`", severity: P3, confidence: Medium, status: Confirmed, category: "Storefront UI", verified: C,
   location: ["frontend/src/app/globals.css dark blocks (no color-scheme anywhere)"],
   explanation: "Native controls keep their light rendering in dark mode.",
   repro: "Dark mode; open a date input.", expected: "Dark native controls.", actual: "Light calendar icon and popup, light scrollbars.", impact: "Poor contrast on native controls.",
   fix: "color-scheme: dark in the .dark blocks, light in the others.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-112, title: "Console profile hides a failed profile load and offers an edit link that cannot work", severity: P3, confidence: High, status: Confirmed, category: "Console UI", verified: C,
   location: ["frontend/src/app/admin/profile/page.tsx:49 (ignores useProfile().error), :114, :193, :199-204, :360-361", "backend seed: OPERATION_MANAGER, SALES_MANAGER, SALES_TEAM, FINANCE lack profile.view"],
   explanation: "GET /api/profile/me/ is 403 for those roles; the page shows “Not set”.",
   repro: "Sign in as a FINANCE-only staff member and open /admin/profile.", expected: "A note that profile details are unavailable.", actual: "“Display name: Not set”; Edit details leads to an error page.", impact: "Misleading.",
   fix: "Read error/isLoading; hide Edit details when the profile is unavailable.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-113, title: "Console profile wallet figures omit expired points", severity: P3, confidence: High, status: Confirmed, category: "Console UI", verified: C,
   location: ["frontend/src/app/admin/profile/page.tsx:288-305 (no wallet.expired figure)"],
   explanation: "The backend sends `expired`; other screens show it.",
   repro: "Staff with expiry: received 500, gave 100, 400 expired.", expected: "Figures that add up to the balance.", actual: "400 points unexplained.", impact: "Confusing ledger.",
   fix: "Add an Expired figure.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-114, title: "“No points yet” shown for any zero balance, even after activity", severity: P3, confidence: Medium, status: Confirmed, category: "Console UI", verified: C,
   location: ["frontend/src/app/admin/profile/page.tsx:124-127"],
   explanation: "The caption keys on balance === 0, not on there being no history.",
   repro: "Receive 200 and give all 200 to sellers.", expected: "“No points left to give.”", actual: "“No points yet.”", impact: "Contradicts the list below.",
   fix: "Use “No points yet” only when there are no transactions.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-115, title: "Console customer directory lists staff and superuser accounts", severity: P3, confidence: Medium, status: Confirmed, category: "Backend/Console", verified: C,
   location: ["backend/customers/views.py:60-61 (GET /api/profile/me/ creates a CustomerProfile)", "frontend/src/context/ProfileContext.tsx (fetched for every signed-in user, Console included)", "backend/shop/admin_views.py:1452-1456 (no role/staff filter)"],
   explanation: "Reading one's profile creates a CustomerProfile, and the directory lists every profile.",
   repro: "A superuser signs in to the Console and opens /admin/customers.", expected: "Customers only (needs a decision).", actual: "The superuser appears as a customer with 0 orders.", impact: "Polluted directory and counts.",
   fix: "Decide: exclude staff/non-CUSTOMER accounts from the list, or stop the GET from creating rows.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-116, title: "Customer search placeholder promises name search the backend does not do", severity: P3, confidence: Medium, status: Confirmed, category: "Console UI", verified: C,
   location: ["frontend/src/app/admin/customers/page.tsx:229", "backend/shop/admin_views.py:1459-1465 (no first_name/last_name)"],
   explanation: "The detail page shows the real name, but search cannot find it.",
   repro: "Search a customer's last name.", expected: "Found.", actual: "“No customers match.”", impact: "Customers hard to find.",
   fix: "Search first/last name too, or change the placeholder.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-117, title: "Debounced Console search can drop a keystroke typed while the URL updates", severity: P3, confidence: Low, status: Probable, category: "Console UI", verified: A,
   location: ["frontend/src/app/admin/customers/page.tsx:58-63, 78-88 (resync during render); the same pattern in 11 admin pages"],
   explanation: "The render-time resync treats the page's own committed URL as an external change.",
   repro: "Type “abc”, pause, type “d” before the navigation lands.", expected: "“abcd”.", actual: "Input reset to “abc”.", impact: "Lost input (not reproduced).",
   fix: "Skip the resync when the URL equals the value this page committed.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-118, title: "A negative or fractional ?page= leaves the Console customers list stuck on an error", severity: P3, confidence: High, status: Confirmed, category: "Console UI", verified: A,
   location: ["frontend/src/app/admin/customers/page.tsx:52"],
   explanation: "Number('-1') is passed through; the backend answers 404 “Invalid page.” and the table's auto-reset only covers page > 1.",
   repro: "Open /admin/customers?page=-1.", expected: "Page 1.", actual: "“Invalid page.” with a Retry that fails the same way.", impact: "Edge case.",
   fix: "Clamp to a whole number ≥ 1.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-119, title: "Demo category counts contradict the demo products", severity: P3, confidence: High, status: Confirmed, category: "Storefront (demo only)", verified: A,
   location: ["frontend/src/lib/api.ts:141-151 vs 153-288"],
   explanation: "Only visible while the demo fallback is active (decision 4 keeps it until production).",
   repro: "API down; pick “Watches • 2 Items”.", expected: "2 products.", actual: "None.", impact: "Demo looks broken.",
   fix: "Derive the counts from DEMO_PRODUCTS, or remove the fallback as planned.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-120, title: "Django admin direct-grant board: the filter blanks every section until reload", severity: P3, confidence: High, status: Confirmed, category: "Django admin UI", verified: C,
   location: ["backend/templates/admin/widgets/minishop_permission_matrix.html:115 (li.ms-perm has no data-pm-row)", "backend/static/js/admin_user_permission.js:270-285 (section hidden when no rows match)"],
   explanation: "With no data-pm-row elements, every section counts 0 matches, including for an empty filter.",
   repro: "Superuser → user → Roles & groups → type in “Filter MiniShop permissions”, then clear it.", expected: "Matching rows shown; all back when cleared.", actual: "Board blank, and stays blank.", impact: "Direct grants cannot be filtered.",
   fix: "Add data-pm-row to each li.ms-perm.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-121, title: "Django admin direct-grant board: counters rewritten to direct grants only on load", severity: P3, confidence: High, status: Confirmed, category: "Django admin UI", verified: C,
   location: ["minishop_permission_matrix.html:124 (data-pm-perm only on unlocked inputs)", "admin_user_permission.js:155-176"],
   explanation: "Inherited (locked) inputs are left out of every count the script recomputes.",
   repro: "An account with 30 inherited permissions and no direct grants.", expected: "“30 / 85 granted”.", actual: "“0 / 85 granted”, chips 0/n, rail badges 0.", impact: "Wrong summary.",
   fix: "Mark locked inputs data-pm-perm too (apply() already skips disabled ones).", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-122, title: "Django admin direct-grant board: Enter in the filter saves the form for full-access accounts", severity: P3, confidence: High, status: Confirmed, category: "Django admin UI", verified: C,
   location: ["admin_user_permission.js:102-103 (returns before binding search and the Enter guard when nothing is unlocked)", "rbac/widgets.py:446"],
   explanation: "For a superuser target every input is locked, so initBoard exits early.",
   repro: "Edit another superuser, type in the MiniShop filter, press Enter.", expected: "Filter applied; no submit.", actual: "The user form is saved (_save).", impact: "Unintended saves.",
   fix: "Same fix as BUG-121.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-123, title: "Role permission board: section and Select-all boxes cannot clear when locked rows are unticked", severity: P3, confidence: High, status: Confirmed, category: "Django admin UI", verified: A,
   location: ["admin_user_permission.js:134-139, 185-225", "role_permission_matrix.html:40, 93, 113-115"],
   explanation: "The roll-up counts locked inputs, so the box stays indeterminate and each click re-applies “check”.",
   repro: "Restricted operator; a section with locked unticked codes; tick then untick the section box.", expected: "Editable codes cleared.", actual: "Nothing clears.", impact: "Tedious editing.",
   fix: "Roll up over enabled inputs only.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-124, title: "Locked grants show as not granted after a validation error re-render", severity: P3, confidence: High, status: Confirmed, category: "Django admin UI", verified: A,
   location: ["backend/rbac/widgets.py:495-502, 568-570 (role form), 426-436 (user form)"],
   explanation: "On a bound form the value is the POST list, and disabled boxes post nothing (save_related keeps the rows).",
   repro: "Restricted operator edits a role holding a locked code and submits an invalid name.", expected: "Locked code still ticked.", actual: "Shown unticked; counts drop.", impact: "Display only.",
   fix: "Use the saved state for locked rows.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-125, title: "User change form hero gauge shows 0 / 0 to non-superuser operators", severity: P3, confidence: High, status: Confirmed, category: "Django admin UI", verified: A,
   location: ["backend/templates/admin/auth/user/change_form.html:81-85", "rbac/admin.py:557-561"],
   explanation: "The gauge is filled by the board script, which has no board when the field is read-only.",
   repro: "Staff (not superuser) opens a user with 40 admin permissions.", expected: "40 / n.", actual: "0 / 0.", impact: "Wrong summary.",
   fix: "Render the counts server-side, or hide the gauge without a board.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-126, title: "Deactivated roles shown as active on the user change form", severity: P3, confidence: High, status: Confirmed, category: "Django admin UI", verified: C,
   location: ["backend/templates/admin/auth/user/change_form.html:66-67", "backend/templates/admin/edit_inline/mp_role.html:57-68"],
   explanation: "Only UserRole.is_active is checked; get_user_role_codes also requires role.is_active.",
   repro: "Switch a role off in RoleAdmin; open a holder's account.", expected: "Chip and card marked inactive.", actual: "Shown active while granting nothing.", impact: "Misleading access view.",
   fix: "Use assignment.is_active and assignment.role.is_active; add a “role disabled” state.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-127, title: "Access-board copy contradicts what the boards do", severity: P3, confidence: High, status: Confirmed, category: "Django admin UI", verified: A,
   location: ["backend/rbac/admin.py:528-536, 598-609 (“Read-only” description kept for superusers)", "minishop_permission_board.html:155-158, 171-176, 234-239 (direct grants shown with no source)"],
   explanation: "Superusers see “Read-only” above an editable board; direct grants look role-derived.",
   repro: "Open a user with a direct grant.", expected: "Accurate labels.", actual: "Contradictory copy.", impact: "Confusion.",
   fix: "Swap the description with the field; tag direct grants.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-128, title: "Saved role cards keep a hidden but focusable role select", severity: P3, confidence: Medium, status: Confirmed, category: "Django admin UI", verified: A,
   location: ["backend/templates/admin/edit_inline/mp_role.html:110-116", "admin_user_permission.css:1290-1299 (clip, not display:none or inert)"],
   explanation: "Keyboard users can tab into the invisible select2 and change which role a saved UserRole points to.",
   repro: "Tab past the status pill, ArrowDown, pick another role, save.", expected: "A saved assignment is removed and re-added, not edited.", actual: "The row's role is rewritten while the card shows the old name.", impact: "Hidden change of access.",
   fix: "Render the field as hidden for saved rows.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-129, title: "Wide permission-matrix checkboxes have no readable accessible name", severity: P3, confidence: Low, status: Probable, category: "Django admin UI", verified: A,
   location: ["backend/templates/admin/widgets/permission_matrix.html:116-127", "admin_user_permission.css:931-932"],
   explanation: "The visible label span is display:none; headers are buttons.",
   repro: "Screen reader on the wide matrix.", expected: "“Product: change”.", actual: "A codename title or nothing.", impact: "Accessibility.",
   fix: "aria-label from the row and action labels.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-130, title: "Django admin dashboard shows create links without add permission", severity: P3, confidence: High, status: Confirmed, category: "Django admin UI", verified: A,
   location: ["backend/templates/admin/index.html:47, 365-384 (New product, quick-create links)", "index.html:110-337 (counts shown to any is_staff; test_admin_dashboard_access keeps them visible on purpose)"],
   explanation: "The links lead to 403 for staff without add permission; the counts are probably an intended policy (confirm).",
   repro: "Staff without shop.add_product opens /admin/.", expected: "No such link.", actual: "Link leading to 403.", impact: "Minor.",
   fix: "Wrap each link in a has-add-permission check; confirm the metrics policy.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}

- {id: BUG-131, title: "Admin templates: external-link hint on a non-link; panes unreachable without JavaScript", severity: P3, confidence: High, status: Confirmed, category: "Django admin UI", verified: A,
   location: ["backend/templates/admin/profile.html:156", "backend/templates/admin/auth/user/change_form.html:177, 220 (panes hidden in markup)"],
   explanation: "“(opens in a new tab)” is rendered when the KPI has no URL; the Roles and Account panes are hidden server-side, contradicting the no-JS promise in admin_user_permission.js:12-13.",
   repro: "Notifications KPI with no URL; or JS disabled.", expected: "No hint; panes reachable.", actual: "Hint on a <div>; username/email/roles unreachable.", impact: "Minor.",
   fix: "Check kpi.url too; hide panes from JS.", effort: XS, release_blocking: no, found_by: TASK-046, task: TASK-049}
```

---

## 4. Prioritized implementation task list (summary)

The full task definitions, with files, acceptance criteria, tests and ordering, are in [`BUG_FIX_TASKS.md`](BUG_FIX_TASKS.md). Every bug above maps to exactly one task.

| Group | Tasks | Bugs covered |
|---|---|---|
| 1. Critical security and data integrity | TASK-001 … TASK-010 | 001, 002, 003, 004, 005, 006, 007, 013, 014, 015, 019, 020, 021, 039, 041, 046, 049 |
| 2. High-priority functional | TASK-011 … TASK-018 | 008, 009, 010, 011, 012, 017, 034, 036, 050, 052, 053, 055, 076, 084, 087, 088 |
| 3. Medium bugs and performance | TASK-019 … TASK-029 | 016, 018, 022–033, 035, 037, 058, 059, 067, 069–072, 079, 092, 095, 096, 099 |
| 4. Low priority | TASK-030 … TASK-041 | 038, 040, 042–045, 047, 048, 051, 054, 056, 057, 060–066, 068, 073–075, 077, 078, 080–083, 085, 086, 089–091, 094, 097, 098, 100 |
| 5. Tests, prevention, investigations | TASK-042 … TASK-048 | 093 (investigation) plus cross-cutting test and CI work |

---

## 5. Maintenance appendix (P4 — not counted as bugs)

**Lint and type checks (from §6)**
- ESLint reports 78 problems:
  - 47 `react-hooks/set-state-in-effect` errors (a known pattern; many older pages).
  - 17 `no-explicit-any`.
  - 10 unused variables: `AdminGuard.tsx:7` `getManagementRoleLabel`, `ThemeContext.tsx:100` `mounted`, `profile/settings/page.tsx:25` `refreshProfile`, `seller/page.tsx:12` `Product`, `lib/api.ts:1` (`BackendCartItem`, `OrderCancelPayload`) and `:1135` `key`. The `seller/orders` ones are BUG-025.
  - 1 `react-hooks/immutability` at `admin/payments/[id]/page.tsx:95/112`. This is lint-only: the callback runs after the declaration has executed. Move the `useState` above the callback.
  - 3 Next font warnings (`app/layout.tsx:25-30`).
- `tsc --noEmit` is clean.

**Project-rule drift (design tokens)**
- About 217 hard-coded palette classes in 37 Console files (`text-red-*`, `bg-red-*`, `text-emerald-*` and others). Twelve storefront files use `bg-black/50`, `text-white`, `bg-white/N` and `amber-*`; Seller Center modals use `bg-black/50`.
- A literal `bg-[#FBF9F4]` appears in `Header.tsx:67` and in the admin login. Both are commented as deliberate.
- No `$` currency was found anywhere; `৳` is used consistently.

**Backend hygiene**
- `rbac/permissions.py:31`: `HasPermission` returns True when no code is configured (fail-open). It is only reached through `require_permission` today.
- `rbac/permissions.py:47-85`: `HasObjectPermission` is unused. Its permission bypass would create an IDOR if it were wired onto customer views — delete or fix it before use.
- `rbac/urls.py:20`: a `test-permission/` verification endpoint ships in the URLconf.
- `rbac/views.py`: duplicate import; `TokenRefreshView` imported but unused.
- `rbac/serializers.py:125`: `except Exception: pass` hides profile-creation failures during registration.
- `config/settings/base.py:30-37`: the `.env` loader keeps quotes and inline comments.
- `config/settings/base.py:127`: the database username is not percent-decoded (the password is).
- `customers/services.py`: `update_profile` is not atomic, and replaced avatars are orphaned in media.
- The admin login footer discloses the framework version and port (`templates/admin/login.html`, approximate).
- The inventory adjust docstrings name routes that do not exist (`shop/api_views.py:813-816`, per auditor).
- `PaymentSerializer.get_refundable_amount` returns a raw Decimal (rendered as a JSON float) while `amount` is a string.
- `Order` money fields are `max_digits=12`, so extreme carts can overflow.
- The staff order list `payment_status` filter matches any payment, not the current one.
- `InventoryTransaction.product` is CASCADE, so deleting a product wipes its ledger; deletion is allowed with open reservations (policy question, TASK-048).
- `expire_all_due_points` re-locks every exempt wallet on each run and aborts the whole run if a wallet disappears mid-run.
- `StaffPointExpiryView` reads the previous value outside the lock (duplicate audit rows possible).
- `set_staff_points_expire` creates a StaffWallet for any user id.
- The nearby search computes `ST_Distance_Sphere` for every located shop, so the spatial index is not used.
- The last-Super-Administrator guard counts only role holders and has a write-skew window (`shop/admin_views.py:313-320`).
- The CUSTOMER role is not protected, so a `roles.admin.manage` holder can deactivate it and break checkout (policy question, TASK-048).
- The category delete counts products outside the transaction (`Product.category` is CASCADE); category PATCH audits only name and is_active.
- `request.data.get` fails on a JSON-list body in one admin view.
- The audit metadata redactor does not recurse into lists.
- `get_console_metrics` computes one aggregate more than it returns.
- Every product change page embeds all categories and shops as JSON.
- There is no per-request permission cache: each permission class runs about 4 queries.
- Support: PDFs are served inline (consider `as_attachment` or a CSP sandbox); the 5 MB limit is checked only after the full upload is received.
- Notifications worker:
  - `run()` has no exception handling (mitigated by systemd `Restart=always`).
  - `TokenBucket` under-delivers for rates below 1/s.
  - The fan-out cap drops recipients beyond 500 with only a warning.
  - A seller ordering from their own shop gets only the customer notification.
  - Seller emails go to the unverified `business_email`.
- Customers:
  - Another user's address id returns 403 rather than 404, which reveals that the id exists.
  - PATCH `is_default=false` can leave a user with no default address.
  - Any IntegrityError is reported as "already reviewed".
  - The favorites list includes products that are no longer public.

**Frontend hygiene**
- CartContext actions are not memoised, and totals are re-summed with `parseFloat` instead of using `BackendCart.total_amount`.
- Checkout posts an `items` payload the server ignores.
- Home hard-codes a page size of 12.
- `Pagination` renders every page number.
- The Navbar has hard-coded fallback category slugs.
- "Clear filters" does not reset the search.
- `lib/auth.ts:31` still reads the legacy `token` / `access_token` keys.
- Customer support pages import Console components; the points components import `lib/admin-format`.
- The raw payment-method code is shown to customers.
- Hard-coded trust claims ("Verified Seller").
- The "Nationwide via ৳" copy.
- The CartDrawer says shipping is "free over ৳99" while checkout always shows FREE.
- Responses still in flight after logout can repopulate the previous user's favorites or profile.
- `FavoriteButton` sends guests to `/login` without `?next=`.
- `AdminGuard` drops the query string on re-login.
- The Console login calls `clearTokens()` on a non-management login, wiping an existing storefront session.
- `sellers/new?user_id=` is not validated.
- `shops`, `orders/[id]` and `payments/[id]` have no page-level view gate (the backend still enforces access).
- The audit-log target-type filter is missing newer target types.
- `StaffPointTransactionType` lacks EXPIRY.
- `users/[id]` shows "Loading the role catalogue…" forever when the catalogue is empty.
- `UserPointsPanel` falls back to a literal 2 months.
- Order row actions use past-tense labels.
- Status-filtered lists keep a row after an action moves it out of the filter.
- The products page refetches the dashboard although SellerGuard already holds it.
- A product slug of `mine` would be shadowed by `/api/products/mine/`.
- `next.config.ts:6-35` has stale port-8000 `remotePatterns`, and `images.unoptimized` means no image optimisation at all.

**Docs, dependencies and CI**
- Stale docs: `backend/README.md` (SQLite, port 8000, legacy templates, media "gitignored") and `GEMINI.md:5` (SQLite).
- `requirements.txt`: `geocoder`, `ratelim` and `future` are used only by the `tools/` scratch scripts; DRF, SimpleJWT and cors-headers are `>=` without an upper bound.
- CI has no `check --deploy`, no ESLint step and no `permissions:` block for `GITHUB_TOKEN`.

**Previously known low issues still open (re-verified)**
- #13: `/api/admin/roles/` is unpaginated; the frontend copes.
- #18: Payment and Refund `metadata` are serialized verbatim (latent).
- #19: Refund amount has no serializer ceiling; the service enforces one.
- #21: the staff refunds list has no filters.
- #27: there is no platform-wide inventory permission (design; see TASK-048).

**Embedded agent instructions (prompt-injection / supply-chain review)**
- `AGENTS.md`, `.cursorrules` and `GEMINI.md` instruct automated agents to run `git add` / `git commit` after every change and to run builds.
  - These are legitimate project guidelines, not malicious.
  - An agent following them literally would commit during a read-only task.
  - They were deliberately not followed in this audit.
- `frontend/AGENTS.md` is empty. The injection planted there earlier was removed in `5552532` and has not reappeared.
- No other agent-directed text was found in source, comments, docs or file names.

**Testing gaps (category J)**
- **Frontend:** there is no test runner and no tests (`frontend/package.json:5-11`). Every frontend finding is untested.
- **Backend change-form lockdown:** tests exist for Seller and Shop only; there are none for Order, Product, ProductInventory or the rbac admins (BUG-002, BUG-006, BUG-021).
- **Backend authorization and lifecycle:** no tests for:
  - delegation on Console user role assignment;
  - seller transitions from illegal source states;
  - a seller cancelling a paid order;
  - delivery of a reservation-less order (#29);
  - a second partial refund.
- **Backend invoices:** no invoice tests exist at all (markup, balance).
- **Backend performance:** no `assertNumQueries` on any list endpoint.
- **Backend concurrency:** coverage is limited to seller point deductions. No tests for opposite transfers, checkout lock ordering, address default races or `expire_points` running alongside spending.
- **Backend security:** no tests for JWT revocation, throttling or audit IP derivation.

---

## 6. Testing and verification results

Every command below was run for this audit, read-only, with `PYTHONDONTWRITEBYTECODE=1` for the Python commands. `DATABASE_URL` was overridden to an unreachable local port (`127.0.0.1:1`), so no command could reach the configured MySQL server.

| # | Command (cwd) | Exit | Result |
|---|---|---|---|
| 1 | `git status --porcelain=v1` (repo root) | 0 | Empty output: clean tree |
| 2 | `git ls-files \| wc -l` | 0 | 651 |
| 3 | `venv/bin/python manage.py check` (backend) | 0 | "System check identified no issues (0 silenced)." |
| 4 | `venv/bin/python manage.py check --deploy` (backend) | 0 | 6 warnings: security.W004, W008, W009, W012, W016, W018 |
| 5 | `venv/bin/python manage.py check --settings=config.settings.test` | 0 | No issues |
| 6 | `venv/bin/python manage.py makemigrations --check --dry-run` | 0 | "No changes detected" (plus the expected RuntimeWarning that the migration-history check could not reach the database) |
| 7 | `venv/bin/python -m pip check` | 0 | "No broken requirements found." |
| 8 | `./node_modules/.bin/tsc --noEmit --incremental false` (frontend) | 0 | No errors; `tsconfig.tsbuildinfo` was not touched (mtime still 2026-10-18) |
| 9 | `./node_modules/.bin/eslint .` (frontend) | 1 | 78 problems (65 errors, 13 warnings) — breakdown in §5 |

**Skipped for safety (NOT TESTED)**

- **Backend test suite.** The suite creates, migrates and clones `test_*` databases on the MySQL server; `backend/.env` points at a remote host. That is a database write, and isolation could not be proven.
- **`npm run build`.** It writes `.next/`, which would break a running `next dev`.
- **Servers, browsers, HTTP requests, `npm audit` / `pip-audit`.** These need the network or are forbidden by the brief.
- **Token forging, throttling probes and concurrency reproduction.** These are runtime attacks and tests; their findings are static.
- **Database contents.** Historical inventory drift (#30) and real seller role assignments (BUG-004) were not checked. Checked since by TASK-047 on a dev snapshot: see audit/DATA_RECONCILIATION.md (no active SALES_TEAM seller; ledger gaps and payment-less orders only in seed and smoke-test rows).

---

## 7. Unresolved questions and limitations

**Decisions needed (they gate fixes)**
- The COD payment lifecycle (BUG-012).
- The DRAFT → published product flow (BUG-011, Known #8).
- The seller permission model, separate from staff permissions (BUG-004, Known #27).
- Whether expiry renewal via take-back is acceptable (BUG-048).
- Whether product rejection or deletion should refund the creation fee (there is no producer for `PointTransaction.TYPE_REFUND`).
- Staff who also hold a seller profile can credit their own seller wallet.
- Whether `users.admin.view` / `roles.admin.view` should expose the full audit log, including payment metadata.
- Whether the CUSTOMER role should be protected.

**Runtime-only facts not established**
- MySQL locking and deadlocks (BUG-023, BUG-058).
- Whether Next 16 `useParams` returns decoded values (BUG-093). Settled by TASK-045: it does not decode %2F; see BUG-093.
- Browser number-input parsing (BUG-076).
- How common MPO JPEGs are (BUG-063).
- Whether the backend accepts blank profile names (BUG-086).

**Partially inspected (scanned with grep for sinks and handlers, not read line by line)**
- Backend:
  - `backend/rbac/widgets.py` lines 121-229.
  - The templates `admin/profile.html`, `admin/index.html`, `admin/auth/user/change_form.html` and the inline/widget templates.
  - `static/js/admin_product_form.js` and `admin_user_permission.js`.
- Frontend:
  - `app/admin/support/[ticketNumber]/page.tsx` lines 420-880; `roleGovernance.tsx` lines 200-657; `roles/[id]` lines 260-614; `categoryGovernance.tsx` lines 140-322.
  - `customerDirectory.tsx`; `customers/page.tsx` lines 130-259; `profile/page.tsx` lines 140-609; `adminProfile.ts`.
  - `lib/types.ts` lines 520-946; `globals.css` (token blocks only); `lib/api.ts` lines 100-245 (demo data).
- TASK-046 was the follow-up pass for these areas (2026-10-25): see §3.5, BUG-101 to BUG-131.

**Assumptions**
- No production deployment exists yet (project decision of 2026-09-18). Severity for configuration findings states the effect on a deployment.
- Prior review-cache entries were re-verified against source and never trusted on their own.

---

## 8. Recommended fixing roadmap

Nothing below has been executed.

1. **Before any shared or deployed instance** (Group 1, about 1–1.5 weeks):
   - TASK-001 settings and secret rotation.
   - TASK-002 token revocation and throttling.
   - TASK-003 / TASK-004 RBAC escalation fixes.
   - TASK-006 Django-admin lockdown.
   - TASK-007 seller-cancel refund.
   - TASK-008 SALE bound (TASK-006 first, so no new inflow appears).
   - TASK-009 audit integrity and TASK-010 invoices.
   - TASK-005 after the TASK-048 decision.
2. **Unblock the core workflows** (Group 2):
   - TASK-014 product publication (decision first) and TASK-015 COD payment record (decision first).
   - TASK-011 stock deltas, TASK-012 seller order detail, TASK-013 cart integrity.
   - TASK-016 seller lifecycle guards, TASK-017 checkout gate, TASK-018 refund UI safety.
3. **Stand up test harnesses early**, in parallel with step 2:
   - TASK-042: a Vitest + React Testing Library harness, so the frontend fixes in steps 2–4 ship with regression tests.
   - TASK-043: backend regression suites for the change-form lockdown pattern, `assertNumQueries` and MySQL concurrency.
4. **Medium bugs and performance** (Group 3): TASK-019 … TASK-029. Batch the pagination and error-parsing contract fixes (TASK-021, TASK-022), since they touch the same client helpers.
5. **Low-priority batches** (Group 4): TASK-030 … TASK-041, grouped by surface to minimise context switching.
6. **Continuous**:
   - TASK-044 CI hardening (`check --deploy`, ESLint gate, permissions block).
   - TASK-045 … TASK-048 investigations and decisions; their outcomes feed back into steps 1–2.

**Verification for every fix** (per the project's `AGENTS.md`):
- `python manage.py test --settings=config.settings.test --parallel --keepdb --noinput` against an isolated MySQL. Prefer `TEST_DATABASE_URL` pointing at a local server.
- `npm run typecheck` and `npm run build`.
- Re-run the specific regression test named on each bug.

---

## 9. Phase 6 — safety verification

- **Baseline** `git status --porcelain=v1`: *(empty)*.
- **Final** `git status --porcelain=v1`: `?? audit/`. With `-uall` it shows exactly `?? audit/BUG_AUDIT_REPORT.md` and `?? audit/BUG_FIX_TASKS.md`.
- `git diff --stat` and `git diff --cached --stat` are empty: no tracked file changed and nothing is staged.
- **Comparison:** the baseline and final outputs differ only by the two authorized, untracked report files.
- No project file was edited, moved or deleted.
- No commit, push, install, migration, server start or HTTP request was made.
- `frontend/tsconfig.tsbuildinfo` was left untouched (`tsc` ran with `--incremental false`).
- No `__pycache__` was written (`PYTHONDONTWRITEBYTECODE=1`).

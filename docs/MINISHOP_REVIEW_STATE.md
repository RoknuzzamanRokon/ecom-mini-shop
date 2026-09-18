# MiniShop — Persistent Review State

**Last full review:** 2026-09-17
**Reviewed at commit:** `ce7cf2a` (`fix(inventory): prevent stock desynchronization`) — the last **backend** commit; unchanged through `5b2a59e`, re-confirmed 2026-09-18 by `git diff --stat ce7cf2a..HEAD` (backend files: none).
**Last targeted update:** 2026-09-18 — `/admin/payments` Management Console module implemented (Payments-only; list + detail + verify + refund), consuming the existing `/api/staff/payments/` API with zero backend changes. See [Review History](#21-review-history).
**Preceding targeted update:** 2026-09-18 — Post-Orders architecture & security audit (no code changes; re-verified the Orders console, all four prior security fixes, RBAC/seller/shop rules, and every open Known Issue against current source; found one new low-severity Orders finding; set Payments as the next task with new evidence).
**Preceding targeted update:** 2026-09-18 — `/admin/orders` Management Console module implemented (Orders-only; list + detail + permission-gated status-transition actions), consuming the existing `/api/staff/orders/` API with zero backend changes.
**Preceding targeted update:** 2026-09-18 — Post-security-fix architecture & roadmap audit (no code changes; re-verified #1/#15/#16/#2 against source, corrected the stale "Reviewed at commit" pointer, replaced the unsourced "Phase 1I spec" claim, and set an evidence-based next task — this Orders module).
**Preceding targeted update:** 2026-09-18 — Stock Desynchronization #2 audit (fixed). `ProductService.update_product` now routes `stock` through `InventoryService` under row lock instead of writing `Product.stock` directly.
**Preceding targeted update:** 2026-09-18 — seller/shop Django-admin action authorization (#16 fixed). This closes the unguarded-admin-action class across the whole project.
**Preceding targeted update:** 2026-09-17 — OrderService authorization audit. #1b re-classified (it is **not** an authorization bypass); a real one found and fixed elsewhere in the call graph (#15).

---

## How To Use This File

This file is a **review cache**, not the source of truth.

The source of truth is always the actual source code, migrations, tests and configuration. This document records what was verified at the date above so that a future review does not have to re-derive the entire architecture from scratch.

**Rules for using it:**

1. Read this file first, before auditing anything.
2. Never treat an entry here as still-true without checking. Entries name `file:line` so they are cheap to re-verify.
3. If the code and this file disagree, **the code wins** — then fix this file.
4. Update the relevant section rather than appending contradictions.
5. Do not record secrets, tokens, passwords or personal data here.

See [Future Review Procedure](#future-review-procedure) at the end.

---

## 1. Project Snapshot

| Item | Value |
|---|---|
| Backend | Django 5.2 + Django REST Framework |
| Database | **MySQL 8 required** — `config/settings.py:102-110` raises `RuntimeError` unless `DATABASE_URL` is a `mysql://` URL |
| Auth | `rest_framework_simplejwt` (access 60 min, refresh 7 days, rotation on, **no blacklist**) — `settings.py:192-198` |
| Frontend | Next.js 16 (Turbopack) + React 19 + TypeScript + Tailwind v4 |
| Ports | Django `8001`, Next.js `3000` |
| Python venv | **`backend/venv/`** — use this one. The repo-root `.venv/` exists but lacks `reportlab`, so `manage.py` fails there. |
| Currency | `৳` (Bangladeshi Taka) everywhere in UI — never `$`/`USD`/`BDT` |
| DRF defaults | JWT + Session auth; `PageNumberPagination`, `PAGE_SIZE = 12` (`settings.py:182-189`) |

**Commands**

```bash
# backend (from backend/)
venv/Scripts/python.exe manage.py check
venv/Scripts/python.exe manage.py test --noinput --keepdb      # --noinput matters: a stale test DB otherwise blocks on a prompt
venv/Scripts/python.exe manage.py seed_rbac

# frontend (from frontend/)
npx tsc --noEmit
npm run build
```

**Project instruction files:** `AGENTS.md` (root, key commandments), `GEMINI.md` (architecture + design-token spec), `frontend/CLAUDE.md` (just imports `frontend/AGENTS.md`), `frontend/AGENTS.md` (**currently empty** — its contents were a prompt injection removed in commit `5552532`). `task/Master_Prompt.md` + `task/task1..17.md` hold the historical task specs. `report.md` is an older audit and is **stale** in several places (it claims there is no registration endpoint and no audit-log API; both now exist).

---

## 2. Backend Layout

> **Naming trap:** `shops/` and `shop/` are different apps.
> `shops/` = the Shop domain (Shop model, shop lifecycle, spatial search).
> `shop/` = the original monolith: Product, Category, Order, OrderItem, Inventory, Payment, Refund, **and all API views including every `/api/admin/` endpoint**.

| App | Contains |
|---|---|
| `config` | settings, root urls, customized Django admin site (`config/admin_site.py`) |
| `rbac` | Role, Permission, RolePermission, UserRole, UserPermission; auth endpoints; `seed_rbac` command |
| `sellers` | SellerProfile, seller lifecycle, seller endpoints |
| `shops` | Shop model + `ShopService` + public/seller/staff shop endpoints; `MySQLPointField` spatial type |
| `points` | SellerWallet, PointTransaction, ProductCreationCost, `PointService` |
| `customers` | CustomerProfile, Address, Favorite, **Review** |
| `cart` | Cart, CartItem (authenticated carts only) |
| `audit` | AuditLog (append-only) + `AuditService` |
| `shop` | Product, Category, Order, OrderItem, ProductInventory, InventoryTransaction, Payment, Refund; `ProductService`, `OrderService`, `InventoryService`, `PaymentService`; `api_views.py`, `admin_views.py`; legacy server-rendered template views |

URL mounting (`config/urls.py:26-35`): `/admin/` → Django admin · `/api/auth/` → rbac · `/api/sellers/` → sellers · `/api/points/` → points · `/api/shops/` → shops · `/api/cart/` → cart · `/api/` → customers · `""` → shop (so shop's routes are literally `/api/...`).

---

## 3. Authentication

| Method | Endpoint | Auth |
|---|---|---|
| POST | `/api/auth/register/` | AllowAny — creates user, assigns `CUSTOMER` role, creates CustomerProfile (`rbac/serializers.py:119-126`) |
| POST | `/api/auth/token/` | AllowAny — JWT obtain |
| POST | `/api/auth/token/refresh/` | refresh token |
| GET | `/api/auth/me/` | authenticated — returns `id, username, email, first_name, last_name, is_staff, is_superuser, roles[], permissions[]` |
| POST | `/api/auth/change-password/` | authenticated |
| GET | `/api/auth/test-permission/` | authenticated — RBAC probe helper |

`/api/auth/me/` does **not** include seller or customer sub-profile data — the frontend fetches `/api/sellers/dashboard/` and `/api/profile/me/` separately.

**No logout / token revocation exists.** `BLACKLIST_AFTER_ROTATION = False` and no blacklist app is installed, so an issued access token stays valid for its full 60 minutes. Frontend "logout" only clears localStorage.

Frontend token storage (`frontend/src/context/AuthContext.tsx:18-19`): `minishop_token` (access) and `minishop_refresh_token`. Some older helpers also probe legacy keys `token` / `access_token`. Tokens live in localStorage, not httpOnly cookies.

---

## 4. RBAC — The Authorization Model

**This is the only API authorization system.** Django's `auth.Permission` / `user_permissions` is **not** used to authorize MiniShop APIs (it appears only as a Django-admin UI surface via `rbac/widgets.py`).

```
User → UserRole → Role → RolePermission → Permission
User → UserPermission → Permission          (direct per-user grant, the single-account exception)
```

Models: `rbac/models.py` — `Role` (8 codes), `Permission` (`<resource>.<action>`), `RolePermission` (unique role+permission), `UserRole` (unique user+role, soft-revoke via `is_active`, records `assigned_by`), `UserPermission` (same shape, records `granted_by` + `note`).

**Resolution** (`rbac/services.py`):
- `get_user_permissions()` — superuser **or** `SUPER_ADMINISTRATOR` → every permission plus the `"*"` wildcard marker (`:44-47`). Everyone else → union of active role permissions and active direct grants (`:49-64`).
- `has_user_permission()` — superuser short-circuit, then `"*"`, then membership (`:67-82`).
- `assign_user_role()` idempotent; `remove_user_role()` deactivates rather than deletes.

**Anti-escalation** — the delegation boundary is *"you may only give away what you already hold"*:
- `get_delegatable_permission_codes()` (`:145-172`) = display projection used by the admin permission catalogue.
- `get_undelegatable_permission_codes()` (`:175-199`) = the single enforcement point used by admin role create **and** patch, so the rule cannot drift between them.
- Wildcard holders are unrestricted.

**Protected roles:** `PROTECTED_ROLE_CODES = {SUPER_ADMINISTRATOR, ADMINISTRATOR}` (`shop/admin_serializers.py:21`), enforced at `shop/admin_views.py:183, 315, 452, 515`.

**Roles** (`seed_rbac`): `SUPER_ADMINISTRATOR`, `ADMINISTRATOR`, `OPERATION_MANAGER`, `SALES_MANAGER`, `SALES_TEAM`, `FINANCE`, `SUPPORT_TEAM`, `CUSTOMER`. Seeding reports **65 permissions, 8 roles, 202 role-permission links**.

Seller-relevant grants: `SALES_TEAM` holds `products.view/create/update`, `orders.seller.*`, `inventory.*` — but **not** `products.delete` (`seed_rbac.py:188-194`). A seller needs `products.delete`, e.g. via `ADMINISTRATOR`, before the delete endpoint will work.

> **Seller is not an RBAC role.** It is a separate SellerProfile attached to a user. A seller's API permissions come from whatever RBAC role that user was separately granted.

---

## 5. Seller System

**SellerProfile** (`sellers/models.py:7-157`), one-to-one with User (`related_name="seller_profile"`).

- Types (`:9-17`): `FULL_SHOP_OWNER` (default), `LIMITED_SHOP_OWNER`, `PRODUCT_OWNER`
- Statuses (`:20-34`): `PENDING` (default), `UNDER_REVIEW`, `APPROVED`, `ACTIVE`, `SUSPENDED`, `REJECTED`
- `is_operational` (`:84-87`) ⇔ status in (`APPROVED`, `ACTIVE`) — this is the gate every seller-facing permission class checks
- Lifecycle services (`sellers/services.py:67-90`), each `@transaction.atomic`: `approve_seller` (approve **then** activate → lands on `ACTIVE`), `reject_seller`, `suspend_seller`, `reactivate_seller`. Reasons are mandatory for reject/suspend (model `clean()`).

| Method | Endpoint | Authorization |
|---|---|---|
| GET | `/api/sellers/` | `sellers.view` |
| POST | `/api/sellers/register/` | **`IsAuthenticated` only** — self-service, lands in `PENDING` (see Known Issues #5) |
| GET/PUT/PATCH | `/api/sellers/me/` | own profile; seller may edit business fields only, never `seller_type`/`status` |
| GET | `/api/sellers/dashboard/` | authenticated — returns `has_seller_profile`, `seller`, `capabilities`, `status`, `is_operational`, `is_suspended` |
| GET | `/api/sellers/<pk>/` | `sellers.view` |
| POST | `/api/sellers/<pk>/approve/` · `/reject/` | `sellers.approve` (+ reason on reject) |
| POST | `/api/sellers/<pk>/suspend/` · `/reactivate/` | `sellers.suspend` |

`capabilities` comes from `get_seller_capabilities()` (`sellers/services.py:40-64`) and is driven **only by seller type**, not status and not RBAC. It still reports `can_create_shop: true` for both shop-owner types, which contradicts the enforced rule (Known Issues #4).

**Creating a SellerProfile does not assign any RBAC role** — verified: no signal, no rbac import in `sellers/`. The only automatic assignment in the codebase is `CUSTOMER` on user registration.

---

## 6. Shop System

**Shop** (`shops/models.py:10-123`). `owner = FK(SellerProfile, related_name="shops")` — a plain FK, so **nothing at the DB level prevents multiple shops per seller**; the cap is enforced in the service layer only.

- Statuses (`:15-29`): `DRAFT` (default), `PENDING`, `APPROVED`, `ACTIVE`, `SUSPENDED`, `REJECTED`
- `is_publicly_visible` ⇔ `APPROVED` or `ACTIVE` (`:81-84`)
- Spatial `location` (`MySQLPointField`, SRID 4326); nearby search uses native `ST_Distance_Sphere` (`shops/services.py:216-257`)
- Reasons mandatory on reject/suspend (`clean()`, `:105-110`)

### Shop creation policy (verified, enforced)

```
Admin creates Shop → assigns SellerProfile as owner → Seller manages that one Shop
```

- **Sellers cannot create shops.** `POST /api/shops/mine/create/` still routes, but `SellerShopCreateView` (`shops/views.py:130-146`) unconditionally raises `PermissionDenied` — deliberately kept so direct API calls get an explicit 403 rather than a confusing 404. The seller UI has no create control at all.
- **Admins create shops** via `POST /api/admin/shops/` (`shop/admin_views.py:809-864`), which delegates to `ShopService.create_shop` (`:830`) inside `transaction.atomic()` with `select_for_update()` on the seller.
- **The single-shop cap is enforced** in `ShopService.validate_seller_eligibility_for_creation` (`shops/services.py:96-115`): non-operational sellers rejected (`:98`), `PRODUCT_OWNER` rejected (`:103`), and `if seller.shops.count() >= 1: raise ShopLimitExceededError` (`:112-115`). Surfaced as a 400 on `seller_id`.

| Method | Endpoint | Authorization |
|---|---|---|
| GET | `/api/shops/` · `/api/shops/<slug>/` · `/api/shops/nearby/` | AllowAny — APPROVED/ACTIVE only |
| GET | `/api/shops/mine/` | own shops |
| POST | `/api/shops/mine/create/` | **always 403 by design** |
| GET/PATCH | `/api/shops/mine/<pk>/` · `/update/` · `/location/` | owner only (`IsShopOwner`) |
| POST | `/api/shops/mine/<pk>/submit/` | owner; DRAFT/REJECTED → PENDING |
| GET | `/api/shops/staff/` · `/staff/<pk>/` | `shops.view` |
| POST | `/api/shops/staff/<pk>/approve|reject|suspend|reactivate/` | `shops.approve` |
| POST/PATCH | `/api/admin/shops/` · `/api/admin/shops/<pk>/status/` | `shops.admin.manage` (status also accepts `shops.approve` for approve-only) |

---

## 7. Product System

**Product** (`shop/models.py:71-200`). Ownership is derived — **there is no `seller` column**; the chain is `Product → shop → shop.owner`.

- Statuses (`:73-87`): `DRAFT` (default), `SUBMITTED`, `APPROVED`, `REJECTED`, `PUBLISHED`, `UNPUBLISHED`
- Fields: name, slug, category FK, shop FK, description, price, old_price, image, stock, badge, is_active, status, rejection_reason, submitted_at, reviewed_at, reviewed_by, timestamps
- Public visibility (`ProductQuerySet.public()`, `:50-68`) requires **all** of: product `is_active`, status `PUBLISHED`, category active, shop present and `APPROVED`/`ACTIVE`, **and** shop owner `APPROVED`/`ACTIVE`

**`ProductService`** (`shop/services.py:43-284`) is the only sanctioned mutation path.

`create_product` (`:51-183`) enforces in order: seller operational → shop exists → **`shop.owner == seller`** → shop APPROVED/ACTIVE → RBAC `products.create` → resolve point cost → pre-check balance → then one `transaction.atomic()` block containing: unique-slug generation, product save (**always `status=DRAFT`**), inventory record creation, `PointService.debit(...)`, and `AuditService.log("PRODUCT_CREATED")`. Any failure rolls the whole thing back (covered by `AtomicRollbackTests`).

`update_product` (`:186-250`) re-checks ownership, rejects reassigning a product to a shop the seller does not own, requires `products.update`, audits. `delete_product` (`:253-284`) same shape with `products.delete`.

### Seller product endpoints

| Method | Endpoint | Authorization |
|---|---|---|
| GET | `/api/products/mine/` | `IsEligibleProductSeller`; queryset is `Product.objects.filter(shop__owner=seller)` — filters (`shop_id`, `status`, `category`, `q`) narrow *within* that scope |
| POST | `/api/products/mine/` | + `CanCreateProduct` (`products.create`) |
| GET/PATCH/DELETE | `/api/products/mine/<pk>/` | + `IsProductOwner` object check; PATCH needs `products.update`, DELETE needs `products.delete` |

Shop resolution on create (`shop/api_views.py:526-558`): if the client omits `shop_id` the backend resolves the seller's own shop; 0 shops → 400 with a "contact an administrator" message; **more than 1 shop → 409 Conflict, never a silent pick**. If `shop_id` *is* supplied, `SellerProductCreateSerializer.validate_shop_id` (`shop/serializers.py:242-261`) independently confirms the shop belongs to the caller, so a forged id cannot reach another seller's shop.

### Product lifecycle (important)

Seller-created products land in `DRAFT`. **There is no seller-facing "submit for review" endpoint** — the only transitions are admin-driven via `POST/PATCH /api/admin/products/<pk>/status/` with `action` ∈ `approve | reject | publish | unpublish` (`shop/admin_views.py:1027-1098`), each gated on `products.approve` / `products.reject` / `products.publish` / `products.admin.manage`. Consequence: `SUBMITTED` is currently unreachable (Known Issues #8), and a seller cannot get a product public without staff action.

**There is no admin product create or update endpoint** — `AdminProductListAPIView` and `AdminProductDetailAPIView` define `get` only. So no admin path bypasses the point cost, because no such path exists.

Categories come from the existing public `GET /api/categories/` (`shop/api_views.py`, `CategoryListView`). Product images use the existing `Product.image` field plus the `ProductImage` gallery model — no separate image subsystem.

---

## 8. Points / Wallet

| Model | Notes |
|---|---|
| `SellerWallet` (`points/models.py:7-44`) | OneToOne seller, `balance` Integer with `MinValueValidator(0)` **and** DB `CheckConstraint balance >= 0` |
| `PointTransaction` (`:47-138`) | Append-only ledger: type, positive `amount`, `balance_before`, `balance_after`, mandatory `reason`, `reference_type`/`reference_id`, `actor`. Types: `BONUS`, `ADMIN_CREDIT`, `ADMIN_DEBIT`, `PRODUCT_CREATION`, `REFUND`, `ADJUSTMENT` |
| `ProductCreationCost` (`:141-172`) | Singleton pinned to `pk=1`, `required_points` **default 5**, falls back to `settings.PRODUCT_CREATION_POINT_COST` (also 5) |

**`1 product = 5 points` — implemented and enforced backend-side.** The cost is read authoritatively via `PointService.get_product_creation_cost()`; `PointService.debit()` (`points/services.py:117-173`) opens `transaction.atomic()`, takes `select_for_update()` on the wallet (`:140`), raises `InsufficientPointsError` if balance < amount (`:145-148`), then writes wallet + ledger row together. The debit happens inside `ProductService.create_product`'s transaction, so product and deduction commit or roll back as one. Concurrency is covered by `ConcurrencySafetyTests` (two simultaneous creations with 5 points → exactly one product, balance ends at 0, never negative).

| Method | Endpoint | Authorization |
|---|---|---|
| GET | `/api/points/wallet/` · `/api/points/history/` | own wallet |
| GET | `/api/points/sellers/<id>/` · `/history/` | `points.view` |
| POST | `/api/points/sellers/<id>/adjust/` | CREDIT → `points.add`/`points.adjust`; DEBIT → `points.deduct`/`points.adjust`; writes ledger + AuditLog in one transaction |

There is **no** `/api/admin/points/` namespace — point administration lives under `/api/points/sellers/...`.

---

## 9. Customer, Cart, Orders, Inventory, Payments

### Customer
`CustomerProfile` (OneToOne user) and `Address` (`customers/models.py`), with a `unique_default_address_per_user` constraint backed by a derived `default_flag` column. Endpoints: `GET/PATCH /api/profile/me/` (`profile.view`/`profile.update`), `/api/addresses/` CRUD + `/api/addresses/<pk>/set-default/` (`address.*` codes + `IsAddressOwner`). Profiles are created at registration or lazily on first profile GET — **no post_save signal**.

### Cart
`Cart` is **OneToOne with User** (`cart/models.py:12-18`) — one cart per user, **no guest cart** in the DRF app. `CartItem` stores no prices; `unit_price`/`line_total` read live from `product.price`. Endpoints `/api/cart/` and `/api/cart/items/[<pk>/]` all require auth plus `cart.view`/`cart.update`. **There is no guest-cart merge on login** — the frontend keeps a guest cart in localStorage (`minishop-cart`) and it is simply abandoned once the server cart loads.

### Orders
Statuses `PENDING → CONFIRMED → PROCESSING → SHIPPED → DELIVERED`, with `CANCELLED` reachable from everything up to PROCESSING; `DELIVERED`/`CANCELLED` terminal (`shop/models.py:330-343`).

`OrderService.create_order_from_cart` (`shop/services.py:361-592`) is fully atomic: `select_for_update()` on cart and items, re-validates every product's public visibility, resolves the address with ownership checks, **snapshots prices server-side onto OrderItem** (client-supplied prices are ignored), reserves inventory, clears the cart, writes an audit entry.

| Surface | Endpoints |
|---|---|
| Customer | `GET/POST /api/orders/`, `GET /api/orders/<pk\|order_number>/`, `PATCH /api/orders/<...>/cancel/` — `orders.view` / `orders.create` / `orders.cancel`, ownership enforced with safe 404 |
| Seller | `GET /api/seller/orders/`, `GET /api/seller/orders/<order_number>/`, `PATCH .../status/` — scoped to the seller's own items via a `Prefetch(to_attr="seller_items")`, so only their items serialize |
| Staff | `GET /api/staff/orders/[<pk\|order_number>/]`, `PATCH .../status/` — `orders.staff.view` / `orders.staff.update`. Consumed by the Next.js console at `/admin/orders` (built 2026-09-18; see [Review History](#21-review-history)). |

**Guest checkout — the precise answer:** through the JSON API, **no** (POST `/api/orders/` requires `IsAuthenticated` + `orders.create`, and the service requires a user cart). Through the **legacy server-rendered flow**, **yes**: `shop/views.py:111-145` `checkout()` has no auth at all and, for a guest, creates an `Order` with `user` left NULL. That path still bypasses `OrderService` entirely — no inventory reservation, no audit, no price re-validation (see Known Issues #1b).

**Legacy order ownership (fixed 2026-09-17).** `checkout()` now records ownership two ways: it sets `Order.user` when the buyer is authenticated, and it writes the new order's id into the session under `placed_order_ids` (`shop/views.py:_remember_placed_order`). `order_success()` authorizes every read through `_can_view_order()` — session that placed the order, owning user, or the staff override — and raises a safe `Http404` otherwise. The session is the ownership token for guests, so guest checkout keeps working with no login and no client-supplied identifier is ever trusted. The staff override is shared with the JSON API through `shop/permissions.py:can_user_view_any_order`.

### Inventory
`ProductInventory` (available / reserved / sold, each with a `>= 0` CheckConstraint) plus an `InventoryTransaction` ledger. `InventoryService` reserve → release → finalize-sale all run inside the caller's atomic block with `select_for_update()`, and release/finalize are idempotent (guarded by an existing RELEASE/SALE row). Endpoints under `/api/seller/inventory/...` (aliased at `/api/inventory/...`) gated on `inventory.view` / `inventory.adjust` plus per-object ownership.

`Product.stock` and `ProductInventory.available_quantity` are **two stores kept in sync by convention**. `InventoryService` (reserve/release/finalize/adjust) always keeps them in lockstep under `select_for_update()`. The one path that used to bypass this — `ProductService.update_product`'s direct `stock` write — was fixed 2026-09-18; see Known Issues #2.

### Payments & Refunds
`Payment` statuses `PENDING/PROCESSING/PAID/FAILED/CANCELLED/REFUNDED/PARTIALLY_REFUNDED`; methods `CASH_ON_DELIVERY/BKASH/NAGAD/ROCKET/CARD/ONLINE`. `Refund` is PROTECT-linked to payment and order. Amounts always come from `order.total_amount` server-side; the client may only pick a method.

Flow: `GET/POST /api/orders/<...>/payment/` (authenticated + ownership, no extra RBAC code) → `POST /api/staff/payments/<pk>/verify/` (`payments.verify`/`payments.process`) → `POST /api/staff/payments/<pk>/refund/` (`payments.refund`/`orders.refund`). All mutations funnel through `PaymentService` with `transaction.atomic()` + `select_for_update()`; there is no generic PUT/PATCH on Payment or Refund, and Django admin registers both read-only. **Refunds do not restore inventory** — stock only returns when an *order* transitions to CANCELLED.

Staff-facing surface: `GET /api/staff/payments/` (list, filters `status`/`payment_method`/`order_number`) and `GET /api/staff/payments/<pk>/` both use the same `PaymentSerializer` — no separate list/detail shape, unlike Orders — which exposes no customer identity at all (only `order_id`/`order_number`). Verify (`POST .../verify/`, body `{status: PAID|FAILED, transaction_id?, reason?}`) returns the full updated `PaymentSerializer`. Refund (`POST .../refund/`, body `{amount?, reason?}`, `amount` omitted = full remaining) returns only the created `RefundSerializer` (201) — **not** the updated payment — so a caller that needs the payment's new `status`/`refundable_amount` must re-fetch it. Consumed by the Next.js console at `/admin/payments` (built 2026-09-18; see [Review History](#21-review-history)).

---

## 10. Reviews & Ratings

`Review` (`customers/models.py:191-242`): `user`, `product` (`related_name="customer_reviews"`), `rating` 1–5 (validators + `clean()`), `comment`, `is_verified_purchase`, timestamps. `UniqueConstraint(user, product)` named `unique_review_per_user_product`.

| Method | Endpoint | Authorization |
|---|---|---|
| POST | `/api/reviews/` | `IsAuthenticated` + `reviews.create`; duplicate → **409 Conflict** |
| PATCH/DELETE | `/api/reviews/<pk>/` | `IsReviewOwner` (owner, or superuser/SUPER_ADMINISTRATOR) |
| GET | `/api/reviews/mine/?product_id=<id>` | authenticated — returns the caller's single review for that product |
| GET | `/api/products/<product_id>/reviews/` | AllowAny, paginated |

**Verified purchase is a badge, not a gate.** Anyone with `reviews.create` may review any public product. `is_verified_purchase` is computed **once at creation** (`customers/services.py:297-301`) as "this user has an OrderItem for this product on an order with status `DELIVERED`", and is never recomputed on edit.

`average_rating` / `review_count` are **query annotations**, not stored columns — added in `ProductService.get_public_products_queryset()` (`shop/services.py:297-305`) and exposed on `/api/products/`, `/api/products/<pk|slug>/`, related products and `/api/hot-deals/`. Any endpoint that serializes products through a different queryset will report zeros (see Known Issues #7).

Not implemented: review images, seller/shop replies, helpful votes, moderation/approval workflow (reviews go live immediately), flagging, rating histogram, review list ordering/filter params.

---

## 11. Management Console (Next.js `/admin`)

Distinct from Django's own admin at backend `/admin/`. They share no code and use different auth (JWT vs session).

**Backend APIs** — all in `shop/admin_views.py`, re-exported through `shop/api_views.py:1356`, routed in `shop/urls.py:63-82`. Pagination `AdminPagination` (page_size 20, max 100) on all lists **except roles, which is unpaginated**.

| Resource | Endpoints | Permission |
|---|---|---|
| Users | GET/POST `/api/admin/users/`, GET/PATCH `/<pk>/` | `users.admin.view` / `users.admin.manage` |
| Roles | GET/POST `/api/admin/roles/`, GET/PATCH/DELETE `/<pk>/`, GET `/api/admin/permissions/` | `roles.admin.view` / `roles.admin.manage` |
| Sellers | GET/POST `/api/admin/sellers/`, GET `/<pk>/`, POST/PATCH `/<pk>/status/` | `sellers.admin.manage` (view also accepts `sellers.view`) |
| Shops | GET/POST `/api/admin/shops/`, GET `/<pk>/`, POST/PATCH `/<pk>/status/` | `shops.admin.manage` (status also accepts `shops.approve`, approve-only) |
| Products | GET `/api/admin/products/`, GET `/<pk>/`, POST/PATCH `/<pk>/status/` | `products.admin.manage`/`products.view`; per-action codes on status. **No create/update.** |
| Categories | GET/POST `/api/admin/categories/`, GET/PATCH/DELETE `/<pk>/` | `categories.admin.manage` on **all** methods, reads included. Delete is blocked when products reference the category. |
| Customers | GET `/api/admin/customers/[<pk>/]` | `customers.admin.view` — **read-only** |
| Metrics | GET `/api/admin/metrics/` | ad-hoc staff/role/`admin:access` check |
| Audit logs | GET `/api/admin/audit-logs/` | `audit.view`/`audit.admin.view`/`users.admin.view`/`roles.admin.view`; `http_method_names` hard-limited to get/head/options |

Every admin mutation writes an `AuditLog` (`ADMIN_USER_CREATED`, `ADMIN_ROLE_CREATED`, `ADMIN_SHOP_<ACTION>`, `ADMIN_PRODUCT_<ACTION>`, …) with actor, reason, previous/new state and client IP. Admin serializers use explicit `fields` + `read_only_fields`, exclude password/hash/token fields entirely (password is `write_only` on user create only), and redact `SENSITIVE_KEYS` from audit metadata (`admin_serializers.py:819`).

**Frontend routes:** `/admin`, `/admin/login`, `/admin/profile`, and list/detail(/new) families for `shops`, `sellers`, `users`, `roles`, `products` (no `new`), `categories`, `customers`, **`orders`**, **`payments`** (list + detail, no `new` for either — orders/payments are never created by staff directly), plus a catch-all `/admin/[...slug]` that renders an "Awaiting Implementation" placeholder for the one remaining nav entry with no page yet (`/admin/audit-logs`).

`AdminGuard` + `isManagementUser` (`frontend/src/lib/admin-auth.ts:52-76`) admits a user holding **any** of: `is_superuser`, `is_staff`, a management role code, or a permission matching `admin:access` / `*` / `*.admin.manage` / `*.staff.view`. This only controls console *navigation* — every backend endpoint still enforces its own permission code. Nav visibility is driven by `admin-navigation.ts`; the console's API layer is the dedicated `frontend/src/lib/admin-api.ts`.

Django's own admin is heavily customized (`config/admin_site.py` swaps in `MiniShopAdminSite` with platform metrics; `rbac/widgets.py` renders MiniShop permissions as a checkbox board on the User page) and remains the raw data-editing surface for staff.

---

## 12. Frontend Route Inventory

Verified against `npm run build` output plus the actual `page.tsx` files.

**Public:** `/`, `/product/[slug]`, `/shop/[slug]`, `/shops`, `/login`, `/register`, `/checkout`, `/order-success/[orderNumber]`

**Customer:** `/profile` (redirects to `/profile/settings`), `/profile/settings`, `/profile/orders`, `/profile/orders/[orderNumber]`, `/profile/addresses`, `/profile/favorites`, `/profile/track`
 — plus `/account`, `/account/profile`, `/account/orders`, `/account/orders/[orderNumber]`, `/account/addresses`, which are **legacy redirect shims** into the `/profile/*` family (each file is a 4-line `redirect()`).

**Seller:** `/seller`, `/seller/shops`, `/seller/products`, `/seller/orders`, `/seller/wallet`, `/seller/profile`
 — flat pages only; the seller panel deliberately has **no `new` or `[id]` sub-routes**, create/edit is modal-based within each page. (The admin console uses the opposite convention.)

**Management:** `/admin`, `/admin/login`, `/admin/profile`, `/admin/shops[/new|/[id]]`, `/admin/sellers[/new|/[id]]`, `/admin/users[/new|/[id]]`, `/admin/roles[/new|/[id]]`, `/admin/products[/[id]]`, `/admin/categories[/[id]]`, `/admin/customers[/[id]]`, `/admin/[...slug]`

Guards: `SellerGuard` (fetches `/api/sellers/dashboard/`, renders "Seller Account Required" on 404), `AdminGuard` (see above), and inline auth checks in `app/profile/layout.tsx`. A `ProtectedRoute` component exists but **is used by zero pages**.

---

## 13. Important Business Rules

### Implemented and verified

| Rule | Where enforced |
|---|---|
| Seller types are `FULL_SHOP_OWNER`, `LIMITED_SHOP_OWNER`, `PRODUCT_OWNER` | `sellers/models.py:9-17` |
| A seller cannot create a Shop | `shops/views.py:130-146` (hard 403); no UI control exists |
| Admin creates the Shop and assigns the owning seller | `shop/admin_views.py:809-864` → `ShopService.create_shop` |
| Max **1 shop** per shop-owner; `PRODUCT_OWNER` gets **0** | `shops/services.py:96-115` |
| Product ownership is `Product → shop → shop.owner`; no seller column | `shop/models.py:71-200` |
| A seller may only read/modify products of their own shop | `IsProductOwner` + `ProductService` ownership checks + `shop__owner=seller` queryset |
| A seller cannot move a product to another seller's shop | `ProductService.update_product:212-218`, `SellerProductUpdateSerializer.validate_shop_id` |
| Product creation costs **5 points**, deducted atomically backend-side | `ProductService.create_product` + `PointService.debit` |
| Insufficient points blocks creation; balance unchanged; never negative | balance check + `select_for_update` + DB CheckConstraint |
| Seller products start as `DRAFT`; only staff can approve/publish | `ProductService.create_product:135`, `shop/admin_views.py:1027-1098` |
| Public catalog requires product PUBLISHED + active, category active, shop APPROVED/ACTIVE, seller APPROVED/ACTIVE | `ProductQuerySet.public()` |
| One review per user per product; rating 1–5; edit/delete only your own | `unique_review_per_user_product`, `IsReviewOwner` |
| Order prices are snapshotted server-side; client prices ignored | `OrderService.create_order_from_cart` |
| API authorization is MiniShop RBAC, never Django `auth.Permission` | `rbac/services.has_user_permission` used by every permission class |
| Only a wildcard holder may delegate beyond their own permissions | `get_undelegatable_permission_codes` |
| `SUPER_ADMINISTRATOR` and `ADMINISTRATOR` are protected roles | `PROTECTED_ROLE_CODES` |

### Intended but NOT fully implemented

| Intent | Reality |
|---|---|
| "Admin creates/configures the Seller" | An authenticated user can self-register a SellerProfile (`POST /api/sellers/register/`). It lands in `PENDING` and is inert until an admin approves it, assigns a shop and grants an RBAC role — but the endpoint contradicts the stated flow. |
| Guest checkout supported | True only on the legacy server-rendered `/checkout/` path, which bypasses `OrderService`. The JSON API used by the Next.js storefront requires authentication. |
| Product `SUBMITTED` state | Constant, column and metrics exist, but nothing can set it — no seller submit endpoint. |
| Seller sees points earned/spent totals | The UI renders these, but the API never returns them (always 0). |

---

## 14. Security & Authorization

**Verified mechanisms**

- JWT bearer auth (SimpleJWT) with rotation; all privileged endpoints declare explicit DRF permission classes.
- Every permission class resolves through `has_user_permission()` → MiniShop RBAC. Superuser / `SUPER_ADMINISTRATOR` short-circuit is consistent and deliberate.
- Ownership is checked **server-side on every seller/customer resource**, independent of the request payload: shop ownership on product create/update, `IsProductOwner` object checks, `shop__owner=seller` list scoping, order ownership with safe 404s, address and review owner checks.
- Cross-shop payload tampering is blocked: a supplied `shop_id` is validated against the caller's own shops before use; a multi-shop data inconsistency returns 409 rather than silently choosing.
- **`OrderService` authorization contract, audited end-to-end 2026-09-17.** Two of its mutators authorize themselves — `cancel_customer_order()` (`shop/services.py:690-698`, owner or staff override) and `transition_seller_order_status()` (`:804-828`, seller must own an item, plus the multi-seller guard). `transition_order_status()` (`:595`) authorizes **nothing** and is the one every caller must guard. Its callers are `StaffOrderStatusAPIView` (`CanUpdateStaffOrders`) and `OrderAdmin._transition_orders` — the latter was unguarded until #15. Reads follow the same shape: `get_seller_order()` raises `NotFound` off-scope, and every view resolving an order from a client-supplied `id`/`order_number` re-checks ownership with a safe 404 before the service is reached.
- Point integrity: `transaction.atomic()` + `select_for_update()` + model validator + **DB CheckConstraint `balance >= 0`**, with an append-only ledger recording before/after balances and the actor.
- Order/inventory/payment mutations are atomic with row locks; inventory release and sale-finalization are idempotent.
- Anti-escalation on role editing; protected roles cannot be abused; role deletion guarded.
- Admin serializers never expose password, hash or token fields; audit metadata redacts sensitive keys.
- Audit logging on product mutations, all admin governance mutations, point adjustments, reviews and orders.

**Known security limitations** (see Known Issues for detail)

- ~~The legacy server-rendered order-success view has **no ownership check** (#1)~~ — **fixed 2026-09-17**; reads are now authorized by session, owner or staff override.
- ~~The Django-admin order actions call `OrderService.transition_order_status()` with no permission of their own (#15)~~ — **fixed 2026-09-17**; they now declare `allowed_permissions = ("change",)`.
- ~~The equivalent Django-admin **seller and shop** lifecycle actions declare no `allowed_permissions` (#16)~~ — **fixed 2026-09-18**; all eight now declare it, and the shared `ReasonRequiredActionMixin` re-checks `has_change_permission()`. With #15 and #16 done, **all three** ModelAdmins that declare custom actions are guarded — the class is closed project-wide.
- API-driven seller lifecycle transitions are not audited (#6).
- Dev-posture settings: `DEBUG = True`, a hardcoded `SECRET_KEY` committed in `settings.py`, and a 4-character minimum password. Must change before any production deployment.
- Access tokens cannot be revoked (no blacklist); "logout" is client-side only.
- JWTs are stored in `localStorage`, so they are reachable by XSS.

---

## 15. Test Status — as of 2026-09-17

**Inventory:** ~493 test methods across 25 files (462 at the full review, +9 from the legacy-IDOR fix, +14 from the OrderService authorization fix, +8 from the seller/shop admin-action fix).

| File | Tests | | File | Tests |
|---|---|---|---|---|
| `shop/test_admin_governance.py` | 84 | | `shop/test_seller_product.py` | 23 |
| `shop/test_public_catalog.py` | 26 | | `shop/test_staff_orders.py` | 23 |
| `points/tests.py` | 29 | | `shop/test_payments.py` | 21 |
| `shops/tests.py` | 27 | | `rbac/test_direct_permissions.py` | 21 |
| `shop/tests.py` | 33 | | `shop/test_admin_phase1.py` / `test_product_reviews.py` | 19 / 19 |
| `cart/tests.py` | 17 | | `customers/tests.py` | 16 |
| `shop/test_inventory.py` / `test_seller_orders.py` | 15 / 15 | | `rbac/tests.py` / `test_admin_permission_board.py` | 14 / 14 |
| `shop/test_customer_orders.py` | 13 | | `shop/test_orders.py` / `test_admin_site.py` | 11 / 11 |
| `rbac/test_registration.py` / `sellers/tests.py` | 8 / 8 | | `shop/test_admin_metrics.py` | 4 |

| Check | Result |
|---|---|
| `manage.py check` | **Pass** — "System check identified no issues (0 silenced)" |
| `manage.py makemigrations --check --dry-run` | **Pass** — "No changes detected" (schema and models are in sync) |
| `shop.test_seller_product` (23 tests) | **Pass** — 23/23 OK, ~500s |
| `shop.tests shop.test_orders shop.test_customer_orders` (57 tests, legacy-IDOR fix) | **Pass** — `Ran 57 tests in 2011s … OK`, 0 failures |
| `shop.test_order_service_authorization` (14 tests, new) | **Pass** — `Ran 14 tests in 145s … OK` |
| `shop.test_customer_orders shop.test_seller_orders shop.test_staff_orders shop.test_admin_site` (62 tests, OrderService-authorization regression) | **Pass apart from the known #14** — `Ran 62 tests in 460s … FAILED (failures=1)`; the single failure is the pre-existing Taka assertion |
| `audit.test_admin_action_authorization` (8 tests, new) | **Pass** — `Ran 8 tests in 61s … OK`. Against the unfixed code the same file reported `FAILED (failures=10)`. |
| `sellers shops shop.test_admin_site` (46 tests, seller/shop admin-action regression) | **Pass apart from the known #14** — `Ran 46 tests in 657s … FAILED (failures=1)`; same pre-existing Taka assertion |
| Full backend suite | **Ran 462 tests in 5509s (~92 min) — `FAILED (failures=1)`.** The single failure is `shop.test_admin_site.AdminRegistrySmokeTests.test_dashboard_renders_taka_not_dollar`, and it is **pre-existing** (see Known Issues #14). Everything else passes. |
| `npx tsc --noEmit` | **Pass** — exit 0 |
| `npm run build` | **Pass** — exit 0, 40 static pages, all seller/admin routes compiled |

**Environment notes for whoever runs these next**
- Always pass `--noinput`; a stale `test_minishop` database otherwise blocks on an interactive prompt and an unattended run hangs forever.
- `--keepdb` saves several minutes of migration replay.
- The suite is **very slow** on this MySQL setup (~4 tests/minute observed). Budget an hour for a full run, or target specific modules.
- Use `backend/venv/`, not the repo-root `.venv/` (missing `reportlab`).

---

## 16. Known Issues

#1–#14 were discovered during the 2026-09-17 review and all were open at that point; **#1, #15 and #16 have since been fixed** — see the Status column. #15 and #16 were both found on 2026-09-17 during the OrderService authorization audit; #16 was fixed on 2026-09-18.

| # | Issue | Area | Severity | Status |
|---|---|---|---|---|
| 1 | **Legacy checkout IDOR.** `order_success(request, order_id)` did `get_object_or_404(Order, id=order_id)` with **no ownership or session check** — any visitor could read any order (customer name, phone, address) by walking sequential ids. | Legacy server-rendered flow | **High** | **FIXED 2026-09-17.** `checkout()` now records ownership server-side (`Order.user` for authenticated buyers, `request.session["placed_order_ids"]` for everyone including guests) and `order_success()` authorizes through `_can_view_order()` — session / owner / staff override — returning a safe 404 otherwise. Covered by `shop.tests.LegacyOrderAccessTests` (9 tests). |
| 1b | The same legacy `checkout()` (`shop/views.py:111-145`) still creates orders **bypassing `OrderService`**: no inventory reservation, no audit entry, no product-eligibility re-validation (`shop/cart.py:68-94` filters on `is_active` only, so a DRAFT product or one from a suspended shop can still be ordered through this path), and none of the `shipping_*`/`subtotal` snapshot fields are populated. Split out of #1 when the IDOR was fixed. | Legacy server-rendered flow | Medium | **Open — re-classified 2026-09-17.** Audited specifically for an authorization bypass and **there is none**: prices come from `Product.price` server-side via the session cart, the session holds no client-supplied totals, and the flow only ever *creates* an order — it accepts no order id and touches no existing order. This is a correctness/consistency gap, not a security issue. Knock-on effect worth noting: because these orders carry no RESERVE ledger row, cancelling one makes `release_order_reservation()` release `min(reserved_quantity, item.quantity)` from stock reserved by *other* orders (`shop/inventory_service.py:258`). |
| 2 | **Stock Desynchronization #2.** `ProductService.update_product` listed `"stock"` in `updatable_fields` (`shop/services.py:220-235`) and wrote `Product.stock` directly **without touching `ProductInventory`**, so `PATCH /api/products/mine/<pk>/` silently desynced `Product.stock` from `ProductInventory.available_quantity`. `Product.in_stock` reads inventory while the cart serializer reads `product.stock`. Reproduced deterministically: `update_product(..., data={"stock": 5})` on a product with `stock=20`/`available_quantity=20` left `Product.stock == 5` while `ProductInventory.available_quantity` stayed `20`. **Audited and confirmed NOT an overselling/security bug** — `InventoryService.reserve_stock_for_cart` (the sole gate used by `OrderService.create_order_from_cart`) reads `ProductInventory.available_quantity`, never `Product.stock`, so the desync could not be exploited to oversell; it was a data-integrity/display-correctness gap. | Seller products / inventory | **Medium** | **FIXED 2026-09-18.** `update_product` (`shop/services.py:220-257`) no longer sets `Product.stock` directly. When `"stock"` is present it takes `select_for_update()` on the product's `ProductInventory` row (creating it first if needed), computes the delta from the requested absolute value against the locked `available_quantity`, and — if non-zero — applies it through `InventoryService.adjust_stock()`, which is what actually keeps `Product.stock` and `ProductInventory.available_quantity` in lockstep, writes the `ADJUSTMENT` ledger row, and records the `INVENTORY_ADJUSTED` audit entry. A no-op request (`stock` unchanged) writes nothing. Locking is held for the remainder of the caller's transaction, so a concurrent reservation cannot land between the read and the write. No new inventory system was introduced — this reuses the existing sanctioned `InventoryService.adjust_stock` path already used by `SellerInventoryAdjustAPIView`. Covered by 5 new tests in `shop/test_inventory.py` (`test_seller_update_stock_stays_synced_with_inventory`, `_increase_`, `_noop_when_unchanged`, `_respects_existing_reservation`, and an API-level `test_api_seller_product_update_stock_stays_synced_with_inventory`). |
| 3 | Seller wallet UI contract mismatch: the page reads `wallet.total_earned` / `wallet.total_spent` (`seller/wallet/page.tsx:96,111`) and `txn.description` (`:204`), but `SellerWalletSerializer` returns neither total (only `balance`) and `PointTransactionSerializer` exposes `reason`, not `description`. The TS types declare the missing fields, so `tsc` cannot catch it. Tiles always show `+0`/`-0`; every row reads "Point transaction". | Seller panel | Medium | Pre-existing; newly documented. |
| 4 | `get_seller_capabilities` reports `can_create_shop: true` for FULL/LIMITED shop owners (`sellers/services.py:51-58`), contradicting the enforced hard-403 on shop creation. Stale flag; misleading to any UI that trusts it. | Sellers | Medium | Pre-existing; newly documented. |
| 5 | `POST /api/sellers/register/` allows **self-service** SellerProfile creation with only `IsAuthenticated` (`sellers/views.py:30-34`), contradicting the documented "admin creates/configures the Seller" flow. Mitigated: the profile lands in `PENDING`, has no shop, and gets no RBAC role, so it can do nothing until an admin acts. No frontend calls it. | Sellers | Medium | Pre-existing; newly documented. Decide intent before changing. |
| 6 | Seller lifecycle transitions performed through the DRF endpoints write **no AuditLog** (`sellers/views.py` contains no `AuditService` call), while the equivalent Django-admin actions do. Approve/reject/suspend via API is therefore untracked. | Sellers / audit | Medium | Pre-existing; newly documented. |
| 7 | `/api/favorites/` serializes products through an unannotated queryset (`customers/views.py:178-183`), so favorites always report `average_rating: 0.0, review_count: 0`. | Reviews / favorites | Low | Pre-existing; newly documented. |
| 8 | `Product.STATUS_SUBMITTED` and `submitted_at` exist and are counted in metrics, but **nothing can set them** — there is no seller "submit for review" endpoint. | Products | Low | Pre-existing; newly documented. |
| 9 | Checkout's login prompt links to `/login?redirect=/checkout` but the login page reads `?next=`, so the return-to-checkout redirect silently does nothing. | Frontend | Low | Pre-existing; newly documented. |
| 10 | Dead surface: `ProtectedRoute` component is referenced by no page; `/account/*` routes are pure redirect shims. | Frontend | Low | Pre-existing. |
| 11 | The seller products page hardcodes `PRODUCT_CREATION_COST = 5` (`seller/products/page.tsx:19`) instead of reading the configurable `ProductCreationCost`. If an admin changes the cost, the UI lies (the backend still charges correctly). | Seller panel | Low | Pre-existing. |
| 12 | Dev-posture config committed: `DEBUG = True`, hardcoded `SECRET_KEY`, password `MinimumLengthValidator` set to 4 characters. | Config | Medium (for production only) | Pre-existing; acceptable for local dev. |
| 13 | `/api/admin/roles/` returns an unpaginated plain array while every other admin list is paginated — an inconsistency for frontend consumers. | Admin API | Low | Pre-existing. |
| 14 | **The one failing backend test.** `shop.test_admin_site.AdminRegistrySmokeTests.test_dashboard_renders_taka_not_dollar` asserts `assertIn("৳", body)` against the raw admin dashboard HTML (`shop/test_admin_site.py:91-95`), but `templates/admin/index.html:80` emits the numeric character reference `&#2547;`, not the literal `৳`. The entity renders correctly as ৳ in a browser, so **this is an assertion/template mismatch in the test, not a user-visible currency bug** — the test as written can never pass. Fixing it means either asserting `&#2547;` or rendering the literal character. Note the test's second assertion (`assertNotIn("$", body)`) has not been exercised and may also fail once the first is fixed. | Tests / Django admin | Low | **Pre-existing**, not caused by current working-tree changes: the render path (`config/admin_site.py`, `shop/metrics.py`, `templates/admin/index.html`) is unmodified at HEAD — the template last changed in `51e6c84`, the test in `3f0a5da`. Reproduces deterministically in isolation. |
| 15 | **Django-admin order actions had no permission of their own.** `OrderAdmin`'s five lifecycle actions (`confirm_orders`, `mark_orders_processing`, `mark_orders_shipped`, `mark_orders_delivered`, `cancel_orders`) called `OrderService.transition_order_status()` while declaring no `allowed_permissions`. Django only permission-filters actions that declare one (`django/contrib/admin/options.py:1063-1077`) and the changelist opens on `has_view_or_change_permission`, so any account with `is_staff` + `shop.view_order` could drive **every customer's** order through the full lifecycle — releasing reservations, writing irreversible SALE ledger rows and triggering automatic refunds on paid orders. Reproduced before the fix: a `view_order`-only account moved a PENDING order to CONFIRMED. | Django admin / orders | **High** | **FIXED 2026-09-17.** All five actions now declare `allowed_permissions = ("change",)`, and `_transition_orders()` re-checks `has_change_permission()` before reaching the service. Covered by `shop.test_order_service_authorization` (14 tests). |
| 16 | The same unguarded-action pattern as #15 on `SellerProfileAdmin` (`sellers/admin.py` — approve/suspend/reject/reactivate) and `ShopAdmin` (`shops/admin.py` — the same four). Neither the eight actions nor their shared helpers (`ReasonRequiredActionMixin.run_simple_action` / `run_reason_action`) checked any permission, so `is_staff` + `view_sellerprofile` / `view_shop` was enough to approve, reject, suspend or reactivate any seller or shop — and to write an AuditLog entry naming the read-only account as actor. **All eight reproduced before the fix** (e.g. a PENDING seller driven to ACTIVE, an ACTIVE shop to SUSPENDED). Posting the `apply_reason` payload directly skipped the confirmation page, which was never a gate. | Django admin / sellers, shops | **High** | **FIXED 2026-09-18.** All eight declare `allowed_permissions = ('change',)`, and both mixin helpers call `_require_change_permission()`. Covered by `audit.test_admin_action_authorization` (8 tests). |
| 17 | **New, found 2026-09-18.** On `/admin/orders` (list page), a successful status-transition action merges only `{id, status}` from the backend's response into the row's local state (`page.tsx`'s `handleActionSuccess`), rather than replacing the whole row. Fields that can also change as a side effect of a transition — e.g. `payment_status` turning `REFUNDED` after cancelling a paid order — stay stale in the list until the page is reloaded or a filter is changed. The **detail page does not have this gap**: `handleActionSuccess` there replaces the entire `AdminOrderDetail` with the fresh API response, so `allowed_transitions`, `payment`, and `refunds` are always current immediately after a transition. | Management Console / Orders | Low (cosmetic; no incorrect mutation, no stale data persists past a refetch) | Open; not fixed by this audit (audit-only scope). |

---

## 17. Known Limitations

Intentionally deferred or simply not built. These are **not** bugs.

- **No logout / token revocation** endpoint; no password reset flow.
- **No guest-cart merge** on login; a guest's localStorage cart is abandoned rather than merged.
- **No guest order-lookup API** — guest orders (`user=NULL`) created by the legacy path are unreachable from `/api/orders/`.
- **Reviews are minimal by design**: no images, seller replies, helpful votes, moderation workflow, flagging, or rating histogram.
- **No seller-side product submission/publishing** — publication is staff-only.
- **No seller-facing dedicated inventory page** in the seller panel (the API exists).
- **Admin console modules not built**: `/admin/audit-logs` appears in navigation but renders the "Awaiting Implementation" placeholder (the read-only API already exists backend-side). `/admin/orders` and `/admin/payments` were both built 2026-09-18 — see [Review History](#21-review-history).
- **No Support ticketing, reports/analytics, or notifications** — no backend at all for these.
- **Refunds do not restore inventory**; stock only returns on order cancellation.

---

## 18. Important Architecture Decisions

Future work must not accidentally reverse these.

1. **The backend is the authority.** Every security-sensitive rule (ownership, points, pricing, status transitions) is enforced server-side regardless of what the frontend sends.
2. **MiniShop RBAC is the API authorization system.** Never use Django `auth.Permission` / `user_permissions` to authorize an API. Never build a second permission system.
3. **Seller is not an RBAC role** — it is a SellerProfile. Product permissions come from a separately granted RBAC role.
4. **Sellers never create shops.** Shops are created and assigned by administrators. `POST /api/shops/mine/create/` is intentionally kept routed so direct calls get an explicit 403 instead of a 404.
5. **Single shop per shop-owner** (`FULL`/`LIMITED` → max 1, `PRODUCT_OWNER` → 0), enforced in `ShopService`. Do not introduce multi-shop UI or "shop switcher" behavior.
6. **Never silently pick a shop.** If a seller somehow owns more than one shop, product creation returns 409 rather than guessing — guessing would be an ownership bypass.
7. **Product ownership is derived through the shop.** Do not add a `seller` FK to Product.
8. **Product creation costs points, deducted atomically with creation** through the existing `PointService` + ledger. Never add a second wallet, a second ledger, or client-side deduction.
9. **Domain services are mandatory paths.** `ProductService`, `OrderService`, `InventoryService`, `PaymentService`, `PointService`, `AuditService` own their mutations; generic CRUD must not bypass them. Admin product *create/update* deliberately does not exist for this reason.
10. **The Next.js management console is separate from Django's `/admin/`.** Both are kept; they serve different purposes.
11. **Reuse the centralized frontend API layer** (`lib/api.ts` for storefront/seller, `lib/admin-api.ts` for the console). Do not scatter raw `fetch()` calls.
12. **Seller panel = flat pages with modals; admin console = nested `new`/`[id]` routes.** Two deliberate conventions; follow whichever panel you are in.
13. **Design tokens only** (`bg-surface`, `text-ink`, `border-line`, …) — never hardcoded Tailwind palette colors. Currency is always `৳`.

---

## 19. Completed Work

Reconstructed from source, tests and git history. Backend work was tracked as **Tasks 1–17** (`task/task*.md`); frontend work as **Phases** (`task/Master_Prompt.md`).

| Work | Status | Evidence |
|---|---|---|
| Tasks 1–12: user/auth/JWT, RBAC, sellers, shops (incl. spatial nearby search), products, categories, customers, addresses, cart | Complete | app code + per-app test suites |
| Task 13–14: orders + inventory (reservation/release/sale ledger) | Complete | `shop/test_orders.py`, `test_customer_orders.py`, `test_inventory.py` |
| Task 15: payments & refunds | Complete | `shop/test_payments.py` (21 tests) |
| Task 16: staff order operations | Complete | `shop/test_staff_orders.py` (23 tests) |
| Task 17: admin & platform governance | Complete | `shop/test_admin_governance.py` (84 tests), `/api/admin/*` |
| Admin console frontend (shops, sellers, products, categories, customers, users, roles) | Complete | `frontend/src/app/admin/**`; commits `d953958`, `e4fa861`, `61eef96`, `e4e42b5`, `98f9031` |
| Admin user/seller/points management | Complete | commit `9753095` |
| Order items inline fix + invoice PDF download | Complete | commit `0d07b8a` |
| Prompt-injection removed from `frontend/AGENTS.md` | Complete | commit `5552532` |
| **Admin-assigned shop ownership + single-shop cap + seller product management** (Phase 1H/1I) | Complete | commit `b623553`; `shop/test_seller_product.py` |
| **Product reviews & ratings** | Complete | commit `c4fb3b8`; `shop/test_product_reviews.py` |
| **Legacy checkout IDOR fix** (Known Issues #1) | Complete — most recent change | `shop/views.py`, `shop/permissions.py`, `shop/api_views.py`; `shop/tests.py::LegacyOrderAccessTests` |

---

## 20. Current Project State

**Last completed change:** `/admin/payments` Management Console module (Phase 1K) — Next.js Payments list + detail with permission-gated verify (mark paid/failed) and refund (full or partial) actions, built entirely on the existing `/api/staff/payments/` API. Zero backend changes. A feature, not a fix.
**Preceding change:** Post-Orders architecture & security audit (2026-09-18, no code changes beyond this file) — re-verified the Orders console against live source, re-confirmed all four prior security fixes and RBAC/seller/shop rules are unchanged (zero backend diff since `ce7cf2a`), re-checked every open Known Issue, found one new low-severity issue (#17), and set **Payments** as the next task on stronger evidence than before.
**Preceding change:** `/admin/orders` Management Console module (Phase 1J) — Next.js Orders list + detail with permission-gated status-transition actions, built entirely on the existing `/api/staff/orders/` API. Zero backend changes. A feature, not a fix.
**Preceding change:** Post-security-fix architecture & roadmap audit (no code changes beyond this file).
**Preceding change:** Stock Desynchronization #2 fix — `ProductService.update_product` no longer writes `Product.stock` directly; it routes through `InventoryService.adjust_stock` under row lock. A targeted data-integrity fix, not a feature. Audited and confirmed there was no overselling/security exposure.
**Preceding change:** Seller/shop Django-admin action authorization (#16) — the eight lifecycle actions now require `change` permission. With #15 this closes the unguarded-admin-action class project-wide.
**Preceding change:** OrderService authorization fix — the Django-admin order actions now require `change` permission (#15).
**Preceding change:** Legacy checkout IDOR fix — a targeted security hardening of the server-rendered `/order-success/<id>/` page, not a feature.
**Last completed feature:** `/admin/payments` Management Console module (this entry).
**Preceding feature:** `/admin/orders` Management Console module (Phase 1J).

**Working tree:** backend clean at `ce7cf2a`; this update adds frontend-only changes (`frontend/src/lib/admin-api.ts`, `frontend/src/app/admin/payments/`) plus this file. `frontend/src/app/admin/orders/` from the preceding task is untouched.

**What is implemented:** the full commerce chain (catalog → cart → checkout → orders → inventory → payments/refunds), the seller panel, the management console (now including Orders and Payments), RBAC governance, points/wallet, and reviews.

**Next planned phase.** With Orders (Phase 1J) and Payments (Phase 1K) both done, `/admin/audit-logs` is the sole remaining "Missing" console module, and it differs from the other two in kind: Django Admin already provides a working (read-only) view of `AuditLog`, so this is a console-consistency gap, not a capability gap the way Payments was before this task. No file in this repo formally names it "Phase 1L" — that would again be this file's own continuation label, not a cited spec, per the same caveat recorded for "Phase 1J"/"1K." Before treating Audit Logs as automatically next, a future review should re-run the same "is there really no other way to do this today" check this audit applied to Payments, and re-scan the Known Issues list (§16) for anything that has become higher priority in the meantime.

**Constraints future work must preserve:** everything in [Architecture Decisions](#18-important-architecture-decisions), plus the regression-sensitive areas — customer auth, storefront catalog, cart, orders, payments, inventory, seller orders/wallet, admin governance, RBAC, and the public `average_rating` / `review_count` fields.

**Immediate follow-ups:** the legacy template checkout still bypasses `OrderService` (#1b, confirmed to be a correctness gap rather than a security one) — decide whether to route it through the service or retire the template flow; decide intent on seller self-registration (#5); the one failing test (#14) is a trivial assertion fix. The legacy order-success IDOR (#1), the whole unguarded-admin-action class (#15, #16), and the `Product.stock` / `ProductInventory` desync on seller product update (#2) are done.

---

## 21. Review History

### 2026-09-18 — `/admin/payments` Management Console module (Phase 1K)

- **Scope**: implement the Next.js Management Console Payments module only — `/admin/payments` (list) and `/admin/payments/[id]` (detail), with verify and refund actions — on top of the existing `/api/staff/payments/` API, per the preceding audit's evidence-based recommendation. No Audit Logs, no backend changes, no RBAC changes, no changes to Orders.
- **Audited before writing any code**: `shop/models.py` (`Payment`/`Refund`, `Payment.VALID_TRANSITIONS`, `can_transition_to`), `shop/api_views.py` (`StaffPaymentListAPIView`, `StaffPaymentDetailAPIView`, `StaffPaymentVerifyAPIView`, `StaffPaymentRefundAPIView`), `shop/serializers.py` (`PaymentSerializer`, `RefundSerializer`, `PaymentVerifySerializer`, `RefundCreateSerializer`), `shop/permissions.py` (`CanViewPayment`, `CanVerifyPayment`, `CanRefundPayment`), `shop/payment_service.py` (`PaymentService.process_payment_success/process_payment_failure/process_refund/handle_order_cancellation`), and `shop/urls.py:51-54`. Confirmed field-for-field and endpoint-for-endpoint before defining any frontend type.
- **Two contract details that shaped the implementation, found only by reading source (not assumed):**
  1. **No separate list/detail serializer.** Unlike Orders, `StaffPaymentListAPIView` and `StaffPaymentDetailAPIView` both use the same `PaymentSerializer`, which exposes no customer identity at all — only `order_id`/`order_number`. The task brief itself warned against inventing customer data the serializer doesn't provide; this was verified directly rather than assumed, and the UI shows only what the field list actually contains, linking to the order for anything more.
  2. **The refund endpoint's response is not the updated payment.** `StaffPaymentRefundAPIView.post` returns `RefundSerializer(refund)` (201) — the created Refund row — never the Payment. `PaymentService.process_refund` computes the new `status`/`refundable_amount` server-side but that result is never returned to this caller. Reconstructing it client-side would mean recomputing a financial state machine in the frontend, which is explicitly forbidden. The frontend instead re-fetches the payment (`getAdminPaymentDetail`) immediately after a successful refund and treats that response as the sole source of truth — never a locally-guessed merge.
- **Zero backend changes were needed.** Verify enforces its own state machine via `payment.can_transition_to()` inside `PaymentService.process_payment_success`/`process_payment_failure`; refund enforces its own eligibility (`status` must be `PAID`/`PARTIALLY_REFUNDED`) and amount bounds (`0 < amount <= remaining_refundable`, remaining computed server-side from the `Refund` ledger under `select_for_update()`) inside `PaymentService.process_refund`. Nothing client-side re-implements any of this — it only decides which buttons to show.
- **Frontend reused, not duplicated**, the existing architecture: `admin-api.ts` for the fetch layer (same `AdminApiError`/`adminRequest` pattern as every other module), the shared `AdminDataTable`/`AdminFilterBar`/`AdminPagination`/`AdminStatusBadge`/`AdminConfirmModal` components **verbatim, with zero modifications** — the refund amount is collected via a plain inline `<input type="number">` on the detail page (not inside the modal), so the existing single-reason-textarea `AdminConfirmModal` could be reused for the confirmation step exactly as-is rather than extending its API and risking every other module that already depends on it. A colocated `paymentGovernance.tsx` mirrors `orderGovernance.tsx`'s shape (status/method label maps, an action-descriptor catalogue, two mutation hooks, an access-notice component). `ADMIN_PERMISSIONS.paymentsView`/`paymentsVerify`/`paymentsRefund` and the `/admin/payments` nav entry already existed in `admin-navigation.ts` and needed no changes.
- **Permissions**: view gated on `payments.view` (`CanViewPayment`), verify on `payments.verify` **or** `payments.process` (`CanVerifyPayment`), refund on `payments.refund` **or** `orders.refund` (`CanRefundPayment`) — all via `hasAnyPermission`, matching the backend classes' own OR-logic exactly, including the superuser/`SUPER_ADMINISTRATOR` bypass. No new permission codes were introduced. UI gating is courtesy-only; every mutation still hits its real endpoint, which independently re-authorizes.
- **Verify actions**: "Mark Paid" and "Mark Failed" only, since `PaymentVerifySerializer.status` never accepts anything else — no UI exists for a transition the endpoint cannot perform. Offered only when the current status is `PENDING` or `PROCESSING`, mirroring the only states `Payment.VALID_TRANSITIONS` allows to reach `PAID`/`FAILED` from — once a payment is `FAILED`, this endpoint genuinely cannot re-verify it (no transition from `FAILED` to `PAID`/`FAILED` exists), and the console does not pretend otherwise. The modal's single reason field is relabeled per action: a transaction reference for "Mark Paid" (stored, but not required — `PaymentService.process_payment_success` doesn't require it either), a failure reason for "Mark Failed".
- **Refund action**: shown only when `status` is `PAID`/`PARTIALLY_REFUNDED` and `refundable_amount > 0` (cosmetic mirror of the backend gate). The amount field is optional and defaults to the full remaining amount when left blank, exactly matching `RefundCreateSerializer`/`PaymentService.process_refund`'s own "omit = full refund" semantics — never separately computed or capped by the frontend beyond an HTML `max` attribute that is a UX hint, not a validation boundary (the real bound is enforced server-side). The confirmation modal states the amount that will be refunded before it is submitted.
- **Files added**: `frontend/src/app/admin/payments/page.tsx` (list — search by order number, status filter, payment-method filter, row verify actions, pagination), `frontend/src/app/admin/payments/[id]/page.tsx` (detail — payment info, metadata, refund history table, inline refund form, verify actions), `frontend/src/app/admin/payments/paymentGovernance.tsx` (shared governance helpers).
- **Files modified**: `frontend/src/lib/admin-api.ts` — appended a new "STAFF PAYMENT OPERATIONS (Phase 1K)" section (`AdminPayment`, `AdminRefund`, `getAdminPayments`, `getAdminPaymentDetail`, `verifyAdminPayment`, `refundAdminPayment`). Nothing existing in the file was changed. `frontend/src/app/admin/orders/**` was not touched.
- **Verification**: `npx tsc --noEmit` → clean, no errors, no `any`/`@ts-ignore`. `npm run build` → succeeded; the route table confirms `/admin/payments` (static) and `/admin/payments/[id]` (dynamic) now compile as real pages, and every previously-existing route (including `/admin/orders` and `/admin/orders/[id]`) is unaffected. No backend code changed, so the backend suite was not required to be re-run — `shop.test_payments` (21 tests) was nonetheless run fresh as read-only confirmation of the exact contract this module depends on: `Ran 21 tests … OK`.
- **Not touched**: `/admin/audit-logs` (left as the placeholder), `PaymentService`/`RefundService` logic, `OrderService`, inventory, `Order`/`OrderItem` models, RBAC, JWT/auth, Django Admin's `PaymentAdmin`/`RefundAdmin` read-only lock (left exactly as-is, per explicit instruction), `/checkout`, `/seller/orders`, the Orders console, and every Known Issue including #17.

### 2026-09-18 — Post-Orders architecture & security audit (audit only, no code changes)

- **Scope**: verify the just-shipped `/admin/orders` module against live source rather than trusting the implementation's own report, re-confirm the four prior security fixes and RBAC/seller/shop rules are still intact, re-check every open Known Issue, search for new problems, and pick exactly one next task with fresh evidence. No feature, fix, model, migration, RBAC, or business-rule change was made.
- **Git baseline confirmed**: HEAD `5b2a59e`; `git diff --stat ce7cf2a..HEAD` touches only `docs/MINISHOP_REVIEW_STATE.md` and the four Orders-module frontend files — **zero backend files changed** since `ce7cf2a`. This alone re-confirms, without needing to re-read every line, that the legacy-checkout IDOR fix (#1), Order Admin authorization (#15), Seller/Shop Admin authorization (#16), and the stock-desync fix (#2) are all still exactly as they were when each was directly verified against source in the preceding two audits — the code implementing them has not moved.
- **Orders console re-verified directly against source** (not assumed from having just written it): re-read `StaffOrderListAPIView`/`StaffOrderDetailAPIView`/`StaffOrderStatusAPIView`, `CanViewStaffOrders`/`CanUpdateStaffOrders`, and `Order.VALID_TRANSITIONS`, and cross-checked every query param, field name, and permission code the frontend uses against them. All matched exactly: `search`/`status`/`payment_status`/`start_date`/`end_date` params, the `StandardResultsSetPagination` page-size-12 contract, every `AdminOrderDetail`/`AdminOrderListItem` field, and the `orders.staff.view`/`orders.staff.update` gates. Ran `shop.test_staff_orders` fresh (23 tests) → `OK` — the API contract the console depends on is validated at this exact commit, not merely "unlikely to have changed."
- **One new finding, self-identified in the console's own code (#17, Low).** On the list page, a successful status transition merges only `{id, status}` from the API response into the row (`orderGovernance.tsx`'s `useOrderStatusAction` + `page.tsx`'s `handleActionSuccess`), so a field that changes as a *side effect* of the transition — e.g. `payment_status` becoming `REFUNDED` when a paid order is cancelled — stays stale in the list view until the page is refetched. The detail page has no such gap: it replaces the whole `AdminOrderDetail` from the fresh response. Cosmetic only — no incorrect mutation, no security exposure, nothing persists past a refetch. Not fixed here (audit-only scope); recorded as Known Issue #17.
- **RBAC premise check.** The task brief for this audit asserted "There is NO `UserPermission`" as something to verify. Checked `rbac/models.py` directly: `UserPermission` **does exist** (line 135) as the documented single-account direct-grant exception (`User → UserPermission → Permission`, alongside `User → UserRole → Role → RolePermission → Permission`) — this file's own §4 already recorded this correctly. The brief's premise was simply wrong; the architecture is unchanged and this file needed no correction here.
- **Known Issues re-checked against current source, not reused from memory**: #6 (seller lifecycle API audit gap) — confirmed still open: `grep AuditService sellers/views.py` returns nothing, so `/api/sellers/<pk>/approve|reject|suspend|reactivate/` still write no audit entry, unlike their Django-admin equivalents. #7 (favorites rating annotation) — confirmed still open: `FavoriteListCreateView.get()` queries `Favorite.objects.filter(user=...)` directly, never through `ProductService.get_public_products_queryset()` where `average_rating`/`review_count` are annotated. #13 (roles endpoint unpaginated) — confirmed still open: `AdminRoleListCreateAPIView.get()` returns `Role.objects.all()` with no pagination class. #3/#9/#10/#11 were re-confirmed in the previous audit turn and are unchanged (no frontend files touched besides the new `orders/` directory). #1b, #5, #8, #12, #14 unchanged; #14 remains the sole pre-existing test failure and was not touched.
- **New evidence gathered on the Payments-vs-Audit-Logs choice.** Read `shop/admin.py:392-446` directly: `PaymentAdmin` and `RefundAdmin` hardcode `has_add_permission`/`has_change_permission`/`has_delete_permission` to `False` — Django Admin is fully locked for both models by design. Combined with `/admin/payments` still being the Next.js placeholder, this means **no administrative UI anywhere in the project can currently invoke `PaymentService.process_payment_success()` or `process_refund()`** (both fully implemented and already reachable at `POST /api/staff/payments/<pk>/verify|refund/`) — only a raw authenticated API call can. By contrast, Audit Logs already has a working (if not the intended) UI: Django Admin registers `AuditLog` read-only and it renders in the sidebar. This is a materially stronger justification for Payments than "it's next in the precedent order," which was the previous audit's reasoning.
- **Verification**: `manage.py check` → no issues. `shop.test_staff_orders` → 23/23 `OK`. `npx tsc --noEmit` → clean. `npm run build` → success, same route table as the implementation turn. Backend suite not re-run in full — no backend files changed, so a full run would re-confirm nothing beyond what the `git diff --stat` already proves.
- **Not touched**: every application file. Only this document changed.

### 2026-09-18 — `/admin/orders` Management Console module (Phase 1J)

- **Scope**: implement the Next.js Management Console Orders module only — `/admin/orders` (list) and `/admin/orders/[id]` (detail) — on top of the existing `/api/staff/orders/` API, per the preceding audit's recommendation. No Payments, no Audit Logs, no backend changes, no RBAC changes.
- **Audited before writing any code**: `shop/api_views.py` (`StaffOrderListAPIView`, `StaffOrderDetailAPIView`, `StaffOrderStatusAPIView`), `shop/serializers.py` (`StaffOrderListSerializer`, `StaffOrderDetailSerializer`, `StaffOrderItemSerializer`, `StaffOrderPaymentSummarySerializer`, `StaffOrderRefundSummarySerializer`, `StaffOrderStatusUpdateSerializer`), `shop/permissions.py` (`CanViewStaffOrders`, `CanUpdateStaffOrders`), `shop/models.py` (`Order.VALID_TRANSITIONS`, `can_transition_to`), and `shop/urls.py:51-60`. Confirmed field-for-field before defining any frontend type — no field was guessed.
- **Zero backend changes were needed.** The API already returns everything the task's detail-page spec asked for (order header, customer, shipping snapshot, items, totals, payment summary, refunds, `allowed_transitions`) and already enforces the state machine server-side via `order.can_transition_to()` inside `OrderService.transition_order_status()`.
- **Frontend reused, not duplicated**, the existing Phase 1B–1I architecture: `admin-api.ts` for the fetch layer (matching the exact `AdminApiError`/`adminRequest` pattern every other module uses), the `AdminDataTable`/`AdminFilterBar`/`AdminPagination`/`AdminStatusBadge`/`AdminConfirmModal` shared components verbatim, and a colocated `orderGovernance.tsx` mirroring `shopGovernance.tsx`'s shape (status labels, an action-descriptor catalogue, a `useOrderStatusAction` hook, an access-notice component) — the same pattern already used by Shops/Sellers/Products. `ADMIN_PERMISSIONS.ordersView`/`ordersUpdate` and `admin-navigation.ts`'s `/admin/orders` nav entry already existed (evidently provisioned ahead of this task) and needed no changes.
- **Permissions**: view gated on `orders.staff.view` (`CanViewStaffOrders` — superuser / `SUPER_ADMINISTRATOR` bypass included), mutation gated on `orders.staff.update` (`CanUpdateStaffOrders`), both via `hasAnyPermission(user, ADMIN_PERMISSIONS.ordersView/ordersUpdate)`. No new permission codes were introduced. UI gating is courtesy-only — a hidden action or an inaccessible page never substitutes for the backend's own check, and every mutation still goes through `StaffOrderStatusAPIView` → `OrderService.transition_order_status()`.
- **Status actions**: one descriptor per reachable target status (`CONFIRMED`, `PROCESSING`, `SHIPPED`, `DELIVERED`, `CANCELLED`), offered per row from a client-side mirror of `Order.VALID_TRANSITIONS` (list page, since the list serializer has no `allowed_transitions`) or from the server-computed `allowed_transitions` field directly (detail page, preferred where available). Confirmation uses the existing `AdminConfirmModal` with an **optional** note field, matching `StaffOrderStatusUpdateSerializer.note` being optional for every transition (no reason is required backend-side, unlike Shop reject/suspend). A rejected transition (e.g. a race with another operator) surfaces the backend's own error message in the modal and leaves state untouched, exactly like the Shop/Product action flow.
- **Files added**: `frontend/src/app/admin/orders/page.tsx` (list — search by order number, status filter, payment-status filter, date range, row actions, pagination), `frontend/src/app/admin/orders/[id]/page.tsx` (detail — header, customer, delivery/shipping, items table, totals, payment + refunds, metadata, action buttons), `frontend/src/app/admin/orders/orderGovernance.tsx` (shared governance helpers for both pages).
- **Files modified**: `frontend/src/lib/admin-api.ts` — appended a new "STAFF ORDER OPERATIONS (Phase 1J)" section (`AdminOrderListItem`, `AdminOrderDetail`, `AdminOrderItem`, `AdminOrderShippingAddress`, `AdminOrderPaymentSummary`, `AdminOrderRefundSummary`, `getAdminOrders`, `getAdminOrderDetail`, `updateAdminOrderStatus`). Nothing existing in the file was changed.
- **Verification**: `npx tsc --noEmit` → clean, no errors. `npm run build` → succeeded; the route table confirms `/admin/orders` (static) and `/admin/orders/[id]` (dynamic) now compile as real pages rather than falling through to the `[...slug]` placeholder, and every other route is unaffected. No backend code changed, so the backend test suite was not re-run (per this task's own instruction not to re-run it unnecessarily when nothing backend-side changed) — `shop.test_staff_orders` was inspected (not executed) to confirm the API contract this module relies on has dedicated coverage already.
- **Not touched**: `/admin/payments`, `/admin/audit-logs` (left as the placeholder, per explicit scope), `OrderService`/`InventoryService`/`PaymentService`, `Order`/`OrderItem` models, RBAC, JWT/auth, `/checkout`, `/seller/orders`, Django Admin, and Known Issues #14.

### 2026-09-18 — Post-security-fix architecture & roadmap audit (audit only, no code changes)

- **Scope**: verify the four recently-completed security/integrity fixes still hold at current HEAD, cross-check this file's frontend/backend claims against live source rather than trusting the prior write-up, and identify one evidence-based next task. No feature, business-logic, API, model, migration, RBAC, auth or frontend code was touched — only this file.
- **All four fixes reconfirmed directly in source** (not re-derived from this file): legacy checkout IDOR (`shop/views.py` — `_can_view_order`/`_remember_placed_order`/`can_user_view_any_order`, safe `Http404`, guest session + owner + staff override all present); Order Admin authorization (`shop/admin.py` — all five order actions declare `allowed_permissions = ("change",)`, `_transition_orders` re-checks `has_change_permission`); Seller/Shop Admin authorization (`sellers/admin.py`, `shops/admin.py` — all eight actions declare `allowed_permissions = ('change',)`; `audit/admin_mixins.py` — `ReasonRequiredActionMixin._require_change_permission()` guards both shared helpers); Stock Desynchronization #2 (`shop/services.py:220-256` — `"stock"` removed from the generic `updatable_fields` loop, routed through `InventoryService.adjust_stock()` under `select_for_update()`).
- **Zero frontend drift.** `git diff --stat c4fb3b8..HEAD -- frontend/` is empty — every commit since the last full review touched only `backend/` and this file. This means the frontend section of this document could be trusted with only spot-verification rather than a full re-audit, and the spot checks (below) all confirmed no discrepancy.
- **Spot-verified against live source** (sample, not exhaustive, chosen to cover both a "definitely still true" and a "would invalidate the recommendation if wrong" check): `/admin/[...slug]` placeholder (`frontend/src/app/admin/[...slug]/page.tsx`) genuinely renders "Awaiting Implementation" with no data fetching for unbuilt modules — confirmed by reading the file, not just the nav config; seller wallet UI mismatch (#3) — `seller/wallet/page.tsx` still reads `wallet.total_earned`/`total_spent`/`txn.description`, `SellerWalletSerializer` still exposes only `balance` — confirmed unresolved; checkout↔login redirect param mismatch (#9) — `checkout/page.tsx` still links `/login?redirect=/checkout`, `login/page.tsx` still only reads `next` — confirmed unresolved; `ProtectedRoute` (#10) — the component file exists and a repo-wide grep for its name returns only its own definition — confirmed still dead; hardcoded product-creation cost (#11) — `seller/products/page.tsx:19` still has `const PRODUCT_CREATION_COST = 5` — confirmed unresolved. None of these were fixed by this audit; they are recorded as still-open, matching their existing Known Issues entries.
- **The "Phase 1I spec" claim in this file did not hold up.** Searched the whole repo (`task/*.md`, `forAdminPanel/*.md`, git log across all branches) for anything naming a "Phase 1I" or "Phase 1J" with a defined scope. Found nothing — `task1.md`–`task17.md` are backend tasks unrelated to this letter/number scheme, and `forAdminPanel/{ImplementationPlan,task_list}.md` use their own unrelated "Phase 0–6" numbering for a *different, already-complete* effort (the **Django** admin at `/admin/`, explicitly out-of-scope of the Next.js console). The "Phase 1H/1I" label on commit `b623553` in the Completed Work table, and the "Phase 1I's spec explicitly defers review moderation..." line this file previously carried in §20, are this file's own retrospective labels, not citations of an actual spec document. Corrected in §20 rather than deleted, so the correction itself is on record.
- **Next task determined from what's actually backend-ready and still a placeholder**, not from the unsupported phase claim: `/admin/orders`, `/admin/payments`, `/admin/audit-logs` are the three remaining "Missing" console modules (verified via the placeholder page plus a repo-wide check that `frontend/src/lib/admin-api.ts` has no order/payment/audit-log API functions yet — only passing references inside dashboard metrics and the customer-detail "recent orders" summary). All three already have working, RBAC-gated backend APIs (`shop/urls.py:51-60` for staff orders/payments, `:82` for admin audit-logs; `orders.staff.view/update`, `payments.verify/refund`, `audit.view`/`audit.admin.view` all seeded in `seed_rbac.py`). Recommended **`/admin/orders`** specifically — the direct Next.js-console counterpart to the just-hardened Django-admin `OrderAdmin` (#15) — as the single next task, with Payments and Audit Logs deliberately left as separate follow-ups to match the project's own one-module-per-commit precedent.
- **Not touched**: all backend and frontend application code, RBAC, auth, all migrations, `#14` (left as pre-existing/out of scope per the task brief), and every other Known Issue — none were fixed, none were newly marked fixed.
- **Verification**: no tests were re-run beyond what the immediately preceding stock-desync task already ran fresh at this same HEAD (`shop.test_inventory shop.test_seller_product` 43/43 OK, `shop.tests cart.tests` 50/50 OK) and the source-level re-reads of the four fix sites above, which is what this audit brief calls for ("do not rerun the entire test suite unless necessary").

### 2026-09-18 — Stock Desynchronization #2 audit (fixed)

- **Scope**: dedicated audit of Known Issues #2, "Stock Desynchronization" — the whole stock lifecycle (product create/update, cart→order reservation, cancellation release, delivery finalization, direct/admin stock mutation, concurrency/locking) was walked against source before touching anything, per the task brief. This file already carried #2 as a documented-but-unfixed finding from the 2026-09-17 review; the audit verified it against current source rather than trusting the prior write-up.
- **Architecture confirmed sound apart from one bypass.** `ProductInventory` (`available_quantity`/`reserved_quantity`/`sold_quantity`, each with a DB `CheckConstraint >= 0`) is the authoritative store. `InventoryService` is the sole sanctioned mutation path: `reserve_stock_for_cart` (called inside `OrderService.create_order_from_cart`'s atomic block, `select_for_update()` per product, rejects if `available_quantity < qty`), `release_order_reservation` (cancellation; idempotent via an existing `RELEASE` ledger-row check), `finalize_order_delivery` (idempotent via an existing `SALE` ledger-row check), and `adjust_stock` (seller/staff manual adjustment). All four lock the `ProductInventory` row with `select_for_update()`, enforce non-negative results, write an immutable `InventoryTransaction` ledger row, and keep `Product.stock` synchronized as they go.
- **No overselling / concurrency vulnerability found.** Order creation's stock gate is `InventoryService.reserve_stock_for_cart`, which locks and re-checks `ProductInventory.available_quantity` inside `create_order_from_cart`'s own `transaction.atomic()` — two concurrent checkouts serialize on the row lock, so the second sees the first's decrement before it can oversell. Cart add/update (`cart/models.py`, `cart/serializers.py`) performs no stock check of its own — it is UX-only and cannot bypass the reservation gate at checkout. Cancellation and delivery-finalization idempotency were re-verified directly (not merely re-asserted): both guard on an existing ledger row of the relevant type before mutating anything, so repeated calls are no-ops.
- **The one confirmed gap: `ProductService.update_product` bypassed `InventoryService` entirely.** `"stock"` was listed in `updatable_fields` (`shop/services.py:220-235` at audit time) and set directly on the `Product` row via `setattr` + `product.save()` — no `ProductInventory` read, no lock, no ledger entry. Reachable via `PATCH /api/products/mine/<pk>/` (`SellerProductUpdateSerializer.stock`, `shop/serializers.py:275`, unrestricted by anything but `min_value=0`).
- **Reproduced deterministically before fixing** (temporary test, discarded after use — not committed): seeded a product with `stock=20` / `ProductInventory.available_quantity=20`, called `ProductService.update_product(product, seller, {"stock": 5}, actor=user)`, and observed `Product.stock == 5` while `ProductInventory.available_quantity` remained `20`. Output captured: `BEFORE: product.stock=20 inventory.available=20` → `AFTER: product.stock=5 inventory.available=20`.
- **Severity assessment: data-integrity bug, not a security/overselling bug.** Every path that actually gates a purchase (`InventoryService.reserve_stock_for_cart`, `Product.in_stock`) reads `ProductInventory.available_quantity`, never `Product.stock`. So the desync could make the seller UI/API lie about quantity, but a seller inflating `Product.stock` this way could not make the checkout gate admit more units than `ProductInventory` actually held, and shrinking it could not free reserved/sold units early. Confirms the pre-existing classification in this file (Medium, not High).
- **Fix**, following "smallest safe architectural change": `shop/services.py`, `ProductService.update_product`. Removed `"stock"` from the generic `updatable_fields` `setattr` loop. When the caller's `data` includes `"stock"`, the method now: (1) ensures a `ProductInventory` row exists, (2) takes `select_for_update()` on it, (3) computes `stock_delta = requested_absolute_stock - locked.available_quantity`, and (4) if the delta is non-zero, applies it through the existing `InventoryService.adjust_stock()` — the same sanctioned path already used by `SellerInventoryAdjustAPIView`. This means the PATCH endpoint's contract (client sends the desired absolute stock) is unchanged, but the mutation is now locked, ledgered, audited, and impossible to desync. Holding the lock for the remainder of the caller's transaction closes the read-then-write race a naive "read available, compute delta, call adjust_stock separately" version would have against a concurrent reservation. No second inventory system was introduced; no other stock-mutation path was touched.
- **Tests**: 5 new tests added to `shop/test_inventory.py` (`InventoryTests`, section 9) — sync on decrease (with ledger-row assertion), sync on increase, no-op / no spurious ledger row when the value is unchanged, correctness when units are already reserved (reserved_quantity must be untouched, only available moves), and an API-level test through `PATCH /api/products/mine/<pk>/`. All reuse existing fixtures; none are timing-based.
- **Verification**: `manage.py check` → no issues. `shop.test_inventory shop.test_seller_product` (43 tests, includes the 5 new + all 23 seller-product tests) → `Ran 43 tests … OK`. Regression: `shop.tests cart.tests` (50 tests, broader Product/cart surface) → `Ran 50 tests … OK`. Full 400+ suite was not run — not required for a change scoped to one method plus new tests in the two directly-affected modules, per the task's own instruction not to run the full suite unless genuinely needed.
- **Not touched**: `InventoryService` itself (already correct), `OrderService`, cancellation/delivery finalization, concurrency/locking elsewhere (already sound), the legacy checkout flow (#1b), review moderation, payment console, RBAC, frontend, and Known Issues #14 (pre-existing Taka assertion, untouched).

### 2026-09-18 — Seller/shop Django-admin action authorization (#16 fixed)

- **Scope**: the vulnerability class from #15, applied to the seller and shop admins. Audited both registrations in full rather than assuming they matched `OrderAdmin`.
- **Seller findings — all four actions vulnerable.** `SellerProfileAdmin` (`sellers/admin.py`) declares `approve_and_activate`, `suspend_sellers`, `reject_sellers`, `reactivate_sellers`. None declared `allowed_permissions`; all four mutate `SellerProfile.status` through `sellers/services.py` and write an `ADMIN_SELLER_*` AuditLog entry.
- **Shop findings — all four actions vulnerable.** `ShopAdmin` (`shops/admin.py`) declares `approve_and_activate`, `suspend_shops`, `reject_shops`, `reactivate_shops`, mutating `Shop.status` through `ShopService` with `ADMIN_SHOP_*` audit entries. Same omission.
- **The shared helpers were unguarded too.** Both admins route through `ReasonRequiredActionMixin.run_simple_action()` / `run_reason_action()` (`audit/admin_mixins.py`), neither of which checked any permission — so the gap sat in the common path, not only in the eight declarations.
- **Reproduced before fixing.** All eight ran successfully for an account with `is_staff` + `view_sellerprofile` + `view_shop` and no change permission: a PENDING seller was driven to ACTIVE, an ACTIVE shop to SUSPENDED, and so on. The suspend/reject confirmation page is **not** a gate — posting the `apply_reason` + `reason` payload directly skips it. The pre-fix run of the new test file reported `FAILED (failures=10)`.
- **Side effect worth recording**: each unauthorized action also wrote an AuditLog row naming the read-only account as `actor`, so the gap corrupted the audit trail as well as the data. The tests assert that no such row is written.
- **Fix**, following #15 exactly: all eight actions declare `allowed_permissions = ('change',)` (`sellers/admin.py`, `shops/admin.py`), and `ReasonRequiredActionMixin` gained `_require_change_permission()`, called at the top of both helpers (`audit/admin_mixins.py`). Django's own admin `view`/`change` authorization — no new permissions, no change to MiniShop RBAC, no new framework, and the seller/shop lifecycle rules and services are untouched.
- **Tests**: `audit/test_admin_action_authorization.py`, 8 tests. Placed in `audit` because that is where the shared mixin lives. Loops over all eight actions from a table of (action, starting status, expected status), driving the real admin changelist POST: read-only refused on every action with state *and* audit trail unchanged; change-authorized user and superuser still able to run every action; and `get_actions()` offering the actions to the editor but not the read-only account.
- **Verification**: `manage.py check` → no issues. `audit.test_admin_action_authorization` → 8/8 OK. `sellers shops shop.test_admin_site` → 46 tests, 1 failure, that failure being the pre-existing #14 Taka assertion.
- **Class now closed.** Only three ModelAdmins in the project declare custom actions — `OrderAdmin` (#15), `SellerProfileAdmin` and `ShopAdmin` (#16) — and all three are guarded. Neither seller nor shop admin defines `get_urls`, `list_editable` or a `save_model` override, so there is no other mutation path on those two surfaces.
- **Not touched**: frontend, MiniShop RBAC, JWT auth, seller onboarding, points, the stock desync (#2), #1b, #14, and the `list_editable` fields on `CategoryAdmin` / `ProductAdmin` / the rbac admins (Django gates those on `has_change_permission` natively, and they are outside this task's seller/shop scope).

### 2026-09-17 — OrderService authorization audit (#1b re-classified, #15 found and fixed)

- **The suspected bypass was not where this file said it was.** #1b was carried forward as "the OrderService-bypass half", and the task framed it as an authorization bypass. Audited against source rather than against this file, and the two do not agree.
- **No cross-customer bypass exists on the JSON API.** Enumerated every DRF view in the backend by AST — all 91 declare either `permission_classes` or `get_permissions()`, none relies on the DRF default. Every view that resolves an order from a client-supplied `id` or `order_number` (`OrderDetailAPIView`, `OrderCancelAPIView`, `_get_customer_order_or_404`, `OrderService.get_seller_order`) re-checks ownership server-side and returns a safe 404 before the service is reached. `CUSTOMER` holds none of `orders.update` / `orders.seller.*` / `orders.staff.*` (`rbac/management/commands/seed_rbac.py:215-222`), and nothing in the codebase sets `is_staff = True` implicitly, so the staff override cannot be reached by an ordinary account.
- **#1b itself is a correctness gap, not a security one** — re-classified in Known Issues with the evidence. The legacy flow only creates orders, accepts no order identifier, and prices from `Product.price` server-side.
- **A real bypass was found one step further out**, at the caller the audit brief called "any direct `OrderService` call": `OrderAdmin._transition_orders` (`shop/admin.py`). Django permission-filters only those changelist actions that declare `allowed_permissions`, and the changelist opens on view permission alone — so `is_staff` + `shop.view_order` was enough to run all five order actions into `OrderService.transition_order_status()`. **Reproduced before fixing**: a `view_order`-only account moved another customer's order PENDING → CONFIRMED. Recorded as #15.
- **Fix** (`backend/shop/admin.py`, +16 lines): the five actions declare `allowed_permissions = ("change",)`, and `_transition_orders()` re-checks `has_change_permission()` so a future action wired to the same helper cannot silently reintroduce the gap. This uses Django's own admin authorization — no new RBAC, no new permission model, and `OrderService` is unchanged.
- **Tests**: `shop/test_order_service_authorization.py`, 14 new tests — the three damaging admin actions refused for a read-only account (status, inventory ledger, payment and refunds all asserted unchanged), the editor and superuser paths still working, cross-customer cancellation by id and by order number, the service-level `PermissionDenied`, and the customer / seller / staff happy paths. `Ran 14 tests … OK`.
- **Regression**: `shop.test_customer_orders shop.test_seller_orders shop.test_staff_orders shop.test_admin_site` → 62 tests, 1 failure, that failure being the pre-existing #14 Taka assertion. `shop.tests.LegacyOrderAccessTests` re-run for guest checkout. `manage.py check` passes.
- **Not touched**: frontend (no API contract changed — the fix is inside Django admin, which the Next.js console does not use), `OrderService` itself, the DRF permission classes, #1b, and the seller/shop admin actions that share the #15 pattern (logged as #16).

### 2026-09-17 — Targeted security fix: legacy checkout IDOR (Known Issues #1)

- **Root cause confirmed in source**, not assumed from this file: `shop/views.py` `order_success()` resolved the order purely from the URL's `order_id` path parameter and rendered it. Any visitor could enumerate ids at `/order-success/<n>/` and read another buyer's name, phone, delivery address, order number and total. Unauthenticated read-only exposure, affecting both guest and authenticated buyers' orders.
- **Fix**: ownership is now recorded server-side at checkout and checked on read.
  - `shop/views.py` — `checkout()` sets `Order.user` for authenticated buyers and calls `_remember_placed_order()`, which appends the order id to `request.session["placed_order_ids"]` (capped at 20). `order_success()` gates on `_can_view_order()`: placing session → owner → staff override, else `Http404`.
  - `shop/permissions.py` — new `can_user_view_any_order()` + `ORDER_OVERRIDE_ROLES`, the single source of truth for the staff/admin order-read override.
  - `shop/api_views.py` — `OrderDetailAPIView` now calls that helper instead of its own inline copy. Behaviour-preserving; it removes the duplicate that would otherwise drift from the legacy path.
- **Guest checkout preserved.** The session is the ownership token, so `Guest → Cart → Checkout → Order` still works with no account and no login prompt. No client-supplied identifier is trusted anywhere in the new path.
- **Deliberately a 404, not a 403**, so the page cannot be used as an order-existence oracle — matching what the JSON order API already returns for someone else's order.
- **Tests**: `shop.tests.LegacyOrderAccessTests` (9 new) covers owner access, cross-visitor 404, id tampering, anonymous access to an owned order, the staff override, unknown ids, guest checkout still succeeding, and rejected cross-customer cancellation. Ran `shop.tests shop.test_orders shop.test_customer_orders` → **57 tests, OK, 0 failures**. `manage.py check` passes.
- **Not touched**: frontend (the Next.js `/order-success/[orderNumber]` page reads the already-secure `/api/orders/<order_number>/`, so no API-contract change was needed), the `OrderService` bypass on the legacy checkout (split out as #1b), and every other known issue.

### 2026-09-17 — Initial persistent review
- Full backend architecture reviewed against source: config/settings, RBAC core, sellers, shops, products, points, customers, cart, orders, inventory, payments, reviews, audit, admin governance.
- Full frontend reviewed: public storefront, customer area, seller panel, management console, API layer, guards, route inventory.
- API and route inventories built from actual `urls.py` files and the production build output.
- Verified: single-shop cap, seller-cannot-create-shop, 5-point product cost with atomic deduction, product ownership chain, RBAC delegation boundary, protected roles, admin audit logging and credential exclusion.
- Ran `manage.py check` (pass), `makemigrations --check` (pass), `npx tsc --noEmit` (pass), `npm run build` (pass), and the **full backend suite: 462 tests, 1 failure** — a pre-existing Taka-entity assertion mismatch in a Django-admin smoke test (#14).
- 14 known issues and 10 known limitations recorded. No application code changed by this review.

---

## Future Review Procedure

Run this loop for every subsequent review:

```
Read this file  →  inspect git changes  →  review affected systems
   →  verify against current source  →  run relevant tests  →  update this file
```

1. **Read `docs/MINISHOP_REVIEW_STATE.md` first.**
2. **Find what changed:**
   ```bash
   git status
   git log --oneline -n 20
   git diff <last-reviewed-commit>..HEAD --stat
   ```
   The "Reviewed at commit" line at the top of this file is your baseline.
3. **Use this document for the prior architecture** — do not re-derive it.
4. **Review the changed files** and the systems they touch.
5. **Re-verify any entry here that those changes affect**, against the real source. Entries carry `file:line` to make this cheap.
6. **Run the relevant tests / build checks** (targeted first; full suite when the change is broad).
7. **Update this file**: changed architecture, new routes/APIs, new or resolved issues, new decisions, new completed work, refreshed test status, and a new Review History entry. Update the "Reviewed at commit" line.
8. **Preserve history.** Correct outdated entries in place; don't delete the record of how the project evolved.

**Do a full deep audit instead of an incremental one when:** this file is missing or clearly stale; authentication, RBAC or security changed; the database schema changed significantly; several phases landed at once; the source contradicts this file; or there is simply not enough evidence to trust the previous state.

**Maintenance rules:** one canonical file (this one) — no per-phase review files, no duplicates. Keep it dense; link to code rather than pasting it. Never record secrets, credentials or personal data. Never let this file outrank the source code.

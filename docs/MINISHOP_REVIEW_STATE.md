# MiniShop — Persistent Review State

**Last full review:** 2026-09-17
**Reviewed at commit:** `c4fb3b8` (`feat(reviews): add product reviews and ratings`)
**Last targeted update:** 2026-09-17 — legacy checkout IDOR fixed (Known Issues #1 resolved). See [Review History](#21-review-history).

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
| Staff | `GET /api/staff/orders/[<pk\|order_number>/]`, `PATCH .../status/` — `orders.staff.view` / `orders.staff.update` |

**Guest checkout — the precise answer:** through the JSON API, **no** (POST `/api/orders/` requires `IsAuthenticated` + `orders.create`, and the service requires a user cart). Through the **legacy server-rendered flow**, **yes**: `shop/views.py:111-145` `checkout()` has no auth at all and, for a guest, creates an `Order` with `user` left NULL. That path still bypasses `OrderService` entirely — no inventory reservation, no audit, no price re-validation (see Known Issues #1b).

**Legacy order ownership (fixed 2026-09-17).** `checkout()` now records ownership two ways: it sets `Order.user` when the buyer is authenticated, and it writes the new order's id into the session under `placed_order_ids` (`shop/views.py:_remember_placed_order`). `order_success()` authorizes every read through `_can_view_order()` — session that placed the order, owning user, or the staff override — and raises a safe `Http404` otherwise. The session is the ownership token for guests, so guest checkout keeps working with no login and no client-supplied identifier is ever trusted. The staff override is shared with the JSON API through `shop/permissions.py:can_user_view_any_order`.

### Inventory
`ProductInventory` (available / reserved / sold, each with a `>= 0` CheckConstraint) plus an `InventoryTransaction` ledger. `InventoryService` reserve → release → finalize-sale all run inside the caller's atomic block with `select_for_update()`, and release/finalize are idempotent (guarded by an existing RELEASE/SALE row). Endpoints under `/api/seller/inventory/...` (aliased at `/api/inventory/...`) gated on `inventory.view` / `inventory.adjust` plus per-object ownership.

`Product.stock` and `ProductInventory.available_quantity` are **two stores kept in sync by convention**, and one path breaks it — see Known Issues #2.

### Payments & Refunds
`Payment` statuses `PENDING/PROCESSING/PAID/FAILED/CANCELLED/REFUNDED/PARTIALLY_REFUNDED`; methods `CASH_ON_DELIVERY/BKASH/NAGAD/ROCKET/CARD/ONLINE`. `Refund` is PROTECT-linked to payment and order. Amounts always come from `order.total_amount` server-side; the client may only pick a method.

Flow: `GET/POST /api/orders/<...>/payment/` (authenticated + ownership, no extra RBAC code) → `POST /api/staff/payments/<pk>/verify/` (`payments.verify`/`payments.process`) → `POST /api/staff/payments/<pk>/refund/` (`payments.refund`/`orders.refund`). All mutations funnel through `PaymentService` with `transaction.atomic()` + `select_for_update()`; there is no generic PUT/PATCH on Payment or Refund, and Django admin registers both read-only. **Refunds do not restore inventory** — stock only returns when an *order* transitions to CANCELLED.

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

**Frontend routes:** `/admin`, `/admin/login`, `/admin/profile`, and list/detail(/new) families for `shops`, `sellers`, `users`, `roles`, `products` (no `new`), `categories`, `customers`, plus a catch-all `/admin/[...slug]` that renders an "Awaiting Implementation" placeholder for nav entries with no page yet (`/admin/orders`, `/admin/payments`, `/admin/audit-logs`).

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
- Point integrity: `transaction.atomic()` + `select_for_update()` + model validator + **DB CheckConstraint `balance >= 0`**, with an append-only ledger recording before/after balances and the actor.
- Order/inventory/payment mutations are atomic with row locks; inventory release and sale-finalization are idempotent.
- Anti-escalation on role editing; protected roles cannot be abused; role deletion guarded.
- Admin serializers never expose password, hash or token fields; audit metadata redacts sensitive keys.
- Audit logging on product mutations, all admin governance mutations, point adjustments, reviews and orders.

**Known security limitations** (see Known Issues for detail)

- ~~The legacy server-rendered order-success view has **no ownership check** (#1)~~ — **fixed 2026-09-17**; reads are now authorized by session, owner or staff override.
- API-driven seller lifecycle transitions are not audited (#6).
- Dev-posture settings: `DEBUG = True`, a hardcoded `SECRET_KEY` committed in `settings.py`, and a 4-character minimum password. Must change before any production deployment.
- Access tokens cannot be revoked (no blacklist); "logout" is client-side only.
- JWTs are stored in `localStorage`, so they are reachable by XSS.

---

## 15. Test Status — as of 2026-09-17

**Inventory:** ~471 test methods across 23 files (462 at the full review, +9 from the legacy-IDOR fix).

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

Discovered during the 2026-09-17 review. All were open at that point; **#1 has since been fixed** — see the Status column.

| # | Issue | Area | Severity | Status |
|---|---|---|---|---|
| 1 | **Legacy checkout IDOR.** `order_success(request, order_id)` did `get_object_or_404(Order, id=order_id)` with **no ownership or session check** — any visitor could read any order (customer name, phone, address) by walking sequential ids. | Legacy server-rendered flow | **High** | **FIXED 2026-09-17.** `checkout()` now records ownership server-side (`Order.user` for authenticated buyers, `request.session["placed_order_ids"]` for everyone including guests) and `order_success()` authorizes through `_can_view_order()` — session / owner / staff override — returning a safe 404 otherwise. Covered by `shop.tests.LegacyOrderAccessTests` (9 tests). |
| 1b | The same legacy `checkout()` (`shop/views.py:111-145`) still creates orders **bypassing `OrderService`**: no inventory reservation, no audit entry, no server-side price re-validation. Split out of #1 when the IDOR was fixed; this half is untouched. | Legacy server-rendered flow | Medium | Open. Not a data-exposure issue; it is a correctness/consistency gap between the legacy template flow and the API order pipeline. |
| 2 | `ProductService.update_product` lists `"stock"` in `updatable_fields` (`shop/services.py:220-235`) and writes `Product.stock` directly **without touching `ProductInventory`**, so `PATCH /api/products/mine/<pk>/` silently desyncs `Product.stock` from `ProductInventory.available_quantity`. `Product.in_stock` reads inventory while the cart serializer reads `product.stock`. | Seller products / inventory | **Medium** | Pre-existing; newly documented. |
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

---

## 17. Known Limitations

Intentionally deferred or simply not built. These are **not** bugs.

- **No logout / token revocation** endpoint; no password reset flow.
- **No guest-cart merge** on login; a guest's localStorage cart is abandoned rather than merged.
- **No guest order-lookup API** — guest orders (`user=NULL`) created by the legacy path are unreachable from `/api/orders/`.
- **Reviews are minimal by design**: no images, seller replies, helpful votes, moderation workflow, flagging, or rating histogram.
- **No seller-side product submission/publishing** — publication is staff-only.
- **No seller-facing dedicated inventory page** in the seller panel (the API exists).
- **Admin console modules not built**: `/admin/orders`, `/admin/payments`, `/admin/audit-logs` appear in navigation but render the "Awaiting Implementation" placeholder (audit-log and payment/order APIs do exist backend-side).
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

**Last completed change:** Legacy checkout IDOR fix — a targeted security hardening of the server-rendered `/order-success/<id>/` page, not a feature.
**Last completed feature:** Product Reviews & Ratings (`c4fb3b8`).
**Preceding feature:** Admin-assigned shop ownership with single-shop cap + seller product management (`b623553`).

**Working tree:** clean as of the legacy-IDOR commit. (The earlier note here described two uncommitted seller-product files; they landed in `c8485f8`.)

**What is implemented:** the full commerce chain (catalog → cart → checkout → orders → inventory → payments/refunds), the seller panel, the management console, RBAC governance, points/wallet, and reviews.

**Next planned phase:** not recorded in the repo beyond the task/phase specs. Phase 1I's spec explicitly defers review moderation, helpful votes, review images and seller responses to a later phase.

**Constraints future work must preserve:** everything in [Architecture Decisions](#18-important-architecture-decisions), plus the regression-sensitive areas — customer auth, storefront catalog, cart, orders, payments, inventory, seller orders/wallet, admin governance, RBAC, and the public `average_rating` / `review_count` fields.

**Immediate follow-ups:** the legacy template checkout still bypasses `OrderService` (#1b) — decide whether to route it through the service or retire the template flow; `Product.stock` / `ProductInventory` desync on seller product update (#2); decide intent on seller self-registration (#5); the one failing test (#14) is a trivial assertion fix. The legacy order-success IDOR (#1) is done.

---

## 21. Review History

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

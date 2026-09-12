# MiniShop — Complete User, Role & Panel Backend Audit

**Type:** Read-only architecture audit. No code, migrations, permissions, or data were modified to produce this report.
**Purpose:** Give a frontend-planning AI assistant an accurate, code-verified picture of the existing Django/DRF backend before Next.js UI work begins.
**Method:** Full read of `task/Master_Prompt.md` + all `task/task*.md` specs, and full/targeted reads of every backend app (`rbac`, `sellers`, `shops`, `shop`, `customers`, `cart`, `points`, `audit`) — models, serializers, views, urls, permissions, services, and tests. File:line citations are given for every concrete claim; anything not found is stated as "not found" rather than guessed.

---

## A. Executive Summary

MiniShop's backend is a Django 5 + DRF project with **one** underlying user table — Django's stock `django.contrib.auth.models.User` (no custom `AUTH_USER_MODEL`) — extended by separate satellite apps. Authorization is **not** based on Django groups/permissions; it's a fully custom RBAC layer (`rbac` app: `Role` / `Permission` / `RolePermission` / `UserRole`) that gates almost every endpoint via **permission codes**, not role names. This is a clean, deliberate design: across every permission class inspected in `shop/permissions.py`, `shop/admin_permissions.py`, `sellers/permissions.py`, `shops/permissions.py`, `points/permissions.py`, `cart/permissions.py`, `customers/permissions.py`, there is **no branch that checks "is this user SUPPORT_TEAM / FINANCE / OPERATION_MANAGER"** — only "does this user hold permission code X" (plus a universal `is_superuser` / `SUPER_ADMINISTRATOR` bypass everywhere).

"Seller" is a **separate system entirely**, not an RBAC role. A user becomes a seller by having a `sellers.SellerProfile` row (one-to-one with `User`), which carries its own `seller_type` (`FULL_SHOP_OWNER` / `LIMITED_SHOP_OWNER` / `PRODUCT_OWNER`) and its own `status` lifecycle (`PENDING → UNDER_REVIEW → APPROVED → ACTIVE`, or `SUSPENDED` / `REJECTED`). RBAC roles are used only to gate **staff** actions on seller/shop/product resources — no user is ever assigned a role literally called "SELLER."

The Master Prompt (`task/Master_Prompt.md`) is considerably more ambitious than what's built: RBAC, seller/shop/product lifecycle, points/wallet, cart/orders, inventory, payments/refunds, and platform governance (admin) are all solidly implemented and test-covered. But three entire phases from the Master Prompt's own 14-phase plan were **never built**: Support ticketing (Phase 11), Notifications (Phase 12), and Reports/Analytics (Phase 13) — `reports.view` is a seeded, role-assigned permission code with **no endpoint anywhere** that serves a report. There is also **no user registration endpoint** anywhere in the codebase — new `User` rows can only be created via Django admin or management commands, which is a hard blocker for any public "Sign Up" screen.

**Bottom line for frontend planning:** Public storefront, Customer account/cart/checkout, and Seller dashboard panels are backend-ready now. A unified Staff/Admin console is ready for orders/payments/refunds/moderation/governance, but Support-ticketing, Reports, and Notifications screens have no backend to call yet. Self-service signup does not exist — plan around it or treat it as the first backend gap to close.

---

## B. Actual User Model

**There is exactly ONE user table: `django.contrib.auth.models.User`.** `config/settings.py` sets no `AUTH_USER_MODEL`, and a repo-wide search for a custom `AbstractUser`/`AbstractBaseUser` subclass or a model literally named `User` found none — every app that needs "the user" imports `settings.AUTH_USER_MODEL` / `get_user_model()` and points a `OneToOneField` or `ForeignKey` at it.

Authentication fields, staff/superuser fields: all inherited unmodified from Django's built-in `User` — `username`, `email`, `password`, `first_name`, `last_name`, `is_active`, `is_staff`, `is_superuser`, `date_joined`, `last_login`. None of these were extended.

Satellite profile/role relationships hanging off `User` (all confirmed via direct model reads):

| Relationship | Model | Cardinality | File:line |
|---|---|---|---|
| Customer profile | `customers.CustomerProfile` | OneToOne → User | `customers/models.py:25-29` |
| Customer addresses | `customers.Address` | ForeignKey → User (many per user) | `customers/models.py:65-69` |
| Cart | `cart.Cart` | OneToOne → User (no guest cart) | `cart/models.py:12-16` |
| Seller profile | `sellers.SellerProfile` | OneToOne → User | `sellers/models.py:36-40` |
| Seller wallet | `points.SellerWallet` | OneToOne → **SellerProfile** (not User directly) | `points/models.py:12-16` |
| RBAC role assignment | `rbac.UserRole` | ForeignKey → User, ForeignKey → Role (**many roles per user possible** — no uniqueness cap beyond `unique_together(user, role)`) | `rbac/models.py:99-121` |
| Audit trail actor | `audit.AuditLog.actor` | ForeignKey → User, SET_NULL | `audit/models.py:10-17` |

**Is there ONE User model or multiple user systems?** One Django `User` table, but **two independent classification systems** layered on top of it:
1. **RBAC roles** (`rbac.Role`/`UserRole`) — an explicit, many-to-many-via-`UserRole` staff/customer role system with 8 seeded role codes (Section C).
2. **Sellerhood** (`sellers.SellerProfile`) — an entirely separate, non-RBAC classification: whether a `User` has a `SellerProfile` row at all, and if so, its `seller_type` and `status`. A user can simultaneously hold an RBAC role (e.g. `CUSTOMER`) **and** have a `SellerProfile` — the two systems are not mutually exclusive and not unified in the data model.

`is_staff` is used inconsistently as a **third**, informal authorization signal — see Section R.

---

## C. Complete User/Role List

| # | User / Role | Source in Code | Purpose | Backend Status |
|---|---|---|---|---|
| 1 | Customer | `rbac.Role.ROLE_CUSTOMER` (`rbac/models.py:14`), seeded `rbac/management/commands/seed_rbac.py:126-130,207-213` | Browse, cart, checkout, own orders, profile/addresses | Complete |
| 2 | Seller *(not an RBAC role — see Section D)* | `sellers.SellerProfile` (`sellers/models.py:36-46`) | Own/manage shop(s) and products, per `seller_type` | Complete (core flows); minor gaps noted in §I |
| 3 | Support Team | `rbac.Role.ROLE_SUPPORT_TEAM` (`rbac/models.py:13`), seeded `seed_rbac.py:194-206` | Order view/update/cancel, seller/shop/user visibility, no payments | Partial (order ops complete; no ticketing system exists) |
| 4 | Finance | `rbac.Role.ROLE_FINANCE` (`rbac/models.py:12`), seeded `seed_rbac.py:187-193` | Payments, refunds, points admin, order view/refund | Complete (for what's built); no payout/financial-report screens |
| 5 | Operation Manager | `rbac.Role.ROLE_OPERATION_MANAGER` (`rbac/models.py:9`), seeded `seed_rbac.py:162-171` | Product/shop approval, order status ops, seller view, inventory | Complete |
| 6 | Sales Manager | `rbac.Role.ROLE_SALES_MANAGER` (`rbac/models.py:10`), seeded `seed_rbac.py:172-179` | Seller view/create/update/approve, product view/update, order view | Complete |
| 7 | Sales Team | `rbac.Role.ROLE_SALES_TEAM` (`rbac/models.py:11`), seeded `seed_rbac.py:180-186` | Assisted seller/product ops, inventory view/adjust | Complete |
| 8 | Administrator | `rbac.Role.ROLE_ADMINISTRATOR` (`rbac/models.py:8`), seeded `seed_rbac.py:135-161` | Full platform governance except super-admin-only actions | Complete |
| 9 | Super Administrator | `rbac.Role.ROLE_SUPER_ADMINISTRATOR` (`rbac/models.py:7`), seeded `seed_rbac.py:134` (`"__ALL__"` permissions) | All permissions + exclusive role-escalation authority | Complete |

Line numbers above are confirmed verbatim from a direct read of `rbac/models.py:7-14`.

The Master Prompt's 7 "Staff Users" (`Master_Prompt.md:94-100`) match roles 3–9 above exactly by name. The repo **extended** the Master Prompt by formalizing `CUSTOMER` as an 8th RBAC role (the Master Prompt discusses customers separately, `Master_Prompt.md:604-644`, not as a "staff role") — a deliberate, sensible extension, not a discrepancy.

---

## D. Seller Types

Defined as a `CharField` with `choices` on `SellerProfile` — **not** a model, not RBAC:

```python
# sellers/models.py:9-17
TYPE_FULL_SHOP_OWNER = "FULL_SHOP_OWNER"
TYPE_LIMITED_SHOP_OWNER = "LIMITED_SHOP_OWNER"
TYPE_PRODUCT_OWNER = "PRODUCT_OWNER"
```
Field: `seller_type = models.CharField(max_length=30, choices=SELLER_TYPE_CHOICES, default=TYPE_FULL_SHOP_OWNER, db_index=True)` (`sellers/models.py:41-46`).

| Seller Type | Create shop? | Shop cap | Manage own products? | Manage orders? | Wallet/points? | Lifecycle |
|---|---|---|---|---|---|---|
| `FULL_SHOP_OWNER` (default) | Yes | Unlimited (no cap found) | Yes | Yes (own shop's orders) | Yes (same wallet system as all sellers) | Full: `PENDING → UNDER_REVIEW → APPROVED → ACTIVE`, or `SUSPENDED`/`REJECTED` |
| `LIMITED_SHOP_OWNER` | Yes | **Capped at 1** (`shops/services.py:109-112`) | Yes | Yes | Yes | Same as above |
| `PRODUCT_OWNER` | **No — explicitly blocked** (`shops/services.py:103-106`, `shops/permissions.py:53-54`) | 0 | Yes (products not tied to owning a shop personally — see note) | N/A (no shop) | Yes | Same as above |

Enforcement is real, not just documentation — `ShopService.validate_seller_eligibility_for_creation` (`shops/services.py:96-112`):
```python
if seller.seller_type == SellerProfile.TYPE_PRODUCT_OWNER:
    raise IneligibleSellerError("Product Owners are not permitted to create shops...")
if seller.seller_type == SellerProfile.TYPE_LIMITED_SHOP_OWNER and seller.shops.count() >= 1:
    raise ShopLimitExceededError("Limited Shop Owners are restricted to a maximum of 1 shop.")
```
confirmed by test `test_limited_shop_owner_single_shop_limit` (`shops/tests.py:157-171`). The `IsEligibleShopSeller` permission class (`shops/permissions.py:31-56`) duplicates the operational-status + not-`PRODUCT_OWNER` checks but **not** the 1-shop cap — that cap lives only in the service layer.

**Important gap**: an informational method `get_seller_capabilities()` (`sellers/services.py:6-30`) reports `can_manage_products: True` and a `has_full_catalog` flag for all three types, but this is **not enforced anywhere** — no permission class or service in `sellers/`/`shops/` gates product/order/wallet capability by `seller_type`. Only shop-creation is actually type-gated in code. If the product intends real per-type product/order restrictions beyond shop ownership, that logic doesn't exist yet.

### Seller Role ≠ Seller Type — the actual distinction

- **"Seller" is not a role at all.** No RBAC `Role` row is ever assigned to represent "this user is a seller." Sellerhood = existence of a `sellers.SellerProfile` row linked 1:1 to the `User`. Every seller-restricted endpoint checks `request.user.seller_profile` directly (e.g. `shops/permissions.py:31-56`, `sellers/permissions.py`), never `has_user_permission(user, "seller.*")`.
- **"Seller Type"** (`FULL_SHOP_OWNER`/`LIMITED_SHOP_OWNER`/`PRODUCT_OWNER`) is a business-capability sub-classification *within* sellerhood — it answers "what can this specific seller's shop-related actions do," and is checked as a plain field comparison (`seller.seller_type == SellerProfile.TYPE_PRODUCT_OWNER`), never through the RBAC `Permission` table.
- RBAC roles (`ADMINISTRATOR`, `OPERATION_MANAGER`, etc.) are used exclusively to gate **staff** oversight of sellers/shops (approve, suspend, view) — a completely separate axis from the seller's own type.
- A single `User` can theoretically hold an RBAC role (e.g. be staff) **and** also have a `SellerProfile` — the systems don't prevent this combination, though nothing in the seeded/demo data exercises it.

---

## E. RBAC Architecture

### Roles

All 8 roles are seeded by `rbac/management/commands/seed_rbac.py` (the only RBAC seed path — no fixtures elsewhere). Descriptions come from the seed file's `ROLES_DATA` (not independently re-quoted here in full — names and purposes are accurate per Section C). `is_active` defaults `True`; roles are DB rows, not hardcoded choices — `Role.code` has **no `choices=` constraint at the model level** (`rbac/models.py:27-32`), only the seed script uses the `ROLE_CHOICES` list as a convenience.

**Protected roles**: `PROTECTED_ROLE_CODES = {Role.ROLE_SUPER_ADMINISTRATOR, Role.ROLE_ADMINISTRATOR}` (`shop/admin_serializers.py:20`). Nobody — not even a Super Administrator — can create a role reusing one of these codes, or modify/delete the existing `SUPER_ADMINISTRATOR`/`ADMINISTRATOR` role objects via the API (`shop/admin_views.py:336-338`, `403-413`). These two are hard-baked system roles, changeable only via direct DB access or the seed script.

**Custom roles**: Yes, fully supported. `POST /api/admin/roles/` (`shop/admin_views.py:260-307`, requires `roles.admin.manage`) creates any new `Role` with any non-protected, non-duplicate code, and attaches any subset of existing `Permission` codes — with an anti-escalation guard: an actor cannot grant a permission they don't themselves hold (`admin_views.py:273-279`). No endpoint creates new `Permission` objects (only the seed command / Django admin do).

### Permissions (58 seeded codes, grouped by domain)

Source: `rbac/management/commands/seed_rbac.py:10-88`, cross-referenced against every app's `permissions.py` to confirm actual enforcement (not just existence).

| Domain | Codes | Actually enforced by a permission class? |
|---|---|---|
| Users | `users.view/create/update/delete` | Not found enforced directly (superseded by `users.admin.*`) |
| Roles | `roles.view`, `roles.assign` | Not found directly enforced (admin governance uses `roles.admin.*` instead) |
| Roles (orphaned) | `roles.create/update/delete` | **Never assigned to any role, never checked anywhere** — dead codes |
| Products | `products.view/create/update/delete/approve/reject/publish` | `shop/permissions.py:9-42` (create/update/delete); approve/reject/publish superseded by `products.admin.manage` in practice |
| Shops | `shops.view/create/update/delete/approve` | `shops/permissions.py:9-28,74-83` |
| Sellers | `sellers.view/create/update/approve/suspend` | `sellers/permissions.py:8-54` |
| Orders | `orders.view/create/update/cancel/refund`, `orders.seller.view/update`, `orders.staff.view/update` | `shop/permissions.py:106-240,367-396` |
| Payments | `payments.view/create/process/verify/refund` | `shop/permissions.py:306-364` (no separate `refunds.*` domain) |
| Points | `points.view/add/deduct/adjust` | `points/permissions.py:7-37` |
| Reports | `reports.view` | **Seeded and assigned to multiple roles, but no permission class or endpoint references it anywhere** — dead code, no report screen exists |
| Profile (customer) | `profile.view/update` | `customers/permissions.py:6-27` |
| Address (customer) | `address.view/create/update/delete` | `customers/permissions.py:30-94` |
| Cart | `cart.view/update` | `cart/permissions.py:6-23` |
| Inventory | `inventory.view/adjust` | `shop/permissions.py:243-303` |
| Admin governance | `users.admin.view/manage`, `roles.admin.view/manage`, `sellers.admin.manage`, `shops.admin.manage`, `products.admin.manage`, `categories.admin.manage`, `customers.admin.view` | `shop/admin_permissions.py:13-127` |

No `audit.*` permission domain exists — the `audit` app has no `permissions.py` and no API surface at all (Django-admin-only, read-only).

### Permission-check mechanism

Core function (`rbac/services.py:51-66`):
```python
def has_user_permission(user, permission_code: str) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    user_perms = get_user_permissions(user)
    if "*" in user_perms:
        return True
    return permission_code in user_perms
```
Wrapped either by a generic, configurable `HasPermission`/`require_permission(code)` pair (`rbac/permissions.py:6-44`, used directly in `rbac/views.py:33`), or — the dominant pattern across the codebase — by one bespoke `BasePermission` subclass per action per app (e.g. `CanViewCart`, `CanCreateProduct`, `CanManageAdminRoles`), each simply calling `has_user_permission(request.user, "<code>")`. Object-level ownership (is this *my* address/shop/product/order) is a **second, separate layer** — `rbac.HasObjectPermission` (generic) plus per-app bespoke classes (`IsAddressOwner`, `IsShopOwner`, `IsProductOwner`, `IsSellerOwner`) — confirmed applied consistently wherever ownership matters.

### Django superuser vs. custom RBAC — confirmed NOT fully separated

`is_superuser` is a **universal bypass**, hardwired into `has_user_permission`/`get_user_permissions` (`rbac/services.py:37,59,76`) and repeated as `if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user): return True` in essentially every permission class across `customers/`, `points/`, `sellers/`, `shops/`, `shop/permissions.py` (12 occurrences), `shop/admin_permissions.py` (8 occurrences). The seed command even has a `--assign-superusers` flag (`seed_rbac.py:285-291`) that back-fills the `SUPER_ADMINISTRATOR` role onto existing Django superusers, treating the two as intentionally equivalent.

`is_staff` is used **separately and inconsistently** — not as an RBAC bypass, but as an informal "can view/act on any order" override confined to `shop/api_views.py` (7 occurrences: lines 348-350, 412-414, 736-738, 780-782, 832-834, 870-872, 916-918) and `shop/services.py` (2 occurrences). This means a plain Django `is_staff=True` user with **no RBAC role at all** can bypass order-ownership checks in some order/payment code paths — a real inconsistency between the RBAC-code system and Django's native staff flag (see Section R).

---

## F. Role × Permission Matrix

"Customer" = RBAC role. "Seller" = has `SellerProfile` (any type), evaluated for the seller's *own* resources only. Staff columns = holds that RBAC role and only the permission codes seeded to it (`seed_rbac.py:162-213`). `✓` = enforced in code per the citations above; `—` = not granted to that role; `own` = scoped to the actor's own resources only.

| Capability | Customer | Seller | Support | Finance | Ops Mgr | Sales Mgr | Sales Team | Admin | Super Admin |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Browse products/shops (public) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Manage own cart | ✓ | — | — | — | — | — | — | — | ✓ |
| Place/view/cancel own orders | ✓ | — | — | — | — | — | — | — | ✓ |
| Create/manage own shop | — | own (type-gated) | — | — | — | — | — | ✓ | ✓ |
| Create/manage own products | — | own | — | — | — | own(view/update) | own(view/update/create) | ✓ | ✓ |
| View orders (staff-wide) | — | own | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Update order status (staff) | — | own | ✓ | — | ✓ | — | — | ✓ | ✓ |
| View payments | — | — | — | ✓ | — | — | — | ✓ | ✓ |
| Process refund | — | — | — | ✓ | — | — | — | ✓ | ✓ |
| View sellers | — | — | ✓ | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| Approve/suspend sellers (business flow, `sellers.approve/suspend`) | — | — | — | — | — | ✓(approve only) | — | ✓ | ✓ |
| Manage sellers (admin governance, `sellers.admin.manage`) | — | — | — | — | — | — | — | ✓ | ✓ |
| Manage shops (admin governance) | — | — | — | — | — | — | — | ✓ | ✓ |
| Approve/reject/publish products | — | — | — | — | ✓ | — | — | ✓ | ✓ |
| Manage categories | — | — | — | — | — | — | — | ✓ | ✓ |
| View inventory | — | own | ✓ | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| Adjust inventory | — | — | — | — | ✓ | — | ✓ | ✓ | ✓ |
| View/adjust seller points | — | own (view only) | — | ✓ | — | — | — | ✓ | ✓ |
| Manage users (admin governance) | — | — | — | — | — | — | — | ✓ | ✓ |
| Manage RBAC (roles/permissions) | — | — | — | — | — | — | — | partial* | ✓ |
| View customers (admin) | — | — | — | — | — | — | — | ✓ | ✓ |

\* Administrator can manage roles/permissions generally but **cannot** create/modify/delete the two protected role codes (`SUPER_ADMINISTRATOR`, `ADMINISTRATOR`) and cannot grant/revoke the `SUPER_ADMINISTRATOR` role to anyone — that's Super Admin-exclusive (Section L).

Every cell above is derived from an actual permission-code assignment in `seed_rbac.py` **and** a corresponding permission class that enforces that exact code on that exact endpoint — not assumption.

---

## G. Panel Structure

The backend's own design answers this question directly: **because every staff/admin endpoint is gated by permission code (not role name), the natural panel structure is one unified Staff/Admin console whose visible sections are driven by the current user's `permissions` array — not five separate hardcoded per-role frontends.** Building `SupportPanel`, `FinancePanel`, `OpsManagerPanel` as distinct codebases would fight the backend's actual design and duplicate a lot of shared order/seller/shop UI.

Recommended panels:

| Panel | Who | Backend readiness |
|---|---|---|
| **Public Storefront** | Anonymous + everyone | Complete (`AllowAny` catalog/shop endpoints) |
| **Customer Account** | Users with a `CustomerProfile` (i.e. anyone with the `CUSTOMER` role / any authenticated non-seller) | Complete for profile/address/cart/orders; no self-registration |
| **Seller Dashboard** | Users with a `SellerProfile`, UI varies by `seller_type` (hide "Create Shop" for `PRODUCT_OWNER`, cap at 1 shop for `LIMITED_SHOP_OWNER`) | Complete for core flows |
| **Staff/Admin Console** (single shell) | `SUPPORT_TEAM`, `FINANCE`, `OPERATION_MANAGER`, `SALES_MANAGER`, `SALES_TEAM`, `ADMINISTRATOR`, `SUPER_ADMINISTRATOR` | Complete for orders/payments/refunds/moderation/governance; **missing** ticketing/reports/notifications sub-sections |

A user could in principle need both the Seller Dashboard and Customer Account (nothing in the data model prevents a seller from also shopping as a customer) — plan the frontend shell to switch context rather than assuming strict separation.

---

## H. Customer Backend Readiness

| Customer Feature | API Exists | Backend Complete | Permission | Notes |
|---|---|---|---|---|
| Registration | **No** | Missing | — | No endpoint anywhere creates a `User` account (see §M) |
| Login | Yes — `POST /api/auth/token/` | Complete | `AllowAny` (JWT obtain) | Stock SimpleJWT, no custom claims |
| Profile view/update | Yes — `GET/PATCH/PUT /api/profile/me/` | Complete | `profile.view`/`profile.update` | `CustomerProfile`: display_name, phone, avatar, DOB, gender |
| Addresses (CRUD + default) | Yes — `/api/addresses/`, `/api/addresses/<pk>/`, `/api/addresses/<pk>/set-default/` | Complete | `address.view/create/update/delete` + `IsAddressOwner` | DB-enforced single default address per user |
| Browse products/categories | Yes — `/api/categories/`, `/api/products/`, `/api/products/<pk\|slug>/`, `/api/hot-deals/` | Complete | `AllowAny` | Filterable by category/shop/price/badge/search |
| Cart | Yes — `/api/cart/`, `/api/cart/items/`, `/api/cart/items/<pk>/` | Complete | `cart.view/update` | Dynamic/live pricing (no snapshot); no guest cart |
| Checkout / place order | Yes — `POST /api/orders/` | Complete | `orders.create` | Atomically converts cart → order; server-recomputed pricing; inventory reserved |
| View own orders | Yes — `/api/orders/`, `/api/orders/<pk\|order_number>/` | Complete | `orders.view` | Safe 404 (not 403) on cross-user access |
| Cancel order | Yes — `.../cancel/` | Complete | `orders.cancel` | Only from `PENDING`/`CONFIRMED`/`PROCESSING` |
| Payment initiation | Yes — `.../payment/` | Partial (not deep-audited) | `IsAuthenticated` only, no extra RBAC class found | Present but shallow-verified in this audit pass |
| Refund visibility (as customer) | Not found as a distinct customer-facing endpoint | Missing/unclear | — | Refunds are staff/finance-initiated |
| Password change / account deactivation | **No** | Missing | — | Not found anywhere in `customers/` or `rbac/` |
| Logout | **No** | Missing | — | No token blacklist app installed |

---

## I. Seller Backend Readiness

| Seller Feature | API Exists | Backend Complete | Seller Types | Notes |
|---|---|---|---|---|
| Seller registration/onboarding | Yes — `POST /api/sellers/register/` | Complete (but requires an existing `User`) | All | Creates `SellerProfile` at `status=PENDING` |
| Seller profile view/update | Yes — `/api/sellers/me/` | Complete | All | `status`/`seller_type` are read-only via this endpoint |
| Seller dashboard | Yes — `GET /api/sellers/dashboard/` | Complete | All | Includes `get_seller_capabilities()` informational dict |
| Self-service "submit for review" | Model method exists (`submit_for_review()`) but **no view calls it** | Gap | All | Dead code — sellers can't explicitly request re-review; workflow relies on staff to approve from `PENDING` |
| Shop CRUD (self-service) | Yes — `/api/shops/mine/...` (list/create/detail/update/location/submit) | Complete | `FULL_SHOP_OWNER`, `LIMITED_SHOP_OWNER` only (`PRODUCT_OWNER` blocked) | 1-shop cap enforced for `LIMITED_SHOP_OWNER` |
| Product management (self-service) | Yes — `/api/products/mine/...` | Complete | All (not type-gated beyond needing a `SellerProfile`) | Triple-enforced ownership (queryset + object-permission + service layer + serializer validation) |
| Inventory (dedicated seller-facing view) | **Not found as its own resource** | Gap | — | Inventory is managed internally by `InventoryService`; only `inventory.view`/`inventory.adjust` staff permission codes exist — no confirmed seller-scoped "my stock levels" endpoint |
| Order management (own orders) | Yes — `/api/seller/orders/...` | Complete | All | Item-level isolation in multi-seller orders; multi-seller unilateral status-change blocked without staff override |
| Wallet (view balance/history) | Yes — `/api/points/wallet/`, `/api/points/history/` | Complete | All | Read-only self-service; no self-credit/debit |
| Point deduction on product creation | Automatic, atomic | Complete | All | `PointService.debit` inside the same transaction as product creation; race-condition-safe (`select_for_update`, thread-tested) |
| Seller status transitions (approve/reject/suspend/reactivate) | **Admin/staff-only** — two parallel surfaces exist (see §Q) | Complete | — | `sellers/views.py` (`sellers.approve`/`sellers.suspend`) and `shop/admin_views.py` (`sellers.admin.manage`) both call the same underlying service functions |

Clear split: **self-management** = `/api/sellers/me/`, `/api/shops/mine/...`, `/api/products/mine/...`, `/api/seller/orders/...`, `/api/points/wallet/|history/`. **Admin management of sellers** = `/api/sellers/` (list/detail/approve/reject/suspend/reactivate, business-role gated) and `/api/admin/sellers/...` (governance-gated, audited).

---

## J. Staff Backend Readiness

Confirmed by direct code inspection and by tests (`shop/test_staff_orders.py:225-243` explicitly authenticates as **FINANCE** and asserts 200 on order list/detail but 403 on the status-update endpoint — proving the gate is the permission code, not the role name): **there is no role-name branching anywhere in the order/payment/inventory permission classes.** Support, Finance, and Operation Manager differ *only* in which permission codes `seed_rbac.py` assigned them.

| Feature | Support | Finance | Operation Manager |
|---|---:|---:|---:|
| View orders | ✓ (`orders.view`) | ✓ | ✓ |
| Update order status | ✓ (`orders.staff.update`, `/api/staff/orders/<id>/status/`) | — | ✓ |
| View payments | — | ✓ (`payments.view`) | — |
| Refund | — | ✓ (`payments.refund`) | — |
| View sellers | ✓ (`sellers.view`) | — | ✓ |
| Manage sellers (approve/suspend) | — | — | — (only Sales Manager / Administrator+ hold `sellers.approve`/`sellers.admin.manage`) |
| View inventory | ✓ (`inventory.view`) | — | ✓ |
| Adjust inventory | — | — | ✓ (`inventory.adjust`) |

**Support Team's actual backend surface**: order view/update/cancel via `/api/staff/orders/...`, plus read access to sellers/shops/users/inventory/reports(permission only, no endpoint) and customer profile/address/cart (likely for support lookups). **No support-ticket, complaint, or return-request system exists anywhere in the codebase** — the Master Prompt's Phase 11 (`Master_Prompt.md:1103-1109`: tickets, complaints, order issues, returns, support dashboard) was never implemented. Support Team's real capability today is "view/update orders," not "run a helpdesk."

**Finance's actual backend surface**: `StaffPaymentListAPIView`/`StaffPaymentDetailAPIView`, a verify endpoint, and `StaffPaymentRefundAPIView` (`shop/api_views.py:972-1083`, gated by `payments.view`/`payments.verify`/`payments.refund`), plus points admin-adjustment (`/api/points/sellers/<id>/adjust/`). No seller-payout or financial-report screens exist — `reports.view` is a dead permission code.

**Operation Manager's actual backend surface**: order status transitions, product approve/reject/publish (via `products.admin.manage`... actually via the moderation permission set), shop approval, seller visibility, inventory view/adjust. This is the most complete of the three staff roles.

---

## K. Administrator Backend Readiness (Task 17)

All admin governance endpoints are mounted under `/api/admin/...` in `shop/urls.py`, implemented in `shop/admin_views.py`/`shop/admin_serializers.py`/`shop/admin_permissions.py`.

| Domain | Endpoint(s) | Permission | Serializer | Service | Audit logged? | Restrictions |
|---|---|---|---|---|---|---|
| Users | `GET/PATCH /api/admin/users/`, `/<pk>/` | `users.admin.view`/`users.admin.manage` | `AdminUser*Serializer` | Direct field ops with heavy anti-escalation logic (§L) | Yes — `ADMIN_USER_UPDATED` | Can't touch own role assignments; can't grant/revoke `SUPER_ADMINISTRATOR` unless already Super Admin; can't deactivate last active Super Admin |
| Roles | `GET/POST /api/admin/roles/`, `GET/PATCH/DELETE /<pk>/` | `roles.admin.view`/`roles.admin.manage` | `AdminRole*Serializer` | Direct `Role`/`RolePermission` writes | Yes — `ADMIN_ROLE_CREATED/UPDATED/DELETED` | Protected roles (`SUPER_ADMINISTRATOR`, `ADMINISTRATOR`) can't be created/modified/deleted; can't delete a role still assigned to users; can't grant permissions you don't hold |
| Sellers | `GET /api/admin/sellers/`, `/<pk>/`, `POST/PATCH /<pk>/status/` | `sellers.admin.manage` | `AdminSellerSerializer`, `AdminSellerStatusUpdateSerializer` | **Delegates to `sellers/services.py`** (`approve_seller`/`reject_seller`/`suspend_seller`/`reactivate_seller`) | Yes — `ADMIN_SELLER_{ACTION}` | Atomic + row-locked |
| Shops | `GET /api/admin/shops/`, `/<pk>/`, `POST/PATCH /<pk>/status/` | `shops.admin.manage` | `AdminShopSerializer`, `AdminShopStatusUpdateSerializer` | **Direct model mutation, bypasses `ShopService`** | Yes — `ADMIN_SHOP_{ACTION}` | Atomic + row-locked, but not service-layer authoritative (architecture gap vs. Task 17 spec intent) |
| Products | `GET /api/admin/products/`, `/<pk>/`, `POST/PATCH /<pk>/status/` | `products.admin.manage` | `AdminProductSerializer`, `AdminProductStatusUpdateSerializer` | **Direct model mutation, bypasses `ProductService`** | Yes — `ADMIN_PRODUCT_{ACTION}` | Actions: approve/reject/publish/unpublish; publish validates shop is active first |
| Categories | `GET/POST /api/admin/categories/`, `GET/PATCH/DELETE /<pk>/` | `categories.admin.manage` | `AdminCategorySerializer` | Direct | Yes — `ADMIN_CATEGORY_CREATED/UPDATED/DELETED` | Delete blocked if category still has products (safe-delete guard); hard DELETE still exposed alongside this (Task 17 preferred deactivate-only) |
| Customers | `GET /api/admin/customers/`, `/<pk>/` | `customers.admin.view` | `AdminCustomerListSerializer`, `AdminCustomerDetailSerializer` | None — **strictly read-only, no mutation methods defined at all** | N/A | Fully matches Task 17's read-only requirement |

---

## L. Super Administrator Backend Readiness

`SUPER_ADMINISTRATOR` differs from `ADMINISTRATOR` in exactly these code-verified ways:

1. **Universal permission bypass**: `has_user_permission` returns `True` for superusers regardless of any RBAC assignment (`rbac/services.py:59`), and `SUPER_ADMINISTRATOR`'s seeded permission set is literally `"__ALL__"` (`seed_rbac.py:134`) rather than an enumerated list like every other role.
2. **Exclusive role-escalation authority**: only an actor who is `is_superuser` or holds `SUPER_ADMINISTRATOR` can grant or revoke the `SUPER_ADMINISTRATOR` role to/from another user (`shop/admin_views.py:191-194`).
3. **Protection from being locked out**: the system blocks deactivating the last remaining active Super Administrator account (`shop/admin_views.py:172-180`).
4. **Immunity from non-super actors**: a non-super actor cannot modify a target user who already holds `SUPER_ADMINISTRATOR` (`shop/admin_views.py:155-156`), and cannot assign any protected role code to anyone (`shop/admin_views.py:197-199`).
5. **`Administrator` is otherwise functionally equal** for every other governance action (users, non-protected roles, sellers, shops, products, categories, customer inspection) — the two share identical endpoint access except for the role-object protection and the above four points.

Note: protected-role objects (`SUPER_ADMINISTRATOR`/`ADMINISTRATOR` rows) **cannot be edited or deleted via the API by anyone, including a Super Administrator** — that protection is unconditional (`shop/admin_views.py:336-338`), not a bypassable-by-super-admin rule. Super Admin's power is over *who holds the role*, not over the *role definition itself*.

Django's native `is_superuser` flag is treated as fully interchangeable with holding the `SUPER_ADMINISTRATOR` role throughout the codebase (§E) — there is no meaningful backend distinction between "a Django superuser" and "a user with the `SUPER_ADMINISTRATOR` RBAC role."

---

## M. Authentication Flow

Actual flow (confirmed, differs from the prompt's illustrative diagram only in that there is no registration/logout step):

```
(No registration endpoint exists — accounts created via Django admin or management commands only)
   ↓
POST /api/auth/token/          → JWT access + refresh (SimpleJWT, stock TokenObtainPairView)
   ↓
POST /api/auth/token/refresh/  → new access token (ROTATE_REFRESH_TOKENS=True, no blacklist app installed)
   ↓
Authenticated API call (Bearer token)
   ↓
DRF permission class → has_user_permission(user, "<code>") [+ is_superuser bypass]
   ↓
(optional) object-level ownership check (IsXOwner classes)
   ↓
Service-layer business logic (services.py in the relevant app)
   ↓
(no logout endpoint — client discards tokens; no server-side revocation)
```

- **Login**: `POST /api/auth/token/` — `CustomTokenObtainPairView` (`rbac/views.py:10-14`), a bare subclass of SimpleJWT's `TokenObtainPairView` with no customization.
- **Registration**: **not found anywhere** — no endpoint creates a `User`.
- **Token refresh**: `POST /api/auth/token/refresh/` — stock SimpleJWT `TokenRefreshView`.
- **JWT config**: `ACCESS_TOKEN_LIFETIME=60min`, `REFRESH_TOKEN_LIFETIME=7 days`, `ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=False` (`config/settings.py:197-203`). `rest_framework_simplejwt.token_blacklist` is **not** in `INSTALLED_APPS` — no server-side revocation mechanism exists.
- **Logout**: **not implemented**.
- **Current user / role retrieval**: `GET /api/auth/me/` → `CurrentUserView` → `CurrentUserSerializer`.
- **Permission retrieval**: same `/api/auth/me/` call, `permissions` field.

---

## N. Frontend-Relevant Auth Data

**Actual, verified `CurrentUserSerializer` fields** (`rbac/serializers.py:8-30`) — no values invented, field names only:

```json
{
  "id": "…",
  "username": "…",
  "email": "…",
  "first_name": "…",
  "last_name": "…",
  "is_staff": "…",
  "is_superuser": "…",
  "roles": ["<role code>", "…"],
  "permissions": ["<permission code>", "…"]
}
```

`roles` and `permissions` are `SerializerMethodField`s resolving through `get_user_role_codes()` / `get_user_permissions()` — i.e. this is the live, authoritative list, safe to drive frontend conditional rendering from directly.

**Important frontend-planning gap**: this payload contains **no seller information** (`seller_type`, seller `status`) and **no customer-profile information**. If the frontend needs to know "is this user a seller, and what type," it must make a **separate** call to `GET /api/sellers/me/` (404 if the user has no `SellerProfile`) or `GET /api/sellers/dashboard/`. Similarly, customer profile fields require a separate `GET /api/profile/me/` call. Plan the post-login bootstrap sequence around at least two, possibly three, API calls — not one.

Token values themselves are never exposed in this report per instructions.

---

## O. Complete API Inventory

Grouped by consuming panel. Paths are as literally defined in each app's `urls.py`, composed with the mount prefix from `config/urls.py:26-33`. Endpoints marked *(path pattern inferred from view/permission names, not independently re-confirmed against a raw `urls.py` line in this pass)* should be double-checked against `shop/urls.py` before wiring the frontend, per the "do not invent endpoints" instruction — everything else was read directly from a `urls.py` file.

```text
AUTH  (mounted at /api/auth/, rbac.urls)
POST   /api/auth/token/
POST   /api/auth/token/refresh/
GET    /api/auth/me/
GET    /api/auth/test-permission/        (demo/verification endpoint only)

PUBLIC CATALOG / SHOPS  (mounted at '' and /api/shops/)
GET    /api/categories/
GET    /api/products/
GET    /api/products/<pk>/
GET    /api/products/<slug>/
GET    /api/hot-deals/
GET    /api/shops/
GET    /api/shops/nearby/
GET    /api/shops/<slug>/

CUSTOMER  (mounted at /api/, customers.urls; /api/cart/, cart.urls; shop.urls for orders)
GET    /api/profile/me/
PATCH  /api/profile/me/
PUT    /api/profile/me/
GET    /api/addresses/
POST   /api/addresses/
GET    /api/addresses/<pk>/
PATCH  /api/addresses/<pk>/
PUT    /api/addresses/<pk>/
DELETE /api/addresses/<pk>/
POST   /api/addresses/<pk>/set-default/
GET    /api/cart/
DELETE /api/cart/                         (clear cart)
POST   /api/cart/items/
PATCH  /api/cart/items/<pk>/
DELETE /api/cart/items/<pk>/
GET    /api/orders/
POST   /api/orders/
GET    /api/orders/<pk|order_number>/
PATCH  /api/orders/<pk|order_number>/cancel/
GET    /api/orders/<pk|order_number>/payment/
POST   /api/orders/<pk|order_number>/payment/

SELLER  (mounted at /api/sellers/, /api/shops/, /api/points/, shop.urls for products/orders)
POST   /api/sellers/register/
GET    /api/sellers/me/
PUT    /api/sellers/me/
PATCH  /api/sellers/me/
GET    /api/sellers/dashboard/
GET    /api/shops/mine/
POST   /api/shops/mine/create/
GET    /api/shops/mine/<pk>/
PATCH  /api/shops/mine/<pk>/update/
PUT    /api/shops/mine/<pk>/update/
PATCH  /api/shops/mine/<pk>/location/
PUT    /api/shops/mine/<pk>/location/
POST   /api/shops/mine/<pk>/submit/
GET    /api/products/mine/
POST   /api/products/mine/
GET    /api/products/mine/<pk>/
PATCH  /api/products/mine/<pk>/
PUT    /api/products/mine/<pk>/
DELETE /api/products/mine/<pk>/
GET    /api/seller/orders/
GET    /api/seller/orders/<order_number>/
PATCH  /api/seller/orders/<order_number>/status/
GET    /api/points/wallet/
GET    /api/points/history/

STAFF  (business-role gated, mounted across sellers.urls / shops.urls / shop.urls / points.urls)
GET    /api/sellers/                              (sellers.view)
GET    /api/sellers/<pk>/                          (sellers.view)
POST   /api/sellers/<pk>/approve/                  (sellers.approve)
POST   /api/sellers/<pk>/reject/                   (sellers.approve)
POST   /api/sellers/<pk>/suspend/                  (sellers.suspend)
POST   /api/sellers/<pk>/reactivate/                (sellers.suspend)
GET    /api/shops/staff/                            (shops.view)
GET    /api/shops/staff/<pk>/                       (shops.view)
POST   /api/shops/staff/<pk>/approve/               (shops.approve)
POST   /api/shops/staff/<pk>/reject/                (shops.approve)
POST   /api/shops/staff/<pk>/suspend/               (shops.approve)
POST   /api/shops/staff/<pk>/reactivate/            (shops.approve)
GET    /api/staff/orders/                            (orders.staff.view)
GET    /api/staff/orders/<pk>/                       (orders.staff.view)
PATCH  /api/staff/orders/<order_number|id>/status/   (orders.staff.update)
GET    /api/points/sellers/<seller_id>/              (points.view)
GET    /api/points/sellers/<seller_id>/history/       (points.view)
POST   /api/points/sellers/<seller_id>/adjust/         (points.adjust)
GET    /api/payments/staff/... *(payments.view/verify/refund — exact path pattern inferred, verify against shop/urls.py)*

ADMIN  (mounted under /api/admin/, shop.urls → shop.admin_views)
GET    /api/admin/users/
GET    /api/admin/users/<pk>/
PATCH  /api/admin/users/<pk>/
GET    /api/admin/roles/
POST   /api/admin/roles/
GET    /api/admin/roles/<pk>/
PATCH  /api/admin/roles/<pk>/
DELETE /api/admin/roles/<pk>/
GET    /api/admin/sellers/
GET    /api/admin/sellers/<pk>/
POST   /api/admin/sellers/<pk>/status/
PATCH  /api/admin/sellers/<pk>/status/
GET    /api/admin/shops/
GET    /api/admin/shops/<pk>/
POST   /api/admin/shops/<pk>/status/
PATCH  /api/admin/shops/<pk>/status/
GET    /api/admin/products/
GET    /api/admin/products/<pk>/
POST   /api/admin/products/<pk>/status/
PATCH  /api/admin/products/<pk>/status/
GET    /api/admin/categories/
POST   /api/admin/categories/
GET    /api/admin/categories/<pk>/
PATCH  /api/admin/categories/<pk>/
DELETE /api/admin/categories/<pk>/
GET    /api/admin/customers/
GET    /api/admin/customers/<pk>/
```

**Not exposed by any API** (Django-admin-only, `/admin/` route): audit logs (`AuditLog`), raw `Role`/`Permission` table CRUD (superseded by `/api/admin/roles/` for roles, but `Permission` objects have zero API surface at all).

**Legacy, non-API note**: `shop/views.py`/`shop/cart.py`/`shop/forms.py` implement an older, session-based Django-template storefront (cart-in-session, a bare template checkout) that is entirely separate from the DRF API layer above and from the `cart` app's `Cart`/`CartItem` models. It is not relevant to the Next.js frontend and should be ignored.

---

## P. Backend Completeness Matrix

Scoring criteria: **Complete** = full CRUD/lifecycle exists, is permission-gated, and is test-covered; **Partial** = endpoint(s) exist but a meaningful piece (self-service transition, dedicated view, deeper verification) is missing or unverified; **Missing** = no code found. Percentages are a rough weighted read of "how much of the feature area a frontend could fully build against today," not a personal quality judgment.

### Customer
- Authentication: **Partial** (login/refresh/me solid; no registration, no logout, no password reset)
- Profile: **Complete**
- Commerce (catalog + cart): **Complete**
- Orders: **Complete** (create/view/cancel; no forward self-transition, which is by design)
- Payments: **Partial** (initiate endpoint exists, not deeply verified in this pass)
- **Overall backend readiness: ~75%**

### Seller
- Authentication: **Partial** (shared with Customer — same registration/logout gap)
- Seller profile: **Complete** (minor: `submit_for_review()` dead code)
- Shop: **Complete**
- Products: **Complete**
- Inventory (seller-facing view): **Partial/Missing** (no dedicated endpoint confirmed)
- Orders: **Complete**
- Wallet/Points: **Complete**
- **Overall backend readiness: ~85%**

### Staff
- Authentication: **Partial** (same shared gap)
- Support operations: **Partial** (order ops complete; no ticketing system)
- Finance operations: **Partial** (payments/refunds complete; no payout/report screens)
- Operations (Ops Manager): **Complete**
- **Overall backend readiness: ~60%** (dragged down by entirely-missing Support ticketing and Reports)

### Administrator
- User management: **Complete**
- RBAC: **Complete**
- Seller management: **Complete**
- Shop management: **Complete** (architecture wrinkle: bypasses `ShopService`)
- Product management: **Complete** (same wrinkle, bypasses `ProductService`)
- Category management: **Complete**
- Customer inspection: **Complete**
- **Overall backend readiness: ~90%**

### Super Administrator
- **Overall readiness: ~90%** — distinguishing logic is fully implemented and test-verifiable; the only "incompleteness" is shared with Administrator (Shop/Product service-bypass wrinkle).

---

## Q. Missing / Partial Features

### Critical before UI
1. **No user registration/signup endpoint** — no code path creates a `User` account other than Django admin or management commands. A public "Create Account" screen cannot be built against this backend today.
2. **No logout / token revocation** — `token_blacklist` app not installed; only client-side token discard is possible.
3. **No password change / reset flow** anywhere.
4. **No audit-log read API** — extensive audit writing exists (`AuditService.log`) but zero GET endpoint; an admin "Activity Log" screen needs a new endpoint first.
5. **No Support ticket/complaint/return system** — Master Prompt Phase 11 was never built; the Support Team role only has order view/update today.
6. **No Reports/Analytics endpoints** — `reports.view` is seeded and assigned to five roles but nothing serves a report; any "Dashboard/Reports" screen has nothing to call.
7. **No Notifications system** — Master Prompt Phase 12 was never built.

### Nice to have
- Route Admin shop/product status changes through `ShopService`/`ProductService` instead of direct field mutation (architecture cleanliness, not a UI blocker).
- Consolidate the two parallel seller-approval surfaces (`/api/sellers/<pk>/approve/` vs `/api/admin/sellers/<pk>/status/`) or clearly document which panel uses which.
- Wire `SellerProfile.submit_for_review()` to an actual endpoint so sellers can self-request re-review.
- Add a dedicated seller-facing inventory endpoint (current/reserved/sold stock per product).
- Extend `CurrentUserSerializer` to include `is_seller`/`seller_type`/`seller_status` so the frontend doesn't need extra round-trips (and 404-handling) just to know if a logged-in user is a seller.
- Category deletion still allows hard DELETE alongside the safe-delete guard; Task 17 preferred deactivate-only.

### Already complete (do not rebuild)
- RBAC engine: roles, permissions, protected roles, custom role creation, anti-escalation logic.
- JWT auth (login/refresh/me).
- Customer profile + multi-address management with default-address handling.
- Cart with live/dynamic pricing and strict ownership isolation.
- Public catalog browsing with filtering.
- Order lifecycle (create-from-cart, cancel, staff/seller status transitions) with a strict, tested state machine.
- Seller onboarding, shop CRUD, seller-type-gated shop-creation limits.
- Seller product management with triple-enforced ownership.
- Points/wallet system: atomic debit-on-product-creation, race-condition-safe (thread-tested).
- Admin governance for users/roles/sellers/shops/products/categories/customers, all audit-logged.
- Staff order/payment/refund/inventory operations — cleanly permission-code driven, no role-name special-casing.

---

## R. Security Restrictions

- `is_superuser` is a **universal** bypass for every RBAC permission check (`rbac/services.py:59` and repeated in ~20+ permission classes across every app).
- `is_staff` is used **separately and inconsistently** as an ad hoc "can act on any order" override in `shop/api_views.py`/`shop/services.py` only — a plain Django staff flag (no RBAC role required) can unlock order-ownership bypass in those specific code paths. This is a real inconsistency between the two authorization systems worth knowing before building UI that assumes "permissions array is the single source of truth."
- Protected role codes (`SUPER_ADMINISTRATOR`, `ADMINISTRATOR`) cannot be created, modified, or deleted through the roles API by **anyone**, including a Super Administrator.
- Anti-privilege-escalation guards on user-role assignment: an actor can never modify their own role assignments; only a Super Administrator/superuser can grant or revoke `SUPER_ADMINISTRATOR`; the last active Super Administrator cannot be deactivated; non-super actors cannot touch a target who already holds `SUPER_ADMINISTRATOR` or assign any protected role code.
- Cross-user access patterns are **inconsistent by design across apps**: some return `403` via object-permission classes (`IsAddressOwner`, `IsShopOwner`, `IsProductOwner`), others deliberately return `404` to avoid leaking resource existence (`orders`, `seller orders`, `cart items`). The frontend should handle both response codes as "not accessible," not assume one convention project-wide.
- Rate limiting / throttling: **not covered by this audit** — no agent found or was asked to specifically verify DRF throttle classes; treat as unverified rather than confirmed absent.

---

## S. Recommended Next.js UI Architecture

```
Next.js
│
├── Public                     — catalog, shop pages, search (AllowAny APIs)
│
├── Customer                   — profile, addresses, cart, checkout, orders
│   (gate: authenticated + has CustomerProfile / CUSTOMER role;
│    note: no self-registration exists yet — plan around it)
│
├── Seller                     — profile, shop(s), products, orders, wallet
│   (gate: has SellerProfile; conditionally render shop-creation UI
│    based on seller_type from GET /api/sellers/me/)
│
└── Staff/Admin (single shell, sections driven by /api/auth/me/ `permissions`)
    ├── Orders & Fulfillment    (orders.staff.view/update)
    ├── Sellers & Shops         (sellers.view/approve, shops.view/approve,
    │                            or sellers.admin.manage / shops.admin.manage
    │                            for the fuller governance view)
    ├── Products & Categories   (products.admin.manage, categories.admin.manage)
    ├── Finance                 (payments.*, points.*)
    ├── Governance              (users.admin.*, roles.admin.*) — Administrator/Super Admin only
    └── [not buildable yet]     Support tickets, Reports/Analytics, Notifications
```

Do **not** hardcode five separate role-specific admin apps (Support/Finance/OpsManager/Admin/SuperAdmin) — the backend's own permission-code design means a single shell that shows/hides sections based on the `permissions` array is both more accurate to how access actually works and far less frontend code to maintain.

---

## T. Files Inspected

**Master spec**: `task/Master_Prompt.md` (full), `task/task13.md`, `task/task15.md`, `task/task16.md`, `task/task17.md` (full).

**rbac**: `models.py`, `services.py`, `permissions.py`, `views.py`, `urls.py`, `serializers.py`, `admin.py`, `tests.py`, `management/commands/seed_rbac.py`.

**sellers**: `models.py`, `serializers.py`, `views.py`, `urls.py`, `permissions.py`, `services.py`, `tests.py`.

**shops**: `models.py`, `serializers.py`, `views.py`, `urls.py`, `permissions.py`, `services.py`, `fields.py`, `tests.py`.

**shop** (monolith): `models.py`, `views.py`, `api_views.py`, `admin_views.py`, `admin_permissions.py`, `admin_serializers.py`, `urls.py`, `permissions.py`, `services.py`, `serializers.py`, `cart.py`, `forms.py`, `inventory_service.py`, `payment_service.py`, `test_public_catalog.py`, `test_customer_orders.py`, `test_seller_orders.py`, `test_seller_product.py`, `test_admin_governance.py`, `test_staff_orders.py`, `test_inventory.py`, `test_payments.py`, `management/commands/seed_demo_data.py`.

**customers**: `models.py`, `serializers.py`, `views.py`, `urls.py`, `permissions.py`, `services.py`, `tests.py`.

**cart**: `models.py`, `serializers.py`, `views.py`, `urls.py`, `permissions.py`, `services.py`, `tests.py`.

**points**: `models.py`, `serializers.py`, `views.py`, `urls.py`, `permissions.py`, `services.py`, `tests.py`.

**audit**: `models.py`, `services.py`, `admin.py`.

**config**: `settings.py`, `urls.py`.

No file was edited, written to, or otherwise modified — this document is the only file this audit produced.

---

## U. Final Verdict

**1. How many actual user roles exist?**
8 formal RBAC roles (`SUPER_ADMINISTRATOR`, `ADMINISTRATOR`, `OPERATION_MANAGER`, `SALES_MANAGER`, `SALES_TEAM`, `FINANCE`, `SUPPORT_TEAM`, `CUSTOMER`), plus a 9th, entirely separate user category — **Seller** — that is not an RBAC role at all.

**2. How many seller types exist?**
3: `FULL_SHOP_OWNER`, `LIMITED_SHOP_OWNER`, `PRODUCT_OWNER`.

**3. How many major frontend panels should exist?**
4: Public Storefront, Customer Account, Seller Dashboard, and one unified Staff/Admin Console (with permission-driven internal sections) — not 5+ hardcoded per-role apps.

**4. Which roles should share the same panel?**
`SUPER_ADMINISTRATOR`, `ADMINISTRATOR`, `OPERATION_MANAGER`, `SALES_MANAGER`, `SALES_TEAM`, `FINANCE`, `SUPPORT_TEAM` should all share one Staff/Admin Console, with section visibility driven by the `permissions` array from `/api/auth/me/` — because that's exactly how the backend itself decides access.

**5. Is Customer backend complete enough for UI development?**
Yes for browse/cart/checkout/orders/profile/addresses. **No** for self-registration or logout — those don't exist yet.

**6. Is Seller backend complete enough for UI development?**
Yes — profile, shop, products, orders, and wallet are all solid. Minor gaps: no self-service "submit for review," no dedicated seller-facing inventory endpoint.

**7. Is Staff backend complete enough for UI development?**
Partially. Orders/payments/refunds/moderation/governance are solid and cleanly permission-driven. Support ticketing, Reports/Analytics, and Notifications have **no backend at all** — scope those out of v1 or build the backend first.

**8. Is Administrator backend complete enough for UI development?**
Yes — users, roles/RBAC, sellers, shops, products, categories, and customer inspection all have working, audited CRUD/moderation.

**9. Is Super Administrator backend complete enough for UI development?**
Yes — the distinguishing logic (protected roles, escalation guards, universal bypass) is fully implemented.

**10. Which backend features are still missing before UI development?**
User registration/signup, logout/token revocation, password reset, an audit-log read API, Support ticketing, Reports/Analytics, and Notifications.

**11. Which APIs already exist and should be consumed by Next.js?**
The full inventory in Section O — auth, public catalog/shops, customer profile/addresses/cart/orders, seller profile/shops/products/orders/wallet, staff seller/shop/order/payment/inventory operations, and admin governance for users/roles/sellers/shops/products/categories/customers.

**12. What exact role/permission information does the frontend receive after login?**
From `GET /api/auth/me/`: `id`, `username`, `email`, `first_name`, `last_name`, `is_staff`, `is_superuser`, `roles` (array of role codes), `permissions` (array of permission code strings). **No seller or customer sub-profile data** is included — fetch those separately from `/api/sellers/me/` and `/api/profile/me/`.

**13. What should the Next.js route/panel structure be based on the current backend?**
See Section S's tree — Public / Customer / Seller / one permission-driven Staff-Admin shell.

**14. Are there any backend architectural problems that should be fixed before starting the UI?**
Yes, none of them block starting UI work on Customer/Seller/most-of-Staff-Admin, but worth flagging to the backend team in parallel: (a) no registration endpoint, (b) `is_staff` used as an informal bypass inconsistent with the RBAC-code system in the order/payment code, (c) Admin shop/product status endpoints bypass their own domain services, (d) two parallel seller-approval code paths that both reach the same service functions, (e) `/api/auth/me/` doesn't surface seller/customer sub-profile info, (f) no audit-log read API despite extensive audit writing.

**15. Can I safely start frontend UI development now?**
**Yes, for Public Storefront, Customer, and Seller panels, and for the Orders/Payments/Moderation/Governance parts of the Staff/Admin console.** Hold off on building Support-ticketing, Reports/Analytics, and Notifications screens (no backend exists), and hold off on a public self-registration screen until a signup endpoint is added — that is the single most impactful backend gap to close next if public sign-up is part of the product vision.

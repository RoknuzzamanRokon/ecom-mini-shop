# Django Superuser Admin — Professional Platform Control Panel

Transform `http://127.0.0.1:8001/admin/` into a powerful, professional, secure, and highly usable internal administration control center for MiniShop superusers.

## Current State

### Already Registered (8 admin.py files)

| App | Models Registered | Quality |
|-----|------------------|---------|
| **audit** | `AuditLog` (read-only ✓) | Good — immutable, no add/change/delete |
| **cart** | `Cart` + `CartItem` (inline ✓) | Basic — missing select_related |
| **customers** | `CustomerProfile`, `Address` | Basic — no order count, no user link optimization |
| **points** | `SellerWallet`, `PointTransaction` (immutable ✓), `ProductCreationCost` | Good — ledger protections in place |
| **rbac** | `Role` (inline ✓), `Permission`, `UserRole`, `RolePermission` | Good — autocomplete fields |
| **sellers** | `SellerProfile` (fieldsets ✓) | Missing lifecycle admin actions |
| **shop** | `Category`, `Product` (inline ✓), `Order` (inline ✓), `OrderItem` | Missing status badges, actions |
| **shops** | `Shop` (fieldsets ✓) | Missing lifecycle admin actions |

### Models NOT Yet Registered in Admin

| Model | App | Priority |
|-------|-----|----------|
| `ProductInventory` | shop | **High** — stock visibility |
| `InventoryTransaction` | shop | **High** — audit ledger |
| `Payment` | shop | **High** — financial visibility |
| `Refund` | shop | **High** — financial visibility |
| `Favorite` | customers | Medium |

### Existing Admin Templates (Preserve & Enhance)

- [base_site.html](file:///mnt/Project/Python/MiniShop/backend/templates/admin/base_site.html) — Custom branding, Google Fonts, CSS
- [index.html](file:///mnt/Project/Python/MiniShop/backend/templates/admin/index.html) — Zen dashboard with 4 KPI cards
- [login.html](file:///mnt/Project/Python/MiniShop/backend/templates/admin/login.html) — Glassmorphism login
- [nav_sidebar.html](file:///mnt/Project/Python/MiniShop/backend/templates/admin/nav_sidebar.html) — Custom sidebar
- [japanese_admin.css](file:///mnt/Project/Python/MiniShop/backend/static/css/japanese_admin.css) — 28.6 KB theme

### Existing Domain Services (Must Reuse)

- `sellers.services` → `approve_seller()`, `reject_seller()`, `suspend_seller()`, `reactivate_seller()`
- `shops.services.ShopService` → `approve_shop()`, `reject_shop()`, `suspend_shop()`, `reactivate_shop()`
- `shop.services.OrderService` → `transition_order_status()`, `cancel_customer_order()`
- `shop.inventory_service.InventoryService` → stock operations
- `shop.payment_service.PaymentService` → payment operations
- `audit.services.AuditService` → `log()` for immutable audit

---

## Proposed Changes

### Phase 1: Register Missing Models + Enhance All ModelAdmin Classes

---

#### [MODIFY] [admin.py](file:///mnt/Project/Python/MiniShop/backend/shop/admin.py) — Shop App Admin

**Register missing models:**
- `ProductInventory` — read-only stock visibility with low-stock indicators (highlight available_quantity < 10)
- `InventoryTransaction` — immutable audit ledger (no add/change/delete), filterable by transaction_type
- `Payment` — read-only financial inspection, no sensitive credential exposure, colored status badges
- `Refund` — read-only, PROTECT-linked to Payment/Order

**Enhance existing:**
- `CategoryAdmin` — add product count column (`get_queryset` annotated)
- `ProductAdmin` — add `select_related('category', 'shop', 'shop__owner')`, colored status badges, stock indicator
- `OrderAdmin` — colored status badges, total items count, `select_related('user')`, `prefetch_related('items')`, admin actions for lifecycle transitions via `OrderService`
- `OrderItemAdmin` — add `select_related('order', 'product', 'shop', 'seller')`

---

#### [MODIFY] [admin.py](file:///mnt/Project/Python/MiniShop/backend/sellers/admin.py) — Sellers Admin

- Add **admin actions**: "Approve & Activate Selected Sellers", "Suspend Selected Sellers", "Reject Selected Sellers" — all using `sellers.services` functions
- Add colored status badges in list_display
- Add `select_related('user', 'reviewed_by')`
- Add shop count and product count columns (annotated)

---

#### [MODIFY] [admin.py](file:///mnt/Project/Python/MiniShop/backend/shops/admin.py) — Shops Admin

- Add **admin actions**: "Approve & Activate Selected Shops", "Suspend Selected Shops", "Reject Selected Shops", "Reactivate Selected Shops" — all using `ShopService` methods
- Add colored status badges in list_display
- Add `select_related('owner', 'owner__user', 'reviewed_by')`
- Add product count column (annotated)

---

#### [MODIFY] [admin.py](file:///mnt/Project/Python/MiniShop/backend/customers/admin.py) — Customers Admin

- Add order count column on `CustomerProfileAdmin` (annotated via `user__orders`)
- Add total addresses count
- Add `select_related('user')`
- Register `Favorite` model

---

#### [MODIFY] [admin.py](file:///mnt/Project/Python/MiniShop/backend/cart/admin.py) — Cart Admin

- Add `select_related('user')` on CartAdmin
- Add `select_related('cart__user', 'product', 'product__shop')` on CartItemAdmin

---

#### [MODIFY] [admin.py](file:///mnt/Project/Python/MiniShop/backend/audit/admin.py) — Audit Admin

- Add `select_related('actor', 'shop', 'seller')` for performance
- Add IP address to list_display

---

#### [MODIFY] [admin.py](file:///mnt/Project/Python/MiniShop/backend/points/admin.py) — Points Admin

- Add `select_related('seller', 'seller__user')` on SellerWalletAdmin
- Add `select_related('wallet', 'seller', 'seller__user', 'actor')` on PointTransactionAdmin

---

#### [MODIFY] [admin.py](file:///mnt/Project/Python/MiniShop/backend/rbac/admin.py) — RBAC Admin

- Add `select_related('user', 'role', 'assigned_by')` on UserRoleAdmin
- Add user count column on RoleAdmin (annotated)
- Add permission count column on RoleAdmin (annotated)

---

### Phase 2: Enhanced Dashboard + Navigation

---

#### [MODIFY] [index.html](file:///mnt/Project/Python/MiniShop/backend/templates/admin/index.html) — Dashboard

Enhance the existing 4-card KPI dashboard to include real platform metrics:
- **Users** — total registered users
- **Sellers** — total / pending / active / suspended
- **Shops** — total / pending / active / suspended
- **Products** — total / published / draft
- **Orders** — total / pending / delivered / cancelled
- **Revenue** — total order value (৳)
- **Payments** — total paid / pending / failed
- **Inventory Alerts** — low stock count

Metrics will be injected via a custom `AdminDashboardView` that replaces the default index with context data.

---

#### [MODIFY] [nav_sidebar.html](file:///mnt/Project/Python/MiniShop/backend/templates/admin/nav_sidebar.html) — Sidebar

Enhance sidebar with organized section groupings:
- **Dashboard** (home)
- **Commerce**: Products, Categories, Orders, Payments, Refunds, Inventory
- **Merchants**: Sellers, Shops, Wallets, Points
- **Customers**: Profiles, Addresses, Favorites, Carts
- **Access Control**: Users, Roles, Permissions, User Roles
- **Audit**: Audit Logs
- **Storefront**: Link to `http://localhost:3000`

---

#### [MODIFY] [japanese_admin.css](file:///mnt/Project/Python/MiniShop/backend/static/css/japanese_admin.css) — Theme

Add CSS for:
- Colored status badges (green=active/approved, blue=pending, red=suspended/rejected, gray=draft)
- Low-stock warning indicators (amber/red)
- Payment status colors
- Dashboard metric cards grid
- Better table row hover states
- Improved mobile responsiveness

---

#### [NEW] [admin_dashboard.py](file:///mnt/Project/Python/MiniShop/backend/shop/admin_dashboard.py)

Custom admin dashboard view providing platform-wide metrics:
- Uses `select_related`/`prefetch_related` and `aggregate()` for efficient queries
- Returns context with all KPI counts
- Currency always ৳

---

#### [MODIFY] [urls.py](file:///mnt/Project/Python/MiniShop/backend/config/urls.py) — Root URLs

Register the custom admin dashboard view to override the default admin index.

---

### Phase 3: Admin Actions with Service Integration

All lifecycle admin actions will:
1. Use existing domain service methods (never bypass business logic)
2. Log via `AuditService.log()` for immutable audit trail
3. Show confirmation messages via `self.message_user()`
4. Handle `ValidationError` gracefully with error messages
5. Require `request.user` as the staff actor

**Seller Actions:**
- `approve_and_activate_sellers` → calls `approve_seller(seller, request.user)` for each
- `suspend_sellers` → prompts reason (via intermediate confirmation page or uses a default), calls `suspend_seller()`
- `reject_sellers` → calls `reject_seller()`

**Shop Actions:**
- `approve_and_activate_shops` → calls `ShopService.approve_shop()`
- `suspend_shops` → calls `ShopService.suspend_shop()`
- `reject_shops` → calls `ShopService.reject_shop()`
- `reactivate_shops` → calls `ShopService.reactivate_shop()`

**Order Actions:**
- `confirm_orders` → calls `OrderService.transition_order_status(order, "CONFIRMED")`
- `mark_processing` → `OrderService.transition_order_status(order, "PROCESSING")`
- `mark_shipped` → `OrderService.transition_order_status(order, "SHIPPED")`
- `mark_delivered` → `OrderService.transition_order_status(order, "DELIVERED")`
- `cancel_orders` → `OrderService.transition_order_status(order, "CANCELLED")`

> [!IMPORTANT]
> Admin actions for suspend/reject that require a **reason** will use Django's intermediate confirmation page pattern. The action redirects to a simple form page where the admin enters the reason, then the service is called.

---

#### [NEW] [admin_actions.html](file:///mnt/Project/Python/MiniShop/backend/templates/admin/admin_actions.html)

Intermediate confirmation form template for actions requiring a reason (suspend seller/shop, reject seller/shop). Styled consistently with the Japanese theme.

---

### Phase 4: User Admin Enhancement

---

#### [MODIFY] [admin.py](file:///mnt/Project/Python/MiniShop/backend/shop/admin.py) or [NEW] [admin.py](file:///mnt/Project/Python/MiniShop/backend/config/admin.py)

Customize the Django `User` admin (currently default `auth.User`):
- Show: username, email, first_name, last_name, is_staff, is_superuser, is_active, date_joined, last_login
- Add inline: `UserRole` (from rbac)
- Search by: username, email, first_name, last_name
- Filter by: is_staff, is_superuser, is_active, date_joined
- Add `select_related` for performance

---

## Security Rules

> [!CAUTION]
> - **Never** weaken existing authentication/RBAC/lifecycle rules
> - **Never** expose sensitive payment credentials (card numbers, gateway secrets)
> - **Never** allow direct status field editing that bypasses service methods for lifecycle-critical models (Payment, Refund, InventoryTransaction, PointTransaction, AuditLog)
> - **Financial records** (PointTransaction, InventoryTransaction, Payment, Refund) remain **immutable** — no delete permission
> - **Confirmation required** for destructive batch actions (suspend, reject, cancel)
> - Admin actions **always** use the existing domain service layer, never raw `save()`

---

## Performance Rules

- Every `list_display` FK reference must use `select_related()` via `get_queryset()`
- Annotation-based computed columns (product count, order count) use `Count()` in `get_queryset()`
- No N+1 queries — verify with Django Debug Toolbar or `assertNumQueries` in tests
- Pagination enforced (Django admin default 100 per page, keep as-is)

---

## Verification Plan

### Automated Tests
```bash
backend/venv/bin/python backend/manage.py test shop sellers shops customers cart points rbac audit --keepdb -v2
```

### Manual Verification
- Django system check: `backend/venv/bin/python backend/manage.py check`
- Frontend build (unchanged but verify): `cd frontend && npm run build`
- Visual inspection of admin at `http://127.0.0.1:8001/admin/`
- Verify all model list pages load without errors
- Verify admin actions execute correctly
- Verify dashboard metrics display

### Git Commit
Single commit after all phases verified:
```
feat(admin): professional django superuser admin control panel
```

---

## Open Questions

> [!IMPORTANT]
> **Reason-Required Actions**: For admin actions like "Suspend Seller" and "Reject Shop" that require a mandatory reason string, should I:
> - **A)** Use Django's intermediate confirmation page (a small form page within admin) — more UX-correct but adds template complexity
> - **B)** Use a simpler approach with a fixed default reason like "Suspended via admin action" and let the admin edit the reason afterward on the detail page
>
> I recommend **Option A** for production quality but **Option B** is faster to implement. Both preserve service layer integrity.

> [!NOTE]
> **Scope Clarification**: The user's specification mentions a "custom admin sidebar" — the project already has a custom [nav_sidebar.html](file:///mnt/Project/Python/MiniShop/backend/templates/admin/nav_sidebar.html) with organized sections. I will enhance the existing sidebar rather than replacing it, preserving the Japanese minimalist theme already established.

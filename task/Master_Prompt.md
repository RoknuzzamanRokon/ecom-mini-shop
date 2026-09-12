# MINISHOP — MASTER PROJECT PROMPT

## Django REST Framework + Next.js Ecommerce Platform

You are working on the ongoing **MiniShop** project.

This document is the primary source of truth for the project's architecture, business rules, security model, frontend structure, backend integration, and implementation workflow.

Before implementing any task:

1. Read this Master Prompt.
2. Inspect the actual existing codebase.
3. Inspect previously implemented features.
4. Reuse existing architecture wherever possible.
5. Do not invent APIs, models, permissions, roles, or business rules.
6. Do not rebuild an existing feature unless the task explicitly requires it.
7. Keep backend authorization as the final security authority.
8. If the required backend capability does not exist, clearly identify the backend gap instead of creating fake/mock frontend functionality.

---

# 1. PROJECT ARCHITECTURE

MiniShop consists of:

```text
MiniShop
│
├── Backend
│   └── Django + Django REST Framework
│
└── Frontend
    └── Next.js
```

The backend is the source of truth for:

* Authentication
* Authorization
* Users
* RBAC
* Sellers
* Shops
* Products
* Categories
* Cart
* Orders
* Payments
* Refunds
* Inventory
* Customer profiles
* Addresses
* Wallet / Points
* Audit
* Platform governance

The Next.js frontend is responsible for:

* Storefront UI
* Customer experience
* Seller experience
* Staff/Admin management experience
* API integration
* Route protection
* Permission-based UI visibility
* Responsive UX

Frontend must NEVER become the final authorization authority.

---

# 2. IMPLEMENTATION WORKFLOW

MiniShop development follows this workflow:

```text
Master Prompt
     ↓
Existing Code Audit
     ↓
Architecture Verification
     ↓
Task Scope
     ↓
Implementation
     ↓
Tests
     ↓
Regression Tests
     ↓
Django Check
     ↓
Frontend Build
     ↓
Git Commit
     ↓
Task Walkthrough
```

For every task:

* First inspect existing implementation.
* Do not assume missing functionality.
* Do not duplicate existing code.
* Do not introduce unnecessary architectural changes.
* Preserve backward compatibility.
* Run appropriate tests.
* Run regression tests for affected existing features.
* Verify frontend build when frontend code changes.
* Provide a final implementation walkthrough.

---

# 3. USER AND RBAC MODEL

## 3.1 Formal RBAC Roles

MiniShop has exactly **8 formal RBAC roles**:

```text
1. SUPER_ADMINISTRATOR
2. ADMINISTRATOR
3. OPERATION_MANAGER
4. SALES_MANAGER
5. SALES_TEAM
6. FINANCE
7. SUPPORT_TEAM
8. CUSTOMER
```

These are system roles managed by the RBAC system.

---

# 4. SELLER IS NOT AN RBAC ROLE

IMPORTANT:

**Seller is NOT a formal RBAC role.**

A Seller is represented through the business/domain model:

```text
User
  ↓
SellerProfile
```

SellerProfile represents the seller/business relationship of a user.

Seller types are:

```text
FULL_SHOP_OWNER
LIMITED_SHOP_OWNER
PRODUCT_OWNER
```

Seller type must NOT be confused with:

* RBAC role
* permission
* management role

Seller type controls seller-specific business capabilities.

---

# 5. PLATFORM USER DOMAINS

MiniShop should be understood as four major user/application domains:

```text
MiniShop
│
├── Public Storefront
│
├── Customer Panel
│
├── Seller Panel
│
└── Staff / Admin Management Console
```

The 8 RBAC roles do NOT mean that MiniShop must have 8 completely separate frontend dashboards.

Management roles should share a common management shell.

UI visibility and actions should be driven primarily by:

```text
permissions[]
```

and secondarily by role/domain context.

---

# 6. CUSTOMER SHOPPING MODEL

MiniShop supports both:

## 6.1 Guest Customer

A guest customer must be able to browse and purchase without first creating an account.

Expected flow:

```text
Home
 ↓
Product Listing
 ↓
Product Detail
 ↓
Add to Cart / Buy Now
 ↓
Checkout
 ↓
Place Order
```

Customer account/profile must NOT be mandatory merely for browsing or purchasing.

However, the actual implementation must follow the capabilities of the backend.

If backend guest checkout is unavailable, do not fake it in the frontend.

Clearly report the backend blocker.

---

# 7. REGISTERED CUSTOMER

Customers may optionally register/login to access account-specific functionality.

The storefront should provide customer authentication access from the top/right area of the UI.

Conceptual flow:

```text
Storefront
   ↓
Login / Register
   ↓
Customer Account
   ├── Profile
   ├── Orders
   ├── Order Details
   ├── Purchase History
   ├── Addresses
   └── Other backend-supported customer features
```

Do not invent customer features that are not supported by the backend.

---

# 8. CUSTOMER AUTHENTICATION

Existing backend authentication APIs include:

```text
POST /api/auth/token/
POST /api/auth/token/refresh/
GET  /api/auth/me/
```

Current user information includes:

```text
id
username
email
first_name
last_name
is_staff
is_superuser
roles[]
permissions[]
```

The frontend should use the existing JWT authentication system.

Do NOT create a second authentication system.

---

# 9. CUSTOMER REGISTRATION GAP

Currently, the backend does not provide a dedicated public customer signup endpoint.

Therefore:

* Do not pretend `/register` is already backend-supported.
* Do not implement fake registration.
* If customer registration is required by a task, identify the backend requirement first.

---

# 10. CUSTOMER LOGOUT

The backend currently does not provide server-side token revocation/logout.

Therefore:

* Do not claim that server-side logout exists.
* Do not invent a token blacklist.
* Frontend logout behavior must be designed according to the actual backend capability.
* If server-side logout is required, treat it as a backend feature requirement.

---

# 11. MANAGEMENT LOGIN

Management users use a separate frontend entry point:

```text
/admin/login
```

This is NOT the customer login page.

It is intended for MiniShop management users.

Management users include:

```text
SUPER_ADMINISTRATOR
ADMINISTRATOR
OPERATION_MANAGER
SALES_MANAGER
SALES_TEAM
FINANCE
SUPPORT_TEAM
```

`CUSTOMER` must not be treated as a management user.

The management console must use the existing backend JWT/RBAC system.

Do NOT create a second authentication backend.

---

# 12. MANAGEMENT CONSOLE

Management users should share one common application shell:

```text
/admin
```

Conceptually:

```text
/admin
├── dashboard
├── orders
├── products
├── shops
├── sellers
├── customers
├── categories
├── users
└── roles
```

Actual routes must be determined from the existing project and task requirements.

Do not blindly create routes just because they appear in this example.

---

# 13. PERMISSION-DRIVEN MANAGEMENT UI

The frontend must not simply say:

```text
if role == ADMINISTRATOR
```

for every feature.

Prefer:

```text
permissions[]
```

for:

* menu visibility
* page access
* action buttons
* edit/delete controls
* management operations

Backend remains the final authority.

Example:

```text
User has:
products.view
products.update
```

Then frontend may show product management and edit controls.

But backend must independently enforce those permissions.

---

# 14. EXISTING STOREFRONT

The existing Next.js storefront already contains pages including:

```text
/
 /product/*
 /checkout
```

These pages MUST be preserved.

Do not rebuild the storefront from scratch.

Any future frontend task must first inspect the current implementation and extend it.

---

# 15. PRODUCT-CENTRIC STOREFRONT

The storefront must support:

```text
Home
 ↓
Product Listing
 ↓
Product Detail
```

Customers can:

```text
Add to Cart
Buy Now
```

from the product experience where backend support exists.

---

# 16. SHOP AS A FIRST-CLASS STOREFRONT ENTITY

Shop is a first-class browsing dimension of MiniShop.

The storefront should expose:

* Categories
* Shops
* Products

Conceptually:

```text
Home
│
├── Categories
│
├── Shops
│
└── Products
```

Shop navigation/filtering must use actual backend data.

Do not create mock shops.

---

# 17. PRODUCT → SHOP RELATIONSHIP

Every publicly available product should expose its associated shop where supported by the backend API.

Conceptual product UI:

```text
Product Name
Price
Stock

Shop: ABC Electronics

[Visit Shop]

[Add to Cart]
[Buy Now]
```

The exact UI must match the actual backend response and existing product implementation.

---

# 18. SHOP PAGE

The storefront should support a shop browsing page conceptually like:

```text
/shop/[slug]
```

A shop page should contain:

```text
Shop Information
      ↓
Products belonging to this Shop
```

Example:

```text
ABC Electronics
----------------------

Products

iPhone
MacBook
AirPods
Samsung Phone
```

Products from other shops must NOT appear on this page.

The frontend must use the actual backend shop/product relationship.

Do not create fake filtering logic that merely hides unrelated products if the backend does not provide the necessary data.

---

# 19. PRODUCT → SHOP CUSTOMER JOURNEY

Target customer journey:

```text
Home
 ↓
Product Card
 ↓
Product Detail
 ↓
Shop Information
 ↓
Visit Shop
 ↓
Shop Page
 ↓
Shop's Products
 ↓
Product Detail
 ↓
Add to Cart / Buy Now
```

When implementing this flow:

* Preserve existing product pages.
* Reuse existing API client.
* Reuse existing types where possible.
* Add only the missing pieces.
* Verify actual backend API support first.

---

# 20. CATEGORY + SHOP DISCOVERY

Home/storefront should allow customers to discover products through:

```text
Category
Shop
Product
```

Category and Shop are separate concepts.

Example:

```text
Category:
Electronics

Shop:
ABC Electronics
```

A product may belong to a category and a shop.

Do not treat Shop as a Product Category.

---

# 21. CART

The existing cart implementation must be reused.

Expected customer flow:

```text
Product
 ↓
Add to Cart
 ↓
Cart
 ↓
Checkout
```

Cart behavior must support the backend's actual guest/authenticated behavior.

Do not invent cart persistence rules.

---

# 22. BUY NOW

If supported by the current implementation, Buy Now should provide a direct purchase path:

```text
Product
 ↓
Buy Now
 ↓
Checkout
 ↓
Place Order
```

Do not create a separate order architecture for Buy Now if the existing cart/checkout architecture can safely support it.

---

# 23. CHECKOUT

Existing route:

```text
/checkout
```

must be preserved.

Before modifying checkout:

* inspect current implementation
* inspect backend order creation
* inspect cart behavior
* inspect authentication requirements
* inspect guest/customer behavior

Do not assume checkout requires login.

Do not assume checkout supports guest purchase unless verified.

---

# 24. CUSTOMER PANEL VS MANAGEMENT PANEL

These are different domains.

## Customer

```text
/login
/register (only when backend-supported)
/account
/account/orders
/account/profile
/account/addresses
```

## Management

```text
/admin/login
/admin/*
```

Customer users must not automatically receive management access.

Management UI must not be shown to ordinary customers.

---

# 25. SELLER PANEL

Seller is a business domain attached to a User through SellerProfile.

Seller Panel must account for:

```text
FULL_SHOP_OWNER
LIMITED_SHOP_OWNER
PRODUCT_OWNER
```

Seller type must be read from actual backend data.

Do not treat all sellers as having identical permissions/capabilities.

Do not create seller functionality that backend APIs do not support.

---

# 26. ADMIN / DJANGO ADMIN

Django's:

```text
http://127.0.0.1:8001/admin/
```

is an internal Django administration interface.

It is NOT the primary MiniShop customer-facing or management-facing application UI.

The actual MiniShop application UI should be provided by Next.js.

Django Admin may remain useful for:

* internal administration
* development
* database/model management
* read-only audit inspection where configured

Do not replace Django Admin unnecessarily.

---

# 27. SECURITY RULE

Frontend is never the final security authority.

Frontend may use:

```text
roles[]
permissions[]
```

to control:

* route visibility
* navigation
* buttons
* UX

Backend must enforce:

* authentication
* authorization
* ownership
* role restrictions
* permission restrictions
* business rules
* state transitions

Never trust frontend-only restrictions.

---

# 28. BACKEND GAPS

Known backend gaps from the architecture audit include:

1. Customer Signup
2. Logout / Token Revocation
3. Password Reset / Change
4. Audit Log API
5. Support Ticket / Complaint / Return
6. Reports / Analytics API
7. Notifications System

These must NOT be faked in the frontend.

If a UI depends on one of these features:

```text
Backend Missing
```

must be reported explicitly.

---

# 29. CURRENT BACKEND READINESS

Approximate frontend-readiness from the architecture audit:

```text
Public Store       → Ready
Customer           → ~75%
Seller             → ~85%
Staff              → ~60%
Administrator      → ~90%
Super Admin        → ~90%
```

These are planning estimates, not guarantees.

Always verify the actual current code before implementation.

---

# 30. API-FIRST FRONTEND RULE

Before creating a frontend feature:

1. Find the backend endpoint.
2. Inspect serializer.
3. Inspect permission class.
4. Inspect URL.
5. Inspect response shape.
6. Inspect existing TypeScript types.
7. Reuse existing API client.
8. Implement UI.
9. Verify authorization and error states.

Never invent an endpoint such as:

```text
/api/shop/products/
```

unless it actually exists or the task explicitly requires implementing it.

---

# 31. NO MOCK BUSINESS DATA

Do not use fake/mock data for:

* Products
* Shops
* Sellers
* Orders
* Customers
* Payments
* Inventory
* Roles
* Permissions

during actual application implementation.

Static placeholder content is acceptable only for purely presentational UI development when clearly isolated and not pretending to be real backend data.

---

# 32. FRONTEND ROUTE PRINCIPLES

Potential conceptual structure:

```text
/
├── product/[slug]
├── category/[slug]
├── shop/[slug]
├── checkout
│
├── login
├── register
└── account
    ├── orders
    ├── orders/[orderNumber]
    ├── profile
    └── addresses

/admin
├── login
├── dashboard
├── orders
├── products
├── shops
├── sellers
├── customers
├── categories
├── users
└── roles
```

This is a conceptual structure only.

Existing routes always take precedence.

Do not create routes without inspecting the existing frontend.

---

# 33. FRONTEND IMPLEMENTATION PRIORITY

When starting frontend work, use this general priority:

```text
1. Existing storefront audit
2. Existing API client audit
3. Authentication foundation
4. Customer authentication/account
5. Shop browsing
6. Product → Shop navigation
7. Guest checkout verification
8. Seller panel
9. Management authentication
10. Shared management console
11. Permission-driven management features
```

Exact task order must always follow the official MiniShop roadmap/Master Prompt.

Do not invent task numbers.

---

# 34. EXISTING FEATURE PRESERVATION

When modifying existing features:

* Do not break `/`
* Do not break `/product/*`
* Do not break `/checkout`
* Do not remove existing cart behavior
* Do not duplicate API clients
* Do not duplicate authentication systems
* Do not duplicate product/shop models
* Do not duplicate RBAC logic

Prefer incremental extension.

---

# 35. TESTING REQUIREMENTS

Backend changes:

```text
Django tests
Regression tests
python manage.py check
```

Frontend changes:

```text
npm build
```

Run relevant tests for affected domains.

For major architectural changes, run broader regression tests.

Never report a test as passed unless it was actually executed.

---

# 36. TASK IMPLEMENTATION RULE

For every task, report:

```text
Task
Goal
Files Changed
Backend Changes
Frontend Changes
API Changes
Security Changes
Tests
Regression Tests
Build Result
Git Commit
Remaining Issues
```

If something cannot be implemented because backend support is missing, say so explicitly.

Do not hide gaps.

---

# 37. FINAL PRINCIPLE

MiniShop must remain:

```text
Backend-authoritative
API-driven
Permission-aware
Role-aware
Shop-centric
Customer-friendly
Guest-purchase capable where backend supports it
Scalable
Secure
Incrementally developed
```

The frontend should provide a polished ecommerce experience without creating a parallel business/security system.

The backend remains the source of truth.

The Master Prompt and actual codebase must always be checked before implementing any new task.

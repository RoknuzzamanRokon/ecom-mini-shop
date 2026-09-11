# MiniShop — Task 10: Authenticated Customer Cart

## Context

Tasks 1–9 are complete.

MiniShop now has:

* authenticated users
* customer profiles
* customer addresses
* sellers
* shops
* products
* public product catalog
* RBAC
* points
* audit logging
* MySQL 8+

The existing frontend previously used localStorage cart behavior.

Task 10 must establish the backend cart architecture.

---

# Objective

Implement an authenticated, database-backed customer cart.

Do NOT implement checkout or order creation.

---

# 1. Audit Existing Cart

Before coding inspect:

* current frontend cart
* Product model
* product public visibility
* User model
* authentication
* existing cart-related code
* Master Prompt

Do not create duplicate cart behavior.

Determine how the existing localStorage cart should coexist with or migrate toward the authenticated backend cart.

---

# 2. Cart Model

Create a persistent cart associated with a User.

Conceptually:

Cart

* user
* created_at
* updated_at

CartItem

* cart
* product
* quantity
* created_at
* updated_at

Use appropriate unique constraints so one cart cannot contain duplicate rows for the same product.

Do not store derived price totals permanently unless the architecture explicitly requires it.

---

# 3. Ownership

A user can only access their own cart.

Never trust:

* cart_id supplied by client
* user_id supplied by client

Derive ownership from `request.user`.

---

# 4. Product Eligibility

Only products currently eligible for customer purchase may be added.

Do not allow adding:

* unpublished products
* rejected products
* inaccessible products
* products whose shop is not publicly active/approved
* otherwise unavailable products according to the existing Product model

Centralize this rule instead of duplicating it across views.

---

# 5. Quantity Rules

Implement sensible validation:

* quantity must be positive
* define a maximum quantity if required by Master Prompt/business rules
* prevent invalid integer values
* handle increment/decrement safely

Do not silently accept zero/negative quantities.

---

# 6. Cart API

Implement authenticated APIs such as:

GET:

`/api/cart/`

POST:

`/api/cart/items/`

PATCH:

`/api/cart/items/<id>/`

DELETE:

`/api/cart/items/<id>/`

DELETE:

`/api/cart/`

The API should allow:

* add product
* change quantity
* remove item
* clear cart
* retrieve current cart

Do not allow client-supplied price values.

---

# 7. Pricing

Cart totals must be derived from current authoritative Product pricing.

Never trust:

* frontend price
* client-submitted subtotal
* client-submitted total

If a cart response includes totals, calculate them server-side.

---

# 8. Concurrency

Handle concurrent cart modifications safely.

Avoid duplicate CartItem rows.

Use database constraints and transactions where required.

---

# 9. Frontend Migration

Update the Next.js cart layer so authenticated users can use the backend cart.

Preserve a sensible guest-cart experience if the Master Prompt requires guest shopping.

If guest cart migration is needed, implement only the minimum migration/synchronization required.

Do not implement checkout.

---

# 10. RBAC

Use the existing authentication/RBAC conventions.

Do not introduce a separate authorization mechanism.

---

# 11. Tests

Comprehensively test:

* authenticated cart creation
* empty cart
* add item
* update quantity
* remove item
* clear cart
* product isolation
* user isolation
* invalid quantity
* inaccessible product
* hidden product
* price calculation
* duplicate product insertion
* concurrent updates
* unauthenticated access
* frontend regression

Run all previous tests.

---

# 12. Verification

Run:

* migrations
* Django system check
* Task 10 tests
* complete backend regression
* frontend build
* API smoke tests

Report exact results.

---

# 13. Git

Create a dedicated Task 10 commit.

Report commit hash and clean working tree.

---

# STOP CONDITION

Implement ONLY Task 10.

Do NOT implement:

* checkout
* orders
* payments
* refunds
* shipping
* notifications

Stop after verification.

# MiniShop — Task 11: Order Creation & Order Lifecycle

## IMPORTANT

Implement **ONLY Task 11**.

Before coding:

1. Read the complete **MiniShop Master Prompt**.
2. Inspect the actual current project state.
3. Inspect the completed Task 1–10 implementation.
4. Do not assume model fields, service names, permission names, or API conventions.
5. Reuse existing architecture wherever appropriate.
6. Do NOT implement Task 12 or any later task.

---

# Context

Tasks 1–10 are complete.

Current MiniShop architecture includes:

* Django 5.2
* Django REST Framework
* MySQL 8+
* JWT authentication
* RBAC
* SellerProfile
* SellerWallet
* immutable PointTransaction ledger
* Shop
* MySQL native POINT location
* Product → Shop → SellerProfile → User ownership
* Product creation point cost
* AuditLog
* CustomerProfile
* Address
* public Product catalog
* Product Category
* centralized public Product visibility
* authenticated database-backed Cart
* CartItem
* server-authoritative cart pricing
* guest localStorage cart fallback

The current relationship is:

```text
User
 ├── CustomerProfile
 ├── Address
 ├── Cart
 │    └── CartItem
 │          └── Product
 │                └── Shop
 │                      └── SellerProfile
 │                            └── User
```

Task 11 introduces the **Order domain**.

The Order must become a **historical snapshot of the purchase transaction**.

---

# 1. ARCHITECTURE AUDIT FIRST

Before implementing anything, inspect:

* existing Product model
* ProductQuerySet.public()
* ProductService
* Shop
* SellerProfile
* CustomerProfile
* Address
* Cart
* CartItem
* CartService
* PointTransaction
* AuditLog
* AuditService
* authentication
* JWT
* RBAC
* existing API conventions
* existing serializers/views/services
* existing migrations
* existing tests

Determine whether any Order/OrderItem implementation already exists.

If something already exists:

* extend it
* do not duplicate it
* preserve existing architecture

Do not create parallel implementations of existing business rules.

---

# 2. OBJECTIVE

Implement the core customer Order system.

The system must support:

* creating an Order from the authenticated user's Cart
* historical Order snapshots
* OrderItem historical snapshots
* server-authoritative pricing
* shipping-address snapshot
* customer ownership isolation
* controlled Order lifecycle
* atomic Cart → Order conversion
* safe concurrency handling
* RBAC
* AuditLog integration
* customer Order APIs
* frontend types/API integration required for verification

Do NOT implement:

* payment gateway integration
* payment verification
* refund system
* shipping calculation
* seller order dashboard
* seller fulfillment workflow
* notifications
* support tickets
* Task 12 functionality

---

# 3. ORDER MODEL

Create an Order model according to the existing project conventions.

At minimum evaluate:

* `user`
* `order_number`
* `status`
* shipping address snapshot fields
* `subtotal`
* `discount_total` if required by the Master Prompt/current architecture
* `total_amount`
* `created_at`
* `updated_at`

## User relationship

Order ownership must belong to the authenticated User.

Use an appropriate database relationship and indexing strategy.

Do not allow a client to supply another user's ID.

Preserve historical orders according to the project's existing User deletion policy.

Do not blindly use cascading deletion if it would destroy required historical transaction records.

Audit the existing project policy and choose appropriately.

---

# 4. ORDER NUMBER

`order_number` / customer-facing order reference must be:

* server-generated
* unique
* immutable
* not client-controlled

Do not trust a client-supplied order number.

If the existing Master Prompt defines a specific order-number format, use it exactly.

Otherwise implement a safe unique server-generated reference consistent with project conventions.

---

# 5. ORDER STATUS

Use the Master Prompt's exact terminology if defined.

Otherwise evaluate:

* `PENDING`
* `CONFIRMED`
* `PROCESSING`
* `SHIPPED`
* `DELIVERED`
* `CANCELLED`

Statuses must be controlled server-side.

Never allow arbitrary client-submitted status values to modify an Order.

## Lifecycle

Implement a clear state-transition policy.

At minimum prevent invalid transitions such as:

```text
DELIVERED → PROCESSING
DELIVERED → CANCELLED
CANCELLED → CONFIRMED
CANCELLED → PROCESSING
```

A reasonable initial lifecycle is:

```text
PENDING → CONFIRMED
PENDING → CANCELLED (only if cancellation is explicitly allowed)

CONFIRMED → PROCESSING
CONFIRMED → CANCELLED (only if explicitly allowed)

PROCESSING → SHIPPED
SHIPPED → DELIVERED
```

Do not invent complex cancellation/refund behavior that belongs to future tasks.

If the Master Prompt does not define customer cancellation rules, do not expose customer cancellation functionality in Task 11.

---

# 6. ORDER IMMUTABILITY

An Order represents a historical transaction.

Therefore, once created:

* order number must not change
* OrderItem quantity must not change
* OrderItem price snapshot must not change
* OrderItem name snapshot must not change
* shipping address snapshot must not change
* persisted monetary totals must not be recalculated from current Product data
* customer must not edit historical Order contents

Future administrative/seller workflows may introduce controlled status changes, but Task 11 must not expose arbitrary customer modification.

Historical order data must remain correct even if:

* Product price changes
* Product name changes
* Product becomes unpublished
* Shop changes status
* Seller status changes
* Customer edits their Address
* Product is later deleted according to the project's deletion policy

---

# 7. ORDER ITEM MODEL

Create `OrderItem`.

At minimum evaluate:

* `order`
* `product` reference where appropriate
* `product_name`
* `unit_price`
* `quantity`
* `line_total`
* shop reference/snapshot
* seller reference/snapshot
* timestamps if consistent with the project

## Historical snapshot requirement

Do NOT depend exclusively on mutable Product/Shop/SellerProfile fields for historical order display.

At minimum preserve the historical customer-facing product information required by the Master Prompt.

The OrderItem must retain enough information for future Task 12 seller order management to determine:

```text
Product → Shop → Seller
```

If references are retained, they must not be the only source of historical information.

Avoid unnecessary duplication where the existing architecture safely provides the required relationship.

---

# 8. PRICE SNAPSHOT

This is a critical requirement.

Cart pricing is live/current.

Order pricing is historical.

Therefore:

## Cart

Uses current Product price.

## Order

Persists the purchase-time price.

OrderItem must persist:

* `unit_price`
* `quantity`
* `line_total`

Order must persist the authoritative order-level totals required by the domain, such as:

* `subtotal`
* `discount_total` if applicable
* `total_amount`

Do NOT calculate historical Order totals from the current Product prices after the Order has been created.

Do NOT trust client-submitted:

* unit price
* line total
* subtotal
* total
* discount

All monetary values must be calculated server-side using Decimal-safe arithmetic.

---

# 9. SHIPPING ADDRESS SNAPSHOT

Do not depend only on:

```text
Order → Address FK
```

for historical shipping information.

At Order creation, copy the required customer-facing shipping address fields from the selected Address into the Order snapshot.

Future edits to the customer's Address must NOT modify an existing Order's shipping address.

If retaining an optional Address reference is useful for traceability, the snapshot remains the authoritative historical record.

The API must not allow a customer to replace the historical shipping snapshot after Order creation.

---

# 10. ORDER CREATION SOURCE

An Order must be created from the authenticated user's current Cart.

The client must NOT be able to independently construct arbitrary OrderItems.

`POST /api/orders/` must NOT trust or accept client-controlled:

* user ID
* order number
* product price
* line total
* order total
* seller ID
* shop ID
* arbitrary OrderItems
* order status

The server derives the Order contents from:

```text
request.user
    ↓
Cart
    ↓
CartItems
    ↓
Product
    ↓
Shop
    ↓
SellerProfile
```

---

# 11. ORDER CREATION SERVICE

Create a dedicated service such as:

```text
OrderService.create_order_from_cart()
```

or the project's equivalent naming convention.

Do not place complex Order creation logic directly inside API views.

The service must:

1. authenticate/identify the current User
2. load the user's Cart
3. lock the Cart appropriately for order creation
4. load CartItems safely
5. validate that the Cart is orderable
6. validate Product eligibility
7. validate current public Product state
8. validate required Shop/Seller state
9. obtain current authoritative Product prices
10. validate required shipping Address
11. calculate authoritative totals
12. generate unique Order number
13. create Order
14. create OrderItems
15. create required historical snapshots
16. clear the Cart
17. create required AuditLog entry
18. commit the transaction

Everything must occur inside one appropriate database transaction.

---

# 12. ATOMIC CART → ORDER CONVERSION

Order creation and Cart clearing must be atomic.

If any step fails:

```text
NO Order
NO OrderItems
NO Cart clearing
```

The customer's Cart must remain available for retry.

If Order creation succeeds:

```text
Order created
OrderItems created
Cart cleared
Audit recorded
transaction committed
```

There must not be a successful Order with only partially cleared Cart contents.

There must not be a cleared Cart when Order creation failed.

---

# 13. CONCURRENCY / DOUBLE ORDER PROTECTION

This is critical.

Consider two simultaneous requests:

```text
POST /api/orders/
POST /api/orders/
```

for the same authenticated user's Cart.

The implementation must safely prevent the same Cart contents from being successfully converted into multiple duplicate Orders.

Use appropriate MySQL transaction/locking mechanisms, such as:

* `transaction.atomic()`
* `select_for_update()`
* database constraints
* appropriate locking/order-state strategy

The exact implementation should follow Django/MySQL capabilities and the existing project's conventions.

Test this race condition where practical.

Desired invariant:

> A single Cart checkout operation cannot successfully create multiple Orders from the same Cart contents.

---

# 14. CART VALIDATION

Before creating an Order, validate the current Cart again.

Do NOT assume the Cart is valid merely because products were valid when added.

Reject or safely handle:

* empty Cart
* unavailable Product
* unpublished Product
* inactive Product
* Product without Shop
* non-public Shop
* suspended/rejected Shop
* non-operational Seller
* inactive Category
* invalid CartItem quantity

Use the existing authoritative public Product architecture.

Prefer:

```text
ProductQuerySet.public()
```

or:

```text
ProductService.get_public_products_queryset()
```

Do NOT create a second independent public visibility implementation.

---

# 15. STALE CART ITEMS

If a Product became unavailable after being added to the Cart:

* do not create an Order containing that Product
* do not silently purchase it
* return a deterministic validation response
* preserve the Cart if Order creation fails

Follow the Task 10 stale-cart behavior where appropriate.

Do not automatically delete stale items unless explicitly required by the Master Prompt.

---

# 16. ORDER OWNERSHIP & SECURITY

Customers may only:

* create Orders from their own Cart
* list their own Orders
* retrieve their own Orders

Never trust:

```text
user_id
customer_id
cart_id
```

from the client to establish ownership.

For:

```text
GET /api/orders/<id>/
```

a customer attempting to access another user's Order must not receive that Order.

Follow the project's existing security conventions for returning `404` versus `403`.

Test user isolation explicitly.

---

# 17. CUSTOMER APIs

Implement customer-facing APIs according to existing project conventions.

Minimum:

### Create Order

```http
POST /api/orders/
```

The request should contain only the minimum information required for order creation, such as the selected shipping Address reference if the existing domain requires it.

The server determines:

* customer
* cart
* products
* quantities
* prices
* totals
* order number
* seller/shop relationships
* status

### List Orders

```http
GET /api/orders/
```

Only the authenticated user's Orders.

### Retrieve Order

```http
GET /api/orders/<id>/
```

Only the authenticated user's Order.

Do NOT expose arbitrary Cart IDs as an ownership mechanism.

---

# 18. STATUS APIs

Do NOT provide a customer endpoint that allows arbitrary status modification.

Do NOT accept:

```json
{
  "status": "DELIVERED"
}
```

from a normal customer request.

If the project architecture requires a status-transition service for future workflows, implement only the minimal domain foundation required by Task 11.

Seller/admin fulfillment operations belong to future tasks.

---

# 19. RBAC

Use the existing RBAC architecture.

Introduce only the permissions required for Task 11.

Follow existing naming conventions.

Potential permissions may include equivalents of:

```text
orders.create
orders.view
```

Use the project's actual naming conventions if different.

Do not hardcode role IDs.

Do not create a separate authorization system.

Remember:

> A seller can also be a customer.

Therefore a seller's User account must be able to use customer Order functionality when appropriately authorized.

Do not accidentally grant seller-management permissions through customer Order permissions.

---

# 20. AUDIT

Use the existing:

```text
AuditService
```

Do not create a second audit implementation.

Audit at minimum:

* Order creation
* controlled Order status changes
* cancellation if cancellation is implemented

Do not generate AuditLog noise for ordinary:

* GET order list
* GET order detail

Do not log unnecessary sensitive information such as credentials or tokens.

Follow the existing AuditLog schema and conventions.

---

# 21. FRONTEND

Implement only the minimum frontend changes required for Task 11.

Update:

* TypeScript Order types
* Order API client
* authenticated Order data handling
* any existing cart-to-order integration required for API verification

Do NOT build a complete checkout experience unless required by the existing architecture or Master Prompt.

Do NOT implement:

* payment UI
* payment gateway
* shipping calculation UI
* seller order dashboard
* refund UI
* notification UI

The backend remains authoritative.

---

# 22. TESTS

Create comprehensive Task 11 backend tests.

## Order creation

Test:

* successful Order creation
* Order number generation
* Order number uniqueness
* Order status initial value
* correct OrderItem creation
* correct quantities
* correct line totals
* correct Order totals
* Cart cleared after success

## Empty/invalid Cart

Test:

* empty Cart rejected
* unavailable Product rejected
* hidden Product rejected
* inactive Product rejected
* invalid quantity rejected
* Product without Shop rejected
* inactive Category rejected
* inactive/suspended Shop rejected
* non-operational Seller rejected

## Price integrity

Test:

* client cannot submit fake unit price
* client cannot submit fake line total
* client cannot submit fake Order total
* Product's current server price is used
* changing Product price after Order creation does NOT change existing Order
* existing OrderItem price snapshot remains unchanged

## Address snapshot

Test:

* Order stores required shipping address snapshot
* editing the original Address does NOT change existing Order
* historical Order still displays original shipping data

## Cart atomicity

Test:

* successful Order clears Cart
* failed Order leaves Cart unchanged
* failed Order creates no partial Order
* failed Order creates no partial OrderItems

## Security

Test:

* unauthenticated creation rejected
* unauthenticated listing rejected
* unauthenticated detail rejected
* User A cannot retrieve User B's Order
* client cannot assign another user
* client cannot submit arbitrary seller/shop ownership
* client cannot arbitrarily change Order status

## Order immutability

Test that customers cannot modify:

* Order number
* OrderItem quantity
* OrderItem price
* OrderItem name snapshot
* shipping address snapshot
* persisted totals

## Status lifecycle

Test:

* valid transitions
* invalid transitions rejected
* terminal statuses cannot be changed
* customer cannot arbitrarily transition status

Use exact Master Prompt lifecycle rules if defined.

## Concurrency

Where practical, test simultaneous Order creation against the same Cart.

Verify that the same Cart cannot successfully generate duplicate Orders.

## Audit

Test:

* Order creation audit entry
* required status-change audit entry
* cancellation audit entry if implemented

## Regression

Run the complete Tasks 1–10 regression suite.

No regression is acceptable.

---

# 23. DATABASE

Create MySQL-compatible migrations.

Verify:

* Order → User relationship
* OrderItem → Order
* OrderItem → Product if retained
* required Shop/Seller references or snapshots
* unique Order number
* monetary field precision
* quantity constraints
* appropriate indexes
* timestamps
* status field constraints/choices where appropriate

Do NOT switch database engines.

Do NOT introduce SQLite.

Do NOT introduce PostgreSQL/PostGIS.

---

# 24. MONETARY INTEGRITY

Use Django `DecimalField` with appropriate precision/scale consistent with the existing Product price implementation.

Do not use floating-point arithmetic for persisted monetary calculations.

Ensure:

```text
OrderItem.line_total
```

matches:

```text
unit_price × quantity
```

and Order totals match the sum of authoritative OrderItems and applicable adjustments.

Do not create unnecessary monetary fields that are not required by the current domain.

---

# 25. PERFORMANCE

Avoid obvious N+1 queries.

Use appropriate:

* `select_related`
* `prefetch_related`

for Order:

* user/customer information where needed
* OrderItems
* Product
* Shop
* Seller information
* required snapshot/display data

Do not introduce Redis or new caching infrastructure.

---

# 26. VERIFICATION

Run all of the following:

1. Django system check
2. migration generation
3. migration application
4. migration verification
5. Task 11 test suite
6. complete backend regression suite covering Tasks 1–11
7. frontend production build
8. API smoke tests
9. concurrency verification where practical

Report exact results.

---

# 27. GIT

Create a dedicated Task 11 commit.

Report:

* exact commit hash
* `git status`
* whether working tree is clean

Do not mix unrelated changes into the Task 11 commit.

---

# 28. FINAL REPORT

Return:

### Task 11 Completed

### Architecture Audit

### Files Changed

### Order Model

### OrderItem Model

### Order Number

### Order Status Lifecycle

### Order Snapshot / Immutability

### Address Snapshot

### Price Integrity

### Cart → Order Transaction

### Concurrency Protection

### Product Eligibility

### API Endpoints

### Security / Ownership

### RBAC

### Audit

### Frontend Changes

### Tests

### Full Regression

### Frontend Build

### System Check

### Migration Result

### API Smoke Tests

### Commit

### Working Tree

### Warnings / Known Issues

---

# 29. SCOPE BOUNDARY

Implement ONLY Task 11.

Do NOT implement:

* payment gateway
* payment verification
* refunds
* disputes
* shipping rate calculation
* shipping fulfillment
* seller order dashboard
* seller fulfillment actions
* customer notifications
* webhooks
* support tickets
* Task 12 or any later task

Do not implement speculative future features.

---

# STOP CONDITION

After Task 11 implementation and verification:

**STOP.**

Do not automatically begin Task 12.

Return the complete final report and wait for further instructions.

# MiniShop — Task 11: Order Creation & Order Lifecycle

## Context

Tasks 1–10 are complete.

MiniShop now has:

User → Customer Profile → Address

Seller → Shop → Product

and:

* JWT
* RBAC
* Point ledger
* AuditLog
* MySQL 8+
* public catalog
* authenticated cart

Task 11 introduces the order domain.

---

# Objective

Implement the core customer order system.

The order must become a historical snapshot of the purchase transaction.

Do NOT implement payment gateway integration in this task.

---

# 1. Audit First

Read the Master Prompt and inspect:

* Product
* Shop
* SellerProfile
* Cart
* CartItem
* Customer Address
* PointTransaction
* AuditLog
* RBAC

Do not duplicate existing models or services.

---

# 2. Order Architecture

Create:

Order
OrderItem

Order should contain appropriate:

* customer/user
* order number/reference
* status
* shipping address snapshot
* pricing totals
* created_at
* updated_at

OrderItem should contain:

* order
* product reference where appropriate
* product name snapshot
* product price snapshot
* quantity
* line total
* shop/seller reference or snapshot according to Master Prompt

Do not depend exclusively on mutable Product fields for historical order information.

---

# 3. Order Status

Use a clear lifecycle.

At minimum evaluate:

* PENDING
* CONFIRMED
* PROCESSING
* SHIPPED
* DELIVERED
* CANCELLED

Use the Master Prompt's exact terminology if different.

Do not allow arbitrary client-side status changes.

---

# 4. Order Creation

Create an atomic checkout/order service.

The service must:

1. authenticate customer
2. load customer's cart
3. validate cart
4. validate each product
5. validate shop/product visibility
6. calculate authoritative prices
7. create Order
8. create OrderItems
9. snapshot required historical information
10. clear the cart
11. create audit entry
12. commit transaction

If any step fails, the entire operation must roll back.

---

# 5. Address Snapshot

Do not store only a foreign key to the current customer address.

At order creation, copy the required shipping address data into the order snapshot.

Future edits to the user's address must not change an existing order's historical shipping address.

---

# 6. Price Integrity

Never trust client-submitted:

* unit price
* subtotal
* total
* discount

Calculate all authoritative values on the backend.

Use Decimal-safe monetary arithmetic.

---

# 7. Order Ownership

Customer can only:

* list own orders
* view own orders

Never allow another user's order to be retrieved by changing the ID.

---

# 8. Seller Relationship

Each OrderItem must retain enough information to determine:

Product → Shop → Seller

for seller order management in Task 12.

Do not create unnecessary duplicate seller ownership if the existing architecture can derive it safely.

---

# 9. APIs

Implement customer APIs such as:

POST:

`/api/orders/`

GET:

`/api/orders/`

GET:

`/api/orders/<id>/`

Do not allow customers to arbitrarily modify order status.

Cancellation rules should be implemented only where clearly defined by the Master Prompt/current lifecycle.

---

# 10. RBAC

Use existing RBAC.

Introduce only required order permissions.

Do not bypass existing authorization.

---

# 11. Audit

Use AuditService.

Audit:

* order creation
* status changes
* cancellation where applicable

---

# 12. Tests

Comprehensively test:

* successful order creation
* empty cart
* invalid product
* hidden product
* inactive shop
* price integrity
* quantity
* address snapshot
* cart clearing
* rollback
* duplicate/order consistency
* user isolation
* status transitions
* unauthorized status modification
* audit records
* concurrency where relevant
* regression across Tasks 1–10

---

# 13. Frontend

Add minimum frontend API/types needed for order creation and order listing.

Do not build the complete checkout UI yet unless required for verification.

---

# 14. Verification

Run:

* migrations
* system check
* Task 11 tests
* full backend regression
* frontend build
* API smoke tests

Report exact test counts and failures.

---

# 15. Git

Dedicated Task 11 commit.

Report:

* commit hash
* clean working tree

---

# STOP CONDITION

Implement ONLY Task 11.

Do NOT implement:

* payment gateway
* refund system
* seller order dashboard
* notifications
* support tickets

Stop after verification.

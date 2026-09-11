# MiniShop — Task 14: Customer Order Management & Cancellation

## IMPORTANT — IMPLEMENT ONLY TASK 14

You are continuing the MiniShop project after completion of Tasks 1–13.

Before writing code:

1. Read the MiniShop Master Prompt completely.
2. Inspect the actual current repository.
3. Review the implementation from Tasks 1–13.
4. Pay special attention to:

   * Order
   * OrderItem
   * OrderService
   * Cart
   * Product
   * ProductInventory
   * InventoryTransaction
   * InventoryService
   * Seller Order Management
   * CustomerProfile
   * Address
   * RBAC
   * AuditLog
5. Treat the actual repository implementation as authoritative.
6. Preserve existing architecture and conventions.

---

# HARD SCOPE RULE

Implement ONLY:

**Task 14 — Customer Order Management & Cancellation**

Do NOT implement:

* payment gateway
* real payment processing
* payment refund integration
* coupon system
* reviews/ratings
* notifications
* returns workflow
* exchange workflow
* frontend customer UI
* seller UI
* admin UI
* inventory dashboard
* Task 15+
* unrelated refactoring

Minimal frontend API/type changes are allowed only if required for API compatibility.

After completing Task 14, STOP.

---

# 1. TASK OBJECTIVE

Complete the customer-facing backend order-management capabilities.

Customers must be able to:

* view their own orders
* view their own order details
* request cancellation when allowed
* receive authoritative cancellation results
* have inventory reservations released atomically when cancellation succeeds
* retain historical order snapshots
* never modify financial/order history directly

The existing Order state machine from Task 11 remains authoritative.

Do NOT create a second order lifecycle.

---

# 2. CURRENT ORDER STATE MACHINE

Task 11 established:

```text
PENDING
   ↓
CONFIRMED
   ↓
PROCESSING
   ↓
SHIPPED
   ↓
DELIVERED
```

Existing cancellation transitions must be inspected from the actual implementation.

Do not silently redesign them.

If the current implementation allows:

```text
PENDING → CANCELLED
CONFIRMED → CANCELLED
PROCESSING → CANCELLED
```

then preserve those rules unless the Master Prompt explicitly requires otherwise.

Terminal states:

```text
DELIVERED
CANCELLED
```

must remain terminal.

---

# 3. CUSTOMER ORDER LIST

Existing endpoint:

```text
GET /api/orders/
```

must remain the authoritative customer order list.

Verify that:

* authentication is required
* customer sees only their own orders
* pagination works
* ordering is safe/whitelisted
* no other customer's order is exposed
* staff/admin behavior follows existing authorization rules

Do not duplicate the customer order system under another unnecessary endpoint.

If existing functionality already satisfies this, preserve it and add only what Task 14 requires.

---

# 4. CUSTOMER ORDER DETAIL

Existing endpoints include:

```text
GET /api/orders/<id>/
GET /api/orders/<order_number>/
```

Verify:

* authenticated customer can access own order
* another customer receives the established safe unauthorized response, preferably 404
* anonymous requests receive 401
* historical snapshots are returned
* seller/shop/product information does not leak unrelated data
* current Product/Shop/Seller changes do not rewrite historical OrderItem values

Do not introduce duplicate order-detail endpoints without architectural need.

---

# 5. CUSTOMER CANCELLATION

Add a customer-specific cancellation action if it does not already exist.

Recommended:

```text
PATCH /api/orders/<order_number>/cancel/
```

or the existing project action convention.

The request must NOT allow arbitrary status updates.

Do NOT accept:

```json
{
  "status": "DELIVERED"
}
```

or any arbitrary lifecycle status.

Cancellation must be a dedicated business operation.

The server decides whether cancellation is allowed.

---

# 6. CANCELLATION AUTHORIZATION

A customer may cancel only their own Order.

Verify:

```text
order.user == request.user
```

Do not trust:

```text
user_id
customer_id
order_owner
```

from the request body.

A customer attempting to cancel another customer's order must not succeed.

Use the existing order ownership/security architecture from Task 11.

---

# 7. CANCELLATION ELIGIBILITY

Cancellation must use the existing Order state machine.

Do not allow cancellation if the order is already:

```text
DELIVERED
CANCELLED
```

Do not allow cancellation from states not permitted by the existing Master Prompt/Task 11 implementation.

If:

```text
PENDING → CANCELLED
```

is allowed, it must succeed only under the established rules.

If:

```text
CONFIRMED → CANCELLED
```

is allowed, preserve that behavior.

If:

```text
PROCESSING → CANCELLED
```

is allowed by the current implementation, preserve it.

Do NOT invent new cancellation states.

---

# 8. ATOMIC CANCELLATION

Cancellation must be atomic.

The following operations must succeed or fail together:

```text
Order status change
+
Inventory reservation release
+
Inventory transaction ledger
+
AuditLog
```

If inventory release fails:

```text
Order must remain in its previous status.
```

If Order transition fails:

```text
Inventory must remain unchanged.
```

No partial cancellation is acceptable.

Reuse:

```text
OrderService.transition_order_status()
```

and:

```text
InventoryService.release_order_reservation()
```

where appropriate.

Do not create a second cancellation implementation.

---

# 9. INVENTORY INTEGRATION

Task 13 established:

```text
Order creation:
available -= quantity
reserved += quantity
```

Cancellation:

```text
reserved -= quantity
available += quantity
```

Task 14 must preserve this exact accounting behavior.

Example:

```text
Before cancellation:

available = 7
reserved = 3
sold = 10

After cancellation:

available = 10
reserved = 0
sold = 10
```

Never change `sold_quantity` during cancellation of a still-reserved order.

---

# 10. CANCELLATION IDEMPOTENCY

Cancellation must be idempotent/safely reject repeated cancellation.

Example:

First request:

```text
PENDING → CANCELLED
```

succeeds.

Second request:

```text
CANCELLED → CANCELLED
```

must NOT:

* release inventory again
* create duplicate RELEASE transactions
* increase available stock again
* create misleading duplicate cancellation events

Return an appropriate business error/status according to existing API conventions.

---

# 11. INVENTORY TRANSACTION INTEGRITY

Task 13 created immutable:

```text
InventoryTransaction
```

Cancellation must create exactly one appropriate:

```text
RELEASE
```

movement per Order when reservation exists.

Verify:

* correct product
* correct quantity
* correct Order
* correct OrderItem where applicable
* correct before/after quantities
* correct actor
* correct reason

Do not modify historical inventory transactions.

---

# 12. AUDIT LOGGING

Customer cancellation must create an immutable AuditLog.

Use the existing:

```text
AuditService
```

Do not create another audit mechanism.

The audit event should capture at minimum:

* actor/customer
* order
* previous status
* new status
* cancellation action
* timestamp
* relevant metadata

Use the project's existing action naming conventions.

If an order cancellation already generates:

```text
ORDER_STATUS_UPDATED
```

ensure Task 14 does not create redundant/conflicting audit records unless explicitly required.

---

# 13. ORDER IMMUTABILITY

Customer cancellation must NOT modify:

* order number
* OrderItem quantity
* OrderItem unit price
* OrderItem line total
* product snapshot
* shop snapshot
* seller snapshot
* shipping address snapshot
* subtotal
* discount_total
* shipping_fee
* total_amount

Only the permitted Order lifecycle state and associated operational timestamps may change.

---

# 14. NO PAYMENT REFUND

There is currently no payment gateway/payment subsystem in scope.

Therefore:

**Do NOT implement actual payment refunds in Task 14.**

Do not create:

```text
Payment
Refund
PaymentTransaction
Gateway
Stripe
SSLCommerz
bKash
Nagad
```

or equivalent payment integrations.

If the current architecture contains no payment system, cancellation should only handle:

```text
Order lifecycle
+
Inventory reservation release
+
Audit
```

If a financial refund would eventually be required, document it as a future dependency.

---

# 15. CUSTOMER ORDER STATUS RESPONSE

Customer order APIs should expose the current authoritative status.

Example:

```json
{
  "order_number": "ORD20260912ABC123",
  "status": "CANCELLED"
}
```

Do not derive status from inventory.

Order status remains authoritative in `Order`.

Inventory is synchronized with Order transitions.

---

# 16. CUSTOMER CANCELLATION REASON

Inspect the Master Prompt and current data model.

If cancellation reason is explicitly required, implement it.

Otherwise, do not add unnecessary complex cancellation metadata.

If a simple server-side audit note is sufficient, use the existing audit mechanism.

Do not allow arbitrary customer text to become a trusted financial/legal record without appropriate handling.

---

# 17. RBAC

Audit existing permissions.

Task 11 already has:

```text
orders.create
orders.view
```

Task 14 should use the existing customer order authorization architecture.

If a dedicated permission is required by the Master Prompt, add the minimum appropriate permission, for example:

```text
orders.cancel
```

Do not grant it broadly without reviewing existing role mappings.

Customer cancellation must not give the customer:

```text
orders.update
```

or unrestricted order status control.

The customer must only have the specific cancellation capability.

---

# 18. CUSTOMER OWNERSHIP SECURITY

Test all of the following:

```text
Customer A → Order A → allowed
Customer A → Order B → rejected
Customer B → Order A → rejected
Anonymous → Order A → 401
```

Do not reveal unnecessary information about another customer's order.

Prefer the existing 404 ownership-isolation behavior.

---

# 19. MULTI-SELLER ORDERS

Cancellation operates on the single authoritative customer Order.

Example:

```text
Order 100

Seller A:
    Product A × 2

Seller B:
    Product B × 3
```

Customer cancellation must:

* cancel the single Order
* release Product A reservation
* release Product B reservation
* create correct inventory RELEASE transactions
* preserve both sellers' historical OrderItem snapshots
* not split the Order

Inventory operations must happen independently per Product.

---

# 20. SELLER ORDER MANAGEMENT COMPATIBILITY

Task 12 established seller order management.

Ensure Task 14 does not bypass seller authorization or create inconsistent seller-visible states.

After customer cancellation:

```text
Seller order API
```

must show the updated authoritative Order status.

Do not create a second seller-specific cancellation state.

---

# 21. PRODUCT / INVENTORY CHANGES AFTER ORDER

Verify that cancellation still works if the Product has subsequently changed.

Historical OrderItem data remains authoritative for the Order.

Inventory release must use the reserved quantity associated with the OrderItem/order transaction, not a newly-read Product price or arbitrary current quantity.

Do not use current Product fields to reconstruct historical order quantities.

---

# 22. CONCURRENCY

Cancellation must be concurrency-safe.

Example:

Two requests simultaneously attempt:

```text
Customer cancellation
Seller/admin status update
```

or two simultaneous customer cancellation requests.

Use:

```text
transaction.atomic()
select_for_update()
```

following the established Task 11/13 locking architecture.

The final result must be consistent.

There must never be:

```text
double inventory release
negative reserved stock
duplicate successful cancellation
```

---

# 23. API ERROR BEHAVIOR

Use the project's existing DRF error conventions.

Examples:

Unauthorized:

```text
401
```

Another customer's order:

```text
404
```

Cancellation not permitted:

```text
400
```

or the established business-rule status.

Already cancelled/delivered:

appropriate validation/business error.

Do not expose internal Python exceptions or database errors.

---

# 24. TEST REQUIREMENTS

Create comprehensive backend tests.

### Order ownership

* customer can view own order
* customer cannot view another customer's order
* customer can cancel own eligible order
* customer cannot cancel another customer's order
* anonymous cancellation rejected

### Cancellation

Test every currently valid cancellation transition.

For example:

```text
PENDING → CANCELLED
CONFIRMED → CANCELLED
PROCESSING → CANCELLED
```

Only test transitions that are actually defined by the existing architecture.

### Invalid cancellation

Verify cancellation fails for:

```text
DELIVERED
CANCELLED
```

and any other non-cancellable state.

### Inventory

Verify:

```text
available += reserved quantity
reserved -= reserved quantity
```

after cancellation.

### Multi-seller

One Order containing products from multiple sellers:

* all relevant product reservations released
* no seller's inventory affects another seller incorrectly
* single Order remains intact

### Idempotency

Repeated cancellation must not:

* release twice
* create duplicate RELEASE transactions
* modify inventory twice

### Atomic rollback

Force an inventory failure and verify:

* Order status unchanged
* inventory unchanged
* no partial release
* no partial audit/inventory transaction

### Historical integrity

Verify cancellation does not change:

* product snapshot
* shop snapshot
* seller snapshot
* quantity
* price
* totals
* shipping snapshot

### Audit

Verify correct cancellation/status audit event.

### Concurrency

Test simultaneous cancellation attempts where practical.

### RBAC

Verify:

* authorized customer
* unauthorized customer
* seller
* administrator
* superuser

according to existing architecture.

### Regression

Run the complete backend suite from Tasks 1–14.

---

# 25. FRONTEND

Frontend remains out of scope.

Only add minimal:

* cancellation API client
* TypeScript payload/response types

if required.

Do NOT build:

* customer order UI
* cancellation button UI
* order history page
* seller dashboard
* admin dashboard

Frontend will be handled later as a dedicated phase.

---

# 26. DATABASE

Use MySQL 8+ only.

Do not introduce:

* PostgreSQL-only features
* PostGIS
* GeoDjango
* SQLite-specific behavior

Create migrations only if genuinely required.

Verify:

```bash
python manage.py makemigrations --check --dry-run
python manage.py showmigrations
```

---

# 27. VERIFICATION

Before declaring Task 14 complete:

### Django

```bash
python manage.py check --database default
```

Must report zero issues.

### Migrations

```bash
python manage.py showmigrations
python manage.py makemigrations --check --dry-run
```

### Task-specific tests

Run all Task 14 tests.

### Full regression

Run the complete backend test suite from Tasks 1–14.

Report the exact count.

### Frontend

If frontend files were changed:

```bash
npm run build
```

Must succeed.

### API smoke tests

Verify:

1. Customer order list
2. Customer order detail
3. Customer cancellation
4. Unauthorized cancellation
5. Invalid cancellation
6. Inventory release
7. Multi-seller cancellation
8. Repeated cancellation
9. Seller view after customer cancellation

### Git

Create a dedicated Task 14 commit.

Verify:

```bash
git status
git log -1 --oneline
```

Working tree should be clean.

---

# 28. FINAL REPORT

Report:

1. Files changed
2. Models changed
3. Services changed
4. APIs added/changed
5. Cancellation rules
6. Order state-machine integration
7. Inventory integration
8. Multi-seller behavior
9. Idempotency behavior
10. RBAC changes
11. Audit behavior
12. Tests added
13. Task-specific test count
14. Full regression test count
15. Migration status
16. Django system check
17. Frontend build result if applicable
18. API smoke-test results
19. Git commit hash
20. Git status
21. Warnings/limitations
22. Future payment/refund dependency, if applicable

Do not claim anything that was not actually tested.

---

# 29. STOP CONDITION

After Task 14 is fully implemented, tested, verified, and committed:

**STOP.**

Do not implement Task 15.

Do not implement payment.

Do not implement refunds.

Do not implement returns.

Do not implement reviews.

Do not implement coupons.

Do not implement notifications.

Do not implement frontend UI.

Wait for the next explicit instruction.

# MiniShop — Task 13: Inventory, Stock & Order Reservation Management

## IMPORTANT — IMPLEMENT ONLY TASK 13

You are continuing the MiniShop project after completion of Tasks 1–12.

Before writing code:

1. Read the MiniShop Master Prompt completely.
2. Inspect the actual current repository.
3. Review Tasks 1–12 implementation.
4. Pay special attention to:

   * Product
   * Shop
   * SellerProfile
   * Cart
   * CartItem
   * Order
   * OrderItem
   * OrderService
   * Seller Order Management
   * RBAC
   * AuditLog
5. Do not assume this prompt overrides the actual architecture.
6. Preserve existing conventions and abstractions.

## HARD SCOPE RULE

Implement ONLY Task 13:

**Inventory, Stock & Order Reservation Management**

Do NOT implement:

* frontend inventory UI
* seller dashboard UI
* payment gateway
* refunds/payment reconciliation
* coupons
* reviews
* notifications
* wishlist
* unrelated product refactoring
* Task 14+
* a new checkout system

Minimal frontend API/type changes are allowed only when required by backend API compatibility.

After Task 13 is complete, STOP.

---

# 1. TASK OBJECTIVE

Introduce a reliable backend inventory system for Products.

The system must:

* maintain stock availability
* prevent overselling
* perform atomic stock operations
* integrate stock reservation with Order creation
* handle concurrent order creation safely
* maintain inventory history/auditability
* respect Product → Shop → Seller ownership
* preserve historical OrderItem snapshots
* remain compatible with MySQL 8+

The inventory system must be server-authoritative.

The client must never be trusted for:

* stock quantity
* availability
* reserved quantity
* sold quantity
* inventory adjustments

---

# 2. ARCHITECTURE AUDIT FIRST

Before implementation, inspect the existing Product model carefully.

Determine whether inventory already exists.

If no inventory domain exists, introduce a dedicated inventory model rather than unnecessarily adding many unrelated fields directly to Product.

Preferred conceptual architecture:

```text
Product
   │
   └── ProductInventory
          ├── available_quantity
          ├── reserved_quantity
          ├── sold_quantity
          └── timestamps
```

Use a OneToOne relationship unless the Master Prompt/current architecture requires another structure.

Do not create duplicate inventory sources.

There must be exactly one authoritative source for current inventory availability.

---

# 3. INVENTORY MODEL

Create the minimum required inventory model.

At minimum support:

* Product
* available quantity
* reserved quantity
* sold quantity
* created_at
* updated_at

Use appropriate non-negative database constraints.

Requirements:

```text
available_quantity >= 0
reserved_quantity >= 0
sold_quantity >= 0
```

Do not permit negative stock.

Use appropriate integer field types for the project's expected scale.

---

# 4. INVENTORY SEMANTICS

Use these definitions consistently:

### Available

Units that can currently be ordered.

```text
available_quantity
```

### Reserved

Units currently committed to active Orders but not yet completed.

```text
reserved_quantity
```

### Sold

Units belonging to successfully completed orders.

```text
sold_quantity
```

The exact transition semantics must be consistent throughout the service layer.

Do not introduce ambiguous concepts such as multiple competing stock counts.

---

# 5. ORDER RESERVATION

Integrate inventory with the existing:

```text
OrderService.create_order_from_cart()
```

Order creation must reserve stock atomically.

For each CartItem:

1. lock the relevant ProductInventory row
2. re-read current available quantity
3. verify sufficient stock
4. reserve the requested quantity
5. create the OrderItem
6. update inventory consistently

Example:

```text
Available = 10
Customer orders = 3

After successful order:

Available = 7
Reserved = 3
```

The operation must happen inside the same database transaction as Order creation.

---

# 6. ZERO STOCK

If:

```text
available_quantity < requested_quantity
```

order creation must fail.

Return an appropriate validation/business error.

The failure must leave:

* Cart unchanged
* no partially-created Order
* no partially-created OrderItems
* inventory unchanged
* no partial reservation

Use the existing atomic transaction strategy from Task 11.

---

# 7. CONCURRENT ORDER CREATION

This is a critical requirement.

Example:

```text
Product stock = 5

Customer A orders = 4
Customer B orders = 3
```

Two requests execute concurrently.

Only one transaction may successfully reserve the stock.

The final state must never become:

```text
available_quantity < 0
```

and total reserved stock must never exceed actual stock.

Use:

```text
transaction.atomic()
select_for_update()
```

or an equally strong MySQL-safe locking strategy.

Do not depend only on Python-level checks.

The database transaction must protect the invariant.

---

# 8. ORDER → INVENTORY LIFECYCLE

Inventory reservation must remain consistent with the existing Order state machine.

Current Order lifecycle:

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

Cancellation may occur according to the existing Task 11 transition rules.

Define and implement consistent inventory behavior for:

### Order creation

Reserve quantity:

```text
available -= quantity
reserved += quantity
```

### Order cancellation

Release reservation:

```text
reserved -= quantity
available += quantity
```

### Order delivery

Finalize the sale:

```text
reserved -= quantity
sold += quantity
```

Do NOT create a second independent Order lifecycle.

Inventory must react to the existing Order state machine.

---

# 9. IDEMPOTENCY

Inventory transitions must be idempotent.

A status transition must not accidentally apply inventory movement twice.

For example:

```text
PROCESSING → SHIPPED
```

must not decrement inventory twice.

Likewise:

```text
PENDING → CANCELLED
```

must release a reservation only once.

Use appropriate transaction/state checks.

Do not rely on the frontend to prevent duplicate requests.

---

# 10. INVENTORY TRANSACTION HISTORY

Create an immutable inventory movement/history model if required by the Master Prompt and current architecture.

Preferred conceptual model:

```text
InventoryTransaction
```

Possible transaction types:

```text
INITIAL_STOCK
STOCK_IN
STOCK_OUT
RESERVATION
RELEASE
SALE
ADJUSTMENT
```

Use the minimum set actually required.

Each transaction should capture, where appropriate:

* Product
* inventory
* quantity
* transaction type
* before quantity
* after quantity
* related Order
* related OrderItem
* actor
* reason/note
* timestamp

Do not create fake movements for read-only operations.

Historical inventory records must be immutable.

---

# 11. STOCK INITIALIZATION

Determine how new Products receive inventory.

The design must avoid products silently having an undefined inventory state.

Preferred behavior:

* Product creation creates its inventory record with zero stock, OR
* another explicit server-side initialization strategy defined by the Master Prompt.

Do not trust a client-provided inventory quantity unless the authenticated actor has explicit inventory permission.

Seller/product creation must not allow arbitrary stock manipulation.

---

# 12. STOCK ADJUSTMENT

Create a backend service for authorized stock adjustments.

Example conceptual operation:

```text
InventoryService.adjust_stock(
    product,
    quantity,
    actor,
    reason
)
```

Requirements:

* atomic
* row-level locking
* no negative stock
* immutable inventory history
* audit logging
* server-authoritative
* explicit RBAC permission

Positive adjustment:

```text
+10
```

Negative adjustment:

```text
-3
```

Negative adjustment must never reduce available stock below zero.

Do not silently modify `sold_quantity` during a normal stock adjustment.

---

# 13. INVENTORY OWNERSHIP

Inventory belongs to the Product.

Product ownership remains:

```text
Product
   ↓
Shop
   ↓
SellerProfile
```

Seller inventory access must follow the existing seller ownership rules.

A seller may only adjust inventory for products belonging to:

* their own Shop
* their own SellerProfile

according to the authoritative existing ownership relationship.

Never trust:

```text
seller_id
shop_id
```

from the client.

Authorization must be derived from database relationships.

---

# 14. SELLER INVENTORY PERMISSIONS

Audit the existing RBAC system first.

Add only the required permissions.

Potential permissions:

```text
inventory.view
inventory.adjust
```

Use the project's existing naming conventions if different.

Determine role mappings according to the Master Prompt.

Do not grant inventory adjustment to ordinary customers.

Seller roles should only receive permissions appropriate to their existing seller capabilities.

Administrator/superuser/support behavior must follow the established RBAC architecture.

---

# 15. INVENTORY API

Create backend APIs according to existing project conventions.

Potential endpoints:

```text
GET   /api/inventory/
GET   /api/inventory/<product_id>/
PATCH /api/inventory/<product_id>/
```

or a seller-specific structure if that better matches the existing architecture.

The APIs should support:

* authorized inventory viewing
* authorized stock adjustment
* seller ownership isolation
* admin access according to RBAC

Do not expose internal inventory fields unnecessarily.

Do not allow clients to directly set:

```text
reserved_quantity
sold_quantity
```

Those must be controlled by domain services.

---

# 16. PUBLIC PRODUCT AVAILABILITY

Integrate inventory with the existing public Product catalog.

Inspect the current:

```text
ProductQuerySet.public()
ProductService.get_public_products_queryset()
Product.is_publicly_visible
```

Do not duplicate public visibility logic.

Product availability should expose an appropriate server-derived availability state.

For example:

```text
in_stock
out_of_stock
```

or the project's established terminology.

Do not expose misleading availability.

A product that is published but has zero available inventory should not be represented as purchasable.

Do not automatically change Product publication status merely because stock reaches zero unless the Master Prompt explicitly requires that behavior.

---

# 17. CART INTEGRATION

Inspect existing Cart behavior.

A stale cart may contain an item whose available stock has changed.

Do NOT reserve stock merely by adding an item to Cart.

Stock reservation occurs during Order creation.

During order creation:

```text
Cart quantity
      ↓
current Product
      ↓
current Inventory
      ↓
availability validation
      ↓
reservation
```

The server must always use current inventory at order time.

---

# 18. PRICE + INVENTORY INTEGRITY

Task 11 already establishes server-authoritative price calculation.

Do not change that architecture.

Order creation must validate both:

```text
current price
+
current inventory
```

inside the same atomic operation.

Do not trust client:

* price
* total
* stock
* availability

---

# 19. HISTORICAL ORDER INTEGRITY

Do not modify Task 11's historical OrderItem snapshots.

After order creation, changes to:

* Product name
* Product price
* Product slug
* Shop name
* Seller name

must not change historical OrderItem values.

Inventory changes must also never rewrite historical OrderItem quantities.

---

# 20. CANCELLATION INTEGRATION

Task 11 already supports cancellation transitions.

When an Order transitions into:

```text
CANCELLED
```

inventory reservations must be released exactly once.

Example:

```text
Order:
Product A × 3

Before cancellation:
available = 7
reserved = 3

After cancellation:
available = 10
reserved = 0
```

Do not allow:

```text
reserved < 0
```

or duplicate release.

Use the existing `OrderService.transition_order_status()` architecture rather than creating a second status mechanism.

---

# 21. DELIVERY INTEGRATION

When an Order transitions into:

```text
DELIVERED
```

reserved stock becomes sold stock.

Example:

```text
Before:
available = 7
reserved = 3
sold = 10

After:
available = 7
reserved = 0
sold = 13
```

This must happen atomically with the existing Order status transition.

---

# 22. MULTI-SELLER ORDERS

Task 12 established that one Order can contain multiple sellers.

Inventory must operate independently per Product/OrderItem.

Example:

```text
Order A

Seller A:
    Product A × 2

Seller B:
    Product B × 3
```

Inventory changes must be:

```text
Product A inventory → 2 units
Product B inventory → 3 units
```

Do not maintain a single seller-level stock counter.

Do not split the customer Order.

Do not allow one seller's inventory operation to modify another seller's inventory.

---

# 23. STATUS TRANSITION + INVENTORY TRANSACTION ATOMICITY

This is critical.

When:

```text
Order → CANCELLED
```

both:

```text
Order status change
+
inventory release
```

must succeed together.

When:

```text
Order → DELIVERED
```

both:

```text
Order status change
+
reserved → sold movement
```

must succeed together.

If inventory processing fails:

```text
Order status must not change.
```

If Order transition fails:

```text
Inventory must not change.
```

No partial state is acceptable.

---

# 24. AUDIT LOGGING

Use the existing `AuditService`.

Inventory adjustments should generate immutable audit records.

Capture:

* actor
* product
* shop
* seller
* adjustment quantity
* reason
* before quantity
* after quantity
* timestamp

Order-driven inventory movements should reference the relevant Order/OrderItem where appropriate.

Do not create a parallel audit framework.

---

# 25. DATABASE CONSTRAINTS

Use database constraints where practical.

At minimum:

```text
available_quantity >= 0
reserved_quantity >= 0
sold_quantity >= 0
```

Ensure the OneToOne Product → Inventory relationship is unique if using that architecture.

Use appropriate indexes for:

* product
* order
* order item
* transaction type
* timestamp

Do not introduce PostgreSQL-specific features.

MySQL 8+ is mandatory.

---

# 26. PERFORMANCE

Inventory operations must be database-efficient.

Use:

```text
select_for_update()
select_related()
prefetch_related()
```

where appropriate.

Avoid loading large product/order datasets into Python just to determine ownership or availability.

Concurrency-sensitive checks must happen under database locks.

---

# 27. TEST REQUIREMENTS

Create comprehensive backend tests.

### Inventory model

* inventory created correctly
* zero stock supported
* negative quantities rejected
* OneToOne uniqueness

### Stock adjustment

* authorized adjustment succeeds
* positive adjustment
* negative adjustment
* cannot go below zero
* unauthorized adjustment rejected
* seller cannot modify another seller's product
* audit created

### Order creation

* sufficient stock succeeds
* exact stock succeeds
* insufficient stock fails
* zero stock fails
* cart remains unchanged on failure
* order is not partially created
* inventory reservation is atomic

### Reservation

Verify:

```text
available -= quantity
reserved += quantity
```

### Cancellation

Verify:

```text
reserved -= quantity
available += quantity
```

and duplicate cancellation does not release twice.

### Delivery

Verify:

```text
reserved -= quantity
sold += quantity
```

and duplicate delivery does not count twice.

### Concurrency

Critical test:

```text
Stock = 5

Request A = 4
Request B = 3
```

Verify only one succeeds and:

```text
available >= 0
reserved <= original_stock
```

Also test concurrent order creation against the same Product.

### Multi-seller

One Order with multiple sellers must update each Product's inventory independently.

### RBAC

Test:

* customer
* seller
* unauthorized seller
* admin
* superuser

according to existing permissions.

### Historical integrity

Verify inventory changes never alter OrderItem snapshots.

### Regression

Run the complete Tasks 1–13 backend test suite.

---

# 28. FRONTEND

Frontend remains out of scope.

Only add minimal:

* TypeScript inventory types
* API client methods

if necessary.

Do NOT build:

* inventory dashboard
* seller stock management UI
* customer UI
* admin inventory UI

Those belong to the later frontend phase.

---

# 29. MIGRATIONS

Use MySQL 8+.

Run:

```bash
python manage.py makemigrations
python manage.py migrate
```

Then verify:

```bash
python manage.py showmigrations
python manage.py makemigrations --check --dry-run
```

No unapplied or unexpected migrations may remain.

---

# 30. VERIFICATION

Before declaring Task 13 complete:

### Django system check

```bash
python manage.py check --database default
```

Must report zero issues.

### Task-specific tests

Run all inventory/stock tests.

### Full regression

Run the complete backend test suite from Tasks 1–13.

### Frontend

If frontend files were changed:

```bash
npm run build
```

Must succeed.

### API smoke testing

Verify at minimum:

* inventory retrieval
* authorized stock adjustment
* unauthorized adjustment
* seller ownership isolation
* order creation with sufficient stock
* insufficient stock rejection
* cancellation inventory release
* delivery inventory finalization

### Git

Create a dedicated Task 13 commit.

Verify:

```bash
git status
git log -1 --oneline
```

Working tree should be clean.

---

# 31. FINAL REPORT

Report:

1. Files changed
2. Inventory model(s)
3. Inventory service/domain logic
4. OrderService integration
5. Order transition integration
6. Reservation behavior
7. Cancellation behavior
8. Delivery behavior
9. Stock adjustment behavior
10. RBAC permissions
11. Seller ownership rules
12. Multi-seller behavior
13. Audit behavior
14. Database constraints/indexes
15. Tests added
16. Full regression count
17. Migration status
18. Django system check
19. Frontend build result if applicable
20. API smoke-test results
21. Git commit hash
22. Git status
23. Warnings/limitations

Do not claim anything that was not actually tested.

---

# 32. STOP CONDITION

After Task 13 is fully implemented, tested, verified, and committed:

**STOP.**

Do not implement Task 14.

Do not implement refunds.

Do not implement reviews.

Do not implement coupons.

Do not implement notifications.

Do not implement frontend UI.

Wait for the next explicit instruction.

# MiniShop — Task 12: Seller Order Management & Seller Order Lifecycle

## IMPORTANT — IMPLEMENT ONLY TASK 12

You are continuing the MiniShop project after completion of Tasks 1–11.

Before writing code:

1. Read the MiniShop Master Prompt completely.
2. Inspect the current repository and actual implementation.
3. Review the existing architecture from Tasks 1–11.
4. Pay special attention to:

   * `Order`
   * `OrderItem`
   * `Cart`
   * `Product`
   * `Shop`
   * `SellerProfile`
   * RBAC
   * `AuditLog`
   * `OrderService`
   * existing order state machine
5. Do NOT assume the architecture from this prompt is more authoritative than the actual existing code.
6. Preserve existing conventions unless a change is required for Task 12.

### HARD SCOPE RULE

Implement **ONLY Task 12: Seller Order Management**.

Do NOT implement:

* customer frontend UI
* seller frontend UI
* payment gateway
* inventory/stock system
* coupons/discount system
* reviews/ratings
* notifications
* refund system
* new checkout flow
* unrelated refactoring
* Task 13 or later features

Minimal frontend API/type changes are allowed only if required to consume the Task 12 backend APIs.

Do not automatically start the next task after completing Task 12.

---

# 1. CURRENT ARCHITECTURE

Tasks 1–11 are already complete.

Current important architecture:

```text
User
 ├── CustomerProfile
 ├── Cart
 └── SellerProfile
       └── Shop
             └── Product
```

Order flow:

```text
Customer
   ↓
Cart
   ↓
Order
   ├── OrderItem
   │     ├── Product reference/snapshot
   │     ├── Shop reference/snapshot
   │     └── Seller reference/snapshot
   │
   └── Shipping address snapshot
```

Task 11 established:

* server-authoritative order creation
* historical snapshots
* immutable order number
* order totals
* atomic cart → order conversion
* order lifecycle state machine
* customer order ownership
* audit logging
* concurrency locking

Current Order status machine:

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

Cancellation exists only where the current Task 11 implementation permits it:

```text
PENDING → CANCELLED
CONFIRMED → CANCELLED
PROCESSING → CANCELLED
```

Do NOT redesign the Task 11 state machine unless an actual implementation defect is discovered.

---

# 2. TASK 12 OBJECTIVE

Build the backend subsystem that allows sellers to manage the order items belonging to their own products/shops.

A customer order may contain products from multiple sellers.

Example:

```text
Order #ORD123

Seller A:
    Product A × 2
    Product B × 1

Seller B:
    Product C × 3
```

Seller A must only be able to access and manage:

```text
Product A
Product B
```

Seller B must only be able to access and manage:

```text
Product C
```

Neither seller may access or modify another seller's order items.

The existing customer-facing Order must remain a single historical order.

Do NOT split one customer Order into separate Orders.

---

# 3. ARCHITECTURE AUDIT FIRST

Before implementation, verify:

### Order

* `Order.user`
* `Order.order_number`
* `Order.status`
* totals
* shipping snapshot
* timestamps

### OrderItem

* `OrderItem.order`
* `OrderItem.product`
* `OrderItem.shop`
* `OrderItem.seller`
* `product_name`
* `product_slug`
* `shop_name`
* `seller_name`
* `unit_price`
* `quantity`
* `line_total`

### SellerProfile

Verify:

* seller ownership
* seller status
* seller type
* approved/active rules

### Shop

Verify:

* owner
* status
* relationship to SellerProfile

### Product

Verify:

```text
Product → Shop → SellerProfile
```

The authoritative current ownership relationship must remain consistent with the architecture established in Task 7.

---

# 4. SELLER ORDER VISIBILITY

A seller may only access OrderItems belonging to:

1. their own SellerProfile, and/or
2. their own Shop according to the authoritative existing ownership relationship.

Prefer the current authoritative relationship already established in the project.

Do NOT rely only on client-supplied seller IDs.

Never trust:

```text
seller_id
shop_id
product_id
```

from the client as proof of ownership.

Ownership must be determined server-side.

---

# 5. MULTI-SELLER ORDER HANDLING

This is a critical requirement.

A single Order can contain multiple sellers.

Example:

```text
Order:
    Item 1 → Seller A
    Item 2 → Seller A
    Item 3 → Seller B
```

When Seller A requests order data:

```text
Seller A sees:
    Order information needed for fulfillment
    Item 1
    Item 2
```

Seller A must NOT see:

```text
Item 3
Seller B's identity/business information
Seller B's product information
```

Likewise Seller B sees only their own order items.

The customer Order itself remains one order.

---

# 6. SELLER ORDER LIST API

Create a seller-specific order endpoint using the project's existing API conventions.

Recommended endpoint:

```text
GET /api/seller/orders/
```

The endpoint must:

* require authentication
* require appropriate seller/order permission
* require an approved/active seller according to existing seller rules
* return only orders containing items belonging to the authenticated seller
* include only that seller's OrderItems
* support pagination
* support useful status filtering where appropriate
* avoid N+1 queries

Do not expose another seller's OrderItems through the response.

---

# 7. SELLER ORDER DETAIL API

Recommended:

```text
GET /api/seller/orders/<order_number>/
```

The seller may retrieve an order only when the order contains at least one OrderItem belonging to that seller.

The response should contain:

### Order-level information

Only information required for fulfillment and seller operations, such as:

* order number
* order status
* order timestamps
* relevant shipping snapshot
* relevant totals

### Seller-owned items

For each visible item:

* product name
* product slug if appropriate
* quantity
* unit price
* line total
* shop snapshot
* seller snapshot where appropriate

Do NOT leak unrelated seller items.

---

# 8. CUSTOMER DATA PRIVACY

Seller order APIs must expose only the customer information necessary for fulfillment.

Do not expose unnecessary private account information such as:

* password
* authentication tokens
* internal user details
* unrelated profile information
* unrelated customer addresses
* unrelated orders

Use the existing shipping address snapshot from Task 11 as the authoritative order shipping information.

Do not query the customer's current Address as a replacement for the historical order snapshot.

---

# 9. SELLER ORDER STATUS MANAGEMENT

Task 11 already created the global Order state machine.

Task 12 must integrate seller management with that state machine rather than bypassing it.

Use the existing transition rules.

Recommended endpoint:

```text
PATCH /api/seller/orders/<order_number>/status/
```

or the project's equivalent action endpoint.

The request must contain only the requested new status.

Example:

```json
{
  "status": "PROCESSING"
}
```

Do NOT accept:

```json
{
  "seller_id": "...",
  "shop_id": "...",
  "price": "...",
  "total": "...",
  "customer_id": "..."
}
```

as authoritative data.

---

# 10. IMPORTANT: GLOBAL ORDER VS SELLER ORDER STATUS

Before implementing status changes, inspect the current Master Prompt and Task 11 implementation carefully.

The existing Order has a single global status.

Therefore, do NOT invent a separate seller-specific status field unless the Master Prompt explicitly requires it.

Do NOT create:

```text
SellerOrderStatus
```

or duplicate the entire Order state machine without explicit architectural justification.

If the current architecture requires seller-level fulfillment status in the future, leave that for a separately scoped task unless it is explicitly required by the Master Prompt.

For Task 12, integrate seller operations with the existing Order state machine safely.

---

# 11. STATUS TRANSITION AUTHORIZATION

A seller must not be able to arbitrarily change status.

Use the existing:

```text
Order.can_transition_to()
Order.transition_to()
```

or the appropriate existing service abstraction.

For example:

```text
PENDING → CONFIRMED
CONFIRMED → PROCESSING
PROCESSING → SHIPPED
SHIPPED → DELIVERED
```

Invalid transitions must fail.

Terminal states must remain terminal.

Do not allow:

```text
DELIVERED → PROCESSING
CANCELLED → CONFIRMED
SHIPPED → PENDING
```

unless the existing Master Prompt explicitly defines such transitions.

---

# 12. MULTI-SELLER STATUS SAFETY

This is another critical architectural issue.

Before allowing a seller to transition the global Order status, determine whether the current Order model/state machine permits a seller to change the status of an entire customer order when the order contains products belonging to multiple sellers.

Do not silently implement unsafe behavior.

If a global Order status transition is semantically valid for seller operations under the Master Prompt, implement it with strict seller authorization.

If the architecture cannot safely represent independent seller fulfillment progress, document that limitation clearly in the final report and do not invent a second state machine outside Task 12 scope.

---

# 13. SELLER OWNERSHIP SECURITY

Every seller API must enforce server-side ownership.

Examples:

Seller A requests Seller B's order:

```text
HTTP 404
```

or the project's established safe ownership response.

Do not return:

```text
HTTP 200
```

with hidden fields after exposing the existence of an unauthorized resource unless the existing security architecture explicitly requires that behavior.

Do not allow:

```text
?shop_id=B
?seller_id=B
?user_id=B
```

to bypass ownership.

---

# 14. RBAC

Audit the existing RBAC system first.

Add only the minimum required seller order permissions.

Potential permissions:

```text
orders.seller.view
orders.seller.update
```

Use the project's existing naming conventions if different.

Permissions must be seeded consistently with the existing RBAC seed system.

Determine which seller roles should receive them based on the Master Prompt and existing seller-role architecture.

Do not grant seller permissions to unrelated customer roles.

Administrator/support access should follow the existing project authorization model.

---

# 15. SELLER STATUS REQUIREMENTS

Verify seller operational status before allowing seller order management.

Respect the existing lifecycle:

```text
PENDING
UNDER_REVIEW
APPROVED
ACTIVE
SUSPENDED
REJECTED
```

A suspended/rejected/non-operational seller must not be able to perform seller order-management actions if the Master Prompt prohibits it.

Do not duplicate seller status logic in multiple places.

Reuse existing seller/service permission logic where possible.

---

# 16. SHOP OWNERSHIP

Respect existing Task 5/7 rules:

```text
SellerProfile
    ↓
Shop
    ↓
Product
```

Do not permit a seller to manage an OrderItem merely because the product name or shop name matches.

Use actual database relationships.

Historical snapshots are for historical display/audit purposes, not authorization.

---

# 17. ORDER IMMUTABILITY

Seller order management must NOT allow modification of historical financial/order data.

Seller APIs must not allow sellers to modify:

* order number
* product name snapshot
* product slug snapshot
* shop snapshot
* seller snapshot
* unit price
* line total
* quantity
* shipping address snapshot
* order totals
* order owner

Task 12 is an order-management task, not an order-editing task.

---

# 18. AUDIT LOGGING

All seller-initiated status changes must create immutable AuditLog records.

Audit data should capture at minimum:

* actor/user
* action
* order
* seller
* previous status
* new status
* timestamp
* relevant metadata

Use the existing `AuditService`.

Do not create a parallel audit system.

---

# 19. CONCURRENCY

Seller status transitions must remain concurrency-safe.

If two requests attempt to change the same Order simultaneously:

* lock the Order row
* re-read the current status
* validate the transition against the current database state
* perform one valid transition
* reject the stale/invalid second transition safely
* create audit records consistently

Reuse the locking pattern established in Task 11.

---

# 20. API SERIALIZATION

Seller serializers must not accidentally expose:

* unrelated OrderItems
* customer internal fields
* authentication data
* another seller's shop
* another seller's seller profile
* internal database-only fields

Write explicit seller-facing serializers instead of blindly serializing the entire Order model.

---

# 21. PERFORMANCE

Seller order queries should use appropriate:

```text
select_related()
prefetch_related()
```

and filtering at the database level.

Avoid:

```text
fetch all orders
→ Python filter seller items
```

Prefer database-side filtering.

Test query behavior where practical.

---

# 22. FRONTEND

Frontend work is NOT a focus of Task 12.

Only make minimal changes if required for API/type compatibility.

Allowed:

* TypeScript Order/SellerOrder types
* API client methods

Not required:

* seller dashboard
* seller order page
* seller UI
* styling
* responsive UI work

The dedicated frontend phase will come later.

---

# 23. TEST REQUIREMENTS

Create comprehensive backend tests.

At minimum cover:

### Authentication

* anonymous seller endpoint rejected
* authenticated customer cannot use seller endpoint

### Seller isolation

* Seller A sees own order items
* Seller B sees own order items
* Seller A cannot access Seller B's order-only data
* seller query parameters cannot bypass isolation

### Multi-seller orders

Create one Order containing products from multiple sellers.

Verify:

```text
Seller A → only A items
Seller B → only B items
```

### Seller lifecycle

Test behavior for:

* APPROVED
* ACTIVE
* SUSPENDED
* REJECTED
* other relevant non-operational states

### Status transitions

Test:

```text
PENDING → CONFIRMED
CONFIRMED → PROCESSING
PROCESSING → SHIPPED
SHIPPED → DELIVERED
```

and invalid transitions.

### Terminal states

Verify:

```text
DELIVERED
CANCELLED
```

cannot be changed.

### Historical integrity

Verify sellers cannot modify:

* prices
* quantities
* snapshots
* shipping address
* totals
* order number

### Audit

Verify every successful seller status transition creates the correct audit record.

### Concurrency

Test concurrent seller status changes where practical.

### RBAC

Verify:

* authorized seller
* unauthorized customer
* unauthorized seller
* administrator/support behavior according to existing rules

### Regression

Run the entire existing backend suite from Tasks 1–11.

No previous functionality may regress.

---

# 24. DATABASE

Use MySQL 8+ only.

Do not introduce:

* PostgreSQL-only features
* PostGIS
* GeoDjango
* SQLite-specific behavior

If migrations are required:

```bash
python manage.py makemigrations
python manage.py migrate
```

Verify migration consistency afterward.

---

# 25. VERIFICATION REQUIREMENTS

Before declaring Task 12 complete:

### Django

```bash
python manage.py check --database default
```

### Migration consistency

```bash
python manage.py showmigrations
python manage.py makemigrations --check --dry-run
```

### Task-specific tests

Run all Task 12 tests.

### Full regression

Run the complete backend test suite from Tasks 1–12.

### Frontend

If frontend files were touched:

```bash
npm run build
```

The build must complete successfully.

### API smoke testing

Test at least:

* seller authentication
* seller order list
* seller order detail
* seller isolation
* seller status transition
* invalid status transition
* unauthorized access

### Git

Create a dedicated commit for Task 12.

Verify:

```bash
git status
git log -1 --oneline
```

The working tree should be clean unless there is a clearly documented reason.

---

# 26. FINAL REPORT

When finished, report:

1. Files changed
2. Models changed
3. Services changed
4. APIs added/changed
5. RBAC permissions added
6. Seller authorization rules
7. Multi-seller behavior
8. Status transition behavior
9. Audit behavior
10. Tests added
11. Full regression count
12. Migration status
13. Django system check result
14. Frontend build result if applicable
15. API smoke-test results
16. Git commit hash
17. `git status`
18. Any warnings, limitations, or architectural concerns

Do not claim success without actual verification.

---

# 27. STOP CONDITION

After Task 12 is implemented, tested, verified, and committed:

**STOP.**

Do not implement Task 13.

Do not implement inventory.

Do not implement refunds.

Do not implement reviews.

Do not implement notifications.

Do not implement frontend UI.

Wait for the next explicit task instruction.

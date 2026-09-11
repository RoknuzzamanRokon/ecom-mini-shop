# Task 16 — Admin & Staff Order Operations

Using the **MiniShop Master Prompt**, existing project files, and all completed Tasks 1–15, implement **only Task 16**.

Do NOT implement Task 17 or any later task.

Before coding, read:

* the complete MiniShop Master Prompt;
* existing Order and OrderItem models;
* Order state machine;
* customer order/cancellation flow;
* seller order management;
* inventory reservation/release/finalization;
* Payment/Refund architecture;
* RBAC;
* AuditLog.

## Objective

Implement a secure staff/admin operational layer for managing orders across the existing single-order, multi-seller architecture.

The implementation must reuse existing services and state machines rather than creating parallel business logic.

## 1. Staff Order Listing

Create staff-authorized order listing.

Requirements:

* paginated;
* searchable by order number;
* filterable by Order status;
* filterable by payment status;
* filterable by seller/shop where appropriate;
* filterable by date range where practical;
* newest orders first by default;
* efficient queryset using `select_related`/`prefetch_related`;
* no N+1 query behavior.

Staff must be able to see operationally necessary order information, but sensitive customer credentials/payment secrets must never be exposed.

## 2. Staff Order Detail

Create a staff order detail endpoint.

It should expose:

* order number;
* customer identity information appropriate for operations;
* shipping snapshot;
* order items;
* product/shop/seller information;
* quantities;
* historical prices;
* totals;
* payment summary;
* refund summary;
* current Order status;
* allowed next lifecycle actions.

Do not expose:

* passwords;
* authentication tokens;
* raw payment credentials;
* card numbers/CVV;
* provider secrets;
* unnecessary internal metadata.

Historical Order/OrderItem snapshots must remain authoritative.

## 3. Staff Order Status Management

Implement a dedicated staff status-transition action.

Example:

```text
PATCH /api/staff/orders/<order_number>/status/
```

The endpoint must NOT allow arbitrary status assignment.

It must use the existing:

```text
OrderService.transition_order_status()
```

and therefore preserve the existing state machine.

Allowed transitions must be centrally validated.

Staff permissions must determine who can perform the transition.

Do not create a second Order status machine.

## 4. Inventory Integration

Status transitions must continue using the existing inventory architecture.

Especially:

### Cancellation

When staff cancels an eligible order:

* Order becomes CANCELLED;
* reserved inventory is released;
* InventoryTransaction RELEASE is created;
* payment cancellation/refund behavior from Task 15 executes;
* AuditLog is created;
* all operations occur atomically.

### Delivery

When an order reaches DELIVERED:

* reserved inventory is finalized;
* available/reserved/sold quantities remain consistent;
* InventoryTransaction SALE is created;
* operation is idempotent.

Do not duplicate inventory logic in the staff API.

## 5. Payment Integration

Staff order operations must integrate with the existing PaymentService.

Do not allow staff order-status operations to:

* manually modify payment amounts;
* bypass payment/refund validation;
* create duplicate refunds;
* directly manipulate payment records outside PaymentService.

Payment-related actions must remain inside the existing payment service.

## 6. Multi-Seller Orders

A multi-seller Order remains exactly one Order.

Staff must see all relevant OrderItems.

Staff global Order status changes must work consistently for the complete Order.

Do not split an order into separate seller orders.

Seller-specific restrictions from Task 12 must remain intact.

## 7. RBAC

Add/seed appropriate staff permissions, following the existing permission architecture.

At minimum:

```text
orders.staff.view
orders.staff.update
```

Use permission-based authorization rather than hard-coded role checks.

Existing administrator/operation/support/sales permissions must continue working according to the Master Prompt.

Customers must not gain access to staff endpoints.

Sellers must not gain staff-wide order access merely because they have seller order permissions.

## 8. Customer Privacy & Security

Implement strict authorization.

Verify:

* anonymous → 401;
* customer → denied staff API;
* seller → denied staff-wide API unless explicitly authorized by an existing permission;
* authorized staff → allowed;
* unauthorized staff role → 403.

Do not leak whether a protected order exists when authorization should fail.

## 9. Audit Logging

Every staff operational state change must create an immutable AuditLog.

Record at minimum:

* actor;
* action;
* target order;
* old status;
* new status;
* reason if supplied;
* timestamp;
* request IP when available.

Do not store sensitive credentials in audit metadata.

## 10. Concurrency & Idempotency

Staff order operations must be concurrency-safe.

Use the existing row-locking/service architecture.

Test scenarios such as:

* two simultaneous cancellation attempts;
* two simultaneous status transitions;
* cancellation racing with another lifecycle transition;
* cancellation racing with refund/payment processing;
* delivery transition repeated twice.

The database and service layer must prevent inconsistent inventory/payment state.

## 11. API Design

Add only the APIs required for staff operations.

Suggested minimum:

```text
GET   /api/staff/orders/
GET   /api/staff/orders/<order_number>/
PATCH /api/staff/orders/<order_number>/status/
```

Do not add arbitrary CRUD endpoints for Orders.

Do not allow staff clients to directly edit:

* order totals;
* historical prices;
* shipping snapshots;
* order number;
* order items.

## 12. Frontend

Keep frontend work minimal.

Add only:

* staff order TypeScript types;
* staff order API client functions;
* any necessary response typing.

Do NOT build a complete admin dashboard or UI in this task.

## 13. Tests

Create focused Task 16 tests covering:

### Authorization

* anonymous 401;
* customer denied;
* seller denied;
* authorized staff allowed;
* unauthorized staff 403.

### Listing/detail

* pagination;
* status filters;
* search;
* payment filters if implemented;
* staff detail;
* customer privacy;
* multi-seller visibility.

### Lifecycle

* valid staff transition;
* invalid transition;
* arbitrary status injection rejected;
* cancellation;
* delivery;
* terminal-state protection.

### Inventory

* cancellation releases reservations;
* delivery finalizes reservations;
* idempotent inventory movement;
* multi-seller inventory correctness.

### Payment

* cancellation integrates with PaymentService;
* automatic refund behavior remains correct;
* no duplicate refund/payment operation.

### Security

* financial fields cannot be modified through status endpoint;
* snapshots cannot be modified;
* ownership boundaries remain intact.

### Audit

* staff lifecycle action creates AuditLog;
* actor/status/reason are correct.

### Concurrency

* concurrent status operations remain consistent.

## 14. Regression

Run the complete backend regression suite for Tasks 1–16.

Do not report Task 16 as complete based only on targeted tests.

## 15. Verification

Run:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py showmigrations
```

Also run:

* targeted Task 16 tests;
* full backend regression;
* frontend build if frontend files changed;
* relevant live API smoke tests.

Verify:

* zero unapplied migrations;
* no unexpected migrations;
* RBAC seed is correct;
* customer/seller isolation remains intact;
* inventory remains consistent;
* payment/refund integration remains consistent;
* AuditLog entries are created;
* working tree is clean.

## 16. Git

Only commit after all verification succeeds.

Use:

```text
feat(orders): implement staff order operations (Task 16)
```

## Final Report

Return a concise walkthrough containing:

1. files changed;
2. staff APIs;
3. RBAC permissions;
4. order state-machine integration;
5. inventory integration;
6. payment/refund integration;
7. privacy/security behavior;
8. audit behavior;
9. concurrency/idempotency behavior;
10. targeted test count/result;
11. full regression test count/result;
12. Django check result;
13. migration result;
14. frontend build result if applicable;
15. live smoke-test result;
16. exact commit hash;
17. clean working-tree confirmation;
18. warnings/limitations.

**STOP after Task 16. Do not implement Task 17 or any later task.**

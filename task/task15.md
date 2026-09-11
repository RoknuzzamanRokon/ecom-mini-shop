# Task 15 — Payment & Refund Management

Using the **MiniShop Master Prompt**, the existing project files, and all completed Tasks 1–14, implement **only Task 15**.

Do NOT start any later task.

Before coding:

1. Read the complete MiniShop Master Prompt.
2. Read the existing backend architecture and relevant previous implementations.
3. Review the existing `Order`, `OrderItem`, order state machine, inventory reservation/release logic, RBAC, AuditLog, and customer cancellation flow.
4. Preserve all existing behavior unless this task explicitly requires a change.

## Objective

Implement a production-safe payment/refund foundation for MiniShop that integrates with the existing Order lifecycle without breaking the current inventory and cancellation architecture.

### 1. Payment Domain

Create a proper payment model associated with an Order.

Requirements:

* One Order may have one current/primary payment record unless the Master Prompt explicitly requires multiple payment attempts.
* Payment must reference the Order.
* Store:

  * payment status
  * payment method
  * amount
  * currency
  * provider/reference identifier where applicable
  * timestamps
* Payment amount must be server-authoritative.
* Never trust a client-supplied payment amount.
* Payment records must preserve historical information.
* Use appropriate database constraints and indexes.
* Do not store raw card numbers, CVV, passwords, or other payment credentials.

Use explicit payment states, for example:

* PENDING
* PROCESSING
* PAID
* FAILED
* CANCELLED
* REFUNDED
* PARTIALLY_REFUNDED

Do not invent unnecessary states if the existing Master Prompt defines the authoritative set.

### 2. Payment Service

Create a dedicated service layer for payment operations.

The service must:

* calculate the authoritative payable amount from the Order;
* create/initiate a payment;
* safely record payment success/failure;
* prevent duplicate successful payment processing;
* use transactions and row-level locking where required;
* validate Order ownership/authorization;
* prevent payment amount tampering;
* preserve payment history.

Do not put business-critical payment logic directly inside API views.

### 3. Order Integration

Integrate payment status with the existing Order lifecycle carefully.

Important:

* Do NOT replace the existing Order state machine.
* Do NOT create a second competing Order lifecycle.
* Do NOT automatically introduce payment requirements into existing flows unless the Master Prompt explicitly requires it.
* Preserve the current cancellation and inventory-release behavior.
* A payment operation must not accidentally alter inventory.
* Order cancellation must remain compatible with the payment/refund architecture.

If payment success is required before a specific Order transition, enforce that rule centrally through the existing service/state-machine architecture.

### 4. Refund Foundation

Implement refund handling for eligible paid orders.

Requirements:

* Refund must be server-authoritative.
* Refund amount cannot exceed the refundable amount.
* Prevent duplicate refunds.
* Support full refund.
* Support partial refund only if the Master Prompt requires it.
* Refund records must be immutable/historically traceable.
* Refund processing must integrate safely with Order and Payment state.
* Customer cancellation/refund behavior must not create duplicate financial records.

Do not implement a real external payment gateway unless the Master Prompt explicitly requires a specific provider in this task.

If no provider is specified, create a clean provider-agnostic payment/refund abstraction that can be connected later.

### 5. Customer APIs

Add authenticated customer payment/refund APIs only where required by the Master Prompt.

Customers must:

* access payment information only for their own Orders;
* never access another customer's payment data;
* never directly modify payment status;
* never submit an arbitrary paid amount;
* never directly mark an Order as paid;
* never directly create a successful refund.

Use safe `404` behavior where appropriate to preserve the existing ownership-isolation pattern.

### 6. Administrative / Staff Operations

Add appropriate RBAC permissions for authorized staff/payment operations.

Follow the existing RBAC architecture.

Do not introduce hard-coded role checks where an existing permission-based mechanism should be used.

Staff operations must be auditable.

At minimum, distinguish appropriate permissions for:

* viewing payment information;
* processing/updating payment state;
* processing refunds.

Use the existing permission seeding architecture.

### 7. Audit Logging

All important financial state changes must create immutable AuditLog records.

Audit at minimum:

* payment creation;
* payment success;
* payment failure;
* payment cancellation;
* refund creation;
* refund completion/failure;
* administrative payment/refund actions.

Do not log sensitive payment credentials.

### 8. Concurrency & Idempotency

This is a critical requirement.

Protect against:

* duplicate payment success callbacks;
* duplicate refund requests;
* concurrent refund attempts;
* concurrent payment state updates;
* payment/order state races.

Use:

* `transaction.atomic()`;
* `select_for_update()`;
* database constraints;
* idempotency checks;

where appropriate.

The same successful payment/refund operation must never be applied twice.

### 9. Security

Strictly enforce:

* authenticated access;
* customer ownership isolation;
* RBAC for staff operations;
* server-authoritative amounts;
* no client-controlled financial totals;
* no sensitive payment credential storage;
* safe error responses;
* immutable financial history.

Do not expose internal payment-provider secrets or credentials through APIs.

### 10. Frontend

Keep frontend work minimal.

Only add:

* payment/refund TypeScript types;
* required API-client functions;
* required response handling.

Do NOT build a complete payment UI, checkout redesign, payment gateway UI, or dashboard unless explicitly required by the Master Prompt.

### 11. Backward Compatibility

All existing Tasks 1–14 behavior must continue working.

Pay particular attention to:

* Customer Order Management;
* Seller Order Management;
* Order state transitions;
* inventory reservation;
* inventory release on cancellation;
* delivery inventory finalization;
* customer ownership isolation;
* seller ownership isolation;
* AuditLog;
* RBAC.

Do not duplicate existing Order, Inventory, or Audit business logic.

### 12. Tests

Create focused Task 15 tests covering at minimum:

* payment creation;
* server-authoritative payment amount;
* customer ownership isolation;
* unauthorized payment mutation;
* successful payment;
* failed payment;
* duplicate payment-success protection;
* invalid payment transitions;
* full refund;
* refund amount validation;
* duplicate refund protection;
* concurrent refund/payment safety;
* cancellation/payment interaction;
* audit logging;
* RBAC;
* historical payment/refund integrity.

Also run the **full backend regression suite** for Tasks 1–15.

### 13. Verification

Before reporting completion:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py showmigrations
```

Run:

* targeted Task 15 tests;
* full backend regression tests;
* frontend build if frontend files were modified;
* relevant live API smoke tests.

Verify:

* migrations are applied;
* no unexpected migration changes remain;
* database constraints work;
* ownership isolation works;
* payment/refund operations are idempotent;
* working tree is clean.

### 14. Git

Create a commit only after all verification passes.

Commit message:

```text
feat(payments): implement payment and refund management (Task 15)
```

## Final Report

Return a concise walkthrough containing:

1. files changed;
2. models and migrations;
3. payment/refund state machines;
4. service-layer behavior;
5. API endpoints;
6. RBAC permissions;
7. audit behavior;
8. concurrency/idempotency protection;
9. targeted test count/result;
10. full regression test count/result;
11. Django check result;
12. migration verification;
13. frontend build result if applicable;
14. live smoke-test results;
15. exact commit hash;
16. confirmation that the working tree is clean;
17. any warnings or limitations.

**STOP after Task 15. Do not implement Task 16 or any later roadmap task.**

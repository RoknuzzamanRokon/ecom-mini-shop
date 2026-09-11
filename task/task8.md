# MiniShop — Task 8: Customer Profile & Address Foundation

## Context

The MiniShop backend has now completed Tasks 1–7.

Current architecture includes:

* Django 5.2 + Django REST Framework
* MySQL 8+
* JWT authentication via SimpleJWT
* RBAC system
* SellerProfile and seller lifecycle
* SellerWallet + immutable PointTransaction ledger
* Shop ownership and lifecycle
* MySQL native POINT location support
* Product → Shop → Seller ownership hierarchy
* Product creation with configurable point cost
* Unified AuditLog
* Product seller APIs
* Next.js frontend

The existing ownership hierarchy is:

Product → Shop → SellerProfile → User

Do not break this hierarchy.

---

# Objective

Implement the **Customer/User Profile and Address foundation** required before building customer carts and orders.

Do NOT implement cart or order functionality in this task.

---

# 1. Architecture Audit First

Before coding:

1. Read the MiniShop Master Prompt completely.
2. Inspect the current backend and frontend.
3. Inspect:

   * User model
   * authentication
   * JWT
   * RBAC
   * SellerProfile
   * Shop
   * Product
   * AuditLog
4. Determine whether an existing profile/address implementation already exists.
5. Reuse existing architecture where appropriate.
6. Do not create duplicate models or duplicate authentication logic.

Do not implement new features before completing this audit.

---

# 2. Customer Profile

Create a proper customer profile layer without replacing the existing Django User model unless the Master Prompt explicitly requires it.

Customer profile should support at minimum:

* user
* display/name information
* phone/contact information where appropriate
* avatar/profile image reference if existing project conventions support it
* created_at
* updated_at

Use appropriate constraints and relationships.

A user may also be a seller.

Do NOT assume:

User = Customer only.

The same authenticated User must be able to participate in seller and customer flows according to RBAC.

---

# 3. Address Model

Create a reusable customer address model.

Minimum conceptual fields:

* user
* label/name
* recipient_name
* phone
* address_line_1
* address_line_2
* area/locality
* city
* state/division where applicable
* postal_code
* country
* latitude/longitude only if justified by the Master Prompt/current architecture
* is_default
* created_at
* updated_at

Use appropriate validation.

Do not add unnecessary geospatial functionality.

The existing Shop.location POINT implementation is for shops and must not be duplicated unnecessarily for customer addresses unless the Master Prompt explicitly requires it.

---

# 4. Address Ownership & Security

A customer must only be able to:

* list own addresses
* view own address
* create own address
* update own address
* delete own address
* change own default address

A user must never be able to access another user's address by changing an ID in the URL.

Use proper DRF queryset/object-level authorization.

Do not rely only on frontend filtering.

---

# 5. Default Address Rules

Implement deterministic default-address behavior.

Rules:

* A user may have zero or one default address.
* Setting an address as default must unset the previous default.
* Creating the first address may make it default if appropriate.
* Deleting the default address must leave the account in a valid state.
* Concurrent default-address updates must not result in multiple defaults where database constraints/transactions can prevent it.

Use database transactions where required.

---

# 6. RBAC

Integrate with the existing RBAC architecture.

Do not invent a parallel permission system.

Add only the permissions actually required, for example:

* profile.view
* profile.update
* address.view
* address.create
* address.update
* address.delete

Use the project's existing naming convention if different.

Seed permissions through the existing RBAC seed mechanism.

Do not hardcode role IDs.

---

# 7. API

Implement authenticated APIs for:

## Profile

GET:

`/api/profile/me/`

PATCH:

`/api/profile/me/`

## Addresses

GET:

`/api/addresses/`

POST:

`/api/addresses/`

GET:

`/api/addresses/<id>/`

PATCH:

`/api/addresses/<id>/`

DELETE:

`/api/addresses/<id>/`

Use serializers and service/queryset patterns consistent with the existing project.

Do not expose unnecessary user fields.

---

# 8. Audit Logging

Use the existing unified AuditLog/AuditService.

Audit important mutations:

* profile update
* address creation
* address update
* address deletion
* default-address changes where appropriate

Do not create another audit system.

---

# 9. Tests

Add comprehensive backend tests covering:

### Profile

* authenticated profile retrieval
* profile update
* unauthenticated access
* unauthorized access
* user isolation

### Addresses

* create
* list
* retrieve
* update
* delete
* user isolation
* invalid data
* first/default address behavior
* switching default
* deleting default
* multiple users
* concurrent/default consistency where practical

### RBAC

* permission denied
* permission granted

### Regression

Run all existing tests from Tasks 1–7.

No existing functionality may regress.

---

# 10. Frontend

Only implement the minimum frontend support required for the new APIs.

Add/update:

* types
* API client helpers
* profile/address data access

Do not build the complete customer account UI yet.

---

# 11. Database

Create migrations.

Verify:

* constraints
* indexes
* foreign keys
* uniqueness
* default-address integrity

Use MySQL-compatible migrations.

Do not reintroduce SQLite.

---

# 12. Verification

Before declaring completion:

* Django system check
* migrations
* Task 8 tests
* complete backend regression suite
* frontend build
* API smoke test

Report exact results.

---

# 13. Git

Create a dedicated commit for Task 8.

Report:

* commit hash
* git status / clean working tree

---

# STOP CONDITION

Implement ONLY Task 8.

Do NOT implement:

* cart
* checkout
* order
* payment
* refund
* notification
* customer frontend shopping flow

Stop after Task 8 verification and report.

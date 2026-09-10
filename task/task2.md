Task 2 — Implement Authentication & RBAC Foundation

Task 1 architecture audit is complete. Now implement ONLY the authentication and RBAC foundation described below.

Before making changes:

* Read the MiniShop Master Prompt again.
* Review the Task 1 architecture audit.
* Inspect the current backend implementation and existing migrations.
* Preserve working functionality wherever possible.

## Scope

Implement the foundation for:

* User authentication
* Role management
* Permission management
* User → Role relationship
* Role → Permission relationship
* DRF permission enforcement
* Object-level authorization foundation
* Initial RBAC seed data
* Automated RBAC tests

Do NOT implement Seller, Shop, Points, Product Approval, Orders/Finance/Support workflows, or other future domain features.

## 1. Existing Authentication

* Preserve the existing Django authentication system where practical.
* Do not replace the existing User model unnecessarily.
* The Task 1 audit found that the project currently uses Django's default `django.contrib.auth.models.User`.
* If a custom User model is truly necessary, explain the migration impact before making the change.
* Avoid destructive changes to existing user data.

## 2. JWT Authentication

Implement JWT authentication for the DRF API using a stable Django REST Framework JWT solution such as `djangorestframework-simplejwt`.

Configure:

* JWT authentication class
* Access token
* Refresh token
* Token obtain endpoint
* Token refresh endpoint

Use a clean API structure, preferably:

/api/auth/token/
/api/auth/token/refresh/

Do not break Django Admin session authentication.

## 3. Role Model

Create a Role model representing staff roles.

Required roles:

SUPER_ADMINISTRATOR
ADMINISTRATOR
OPERATION_MANAGER
SALES_MANAGER
SALES_TEAM
FINANCE
SUPPORT_TEAM

Use stable machine-readable identifiers/codes rather than relying on display names.

Roles must be database-backed.

## 4. Permission Model

Create a granular Permission model.

Use the format:

<resource>.<action>

Examples:

users.view
users.create
users.update
users.delete

products.view
products.create
products.update
products.delete
products.approve
products.reject
products.publish

shops.view
shops.create
shops.update
shops.delete
shops.approve

sellers.view
sellers.create
sellers.update
sellers.suspend

orders.view
orders.create
orders.update
orders.cancel
orders.refund

payments.view
payments.verify
payments.refund

points.view
points.add
points.deduct

reports.view

Do not hardcode role names as the authorization mechanism.

## 5. Relationships

Implement:

User → Role
Role → Permission

Use proper database relationships and constraints.

A user may have one or more roles if that fits the architecture.

Avoid duplicating authorization logic in multiple places.

## 6. Permission Classes

Implement reusable DRF permission classes.

For example, create a permission mechanism capable of enforcing:

users.view
products.update
products.approve
orders.refund
etc.

Authorization must be based on database-backed permissions.

Do NOT write logic such as:

if user.role == "ADMIN":

as the primary authorization mechanism.

Instead, authorization should resolve the user's assigned roles and their permissions.

## 7. Super Administrator

SUPER_ADMINISTRATOR must have full permissions.

Prefer implementing this through the permission assignment/authorization architecture rather than scattering special-case role-name checks throughout views.

Django's existing superuser behavior must continue to work correctly.

## 8. Object-Level Authorization

Create the foundation for object-level authorization where ownership or object access matters.

Examples:

* A user should only modify objects they are authorized to access.
* Staff permissions should determine whether an action is allowed.
* Do not implement Seller/Shop ownership rules yet because those domains are not part of this task.

Keep the implementation reusable for later Seller, Shop, Product, Order, and other domains.

## 9. Seed Mechanism

Create a safe, repeatable seed mechanism for initial roles and permissions.

It must:

* Create missing permissions
* Create missing roles
* Assign permissions to the appropriate roles
* Be safe to run more than once
* Not create duplicates
* Not delete existing custom permissions or roles
* Not overwrite unrelated administrator configuration

Prefer a Django management command or an equivalent migration-safe mechanism.

Document how to run it.

## 10. Admin

Register the RBAC models in Django Admin where appropriate.

Administrators should be able to inspect/manage:

* Users
* Roles
* Permissions
* User-role assignments
* Role-permission assignments

Do not redesign the existing admin UI unless required for RBAC functionality.

## 11. Tests

Add automated backend tests covering at minimum:

### Authentication

* JWT token obtain works
* JWT refresh works
* Unauthenticated API requests are rejected where authentication is required

### Roles

* All seven required roles can be seeded
* Roles are not duplicated when seed runs multiple times

### Permissions

* Required permissions can be seeded
* Permissions are not duplicated
* Role-permission assignments work

### Authorization

* User with required permission is allowed
* User without required permission is denied
* Multiple roles combine permissions correctly
* SUPER_ADMINISTRATOR has full permissions
* Object-level permission checks behave correctly where implemented

### Regression

Run the existing test suite and ensure existing functionality remains intact.

## 12. Security

Follow these rules:

* Never trust frontend role/permission information.
* Backend is the source of truth for authorization.
* Do not expose sensitive authentication data.
* Do not disable CSRF/session protections for Django Admin.
* Do not use wildcard CORS with credentials.
* Do not introduce insecure token storage or authentication shortcuts.
* Do not bypass existing security controls simply to make tests pass.

## 13. Explicitly OUT OF SCOPE

Do NOT implement:

* Seller model/system
* Seller types
* Shop model/system
* Shop ownership
* Points/credits
* PointWallet
* PointTransaction
* Product approval workflow
* Product lifecycle
* Product seller/shop relationships
* Order workflow redesign
* Finance workflow
* Support workflow
* AuditLog system

Those belong to later tasks.

## 14. Verification

After implementation:

1. Run Django migrations.
2. Run the RBAC seed command.
3. Run the complete backend test suite.
4. Verify JWT endpoints.
5. Verify representative permission checks.
6. Verify Django Admin still works.
7. Verify existing public storefront APIs still work.
8. If frontend changes are required for authentication, make only the minimum necessary changes. Do not build the full customer/seller/admin frontend yet.

## 15. Final Report

At the end, report:

1. Files created
2. Files modified
3. Database migrations created
4. Models added
5. Authentication changes
6. Permission architecture
7. Seed command and usage
8. Test results
9. Any migration/security risks
10. Anything intentionally left for future tasks

IMPORTANT:

This is an implementation task, but it is ONLY the authentication + RBAC foundation.

Do not proceed into the next MiniShop domain phase automatically.

Stop after Task 2 verification and wait for the next instruction.

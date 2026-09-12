# MiniShop — Task 17 Final Verification & Hardening

You are working on the existing **MiniShop** project, a production-grade ecommerce system using:

* Django
* Django REST Framework
* MySQL
* JWT authentication
* RBAC
* Next.js frontend

## OBJECTIVE

Task 17 — **Admin & Platform Governance Management** has been implemented, but it must NOT be considered complete until this final verification and hardening pass succeeds.

Your job is to:

1. Audit the existing Task 17 implementation.
2. Identify violations of the Task 17 requirements.
3. Fix only Task 17-related problems.
4. Preserve Tasks 1–16 behavior.
5. Run the required regression/security tests.
6. Confirm the repository is clean.
7. Do NOT begin Task 18.

---

# 1. READ THE MASTER PROMPT FIRST

Before changing code:

* Read the MiniShop Master Prompt.
* Identify the exact requirements for Task 17.
* Do not invent requirements.
* Do not implement Task 18 or later.
* Compare the current implementation against the Master Prompt and existing architecture.

If the Master Prompt is available in the repository/project context, use that version as the source of truth.

---

# 2. AUDIT TASKS 1–16

Inspect the existing implementation of:

* User
* Authentication/JWT
* RBAC
* SellerProfile
* Seller lifecycle
* Seller types
* Shop
* Product
* Category
* CustomerProfile
* Addresses
* Cart
* Order
* OrderItem
* Inventory
* StockReservation
* Payment
* Refund
* Wallet
* PointTransaction
* AuditLog
* OrderService
* InventoryService
* PaymentService
* PointService
* AuditService
* Task 16 staff order APIs

Do not replace existing architecture.

Do not duplicate business logic.

---

# 3. VERIFY TASK 17 FILES

Audit all Task 17 changes, including:

* `backend/shop/admin_permissions.py`
* `backend/shop/permissions.py`
* `backend/shop/serializers.py`
* `backend/shop/api_views.py`
* `backend/shop/urls.py`
* `backend/rbac/management/commands/seed_rbac.py`
* Task 17 tests
* Any frontend type/API changes

Important:

Task 16 already used `backend/shop/api_views.py`.

If Task 17 incorrectly recreated/replaced an existing file instead of extending it, investigate this carefully and restore/preserve Task 16 behavior.

Do not blindly overwrite existing code.

---

# 4. ADMIN AUTHORIZATION AUDIT

Verify every admin endpoint.

Required behavior:

| Actor               | Expected                                          |
| ------------------- | ------------------------------------------------- |
| Anonymous           | 401                                               |
| Customer            | 403                                               |
| Seller              | 403 unless explicitly authorized by Master Prompt |
| Support             | Only explicitly permitted operations              |
| Finance             | Only explicitly permitted operations              |
| Operation Manager   | Only explicitly permitted operations              |
| Administrator       | Explicitly permitted admin operations             |
| Super Administrator | Highest permitted privileges                      |

Do not assume that being staff automatically grants every permission.

Use the existing RBAC architecture.

Use existing permission helpers such as:

`has_user_permission`

Do not create a second authorization system.

---

# 5. CRITICAL RBAC SECURITY AUDIT

This is mandatory.

Test whether an Administrator or Operation Manager can:

* create SUPER_ADMINISTRATOR
* assign SUPER_ADMINISTRATOR to a user
* assign Administrator to itself
* assign higher privileges to itself
* assign protected roles to another user
* modify protected roles
* delete protected roles
* modify permissions
* create arbitrary permissions
* bypass seeded RBAC restrictions
* remove restrictions from its own account
* escalate from Administrator → Super Administrator

These must be prevented unless the MiniShop Master Prompt explicitly requires them.

Also test:

* Can Finance modify RBAC?
* Can Support modify RBAC?
* Can ordinary users access RBAC?
* Can sellers access RBAC?
* Can an administrator delete a role currently assigned to users?

Do not allow privilege escalation.

---

# 6. USER ADMINISTRATION AUDIT

Inspect:

`AdminUserViewSet`

Verify that administration does NOT expose:

* password
* password hash
* JWT
* refresh token
* access token
* authentication secret
* API secret
* reset token
* sensitive security fields

Verify whether POST/PATCH/DELETE user operations are actually required by the Master Prompt.

If they are not required, remove unnecessary mutation endpoints.

If mutation is required:

* enforce strict authorization
* prevent privilege escalation
* prevent arbitrary authentication-field changes
* use proper validation
* use transactions
* audit mutations

Do not create a second User model.

---

# 7. ROLE MANAGEMENT AUDIT

Inspect:

`AdminRoleViewSet`

Verify:

* role listing works
* role inspection works
* role assignment follows RBAC policy
* protected roles cannot be abused
* permissions cannot be arbitrarily modified
* self-escalation is impossible
* deletion of roles assigned to users is safely prevented
* role changes are transactional
* role changes are audited

Do not redesign the existing RBAC system.

Preserve seeded roles and permissions.

---

# 8. SELLER ADMIN AUDIT

Inspect:

`AdminSellerViewSet`

Verify:

* list
* search
* filtering
* detail
* status/lifecycle management

Reuse the existing seller lifecycle.

Do NOT directly manipulate database fields if a SellerService/state-machine mechanism already exists.

Preserve:

* FULL_SHOP_OWNER
* LIMITED_SHOP_OWNER
* PRODUCT_OWNER

Verify that seller approval/rejection/suspension/reactivation:

* is authorized
* is transactional
* cannot corrupt ownership
* is audited
* cannot bypass business rules

---

# 9. SHOP ADMIN AUDIT

Inspect:

`AdminShopViewSet`

Verify:

* list
* search
* filtering
* detail
* lifecycle/status changes

Reuse existing Shop business logic.

Preserve:

* shop ownership
* seller relationship
* public visibility
* nearby-shop functionality
* spatial data integrity

Do not introduce duplicate shop lifecycle logic.

---

# 10. PRODUCT ADMIN AUDIT

Inspect:

`AdminProductViewSet`

This is a high-risk area.

Verify that admin operations do NOT bypass:

* ProductService
* seller ownership
* shop ownership
* category requirements
* product validation
* ProductCreationCost
* points logic
* publication rules
* approval rules
* stock/inventory rules

If POST/PATCH/DELETE exists, determine whether the Master Prompt actually requires it.

Do not allow generic admin CRUD to bypass domain services.

Particularly verify:

* Product creation cost
* wallet/points deduction
* seller ownership
* category validation
* shop validation
* publication lifecycle
* audit logging

If direct CRUD violates the architecture, refactor it to use the existing service layer.

---

# 11. CATEGORY ADMIN AUDIT

Inspect `AdminCategoryViewSet`.

Verify:

* list
* search
* create/update only if required
* activate/deactivate

Do NOT allow unsafe deletion of categories referenced by products.

Prefer:

`deactivate`

over:

`DELETE`

unless the Master Prompt explicitly requires deletion and the operation is safely protected.

Test referenced categories.

---

# 12. CUSTOMER ADMIN AUDIT

Inspect `AdminCustomerViewSet`.

Customer administration should be **read-only by default**.

Verify:

* profile
* contact information
* addresses
* account state
* order history where required

Never expose:

* password
* password hash
* JWT
* refresh token
* authentication secrets

Do not allow generic admin modification of:

* historical orders
* order totals
* order items
* payment records
* refunds
* inventory
* wallet balances
* point transactions

---

# 13. FINANCIAL DATA TAMPER PROTECTION

This is mandatory.

Verify that admin APIs cannot directly modify:

* Order total
* Order number
* OrderItem price snapshot
* OrderItem quantity/history
* Payment amount
* Payment status
* Refund amount
* Refund status
* Inventory quantity
* Inventory transaction history
* Wallet balance
* PointTransaction
* AuditLog

These must remain protected behind their domain services.

Use:

* OrderService
* InventoryService
* PaymentService
* PointService
* AuditService

where applicable.

---

# 14. AUDIT LOGGING

Every admin mutation must generate an audit event containing, where appropriate:

* actor
* action
* target
* previous state
* new state
* reason
* timestamp
* IP address

Never put secrets into audit metadata.

Verify that audit logging itself cannot be manipulated through generic admin CRUD.

---

# 15. CONCURRENCY

For state-changing operations verify:

```python
transaction.atomic()
```

and where required:

```python
select_for_update()
```

Test concurrent operations involving:

* seller status
* shop status
* product status
* user state
* role assignment
* role changes

Prevent race-condition privilege escalation and duplicate/corrupt mutations.

---

# 16. API DESIGN

Keep the existing namespace:

`/api/admin/`

unless the Master Prompt explicitly requires another namespace.

Verify pagination for list endpoints.

Verify:

* search
* filtering
* ordering where appropriate
* efficient querysets
* `select_related`
* `prefetch_related`

Avoid N+1 queries.

Use dedicated serializers with explicit fields.

Do not use unrestricted model serializers for sensitive models.

---

# 17. TASK 16 REGRESSION

Task 16 must continue working exactly as before.

Run the existing staff order tests.

Verify:

* staff order list
* staff order detail
* status transitions
* cancellation
* inventory behavior
* refund behavior
* audit behavior
* authorization

Do not break:

`/api/staff/orders/`

or its existing functionality.

---

# 18. TEST TASK 17 SECURITY

Expand/fix the Task 17 test suite as required.

At minimum test:

### Authorization

* anonymous → 401
* customer → 403
* seller → 403
* unauthorized staff → 403
* authorized staff → allowed
* administrator → allowed where appropriate
* super administrator → highest permitted access

### RBAC security

* privilege escalation blocked
* self-escalation blocked
* protected role modification blocked
* protected role deletion blocked
* unauthorized permission modification blocked

### Privacy

Verify response does not contain:

* password
* password hash
* JWT
* refresh token
* secret fields

### Financial protection

Verify admin cannot tamper with:

* orders
* order totals
* order item historical prices
* payments
* refunds
* inventory
* wallets
* points

### Lifecycle

Test:

* seller
* shop
* product
* category

status transitions.

### Audit

Verify all mutations create correct audit records.

### Pagination/search/filtering

Verify all required list APIs.

### Concurrency

Verify important state mutations are protected.

---

# 19. RUN TESTS

Do NOT claim full regression based only on:

```bash
manage.py test shop
```

Run the actual full backend test suite.

Preferred:

```bash
cd backend
venv/bin/python manage.py test --keepdb
```

If the project uses another documented full-suite command, use that instead.

Also run:

```bash
venv/bin/python manage.py check
```

```bash
venv/bin/python manage.py makemigrations --check --dry-run
```

```bash
venv/bin/python manage.py showmigrations
```

Run the RBAC seed command if appropriate:

```bash
venv/bin/python manage.py seed_rbac
```

Run dedicated Task 17 tests.

Run Task 16 regression tests.

If frontend files were modified, run the frontend build.

---

# 20. MIGRATION RULE

Do NOT create migrations unless genuinely required.

If no schema changes are required:

* keep migrations unchanged
* confirm `makemigrations --check --dry-run` passes

If a migration is genuinely required, explain exactly why before considering Task 17 complete.

---

# 21. FRONTEND

Do NOT build:

* admin dashboard
* admin UI
* full frontend
* Task 18 frontend

Only maintain frontend:

* API client
* TypeScript types

if necessary for Task 17 backend compatibility.

If frontend files are changed, run the production build.

---

# 22. CODE QUALITY

Review:

* imports
* circular dependencies
* duplicated logic
* permission duplication
* serializer overexposure
* N+1 queries
* transaction boundaries
* exception handling
* API consistency
* naming
* URL routing
* tests

Do not perform unrelated refactoring.

---

# 23. GIT VERIFICATION

After all fixes:

Run:

```bash
git status
```

Then:

```bash
git log -1 --oneline
```

The commit must use exactly:

```text
feat(admin): implement platform governance (Task 17)
```

Do NOT report `<commit-hash>` or any placeholder.

Return the actual commit hash.

The working tree must be clean.

---

# 24. FINAL ACCEPTANCE CRITERIA

Task 17 is complete only if ALL are true:

* Master Prompt requirements satisfied
* Tasks 1–16 preserved
* Task 16 staff order APIs still work
* Admin authorization is correct
* RBAC privilege escalation is impossible
* sensitive credentials are never exposed
* financial data cannot be directly tampered with
* domain services remain authoritative
* lifecycle state machines remain authoritative
* audit logging works
* concurrency protection works
* pagination works
* search/filtering works where required
* no unnecessary CRUD remains
* category deletion is safely controlled
* customer admin remains read-only unless explicitly required
* Task 17 tests pass
* full backend regression passes
* Django check passes
* migration check passes
* frontend build passes if applicable
* actual Git commit exists
* working tree is clean

---

# 25. IMPORTANT SCOPE RULE

**STOP after Task 17.**

Do NOT:

* implement Task 18
* implement payment enhancements
* implement analytics
* implement notifications
* build admin dashboard
* redesign frontend
* refactor unrelated architecture
* add speculative features
* create future-task APIs

Only fix and harden Task 17.

---

# 26. FINAL REPORT

After completing the work, provide:

1. Task 17 status
2. Files inspected
3. Files changed
4. Security issues found
5. Security issues fixed
6. RBAC verification results
7. User privacy verification
8. Seller administration verification
9. Shop administration verification
10. Product administration verification
11. Category administration verification
12. Customer administration verification
13. Financial tamper-protection verification
14. Audit verification
15. Concurrency verification
16. Task 16 regression result
17. Task 17 test count/result
18. Full backend regression count/result
19. Django check result
20. Migration check result
21. Frontend build result, if applicable
22. Migration status
23. Git commit hash
24. Git status
25. Any remaining warnings
26. Explicit confirmation:

**“Task 17 verified and hardened. No Task 18 work was performed.”**

Do not claim success for anything that was not actually executed and verified.

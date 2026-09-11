# MiniShop — Task 9: Public Product Catalog & Categories

## Context

Tasks 1–8 are complete.

Current product ownership:

Product → Shop → SellerProfile → User

Product creation already supports:

* seller ownership
* shop ownership
* seller eligibility
* RBAC
* configurable creation cost
* point deduction
* PointTransaction
* AuditLog
* atomic rollback

Task 9 must build the **public customer-facing product catalog foundation**.

Do not implement cart or order functionality.

---

# Objective

Implement a clean, secure public product catalog with category support and product discovery.

---

# 1. Audit First

Read the MiniShop Master Prompt and inspect:

* Product model
* Shop model
* SellerProfile
* existing product APIs
* existing frontend product pages
* RBAC
* audit system
* existing Product status fields

Do not duplicate existing Product functionality.

---

# 2. Product Categories

Introduce category support if not already present.

Category should support at minimum:

* name
* slug
* description where appropriate
* active/inactive state
* created_at
* updated_at

Use unique slugs.

If hierarchical categories are required by the Master Prompt, implement the hierarchy cleanly.

Do not over-engineer category functionality beyond the Master Prompt.

---

# 3. Product Public Visibility

Define one authoritative public visibility rule.

Only products satisfying the project's approved/publication rules may appear publicly.

Do not expose:

* rejected products
* unpublished products
* products belonging to inaccessible shops
* products belonging to suspended/rejected shops

Ensure Product → Shop → Seller visibility is respected.

Do not rely on frontend filtering.

---

# 4. Public Product API

Implement public APIs such as:

GET:

`/api/products/`

GET:

`/api/products/<id>/`

Support appropriate:

* pagination
* category filtering
* shop filtering
* search
* ordering/sorting

Use DRF's existing project conventions.

Do not expose seller-private fields.

---

# 5. Search

Implement a practical MySQL-compatible product search.

At minimum support product name/title search.

If description search is appropriate, include it.

Do not introduce Elasticsearch/OpenSearch or another search engine in this task.

---

# 6. Filtering

Support only meaningful filters, such as:

* category
* shop
* price range
* publication status internally
* availability if the existing Product model supports it

All public filtering must still enforce visibility.

---

# 7. Product Detail Security

Product detail must not become an object-level visibility bypass.

Test URLs for:

* public product
* draft product
* rejected product
* unpublished product
* product in suspended shop
* product in another private state

---

# 8. Seller APIs Regression

Existing seller product APIs must continue working:

* mine list
* mine detail
* create
* update
* delete

Public catalog filtering must not weaken seller isolation.

---

# 9. Category APIs

If categories are public:

GET:

`/api/categories/`

Only active categories should be publicly exposed.

Admin/staff management can be deferred unless already required by the Master Prompt.

---

# 10. Frontend

Update the Next.js frontend only as needed to consume:

* product list
* product detail
* categories
* filtering/search

Do not implement cart or checkout.

---

# 11. Tests

Test:

* public product visibility
* hidden product protection
* suspended shop protection
* category filtering
* search
* price filtering
* pagination
* ordering
* seller product regression
* category slug uniqueness
* inactive categories
* unauthenticated public access
* malformed query parameters

Run the entire existing regression suite.

---

# 12. Verification

Run:

* migrations
* Django system check
* Task 9 tests
* full backend regression
* frontend build
* API smoke tests

Report exact counts.

---

# 13. Git

Create a dedicated Task 9 commit.

Report:

* commit hash
* clean working tree

---

# STOP CONDITION

Implement ONLY Task 9.

Do NOT implement:

* cart
* checkout
* orders
* payments
* refunds

Stop after verification.

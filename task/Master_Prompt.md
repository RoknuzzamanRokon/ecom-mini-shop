You are a senior software architect and full-stack developer.

I am building a multi-vendor e-commerce platform called **MiniShop**.

The project has already been started.

### Current Technology Stack

Backend:

* Django
* Django REST Framework
* PostgreSQL
* PostGIS
* REST API
* JWT Authentication

Frontend:

* Next.js
* TypeScript

Do NOT rebuild the project from scratch.

First understand the existing project and then extend it step by step.

---

# 1. Main Goal

I want to turn my current MiniShop project into a fully functional, scalable and production-ready multi-vendor e-commerce platform.

The platform will have:

* Multiple staff roles
* Role-based permissions
* Multiple seller types
* Seller dashboards
* Shop management
* Product management
* Product approval workflow
* Point/credit system
* Customer accounts
* Guest checkout
* Order management
* Shop-based product browsing
* Location-based shop search
* Location-based product search
* Nearby shop/product discovery
* Payment and finance management
* Customer support
* Notifications
* Audit logs
* Reporting

The system should be designed so that more features can be added later without rewriting the core architecture.

---

# 2. Important Development Rule

Do NOT try to build the entire system at once.

The system must be developed **incrementally**.

For every task:

1. Analyze the existing project.
2. Understand the existing architecture.
3. Identify what already exists.
4. Reuse existing code where possible.
5. Design the required changes.
6. Implement only the current task.
7. Add required database migrations.
8. Add/update API endpoints.
9. Add frontend changes only when required.
10. Add tests.
11. Explain how to verify the implementation.

Do not implement future tasks unless they are required dependencies for the current task.

Do not unnecessarily rewrite existing functionality.

---

# 3. User Types

MiniShop will have three major user categories.

## A. Staff Users

The platform will have these staff roles:

1. Super Administrator
2. Administrator
3. Operation Manager
4. Sales Manager
5. Sales Team
6. Finance
7. Support Team

Each role will have different responsibilities and permissions.

---

# 4. Role and Permission System

Do NOT implement authorization only with hardcoded role checks such as:

```python
if user.role == "admin":
```

Instead, implement a proper RBAC system:

```text
User
  ↓
Role
  ↓
Permissions
```

Permissions should be granular.

For example:

```text
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
sellers.approve
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
```

Roles should be collections of permissions.

For example:

```text
Super Administrator
    → all permissions

Administrator
    → administrative permissions

Operation Manager
    → operation-related permissions

Sales Manager
    → sales and seller management permissions

Sales Team
    → assigned sales/product permissions

Finance
    → payment, transaction and payout permissions

Support Team
    → customer/order/support permissions
```

The exact permission mapping should be designed based on responsibilities.

---

# 5. Authorization Rules

A permission alone should not always be enough.

The backend must also check business rules.

For example:

```text
Authentication
      ↓
Permission
      ↓
User/Seller status
      ↓
Seller type
      ↓
Point balance
      ↓
Ownership
      ↓
Business rules
      ↓
Action allowed
```

The frontend may hide unauthorized buttons for better UX, but **frontend restrictions must never be considered security**.

Every sensitive action must be validated by the backend.

---

# 6. Seller System

MiniShop will support three types of sellers.

## Seller Type 1 — Full Shop Owner

A Full Shop Owner can:

* Create/manage their shop
* Add products
* Update products
* Manage their products
* View their orders
* Manage their shop information

## Seller Type 2 — Limited Shop Owner

A Limited Shop Owner has a shop but cannot necessarily upload/manage every type of product.

Their available product capabilities should be controlled by business rules and permissions.

## Seller Type 3 — Product Owner

A Product Owner can upload/manage products but does not necessarily own a complete shop.

The architecture must support sellers without forcing every seller type to have the same capabilities.

---

# 7. Seller Dashboard

Each seller should have a separate authenticated dashboard.

Example:

```text
Seller Dashboard

Overview
Products
Add Product
My Shop
Orders
Points
Point History
Profile
Notifications
Settings
```

The dashboard should only show features that the seller is authorized to use.

Example:

If a seller does not have enough points to create a product, the frontend should show the restriction clearly.

---

# 8. Point/Credit System

Product creation requires points.

For example:

```text
Product creation cost = 5 points
```

If a seller has:

```text
10 points
```

they can create a product.

If a seller has:

```text
3 points
```

they cannot create the product.

However, this must NOT be implemented as a simple hardcoded check inside the API view.

Create a proper point/credit system.

The system should maintain:

```text
Point Balance
Point Transactions
Transaction Type
Amount
Balance After Transaction
Reason
Reference
Created At
```

Example transactions:

```text
BONUS
ADMIN_CREDIT
ADMIN_DEBIT
PRODUCT_CREATION
REFUND
ADJUSTMENT
```

Never change a seller's balance without creating an auditable transaction.

Point deduction and product creation must be atomic.

If product creation fails, the point deduction must also be rolled back.

The required product creation cost should preferably be configurable.

---

# 9. Shop Feature

A new major feature will be called:

**Shop**

A seller can have a shop.

When a seller adds or updates a product, the product should be associated with the seller's shop when applicable.

Expected relationship:

```text
Seller
   ↓
Shop
   ↓
Products
```

A Shop should contain information such as:

```text
Shop
 ├── Owner
 ├── Name
 ├── Slug
 ├── Description
 ├── Logo
 ├── Cover Image
 ├── Phone
 ├── Address
 ├── Location
 ├── Status
 ├── Created At
 └── Updated At
```

---

# 10. Shop Public Page

Customers should be able to browse shops.

Example flow:

```text
Home
   ↓
Shop Category
   ↓
Shop List
   ↓
Click Shop
   ↓
Shop Details
   ↓
Shop Products
```

Example URL:

```text
/shops
/shops/[slug]
```

Shop page should show:

* Shop name
* Logo
* Cover image
* Description
* Address
* Location
* Contact information
* Products
* Product categories
* Shop status
* Distance from customer when location is available

---

# 11. Product and Shop Relationship

Products should be connected to the appropriate seller/shop.

Expected relationship:

```text
Product
   ↓
Shop
   ↓
Seller
```

This relationship must enforce ownership.

For example:

Seller A must NOT be able to assign a product to Seller B's shop.

Seller A must NOT be able to update Seller B's products unless explicitly authorized by a staff permission.

---

# 12. Product Workflow

Products should not necessarily become public immediately.

Use a product lifecycle such as:

```text
DRAFT
   ↓
SUBMITTED
   ↓
UNDER REVIEW
   ↓
APPROVED
   ↓
PUBLISHED
```

If rejected:

```text
REJECTED
   ↓
Seller edits product
   ↓
SUBMITTED again
```

Authorized staff should be able to:

* Review product
* Approve product
* Reject product
* Publish product
* Unpublish product

---

# 13. Seller Location

When a seller/shop adds or updates their product/shop information, location information should be supported.

Use:

```text
Latitude
Longitude
```

For shop-based products, preferably store the primary location at the Shop level:

```text
Product
   ↓
Shop
   ↓
Location
```

This avoids storing duplicate location data for every product.

If a specific product needs a different location, the architecture may support an optional product-level location.

---

# 14. Geographic Search

Use:

```text
PostgreSQL + PostGIS
```

for geographic search.

Customers should be able to provide/select:

```text
Latitude
Longitude
Radius
```

For example:

```text
Latitude: 23.8103
Longitude: 90.4125
Radius: 2 KM
```

The system should return shops within 2 kilometers.

Example API:

```text
GET /api/shops/nearby/?lat=23.8103&lng=90.4125&radius=2
```

The response should include:

```text
Shop
Distance
```

and results should be sorted by nearest distance.

---

# 15. Nearby Product Search

The same location system should later support nearby products.

Example:

```text
Customer Location
      ↓
Select Radius
      ↓
2 KM
      ↓
Nearby Shops
      +
Nearby Products
```

Customers should eventually be able to filter nearby results by:

* Category
* Product
* Shop
* Price
* Availability
* Distance

Design the API so these filters can be added without major restructuring.

---

# 16. Customer System

There will be two types of customers.

## A. Registered Customer

A registered customer can:

* Login
* Manage profile
* Manage addresses
* Browse products
* Browse shops
* Add products to cart
* Place orders
* View previous orders
* Track order status
* Manage wishlist
* Receive notifications

## B. Guest Customer

A guest user can:

* Browse products
* Browse shops
* Add products to cart
* Checkout
* Place an order without creating an account

Guest checkout should not require account registration.

Guest order information may include:

```text
Name
Phone
Email
Shipping Address
```

---

# 17. Order System

Order lifecycle should support states such as:

```text
PENDING
CONFIRMED
PROCESSING
PACKED
SHIPPED
OUT_FOR_DELIVERY
DELIVERED
CANCELLED
RETURNED
REFUNDED
```

Orders should contain:

```text
Customer
Guest Information (if applicable)
Order Items
Products
Shop
Shipping Address
Payment
Status
Status History
Created At
Updated At
```

Important order status changes should be recorded.

---

# 18. Staff Responsibilities

The system should be designed around clear responsibilities.

### Super Administrator

Responsible for:

* Complete system control
* User management
* Role management
* Permission management
* System settings
* Seller management
* Shop management
* Product management
* Order management
* Finance oversight
* Reports

### Administrator

Responsible for:

* General administration
* User management
* Seller management
* Product/shop management
* Operational administration

### Operation Manager

Responsible for:

* Product review
* Product approval
* Shop review
* Order operations
* Seller operations
* Fulfillment workflow

### Sales Manager

Responsible for:

* Seller management
* Sales team management
* Sales monitoring
* Seller performance
* Product/sales operations

### Sales Team

Responsible for:

* Seller assistance
* Product assistance
* Sales-related activities
* Assigned seller/product operations

### Finance

Responsible for:

* Payments
* Transactions
* Refunds
* Seller payouts
* Financial records
* Finance reports

### Support Team

Responsible for:

* Customer support
* Order issues
* Complaints
* Returns
* Support tickets

These responsibilities must be implemented through permissions and business rules rather than only role-name checks.

---

# 19. Audit Log

Important system actions must be auditable.

Create an audit system that can track:

```text
Who performed the action
What action was performed
Which object was affected
Old value
New value
Timestamp
IP address when appropriate
```

Examples:

```text
Admin approved seller
Sales Manager approved product
Finance verified payment
Admin added seller points
Seller created product
Support changed order status
```

This is especially important for:

* Points
* Orders
* Payments
* Seller status
* Product approval
* Shop approval
* User permissions

---

# 20. Security Requirements

The application must enforce:

* Authentication
* Role-based permissions
* Object-level permissions
* Seller ownership
* Staff permissions
* Point validation
* Input validation
* API security
* Rate limiting where appropriate
* Secure authentication
* Secure file uploads
* Proper error handling
* Database transaction safety

Never trust data sent by the frontend.

The backend must validate all important business rules.

---

# 21. Backend Architecture

Prefer a clean Django architecture.

For example:

```text
apps/
    users/
    authentication/
    sellers/
    shops/
    products/
    categories/
    cart/
    orders/
    payments/
    finance/
    points/
    support/
    notifications/
    audit/
```

Use appropriate separation between:

```text
Models
Serializers
Views/ViewSets
Permissions
Services
Selectors/Queries
Utilities
```

Complex business logic should preferably live in service/domain logic instead of becoming tightly coupled to API views.

---

# 22. Frontend Architecture

Use Next.js + TypeScript.

The frontend should have separate areas for:

```text
Public Store
Customer Account
Seller Dashboard
Staff/Admin Dashboard
```

Example:

```text
/
 /products
 /products/[slug]

 /shops
 /shops/[slug]

 /cart
 /checkout

 /login
 /register

 /account
 /account/orders
 /account/profile

 /seller
 /seller/products
 /seller/products/create
 /seller/shop
 /seller/orders
 /seller/points

 /admin
 /admin/users
 /admin/sellers
 /admin/shops
 /admin/products
 /admin/orders
 /admin/finance
 /admin/support
 /admin/reports
```

Actual route structure should be adapted to the existing project.

---

# 23. API Design

Use RESTful APIs.

Example:

```text
/api/auth/
/api/users/
/api/sellers/
/api/shops/
/api/products/
/api/categories/
/api/cart/
/api/orders/
/api/payments/
/api/points/
/api/support/
/api/notifications/
/api/reports/
```

Use:

* Proper HTTP methods
* Proper status codes
* Pagination
* Filtering
* Searching
* Ordering
* Validation
* Consistent error responses

---

# 24. Important Business Rule Example

Product creation should work approximately like this:

```text
Seller clicks "Add Product"
          ↓
Is user authenticated?
          ↓
Does user have products.create permission?
          ↓
Is seller active?
          ↓
Does seller type allow product creation?
          ↓
Is required shop information available?
          ↓
Does seller have enough points?
          ↓
Does selected shop belong to seller?
          ↓
Validate product
          ↓
Create product
          ↓
Deduct points
          ↓
Create point transaction
          ↓
Create audit log
          ↓
Return success
```

If any step fails:

```text
No product
+
No point deduction
```

---

# 25. Development Phases

Implement the project in the following order.

## Phase 1 — Foundation

1. Existing project architecture audit
2. Database architecture
3. Custom User/authentication review
4. JWT authentication
5. Base API structure
6. Error handling
7. Testing foundation

## Phase 2 — RBAC

8. Permission system
9. Role system
10. User-role relationship
11. Role-permission relationship
12. Permission classes
13. Staff role setup

## Phase 3 — Seller

14. Seller profile
15. Seller types
16. Seller status
17. Seller approval workflow
18. Seller dashboard

## Phase 4 — Points

19. Point wallet
20. Point transaction ledger
21. Credit/debit system
22. Point history
23. Point permissions
24. Product creation point requirement

## Phase 5 — Shop

25. Shop model
26. Shop ownership
27. Shop CRUD
28. Shop approval
29. Shop dashboard
30. Public shop page
31. Shop product listing

## Phase 6 — Location

32. PostGIS setup
33. Shop location
34. Location update
35. Nearby shop search
36. Radius search
37. Distance calculation
38. Nearby product search

## Phase 7 — Product

39. Product-Shop integration
40. Product-Seller ownership
41. Product approval
42. Product rejection
43. Product publishing
44. Inventory
45. Product search/filter

## Phase 8 — Customer

46. Customer profile
47. Customer addresses
48. Cart
49. Wishlist
50. Guest checkout
51. Registered checkout

## Phase 9 — Orders

52. Order creation
53. Order items
54. Order status
55. Order status history
56. Seller order management
57. Customer order tracking

## Phase 10 — Finance

58. Payment
59. Payment verification
60. Refund
61. Seller payout
62. Finance dashboard
63. Financial reports

## Phase 11 — Support

64. Support tickets
65. Customer complaints
66. Order issues
67. Return requests
68. Support dashboard

## Phase 12 — Notifications

69. In-app notifications
70. Email notifications
71. Order notifications
72. Seller notifications
73. Staff notifications

## Phase 13 — Audit & Reporting

74. Audit logs
75. Activity logs
76. Sales reports
77. Seller reports
78. Product reports
79. Shop performance
80. Finance reports

## Phase 14 — Production

81. Production settings
82. Docker
83. Media storage
84. Background tasks
85. Caching
86. Logging
87. Monitoring
88. API rate limiting
89. Security audit
90. Final testing

---

# 26. How You Must Work on Each Task

When I give you a task number, do NOT jump directly into random code.

Follow this exact process:

### Step 1 — Understand

Explain what this task means in the MiniShop architecture.

### Step 2 — Inspect Existing Code

Identify:

* Existing files
* Existing models
* Existing APIs
* Existing components
* Existing utilities

that are relevant.

### Step 3 — Architecture Decision

Explain what should be added or changed and why.

### Step 4 — Implementation

Provide production-quality code.

### Step 5 — Database

Provide migrations/model changes if required.

### Step 6 — API

Explain:

```text
Endpoint
Method
Authentication
Permission
Request
Response
Error cases
```

### Step 7 — Frontend

If required, implement the corresponding Next.js/TypeScript changes.

### Step 8 — Security

Explain:

* Authentication
* Permission
* Ownership
* Business-rule validation

### Step 9 — Tests

Add tests for:

* Success
* Invalid input
* Unauthorized user
* Permission failure
* Ownership violation
* Business-rule failure
* Important edge cases

### Step 10 — Verification

Give exact commands and steps to verify the task.

---

# 27. Critical Rule

Do not over-engineer unnecessarily.

Do not create unnecessary microservices.

Keep the initial architecture as a well-structured Django monolith with REST APIs and a separate Next.js frontend.

The architecture should be scalable, but it should also remain understandable and maintainable for a small development team.

---

# 28. Final Objective

The final MiniShop platform should allow:

```text
Seller
   ↓
Own Shop
   ↓
Add Products
   ↓
Points + Permissions + Business Rules
   ↓
Product Approval
   ↓
Published Product
   ↓
Customer discovers Product/Shop
   ↓
Location/Radius Search
   ↓
Cart
   ↓
Guest or Registered Checkout
   ↓
Order
   ↓
Operation
   ↓
Payment
   ↓
Finance
   ↓
Delivery
   ↓
Completed
```

And staff responsibilities should be controlled through:

```text
User
 ↓
Role
 ↓
Permission
 ↓
Business Rules
 ↓
Ownership
 ↓
Action
```

Build the system incrementally and preserve the existing MiniShop functionality throughout the development process.

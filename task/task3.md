Using the MiniShop Master Prompt and the completed RBAC system, implement the Seller system.

Seller types:

1. FULL_SHOP_OWNER
2. LIMITED_SHOP_OWNER
3. PRODUCT_OWNER

Requirements:

* SellerProfile
* seller type
* seller status
* seller approval workflow
* seller ownership
* seller activation/deactivation
* seller suspension
* seller API endpoints
* seller serializers
* seller permissions
* seller dashboard API

Seller status should support an appropriate lifecycle such as:

PENDING
UNDER_REVIEW
APPROVED
ACTIVE
SUSPENDED
REJECTED

Rules:

* Only authorized staff can approve sellers.
* Sellers can only modify their own seller profile.
* A suspended seller cannot perform seller operations.
* Seller type must be validated by backend business rules.
* Do not implement Shop yet.
* Do not implement Points yet.

Add tests for:

* seller creation
* approval
* unauthorized approval
* seller ownership
* suspended seller
* invalid seller type

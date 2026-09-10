Using the MiniShop Master Prompt and the completed Seller system, implement the Shop system.

Requirements:

Create Shop model with:

* owner
* name
* slug
* description
* logo
* cover image
* phone
* address
* location
* status
* created_at
* updated_at

Relationships:

Seller -> Shop
Shop -> Products

Rules:

* A seller can create/manage only shops they own.
* Product Owner may not automatically create a shop unless business rules allow it.
* Full Shop Owner can manage their shop.
* Limited Shop Owner follows restricted shop rules.
* Authorized staff can review/approve shops.
* Public users can view only active/approved shops.

Shop statuses:

DRAFT
PENDING
APPROVED
ACTIVE
SUSPENDED
REJECTED

Implement:

* models
* migrations
* serializers
* services
* permissions
* APIs
* admin configuration
* tests

Do not implement nearby/location search yet.

Do not implement product changes beyond the minimum relationship needed for Shop.

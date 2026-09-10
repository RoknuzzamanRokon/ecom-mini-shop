Using the MiniShop Master Prompt, integrate Product with Seller and Shop.

Product ownership should follow:

Product
-> Shop
-> Seller

Requirements:

1. Product belongs to a Shop.
2. Product ownership can be determined through Shop/Seller.
3. Seller can only manage products belonging to their own shop.
4. Product Owner behavior must follow seller type rules.
5. Product creation requires `products.create`.
6. Product creation must check seller status.
7. Product creation must check seller type.
8. Product creation must check required points.
9. Required points should be configurable, not hardcoded in the view.
10. If product creation succeeds, deduct points atomically.
11. Create a point transaction.
12. Create audit log.
13. If any step fails, rollback the entire operation.
14. Prevent sellers from assigning products to another seller's shop.

Product status:

DRAFT
SUBMITTED
APPROVED
REJECTED
PUBLISHED
UNPUBLISHED

Implement backend first and then required frontend changes.

Add comprehensive tests.

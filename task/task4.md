Using the MiniShop Master Prompt, implement a production-ready seller point/credit system.

Requirements:

1. Seller wallet/balance.
2. Point transaction ledger.
3. Credit/debit transactions.
4. Balance tracking.
5. Transaction reason.
6. Reference object support.
7. Atomic transactions.
8. Concurrency-safe balance updates.
9. Admin/staff point adjustment with permission.
10. Seller point history API.

Never directly change the point balance without creating an auditable transaction.

Create transaction types such as:

BONUS
ADMIN_CREDIT
ADMIN_DEBIT
PRODUCT_CREATION
REFUND
ADJUSTMENT

Implement:

* PointService
* balance checking
* credit
* debit
* transaction history
* permission checks
* audit logging

Do not implement product creation point deduction yet.

Add comprehensive tests, especially for:

* insufficient points
* concurrent deductions
* unauthorized adjustment
* negative balance prevention
* transaction rollback

# Data reconciliation — TASK-047

**Date:** 2026-10-25 · **Data:** a read-only snapshot of the shared dev database (MySQL 8.0.46), restored into a throwaway local MySQL container. The dump used `--single-transaction`; nothing was written to the dev database. The snapshot, its container and the local password were deleted afterwards.

**Tool:** `python manage.py reconcile_data [--json]` (backend/shop/management/commands/reconcile_data.py). The command is read-only and is tested in `shop/test_reconcile_data.py`. Run it against a snapshot of production before launch, and again whenever a repair is considered.

## Summary

| Check | Result on the dev snapshot |
|---|---|
| Inventory counters equal the last ledger row | **OK** for all 9 products that have ledger rows |
| Every product has an inventory row | 3 products have none (ids 2–4, smoke-test products) |
| Every product has ledger rows | 21 products have none (ids 7–27, the seeded catalogue) |
| Ledger rows chain (each starts where the last ended) | 7 breaks across products 5, 6 and 28–31 |
| `product.stock` equals `available` | 1 product differs (id 7: stock 0, available 98) |
| Delivered orders have a reservation and a sale | 1 of 2 has neither (`ORD-DELIV-30520469`) |
| Every order has a payment | 13 of 14 orders have none |
| Latest payment agrees with its order | OK (the one order with a payment) |
| Sellers holding an active SALES_TEAM role (BUG-004) | **None**. 8 sellers hold it inactive, switched off by the TASK-005 migration |
| Seller wallets equal their ledger and lots | **OK** |

## Findings and causes

1. **Products without ledger rows (21) and ledgers that start part-way (products 28–31, 6).** The seed commands set stock directly before TASK-037 sent them through `InventoryService`. Their first ledger row is a reservation from stock that has no INITIAL_STOCK row. The counters are right; only the history is missing.
2. **Counters changed between two ledger rows.**
   - Product 5 lost 10 units between rows 2 and 3.
   - Product 6 shows a reservation that was never written to the ledger.

   Both changes date from 2026-09-11. That is before TASK-006 locked the admin change forms and before reservations were always written to the ledger.
3. **Products without an inventory row (2–4).** These are smoke-test products created with `Product.objects.create`. `InventoryService.get_or_create_inventory` creates the row, with an INITIAL_STOCK entry, the first time stock is touched.
4. **`product.stock` behind `available` (product 7).** The legacy denormalised field was not synced on that early path.
5. **Delivered order without reservation or sale (`ORD-DELIV-30520469`).** This is a 2026-09-11 smoke order. It was delivered before delivery finalised the reservation.
6. **Orders without payments (13).** These are all orders placed before TASK-015, which opens a cash-on-delivery payment at checkout. TASK-048 decision 3 left the backfill to this task. Their states:

   | Order status | Count |
   |---|---|
   | PENDING | 4 |
   | CONFIRMED | 2 |
   | PROCESSING | 1 |
   | DELIVERED | 2 |
   | CANCELLED | 4 |

## Repairs — proposed, not run

Every affected row is development or demo data. The project decided to keep demo data until just before production (TASK-048 decision 4) and not to touch it until asked. So nothing was repaired. If a repair is wanted, take a backup first (`mysqldump --single-transaction`), run the steps below, and rerun `reconcile_data`:

1. **Inventory.**
   - Create the 3 missing inventory rows through `InventoryService.get_or_create_inventory`.
   - Add one opening ADJUSTMENT row per product whose ledger is missing or starts part-way. Each row records the counters it starts from, so the chain becomes continuous.
   - Set `product.stock` to `available` for product 7.
2. **Payments.** Create a cash-on-delivery payment for each order without one:

   | Order status | Payment status |
   |---|---|
   | Open orders | PENDING |
   | DELIVERED | PAID, with `paid_at` set to the delivery time |
   | CANCELLED | CANCELLED |

   This needs a decision: it puts historical rows into the payment reports.
3. **The delivered smoke order.** Leave it as is, or delete it with the other smoke-test rows when demo data is removed before production.

The simplest route to a clean production start is the TASK-048 decision 4 plan: remove the demo and smoke-test data, then run `reconcile_data` on the production snapshot. It should report nothing.

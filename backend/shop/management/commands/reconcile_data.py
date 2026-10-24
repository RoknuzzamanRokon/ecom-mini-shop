"""
Read-only data reconciliation (TASK-047): where the stored rows disagree
with the rules the services now enforce. It changes nothing.

    python manage.py reconcile_data          # a readable report
    python manage.py reconcile_data --json   # the same, as JSON

Run it on a snapshot rather than a shared live database. Each check:

- inventory: every product has an inventory row and an unbroken ledger
  (each row starts where the previous one ended, the first from zero or as
  INITIAL_STOCK), the counters equal the last ledger row, and the legacy
  product.stock equals the available count (Known #30);
- delivered orders have a reservation and a sale in the ledger;
- every order has a payment (checkout opens a cash-on-delivery one since
  TASK-015), and the latest payment agrees with the order: delivered COD
  is PAID, a cancelled order's money is not still pending or held, and the
  amount matches the order total;
- no seller account holds an active SALES_TEAM role (BUG-004);
- each seller wallet's balance equals its last ledger row and its lots.
"""

import json

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum

from points.models import PointTransaction, SellerWallet
from rbac.models import Role, UserRole
from shop.models import InventoryTransaction, Order, Payment, Product

COUNTERS = ("available", "reserved", "sold")


def _after(row):
    return [row.after_available, row.after_reserved, row.after_sold]


def _before(row):
    return [row.before_available, row.before_reserved, row.before_sold]


def check_inventory():
    ledger = InventoryTransaction.objects.order_by("created_at", "pk")
    products = (
        Product.objects.select_related("inventory")
        .prefetch_related(Prefetch("inventory_transactions", queryset=ledger, to_attr="ledger"))
        .order_by("pk")
    )
    found = {
        "products_without_inventory_row": [],
        "products_without_ledger_rows": [],
        "ledger_chain_breaks": [],
        "counters_differ_from_last_ledger_row": [],
        "product_stock_differs_from_available": [],
    }
    for product in products:
        inventory = getattr(product, "inventory", None)
        label = {"product_id": product.pk, "name": product.name}
        if inventory is None:
            found["products_without_inventory_row"].append({**label, "stock": product.stock})
            continue
        counters = [inventory.available_quantity, inventory.reserved_quantity, inventory.sold_quantity]
        if product.stock != inventory.available_quantity:
            found["product_stock_differs_from_available"].append(
                {**label, "product_stock": product.stock, "available": inventory.available_quantity}
            )
        rows = product.ledger
        if not rows:
            found["products_without_ledger_rows"].append({**label, **dict(zip(COUNTERS, counters))})
            continue
        first = rows[0]
        if first.transaction_type != InventoryTransaction.TYPE_INITIAL_STOCK and any(_before(first)):
            found["ledger_chain_breaks"].append(
                {**label, "row": first.pk, "type": first.transaction_type, "before": _before(first),
                 "problem": "the ledger starts part-way, with stock already there"}
            )
        for previous, row in zip(rows, rows[1:]):
            if _after(previous) != _before(row):
                found["ledger_chain_breaks"].append(
                    {**label, "row": row.pk, "type": row.transaction_type, "before": _before(row),
                     "previous_after": _after(previous), "at": row.created_at.isoformat(),
                     "problem": "the counters changed between two ledger rows"}
                )
        if _after(rows[-1]) != counters:
            found["counters_differ_from_last_ledger_row"].append(
                {**label, "counters": counters, "last_ledger_after": _after(rows[-1])}
            )
    return found


def check_orders():
    reservation = Q(inventory_transactions__transaction_type=InventoryTransaction.TYPE_RESERVATION)
    sale = Q(inventory_transactions__transaction_type=InventoryTransaction.TYPE_SALE)
    delivered = (
        Order.objects.filter(status=Order.STATUS_DELIVERED)
        .annotate(reservations=Count("inventory_transactions", filter=reservation),
                  sales=Count("inventory_transactions", filter=sale))
        .filter(Q(reservations=0) | Q(sales=0))
        .order_by("created_at")
    )
    orders = Order.objects.prefetch_related("payments").order_by("created_at")
    without_payment, mismatched = [], []
    for order in orders:
        payment = order.current_payment
        if payment is None:
            without_payment.append({"order_number": order.order_number, "status": order.status,
                                    "total_amount": str(order.total_amount), "created_at": order.created_at.isoformat()})
            continue
        problems = []
        if (order.status == Order.STATUS_DELIVERED and payment.payment_method == Payment.METHOD_CASH_ON_DELIVERY
                and payment.status != Payment.STATUS_PAID):
            problems.append("delivered cash on delivery, payment not PAID")
        if order.status == Order.STATUS_CANCELLED and payment.status in (
            Payment.STATUS_PENDING, Payment.STATUS_PROCESSING, Payment.STATUS_PAID
        ):
            problems.append("cancelled, payment still open or paid")
        if payment.amount != order.total_amount:
            problems.append("payment amount differs from the order total")
        if problems:
            mismatched.append({"order_number": order.order_number, "order_status": order.status,
                               "payment_number": payment.payment_number, "payment_status": payment.status,
                               "problems": problems})
    return {
        "delivered_orders_without_reservation_or_sale": [
            {"order_number": o.order_number, "reservations": o.reservations, "sales": o.sales} for o in delivered
        ],
        "orders_without_payment": without_payment,
        "payment_disagrees_with_order": mismatched,
    }


def check_roles():
    sales_team = UserRole.objects.filter(
        role__code=Role.ROLE_SALES_TEAM, user__seller_profile__isnull=False
    ).select_related("user__seller_profile")
    return {
        "sellers_with_active_sales_team_role": [
            {"seller_id": r.user.seller_profile.pk, "business_name": r.user.seller_profile.business_name}
            for r in sales_team if r.is_active
        ],
        "sellers_with_inactive_sales_team_role": sum(1 for r in sales_team if not r.is_active),
    }


def check_wallets():
    found = []
    wallets = SellerWallet.objects.select_related("seller").annotate(lots_remaining=Sum("lots__remaining"))
    for wallet in wallets:
        last = PointTransaction.objects.filter(wallet=wallet).order_by("-created_at", "-pk").first()
        lots = wallet.lots_remaining or 0
        if (last is not None and last.balance_after != wallet.balance) or lots != wallet.balance:
            found.append({"wallet_id": wallet.pk, "seller": wallet.seller.business_name, "balance": wallet.balance,
                          "last_ledger_balance": last.balance_after if last else None, "lots_remaining": lots})
    return {"wallets_disagreeing_with_ledger_or_lots": found}


def reconcile():
    # One read-only transaction: every check sees the same moment.
    with transaction.atomic():
        return {"inventory": check_inventory(), "orders": check_orders(), "roles": check_roles(),
                "points": check_wallets()}


class Command(BaseCommand):
    help = "Reports stored data that disagrees with the rules the services enforce. Changes nothing."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Print the findings as JSON.")

    def handle(self, *args, **options):
        report = reconcile()
        if options["json"]:
            self.stdout.write(json.dumps(report, indent=1, default=str))
            return
        for section, checks in report.items():
            self.stdout.write(self.style.MIGRATE_HEADING(section))
            for name, value in checks.items():
                count = value if isinstance(value, int) else len(value)
                style = self.style.SUCCESS if not count or name.startswith("sellers_with_inactive") else self.style.WARNING
                self.stdout.write(style(f"  {name}: {count}"))
                if isinstance(value, list):
                    for item in value:
                        self.stdout.write(f"    {item}")

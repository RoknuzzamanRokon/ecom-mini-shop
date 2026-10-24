"""
TASK-047: `manage.py reconcile_data` reports stored rows that disagree with
the rules the services enforce, and writes nothing.
"""

import json
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from points.models import PointTransaction, SellerWallet
from points.services import PointService
from rbac.models import Role, UserRole
from sellers.models import SellerProfile
from shop.inventory_service import InventoryService
from shop.models import Category, InventoryTransaction, Order, Payment, Product, ProductInventory
from shops.models import Shop

User = get_user_model()


def run():
    out = StringIO()
    call_command("reconcile_data", "--json", stdout=out)
    return json.loads(out.getvalue())


class ReconcileDataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.seller = SellerProfile.objects.create(
            user=User.objects.create_user(username="recon_seller", password="Recon-Seller-1"),
            business_name="Recon Seller", status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop = Shop.objects.create(owner=cls.seller, name="Recon Shop", slug="recon-shop", status=Shop.STATUS_ACTIVE)
        cls.category = Category.objects.create(name="Recon", slug="recon")
        cls.customer = User.objects.create_user(username="recon_customer", password="Recon-Cust-1")

    def product(self, slug, stock=10, inventory=True):
        product = Product.objects.create(
            name=slug.title(), slug=slug, category=self.category, shop=self.shop, price=Decimal("100.00"),
            stock=stock, description="Recon test product.",
        )
        if inventory:
            InventoryService.get_or_create_inventory(product, default_available=stock)
        return product

    def order(self, number, status, payment_status=None, method=Payment.METHOD_CASH_ON_DELIVERY):
        order = Order.objects.create(
            user=self.customer, order_number=number, status=status,
            subtotal=Decimal("100.00"), total_amount=Decimal("100.00"),
        )
        if payment_status:
            Payment.objects.create(
                order=order, user=self.customer, payment_number=f"PAY-{number}", payment_method=method,
                status=payment_status, amount=Decimal("100.00"),
            )
        return order

    def test_consistent_data_reports_nothing(self):
        self.product("recon-clean")
        self.order("ORD-RECON-OK", Order.STATUS_PENDING, Payment.STATUS_PENDING)
        PointService.credit(seller=self.seller, amount=30, transaction_type=PointTransaction.TYPE_BONUS, reason="Grant")

        report = run()

        for section in report.values():
            for name, value in section.items():
                with self.subTest(check=name):
                    self.assertFalse(value, f"{name}: {value}")

    def test_inventory_drift_is_reported(self):
        missing = self.product("recon-no-inventory", inventory=False)
        drifted = self.product("recon-drifted")
        # Counters edited outside the ledger, and product.stock left behind.
        ProductInventory.objects.filter(product=drifted).update(available_quantity=7)
        broken = self.product("recon-broken")
        InventoryTransaction.objects.create(
            product=broken, inventory=broken.inventory, transaction_type=InventoryTransaction.TYPE_ADJUSTMENT,
            quantity=-1, before_available=9, after_available=8,
        )
        ProductInventory.objects.filter(product=broken).update(available_quantity=8)
        Product.objects.filter(pk=broken.pk).update(stock=8)

        inventory = run()["inventory"]

        self.assertEqual([p["product_id"] for p in inventory["products_without_inventory_row"]], [missing.pk])
        self.assertEqual(
            [(p["product_id"], p["counters"], p["last_ledger_after"]) for p in inventory["counters_differ_from_last_ledger_row"]],
            [(drifted.pk, [7, 0, 0], [10, 0, 0])],
        )
        self.assertEqual(
            [(p["product_id"], p["product_stock"], p["available"]) for p in inventory["product_stock_differs_from_available"]],
            [(drifted.pk, 10, 7)],
        )
        breaks = inventory["ledger_chain_breaks"]
        self.assertEqual([(b["product_id"], b["previous_after"], b["before"]) for b in breaks], [(broken.pk, [10, 0, 0], [9, 0, 0])])

    def test_order_and_payment_gaps_are_reported(self):
        self.order("ORD-RECON-NOPAY", Order.STATUS_CONFIRMED)
        self.order("ORD-RECON-DELIVERED", Order.STATUS_DELIVERED, Payment.STATUS_PENDING)
        self.order("ORD-RECON-CANCELLED", Order.STATUS_CANCELLED, Payment.STATUS_PAID)

        orders = run()["orders"]

        self.assertEqual([o["order_number"] for o in orders["orders_without_payment"]], ["ORD-RECON-NOPAY"])
        self.assertEqual(
            [o["order_number"] for o in orders["delivered_orders_without_reservation_or_sale"]], ["ORD-RECON-DELIVERED"]
        )
        self.assertEqual(
            {o["order_number"]: o["problems"] for o in orders["payment_disagrees_with_order"]},
            {
                "ORD-RECON-DELIVERED": ["delivered cash on delivery, payment not PAID"],
                "ORD-RECON-CANCELLED": ["cancelled, payment still open or paid"],
            },
        )

    def test_sellers_with_sales_team_and_wallet_drift_are_reported(self):
        role = Role.objects.get(code=Role.ROLE_SALES_TEAM)
        UserRole.objects.create(user=self.seller.user, role=role, is_active=True)
        PointService.credit(seller=self.seller, amount=30, transaction_type=PointTransaction.TYPE_BONUS, reason="Grant")
        SellerWallet.objects.filter(seller=self.seller).update(balance=50)

        report = run()

        self.assertEqual(
            [s["seller_id"] for s in report["roles"]["sellers_with_active_sales_team_role"]], [self.seller.pk]
        )
        self.assertEqual(
            [(w["balance"], w["last_ledger_balance"], w["lots_remaining"]) for w in report["points"]["wallets_disagreeing_with_ledger_or_lots"]],
            [(50, 30, 30)],
        )

    def test_it_only_reads(self):
        self.product("recon-read-only")
        self.order("ORD-RECON-READ", Order.STATUS_PENDING)
        with CaptureQueriesContext(connection) as queries:
            run()
        writes = [q["sql"] for q in queries if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))]
        self.assertEqual(writes, [])

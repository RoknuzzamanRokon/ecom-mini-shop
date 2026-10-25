"""
TASK-048 decision 6: when staff delete a product that never went live, the
seller gets its creation fee back, once, as a REFUND. A product that was
ever published keeps the fee, and the deletion is audited either way.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from audit.models import AuditLog
from points.models import PointTransaction
from points.services import PointService
from sellers.models import SellerProfile
from shop.models import Category, Product
from shop.services import ProductService
from shops.models import Shop

User = get_user_model()


class CreationFeeRefundTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(username="refund_staff", email="rs@example.com", password="Refund-Staff-1")
        cls.seller = SellerProfile.objects.create(
            user=User.objects.create_user(username="refund_seller", password="Refund-Seller-1"),
            business_name="Refund Seller", status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop = Shop.objects.create(owner=cls.seller, name="Refund Shop", slug="refund-shop", status=Shop.STATUS_ACTIVE)
        cls.category = Category.objects.create(name="Refund Goods", slug="refund-goods")

    def setUp(self):
        PointService.credit(seller=self.seller, amount=50, transaction_type=PointTransaction.TYPE_BONUS, reason="Grant")
        self.client.force_login(self.staff)

    def create(self, name):
        return ProductService.create_product(
            seller=self.seller, name=name, category=self.category, shop=self.shop,
            description="A product for the refund tests.", price=Decimal("100.00"), actor=self.seller.user,
        )

    def balance(self):
        return PointService.get_balance(self.seller)

    def refunds(self, product_id):
        return PointTransaction.objects.filter(
            transaction_type=PointTransaction.TYPE_REFUND, reference_type="PRODUCT", reference_id=str(product_id)
        )

    def delete_in_admin(self, product):
        response = self.client.post(reverse("admin:shop_product_delete", args=[product.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=product.pk).exists())

    def test_deleting_a_product_that_never_went_live_refunds_its_fee(self):
        product = self.create("Draft Lamp")
        fee = PointService.get_product_creation_cost()
        self.assertEqual(self.balance(), 50 - fee)

        self.delete_in_admin(product)

        self.assertEqual(self.balance(), 50)
        self.assertEqual(self.refunds(product.pk).get().amount, fee)
        row = AuditLog.objects.get(action="PRODUCT_DELETED", target_id=str(product.pk))
        self.assertEqual(row.actor, self.staff)
        self.assertEqual(row.metadata["fee_refunded"], fee)

    def test_a_product_that_was_live_keeps_its_fee(self):
        published = self.create("Live Lamp")
        ProductService.publish(published, actor=self.staff)
        # Rejected after being live: still no refund.
        was_live = self.create("Once Live Lamp")
        ProductService.publish(was_live, actor=self.staff)
        ProductService.reject(was_live, actor=self.staff, reason="Wrong photos")
        before = self.balance()

        self.delete_in_admin(published)
        self.delete_in_admin(was_live)

        self.assertEqual(self.balance(), before)
        self.assertFalse(self.refunds(published.pk).exists())
        self.assertFalse(self.refunds(was_live.pk).exists())
        self.assertEqual(
            AuditLog.objects.get(action="PRODUCT_DELETED", target_id=str(was_live.pk)).metadata["fee_refunded"], 0
        )

    def test_the_bulk_delete_action_refunds_each_once(self):
        first, second = self.create("Bulk One"), self.create("Bulk Two")
        response = self.client.post(
            reverse("admin:shop_product_changelist"),
            {"action": "delete_selected", "_selected_action": [first.pk, second.pk], "post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.balance(), 50)
        self.assertEqual(self.refunds(first.pk).count(), 1)
        self.assertEqual(self.refunds(second.pk).count(), 1)

    def test_a_fee_is_refunded_only_once(self):
        product = self.create("Twice Lamp")
        self.assertIsNotNone(ProductService.refund_creation_fee(product, actor=self.staff))
        self.assertIsNone(ProductService.refund_creation_fee(product, actor=self.staff))
        self.assertEqual(self.refunds(product.pk).count(), 1)

"""
TASK-021: list endpoints let every row be reached.

- BUG-024: a client that sends page_size gets pages of that size.
- BUG-026: ?status= on the customer order list finds an old active order
  behind newer finished ones, and the seller's own shop list is not cut off
  at one page.
"""

from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shop.models import Order
from shops.models import Shop

User = get_user_model()

ACTIVE = "PENDING,CONFIRMED,PROCESSING,SHIPPED"


class CustomerOrderListTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.customer = User.objects.create_user(username="paging_customer", password="Paging-Customer-123")
        assign_user_role(cls.customer, Role.ROLE_CUSTOMER)
        # The oldest order is still on its way; thirteen newer ones are done.
        cls.shipped = cls.make_order(0, Order.STATUS_SHIPPED)
        for n in range(1, 13):
            cls.make_order(n, Order.STATUS_DELIVERED)
        cls.make_order(13, Order.STATUS_CANCELLED)

    @classmethod
    def make_order(cls, n, order_status):
        return Order.objects.create(
            user=cls.customer, order_number=f"ORD-PAGING-{n:02d}", status=order_status,
            subtotal=Decimal("100.00"), total_amount=Decimal("100.00"),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.customer)

    def test_the_status_filter_finds_an_old_active_order(self):
        unfiltered = self.client.get("/api/orders/")
        self.assertNotIn(self.shipped.order_number, [o["order_number"] for o in unfiltered.data["results"]])

        response = self.client.get("/api/orders/", {"status": ACTIVE})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["order_number"], self.shipped.order_number)

    def test_the_status_filter_is_case_insensitive_and_takes_several(self):
        response = self.client.get("/api/orders/", {"status": "shipped, delivered"})
        self.assertEqual(response.data["count"], 13)  # all but the cancelled one

    def test_an_unknown_status_is_refused(self):
        response = self.client.get("/api/orders/", {"status": "SHIPPED,LOST"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("LOST", str(response.data["status"]))

    def test_the_requested_page_size_is_used(self):
        first = self.client.get("/api/orders/", {"page_size": 10})
        self.assertEqual(len(first.data["results"]), 10)
        self.assertIsNotNone(first.data["next"])
        last = self.client.get("/api/orders/", {"page_size": 10, "page": 2})
        self.assertEqual(last.status_code, status.HTTP_200_OK)
        self.assertEqual(len(last.data["results"]), 4)
        self.assertIsNone(last.data["next"])


class SellerShopListTests(APITestCase):
    def test_every_shop_of_the_seller_is_listed(self):
        user = User.objects.create_user(username="paging_seller", password="Paging-Seller-123")
        seller = SellerProfile.objects.create(
            user=user, business_name="Paging Seller", status=SellerProfile.STATUS_ACTIVE,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
        )
        for n in range(13):
            Shop.objects.create(owner=seller, name=f"Paging Shop {n}", slug=f"paging-shop-{n}", status=Shop.STATUS_ACTIVE)

        self.client.force_authenticate(user=user)
        response = self.client.get("/api/shops/mine/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertEqual(len(response.data), 13)

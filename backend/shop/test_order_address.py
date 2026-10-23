"""
TASK-017 / BUG-053: an order needs a real delivery address. The server takes
a saved address (address_id, or the customer's default) or a typed one with a
non-blank recipient, phone, line 1 and city. It never invents one.
"""

from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from cart.services import CartService
from customers.models import Address
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shop.models import Category, Order, Product
from shops.models import Shop

User = get_user_model()

TYPED_ADDRESS = {
    "shipping_recipient_name": "Rahim Uddin",
    "shipping_phone": "01711223344",
    "shipping_address_line_1": "House 12, Road 4",
    "shipping_city": "Dhaka",
}


class OrderAddressTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        seller = SellerProfile.objects.create(
            user=User.objects.create_user(username="addr_seller", password="Addr-Seller-123"),
            business_name="Addr Seller",
            status=SellerProfile.STATUS_ACTIVE,
        )
        shop = Shop.objects.create(owner=seller, name="Addr Shop", slug="addr-shop", status=Shop.STATUS_ACTIVE)
        category = Category.objects.create(name="Addr Things", slug="addr-things", is_active=True)
        cls.product = Product.objects.create(
            name="Addr Kettle", slug="addr-kettle", category=category, shop=shop,
            price=Decimal("900.00"), stock=20, status=Product.STATUS_PUBLISHED, is_active=True,
        )
        cls.customer = User.objects.create_user(username="addr_customer", password="Addr-Customer-123")
        assign_user_role(cls.customer, Role.ROLE_CUSTOMER)

    def setUp(self):
        CartService.add_item(self.customer, self.product.pk, quantity=1)
        self.client.force_authenticate(user=self.customer)

    def order(self, payload):
        return self.client.post("/api/orders/", payload, format="json")

    def assert_refused(self, response, *fields):
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        for field in fields:
            self.assertIn(field, response.data)
        self.assertFalse(Order.objects.filter(user=self.customer).exists())
        # The cart is kept for the next attempt.
        self.assertEqual(CartService.get_or_create_cart(self.customer).items.count(), 1)

    def test_a_blank_phone_alone_is_refused(self):
        self.assert_refused(self.order({"phone": ""}), "shipping_phone", "shipping_address_line_1", "shipping_city")

    def test_blank_or_whitespace_fields_are_refused(self):
        payload = {**TYPED_ADDRESS, "shipping_recipient_name": "   ", "shipping_city": ""}
        self.assert_refused(self.order(payload), "shipping_recipient_name", "shipping_city")

    def test_items_without_an_address_are_refused(self):
        payload = {"items": [{"product_id": self.product.pk, "quantity": 1}]}
        self.assert_refused(self.order(payload), "address_id")

    def test_no_address_and_no_saved_default_is_refused_not_invented(self):
        self.assert_refused(self.order({}), "address_id")
        self.assertFalse(Order.objects.filter(shipping_address_line_1="Standard Delivery Address").exists())

    def test_a_typed_address_is_used(self):
        response = self.order(TYPED_ADDRESS)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        order = Order.objects.get(user=self.customer)
        self.assertEqual(order.shipping_recipient_name, "Rahim Uddin")
        self.assertEqual(order.shipping_phone, "01711223344")
        self.assertEqual(order.shipping_address_line_1, "House 12, Road 4")
        self.assertEqual(order.shipping_city, "Dhaka")

    def test_the_saved_default_address_is_used_when_none_is_sent(self):
        Address.objects.create(
            user=self.customer, recipient_name="Default Home", phone="01800000000",
            address_line_1="Plot 7", city="Sylhet", country="Bangladesh", is_default=True,
        )
        response = self.order({})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Order.objects.get(user=self.customer).shipping_city, "Sylhet")

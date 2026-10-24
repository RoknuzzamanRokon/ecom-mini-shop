"""
TASK-029: concurrent requests that raced into a 500 now succeed, or answer
409 "try again".

- BUG-059: a double-submitted first address, a double-clicked first cart add
  and two shops saved with one name at the same moment each succeed.
- BUG-058: verify and refund lock the order before the payment, as cancel
  and delivery do; two checkouts sharing products in opposite cart order both
  go through; a deadlock or lock-wait timeout that still happens is a 409.

The thread tests run on MySQL, each request on its own connection. A
"meeting point" holds each request at a write for up to three seconds so the
racing requests reach it together, which is how the old code failed; with
the fix one request waits at a lock before it instead, and goes on once the
other commits.
"""

import threading
import time
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import OperationalError, transaction
from django.http import Http404
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from cart.models import Cart, CartItem
from cart.services import CartService
from config.api_errors import RETRY_MESSAGE
from customers.models import Address
from customers.services import AddressService
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shop.inventory_service import InventoryService
from shop.models import Category, Order, Payment, Product, ProductInventory
from shop.payment_service import PaymentService
from shop.services import OrderService
from shops.models import Shop
from utils.testing import locked_tables, meeting_point, run_together

User = get_user_model()

ADDRESS = {
    "recipient_name": "Race Customer", "phone": "01700000000", "address_line_1": "1 Race Road",
    "city": "Dhaka", "postal_code": "1212",
}


def make_catalog(tag, products=1):
    seller = SellerProfile.objects.create(
        user=User.objects.create_user(username=f"{tag}_seller", password="Race-Seller-123"),
        business_name=f"{tag} Seller", status=SellerProfile.STATUS_ACTIVE,
    )
    shop = Shop.objects.create(owner=seller, name=f"{tag} Shop", slug=f"{tag}-shop", status=Shop.STATUS_ACTIVE)
    category = Category.objects.create(name=f"{tag} Category", slug=f"{tag}-category", is_active=True)
    made = []
    for n in range(products):
        product = Product.objects.create(
            name=f"{tag} Product {n}", slug=f"{tag}-product-{n}", category=category, shop=shop,
            price=Decimal("100.00"), stock=20, status=Product.STATUS_PUBLISHED, is_active=True,
        )
        ProductInventory.objects.create(product=product, available_quantity=20)
        made.append(product)
    return seller, made


class CheckThenInsertRaceTests(TransactionTestCase):
    """BUG-059."""

    def setUp(self):
        self.user = User.objects.create_user(username="race_customer", password="Race-Customer-123")

    def test_a_double_submitted_first_address_makes_one_default(self):
        with meeting_point(Address, "save"):
            errors = run_together(
                lambda: AddressService.create_address(self.user, dict(ADDRESS)),
                lambda: AddressService.create_address(self.user, dict(ADDRESS)),
            )
        self.assertEqual(errors, [])
        self.assertEqual(Address.objects.filter(user=self.user).count(), 2)
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)

    def test_two_tabs_setting_different_defaults_leave_one(self):
        first = AddressService.create_address(self.user, dict(ADDRESS))
        second = AddressService.create_address(self.user, dict(ADDRESS))
        third = AddressService.create_address(self.user, dict(ADDRESS))
        self.assertTrue(Address.objects.get(pk=first.pk).is_default)

        with meeting_point(Address, "save"):
            errors = run_together(
                lambda: AddressService.set_default_address(Address.objects.get(pk=second.pk)),
                lambda: AddressService.set_default_address(Address.objects.get(pk=third.pk)),
            )
        self.assertEqual(errors, [])
        defaults = list(Address.objects.filter(user=self.user, is_default=True).values_list("pk", flat=True))
        self.assertEqual(len(defaults), 1)
        self.assertIn(defaults[0], (second.pk, third.pk))

    def test_a_double_clicked_first_add_makes_one_line(self):
        _seller, (product,) = make_catalog("race-cart")
        Cart.objects.create(user=self.user)

        with meeting_point(CartItem, "save"):
            errors = run_together(
                lambda: CartService.add_item(self.user, product.pk, 1),
                lambda: CartService.add_item(self.user, product.pk, 1),
            )
        self.assertEqual(errors, [])
        self.assertEqual(list(CartItem.objects.filter(cart__user=self.user).values_list("quantity", flat=True)), [2])

    def test_two_shops_saved_with_one_name_both_save(self):
        seller, _products = make_catalog("race-slug", products=0)
        first_saved, release = threading.Event(), threading.Event()

        def first():
            with transaction.atomic():
                Shop.objects.create(owner=seller, name="Race Shop")
                first_saved.set()
                release.wait(30)  # uncommitted while the second one inserts

        def second():
            first_saved.wait(30)
            Shop.objects.create(owner=seller, name="Race Shop")

        def commit_the_first_once_the_second_is_inserting():
            first_saved.wait(30)
            time.sleep(4)
            release.set()

        errors = run_together(first, second, commit_the_first_once_the_second_is_inserting)
        self.assertEqual(errors, [])
        self.assertEqual(
            sorted(Shop.objects.filter(name="Race Shop").values_list("slug", flat=True)),
            ["race-shop", "race-shop-1"],
        )


class CheckoutDeadlockTests(TransactionTestCase):
    """BUG-058: two checkouts of the same two products, in opposite cart order."""

    def test_both_checkouts_go_through(self):
        _seller, (apple, pear) = make_catalog("race-checkout", products=2)
        customers = []
        for n, products in enumerate(((apple, pear), (pear, apple))):
            customer = User.objects.create_user(username=f"race_buyer_{n}", password="Race-Buyer-123")
            cart = Cart.objects.create(user=customer)
            for product in products:
                CartItem.objects.create(cart=cart, product=product)
            Address.objects.create(user=customer, is_default=True, default_flag=1, **ADDRESS)
            customers.append(customer)

        with meeting_point(InventoryService, "reserve_stock_for_cart"):
            errors = run_together(
                *[lambda customer=customer: OrderService.create_order_from_cart(user=customer) for customer in customers]
            )
        self.assertEqual(errors, [])
        self.assertEqual(Order.objects.count(), 2)
        for product in (apple, pear):
            inventory = ProductInventory.objects.get(product=product)
            self.assertEqual((inventory.available_quantity, inventory.reserved_quantity), (18, 2))


class LockOrderTests(TestCase):
    """BUG-058: a payment change locks its order first, as cancel and delivery do."""

    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="lock_order_customer", password="Lock-Order-123")
        cls.order = Order.objects.create(
            user=cls.customer, order_number="ORD-LOCK-ORDER", subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
        )

    def make_payment(self, payment_status):
        return Payment.objects.create(
            order=self.order, user=self.customer, payment_number=f"PAY-LOCK-{payment_status}",
            payment_method=Payment.METHOD_CASH_ON_DELIVERY, status=payment_status, amount=Decimal("100.00"),
        )

    def test_verify_locks_the_order_then_the_payment(self):
        payment = self.make_payment(Payment.STATUS_PENDING)
        tables = locked_tables(lambda: PaymentService.process_payment_success(payment))
        self.assertEqual(tables[:2], ["shop_order", "shop_payment"])

    def test_refund_locks_the_order_then_the_payment(self):
        payment = self.make_payment(Payment.STATUS_PAID)
        tables = locked_tables(lambda: PaymentService.process_refund(payment, amount=Decimal("10.00")))
        self.assertEqual(tables[:2], ["shop_order", "shop_payment"])


class AddressGoneTests(TestCase):
    def test_changing_an_address_deleted_meanwhile_is_a_404(self):
        user = User.objects.create_user(username="gone_customer", password="Gone-Customer-123")
        address = AddressService.create_address(user, dict(ADDRESS))
        Address.objects.filter(pk=address.pk).delete()
        for change in (AddressService.set_default_address, AddressService.delete_address):
            with self.subTest(change=change.__name__), self.assertRaises(Http404):
                change(address)


class RetryableDatabaseErrorTests(APITestCase):
    """A deadlock or lock-wait timeout answers 409 'try again'; other database errors still raise."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.customer = User.objects.create_user(username="retry_customer", password="Retry-Customer-123")
        assign_user_role(cls.customer, Role.ROLE_CUSTOMER)

    def setUp(self):
        self.client.force_authenticate(user=self.customer)

    def add_to_cart_failing_with(self, error):
        with mock.patch("cart.views.CartService.add_item", side_effect=error):
            return self.client.post("/api/cart/items/", {"product_id": 1, "quantity": 1}, format="json")

    def test_deadlock_and_lock_wait_timeout_are_409(self):
        for code, message in ((1213, "Deadlock found when trying to get lock"), (1205, "Lock wait timeout exceeded")):
            with self.subTest(code=code):
                response = self.add_to_cart_failing_with(OperationalError(code, message))
                self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
                self.assertEqual(response.data["detail"], RETRY_MESSAGE)

    def test_other_database_errors_are_not_hidden(self):
        with self.assertRaises(OperationalError):
            self.add_to_cart_failing_with(OperationalError(2006, "MySQL server has gone away"))

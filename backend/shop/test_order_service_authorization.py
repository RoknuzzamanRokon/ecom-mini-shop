"""
Authorization tests for the OrderService call graph.

`OrderService.transition_order_status()` performs no authorization of its own --
it locks the row, advances the state machine, moves inventory, cancels or refunds
payments and writes the audit entry. Every caller is therefore responsible for
proving the actor may mutate that order, and these tests pin that contract down
for each caller: the DRF staff endpoint, the seller endpoint, the customer
cancellation endpoint and the Django-admin changelist actions.

The Django-admin half is the reason this file exists. Custom ModelAdmin actions
carry no permission requirement unless one is declared, and the changelist is
reachable with view permission alone -- so the five order actions were runnable
by a read-only admin account.
"""
from decimal import Decimal

from django.contrib.admin import helpers
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APITestCase

from cart.models import Cart, CartItem
from customers.models import Address
from points.models import SellerWallet
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.models import Shop
from shop.models import (
    Category,
    InventoryTransaction,
    Order,
    Payment,
    Product,
    ProductInventory,
)
from shop.payment_service import PaymentService
from shop.services import OrderService, ProductService

User = get_user_model()


class OrderServiceAuthorizationTests(APITestCase):
    """Every caller of an OrderService mutation must prove the actor may mutate that order."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        # --- Platform staff -------------------------------------------------
        cls.admin_user = User.objects.create_user(
            username="osa_admin",
            email="osa_admin@minishop.com",
            password="Password123!",
        )
        assign_user_role(cls.admin_user, Role.ROLE_ADMINISTRATOR)

        order_ct = ContentType.objects.get_for_model(Order)
        view_order = Permission.objects.get(content_type=order_ct, codename="view_order")
        change_order = Permission.objects.get(content_type=order_ct, codename="change_order")

        # Django-admin account that may READ orders and nothing more. This is the
        # account the changelist actions must refuse.
        cls.readonly_admin_staff = User.objects.create_user(
            username="osa_readonly_staff",
            email="osa_readonly@minishop.com",
            password="Password123!",
            is_staff=True,
        )
        cls.readonly_admin_staff.user_permissions.add(view_order)

        # Django-admin account that may edit orders -- its existing capability
        # must survive the fix.
        cls.editor_admin_staff = User.objects.create_user(
            username="osa_editor_staff",
            email="osa_editor@minishop.com",
            password="Password123!",
            is_staff=True,
        )
        cls.editor_admin_staff.user_permissions.add(view_order, change_order)

        cls.superuser = User.objects.create_superuser(
            username="osa_superuser",
            email="osa_super@minishop.com",
            password="Password123!",
        )

        # --- Sellers --------------------------------------------------------
        cls.seller_user_a = User.objects.create_user(
            username="osa_seller_a",
            email="osa_seller_a@minishop.com",
            password="Password123!",
        )
        assign_user_role(cls.seller_user_a, Role.ROLE_SALES_TEAM)
        cls.seller_a = SellerProfile.objects.create(
            user=cls.seller_user_a,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Order Auth Alpha",
        )
        SellerWallet.objects.create(seller=cls.seller_a, balance=5000)
        cls.shop_a = Shop.objects.create(
            owner=cls.seller_a,
            name="Order Auth Alpha Shop",
            slug="order-auth-alpha",
            status=Shop.STATUS_ACTIVE,
        )

        cls.seller_user_b = User.objects.create_user(
            username="osa_seller_b",
            email="osa_seller_b@minishop.com",
            password="Password123!",
        )
        assign_user_role(cls.seller_user_b, Role.ROLE_SALES_TEAM)
        cls.seller_b = SellerProfile.objects.create(
            user=cls.seller_user_b,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Order Auth Beta",
        )
        SellerWallet.objects.create(seller=cls.seller_b, balance=5000)
        cls.shop_b = Shop.objects.create(
            owner=cls.seller_b,
            name="Order Auth Beta Shop",
            slug="order-auth-beta",
            status=Shop.STATUS_ACTIVE,
        )

        # --- Customers ------------------------------------------------------
        cls.customer_a = User.objects.create_user(
            username="osa_customer_a",
            email="osa_customer_a@test.com",
            password="Password123!",
        )
        assign_user_role(cls.customer_a, Role.ROLE_CUSTOMER)
        cls.address_a = Address.objects.create(
            user=cls.customer_a,
            label="Home",
            recipient_name="Customer A",
            phone="01700000011",
            address_line_1="House 1, Road 1, Banani",
            city="Dhaka",
            country="Bangladesh",
            is_default=True,
        )

        cls.customer_b = User.objects.create_user(
            username="osa_customer_b",
            email="osa_customer_b@test.com",
            password="Password123!",
        )
        assign_user_role(cls.customer_b, Role.ROLE_CUSTOMER)
        cls.address_b = Address.objects.create(
            user=cls.customer_b,
            label="Home",
            recipient_name="Customer B",
            phone="01700000012",
            address_line_1="House 2, Road 2, Gulshan",
            city="Dhaka",
            country="Bangladesh",
            is_default=True,
        )

        cls.category = Category.objects.create(
            name="Order Auth Category",
            slug="order-auth-cat",
            is_active=True,
        )

    def setUp(self):
        self.product_a = ProductService.create_product(
            seller=self.seller_a,
            name=f"Auth Keyboard {self.id()}",
            category=self.category,
            shop=self.shop_a,
            description="Mechanical keyboard",
            price=Decimal("3500.00"),
            stock=40,
            is_active=True,
            actor=self.seller_user_a,
        )
        self.product_a.status = Product.STATUS_PUBLISHED
        self.product_a.save()

        self.product_b = ProductService.create_product(
            seller=self.seller_b,
            name=f"Auth Mouse {self.id()}",
            category=self.category,
            shop=self.shop_b,
            description="Wireless mouse",
            price=Decimal("1200.00"),
            stock=50,
            is_active=True,
            actor=self.seller_user_b,
        )
        self.product_b.status = Product.STATUS_PUBLISHED
        self.product_b.save()

    # -- helpers -------------------------------------------------------------

    def _create_order(self, customer=None, address=None, product=None, qty=2):
        customer = customer or self.customer_a
        address = address or self.address_a
        product = product or self.product_a
        cart, _ = Cart.objects.get_or_create(user=customer)
        CartItem.objects.filter(cart=cart).delete()
        CartItem.objects.create(cart=cart, product=product, quantity=qty)
        return OrderService.create_order_from_cart(user=customer, address_id=address.id)

    def _run_admin_action(self, user, action_name, order):
        """POSTs `action_name` against `order` on the Django-admin order changelist."""
        admin_client = Client()
        admin_client.force_login(user)
        return admin_client.post(
            reverse("admin:shop_order_changelist"),
            {
                "action": action_name,
                "index": "0",
                helpers.ACTION_CHECKBOX_NAME: [str(order.pk)],
            },
            follow=True,
        )

    # -----------------------------------------------------------------------
    # 1. The bypass: Django-admin changelist actions calling OrderService
    # -----------------------------------------------------------------------

    def test_readonly_admin_staff_reaches_the_order_changelist(self):
        """
        Pins the precondition for the tests below: view permission alone opens the
        changelist, which is why the actions on it needed their own permission.
        """
        admin_client = Client()
        admin_client.force_login(self.readonly_admin_staff)
        response = admin_client.get(reverse("admin:shop_order_changelist"))
        self.assertEqual(response.status_code, 200)

    def test_readonly_admin_staff_cannot_confirm_orders(self):
        order = self._create_order()

        self._run_admin_action(self.readonly_admin_staff, "confirm_orders", order)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)

    def test_readonly_admin_staff_cannot_cancel_orders_or_move_inventory(self):
        """
        Cancellation is the damaging one: it releases the reservation and hands the
        customer an automatic refund, neither of which a read-only account may trigger.
        """
        order = self._create_order()
        payment = PaymentService.create_or_get_payment(
            order=order,
            payment_method=Payment.METHOD_BKASH,
            actor=self.customer_a,
        )
        PaymentService.process_payment_success(
            payment=payment,
            transaction_id="OSA-TXN-1",
            provider="test",
            actor=self.admin_user,
        )
        reserved_before = ProductInventory.objects.get(product=self.product_a).reserved_quantity

        self._run_admin_action(self.readonly_admin_staff, "cancel_orders", order)

        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)
        self.assertEqual(payment.status, Payment.STATUS_PAID)
        self.assertEqual(
            ProductInventory.objects.get(product=self.product_a).reserved_quantity,
            reserved_before,
        )
        self.assertFalse(
            InventoryTransaction.objects.filter(
                order=order, transaction_type=InventoryTransaction.TYPE_RELEASE
            ).exists()
        )
        self.assertEqual(order.refunds.count(), 0)

    def test_readonly_admin_staff_cannot_finalize_delivery(self):
        """The SALE ledger entry is irreversible, so it must not be reachable either."""
        order = self._create_order()
        OrderService.transition_order_status(order, Order.STATUS_CONFIRMED, actor=self.admin_user)
        OrderService.transition_order_status(order, Order.STATUS_PROCESSING, actor=self.admin_user)
        OrderService.transition_order_status(order, Order.STATUS_SHIPPED, actor=self.admin_user)

        self._run_admin_action(self.readonly_admin_staff, "mark_orders_delivered", order)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_SHIPPED)
        self.assertFalse(
            InventoryTransaction.objects.filter(
                order=order, transaction_type=InventoryTransaction.TYPE_SALE
            ).exists()
        )

    def test_admin_staff_with_change_permission_can_still_confirm_orders(self):
        order = self._create_order()

        self._run_admin_action(self.editor_admin_staff, "confirm_orders", order)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)

    def test_superuser_can_still_cancel_orders_and_release_inventory(self):
        order = self._create_order()

        self._run_admin_action(self.superuser, "cancel_orders", order)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertTrue(
            InventoryTransaction.objects.filter(
                order=order, transaction_type=InventoryTransaction.TYPE_RELEASE
            ).exists()
        )

    # -----------------------------------------------------------------------
    # 2. Customer cancellation -- ownership, and id/order_number tampering
    # -----------------------------------------------------------------------

    def test_customer_cannot_cancel_another_customers_order_by_id(self):
        victim_order = self._create_order(customer=self.customer_a)

        self.client.force_authenticate(user=self.customer_b)
        response = self.client.patch(f"/api/orders/{victim_order.id}/cancel/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        victim_order.refresh_from_db()
        self.assertEqual(victim_order.status, Order.STATUS_PENDING)

    def test_customer_cannot_cancel_another_customers_order_by_order_number(self):
        victim_order = self._create_order(customer=self.customer_a)

        self.client.force_authenticate(user=self.customer_b)
        response = self.client.patch(
            f"/api/orders/{victim_order.order_number}/cancel/", {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        victim_order.refresh_from_db()
        self.assertEqual(victim_order.status, Order.STATUS_PENDING)

    def test_order_service_rejects_cancellation_by_a_non_owner(self):
        """The service does not lean on the view alone for the ownership rule."""
        victim_order = self._create_order(customer=self.customer_a)

        with self.assertRaises(PermissionDenied):
            OrderService.cancel_customer_order(order=victim_order, customer=self.customer_b)

        victim_order.refresh_from_db()
        self.assertEqual(victim_order.status, Order.STATUS_PENDING)

    def test_customer_can_still_cancel_their_own_order(self):
        order = self._create_order(customer=self.customer_a)

        self.client.force_authenticate(user=self.customer_a)
        response = self.client.patch(f"/api/orders/{order.order_number}/cancel/", {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELLED)

    # -----------------------------------------------------------------------
    # 3. Seller and staff endpoints keep their existing scope
    # -----------------------------------------------------------------------

    def test_seller_can_still_transition_an_order_holding_their_items(self):
        order = self._create_order(product=self.product_a)

        self.client.force_authenticate(user=self.seller_user_a)
        response = self.client.patch(
            f"/api/seller/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CONFIRMED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)

    def test_seller_cannot_transition_an_order_without_their_items(self):
        order = self._create_order(product=self.product_a)

        self.client.force_authenticate(user=self.seller_user_b)
        response = self.client.patch(
            f"/api/seller/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CANCELLED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)

    def test_staff_with_orders_staff_update_can_still_transition_any_order(self):
        order = self._create_order(customer=self.customer_a)

        self.client.force_authenticate(user=self.admin_user)
        response = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CONFIRMED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)

    def test_customer_cannot_transition_orders_through_the_staff_endpoint(self):
        order = self._create_order(customer=self.customer_a)

        self.client.force_authenticate(user=self.customer_a)
        response = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CONFIRMED},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)

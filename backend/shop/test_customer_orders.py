import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from cart.models import Cart, CartItem
from customers.models import Address
from points.models import SellerWallet
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.models import Shop
from shop.inventory_service import InventoryService
from shop.models import Category, InventoryTransaction, Order, OrderItem, Product, ProductInventory
from shop.services import OrderService, ProductService

User = get_user_model()


class CustomerOrderManagementTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        # 1. Platform Admin
        cls.admin_user = User.objects.create_user(
            username="ord_admin",
            email="admin@test.com",
            password="Password123!",
        )
        assign_user_role(cls.admin_user, Role.ROLE_ADMINISTRATOR)

        # 2. Operational Seller A
        cls.user_seller_a = User.objects.create_user(
            username="ord_seller_a",
            email="seller_a@test.com",
            password="Password123!",
        )
        assign_user_role(cls.user_seller_a, Role.ROLE_SALES_TEAM)
        cls.seller_a = SellerProfile.objects.create(
            user=cls.user_seller_a,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Vertex Audio",
        )
        SellerWallet.objects.create(seller=cls.seller_a, balance=5000)
        cls.shop_a = Shop.objects.create(
            owner=cls.seller_a,
            name="Vertex Audio Shop",
            slug="vertex-audio-shop",
            status=Shop.STATUS_ACTIVE,
        )

        # 3. Operational Seller B
        cls.user_seller_b = User.objects.create_user(
            username="ord_seller_b",
            email="seller_b@test.com",
            password="Password123!",
        )
        assign_user_role(cls.user_seller_b, Role.ROLE_SALES_TEAM)
        cls.seller_b = SellerProfile.objects.create(
            user=cls.user_seller_b,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Urban Apparel",
        )
        SellerWallet.objects.create(seller=cls.seller_b, balance=5000)
        cls.shop_b = Shop.objects.create(
            owner=cls.seller_b,
            name="Urban Apparel Shop",
            slug="urban-apparel-shop",
            status=Shop.STATUS_ACTIVE,
        )

        # 4. Customer A
        cls.customer_a = User.objects.create_user(
            username="customer_alpha",
            email="alpha@customer.com",
            password="Password123!",
        )
        assign_user_role(cls.customer_a, Role.ROLE_CUSTOMER)
        cls.address_a = Address.objects.create(
            user=cls.customer_a,
            label="Home",
            recipient_name="Alpha Customer",
            phone="01711111111",
            address_line_1="House 1, Road 1",
            city="Dhaka",
            country="Bangladesh",
            is_default=True,
        )

        # 5. Customer B
        cls.customer_b = User.objects.create_user(
            username="customer_beta",
            email="beta@customer.com",
            password="Password123!",
        )
        assign_user_role(cls.customer_b, Role.ROLE_CUSTOMER)
        cls.address_b = Address.objects.create(
            user=cls.customer_b,
            label="Office",
            recipient_name="Beta Customer",
            phone="01722222222",
            address_line_1="House 2, Road 2",
            city="Chittagong",
            country="Bangladesh",
            is_default=True,
        )

        # Category
        cls.category = Category.objects.create(
            name="Electronics",
            slug="electronics",
            is_active=True,
        )

    def setUp(self):
        # Create fresh products per test
        self.product_a = ProductService.create_product(
            seller=self.seller_a,
            name=f"Noise Cancelling Headphones {self.id()}",
            category=self.category,
            shop=self.shop_a,
            description="High fidelity headphones",
            price=Decimal("3000.00"),
            stock=25,
            is_active=True,
            actor=self.user_seller_a,
        )
        self.product_a.status = Product.STATUS_PUBLISHED
        self.product_a.save()

        self.product_b = ProductService.create_product(
            seller=self.seller_b,
            name=f"Cotton Hoodie {self.id()}",
            category=self.category,
            shop=self.shop_b,
            description="Warm winter hoodie",
            price=Decimal("1200.00"),
            stock=15,
            is_active=True,
            actor=self.user_seller_b,
        )
        self.product_b.status = Product.STATUS_PUBLISHED
        self.product_b.save()

    def _create_customer_order(self, customer, address, product, quantity):
        """Helper to create an order from customer's cart."""
        cart, _ = Cart.objects.get_or_create(user=customer)
        CartItem.objects.filter(cart=cart).delete()
        CartItem.objects.create(cart=cart, product=product, quantity=quantity)
        return OrderService.create_order_from_cart(user=customer, address_id=address.id)

    # --- 1. Customer Order List & Ownership Isolation ---

    def test_customer_order_list_isolation(self):
        """Verify GET /api/orders/ shows only authenticated customer's own orders."""
        order_a = self._create_customer_order(self.customer_a, self.address_a, self.product_a, 2)
        order_b = self._create_customer_order(self.customer_b, self.address_b, self.product_b, 1)

        # Anonymous request -> 401
        res = self.client.get("/api/orders/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Customer A sees only order_a
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.get("/api/orders/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        order_numbers = [item["order_number"] for item in res.data.get("results", res.data)]
        self.assertIn(order_a.order_number, order_numbers)
        self.assertNotIn(order_b.order_number, order_numbers)

        # Customer B sees only order_b
        self.client.force_authenticate(user=self.customer_b)
        res = self.client.get("/api/orders/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        order_numbers = [item["order_number"] for item in res.data.get("results", res.data)]
        self.assertIn(order_b.order_number, order_numbers)
        self.assertNotIn(order_a.order_number, order_numbers)

    # --- 2. Customer Order Detail Access & Safe 404 Isolation ---

    def test_customer_order_detail_access_and_safe_404_isolation(self):
        """Verify Customer A can view own order, but Customer B receives 404 for Customer A's order."""
        order_a = self._create_customer_order(self.customer_a, self.address_a, self.product_a, 1)

        # Customer A accesses own order by order_number -> 200 OK
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.get(f"/api/orders/{order_a.order_number}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["order_number"], order_a.order_number)
        self.assertTrue(res.data["can_cancel"])

        # Customer A accesses own order by integer id -> 200 OK
        res = self.client.get(f"/api/orders/{order_a.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Customer B accesses Customer A's order -> 404 Not Found (safe isolation)
        self.client.force_authenticate(user=self.customer_b)
        res = self.client.get(f"/api/orders/{order_a.order_number}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # Anonymous request -> 401 Unauthorized
        self.client.logout()
        res = self.client.get(f"/api/orders/{order_a.order_number}/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- 3. Customer Cancellation of Eligible Orders ---

    def test_customer_cancel_pending_order_releases_inventory(self):
        """Verify customer can cancel own PENDING order, releasing inventory reservation."""
        # Stock: 25. Order 5 units.
        order = self._create_customer_order(self.customer_a, self.address_a, self.product_a, 5)

        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 20)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 5)

        # Cancel via PATCH /api/orders/<order_number>/cancel/
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.patch(
            f"/api/orders/{order.order_number}/cancel/",
            {"reason": "Ordered by mistake"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "CANCELLED")
        self.assertFalse(res.data["can_cancel"])

        # Inventory must be fully released back to available
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 25)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 0)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, 25)

        # Verify RELEASE transaction record
        release_tx = InventoryTransaction.objects.filter(
            product=self.product_a,
            order=order,
            transaction_type=InventoryTransaction.TYPE_RELEASE,
        ).first()
        self.assertIsNotNone(release_tx)
        self.assertEqual(release_tx.quantity, 5)
        self.assertEqual(release_tx.after_available, 25)
        self.assertEqual(release_tx.after_reserved, 0)
        self.assertEqual(release_tx.actor, self.customer_a)

    def test_customer_cancel_confirmed_order(self):
        """Verify customer can cancel CONFIRMED order."""
        order = self._create_customer_order(self.customer_a, self.address_a, self.product_a, 3)
        OrderService.transition_order_status(order, Order.STATUS_CONFIRMED, actor=self.admin_user)

        self.client.force_authenticate(user=self.customer_a)
        res = self.client.patch(
            f"/api/orders/{order.order_number}/cancel/",
            {"reason": "Delivery timeline too long"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "CANCELLED")

        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 25)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 0)

    def test_customer_cancel_processing_order(self):
        """Verify customer can cancel PROCESSING order."""
        order = self._create_customer_order(self.customer_a, self.address_a, self.product_a, 4)
        OrderService.transition_order_status(order, Order.STATUS_CONFIRMED, actor=self.admin_user)
        OrderService.transition_order_status(order, Order.STATUS_PROCESSING, actor=self.admin_user)

        self.client.force_authenticate(user=self.customer_a)
        res = self.client.post(
            f"/api/orders/{order.order_number}/cancel/",
            {"reason": "Found alternative item"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "CANCELLED")

        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 25)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 0)

    # --- 4. Terminal & Ineligible Cancellation Rejection ---

    def test_customer_cancel_delivered_order_rejected(self):
        """Cancelling a DELIVERED order must be rejected with 400 Bad Request."""
        order = self._create_customer_order(self.customer_a, self.address_a, self.product_a, 2)
        OrderService.transition_order_status(order, Order.STATUS_CONFIRMED, actor=self.admin_user)
        OrderService.transition_order_status(order, Order.STATUS_PROCESSING, actor=self.admin_user)
        OrderService.transition_order_status(order, Order.STATUS_SHIPPED, actor=self.admin_user)
        OrderService.transition_order_status(order, Order.STATUS_DELIVERED, actor=self.admin_user)

        self.client.force_authenticate(user=self.customer_a)
        res = self.client.patch(f"/api/orders/{order.order_number}/cancel/", format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Sold quantity must remain unchanged
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.sold_quantity, 2)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 0)

    def test_customer_cancel_shipped_order_rejected(self):
        """Cancelling a SHIPPED order must be rejected with 400 Bad Request."""
        order = self._create_customer_order(self.customer_a, self.address_a, self.product_a, 2)
        OrderService.transition_order_status(order, Order.STATUS_CONFIRMED, actor=self.admin_user)
        OrderService.transition_order_status(order, Order.STATUS_PROCESSING, actor=self.admin_user)
        OrderService.transition_order_status(order, Order.STATUS_SHIPPED, actor=self.admin_user)

        self.client.force_authenticate(user=self.customer_a)
        res = self.client.patch(f"/api/orders/{order.order_number}/cancel/", format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Order must remain in SHIPPED status
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_SHIPPED)

    def test_repeated_cancellation_idempotency(self):
        """Repeated cancellation of already CANCELLED order returns 400 and does not duplicate releases."""
        order = self._create_customer_order(self.customer_a, self.address_a, self.product_a, 3)

        self.client.force_authenticate(user=self.customer_a)
        # First cancellation succeeds
        res1 = self.client.patch(f"/api/orders/{order.order_number}/cancel/", format="json")
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 25)

        # Second cancellation fails with 400
        res2 = self.client.patch(f"/api/orders/{order.order_number}/cancel/", format="json")
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

        # Stock must NOT be incremented again (must still be 25, not 28)
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 25)

        # Exactly 1 RELEASE transaction should exist
        release_tx_count = InventoryTransaction.objects.filter(
            product=self.product_a,
            order=order,
            transaction_type=InventoryTransaction.TYPE_RELEASE,
        ).count()
        self.assertEqual(release_tx_count, 1)

    # --- 5. Cross-Customer & Security Isolation ---

    def test_customer_cannot_cancel_another_customers_order(self):
        """Customer B attempting to cancel Customer A's order receives safe 404."""
        order_a = self._create_customer_order(self.customer_a, self.address_a, self.product_a, 2)

        self.client.force_authenticate(user=self.customer_b)
        res = self.client.patch(f"/api/orders/{order_a.order_number}/cancel/", format="json")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # Order A remains PENDING and reservation intact
        order_a.refresh_from_db()
        self.assertEqual(order_a.status, Order.STATUS_PENDING)
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.reserved_quantity, 2)

    def test_anonymous_cancellation_rejected(self):
        """Unauthenticated user cannot cancel any order."""
        order = self._create_customer_order(self.customer_a, self.address_a, self.product_a, 2)
        res = self.client.patch(f"/api/orders/{order.order_number}/cancel/", format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_arbitrary_status_payload_ignored_or_rejected(self):
        """Client cannot alter lifecycle arbitrarily by passing status payload."""
        order = self._create_customer_order(self.customer_a, self.address_a, self.product_a, 1)

        self.client.force_authenticate(user=self.customer_a)
        # Attempt to inject 'status': 'DELIVERED'
        res = self.client.patch(
            f"/api/orders/{order.order_number}/cancel/",
            {"status": "DELIVERED", "reason": "Attempting exploit"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        # Order must be CANCELLED, NEVER DELIVERED
        self.assertEqual(order.status, Order.STATUS_CANCELLED)

    # --- 6. Multi-Seller Order Cancellation ---

    def test_multi_seller_order_cancellation(self):
        """Cancelling an order containing items from multiple sellers releases all reservations independently."""
        cart, _ = Cart.objects.get_or_create(user=self.customer_a)
        CartItem.objects.filter(cart=cart).delete()
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=3)  # Seller A
        CartItem.objects.create(cart=cart, product=self.product_b, quantity=2)  # Seller B

        order = OrderService.create_order_from_cart(user=self.customer_a, address_id=self.address_a.id)

        self.product_a.inventory.refresh_from_db()
        self.product_b.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.reserved_quantity, 3)
        self.assertEqual(self.product_b.inventory.reserved_quantity, 2)

        # Cancel the order
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.patch(f"/api/orders/{order.order_number}/cancel/", format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Both product reservations must be released back to available
        self.product_a.inventory.refresh_from_db()
        self.product_b.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 25)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 0)
        self.assertEqual(self.product_b.inventory.available_quantity, 15)
        self.assertEqual(self.product_b.inventory.reserved_quantity, 0)

        # Order must remain a single unified order
        self.assertEqual(Order.objects.filter(order_number=order.order_number).count(), 1)
        self.assertEqual(order.items.count(), 2)

    # --- 7. Order Immutability & Seller View Synchronization ---

    def test_order_immutability_and_seller_view_sync(self):
        """Historical snapshots remain intact upon cancellation; seller view reflects CANCELLED status."""
        order = self._create_customer_order(self.customer_a, self.address_a, self.product_a, 2)
        item = order.items.first()
        orig_price = item.unit_price
        orig_total = order.total_amount
        orig_recipient = order.shipping_recipient_name

        # Cancel order
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.patch(f"/api/orders/{order.order_number}/cancel/", format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Verify historical snapshots remain unchanged
        order.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(item.unit_price, orig_price)
        self.assertEqual(order.total_amount, orig_total)
        self.assertEqual(order.shipping_recipient_name, orig_recipient)

        # Verify Seller A views the updated status as CANCELLED via seller API
        self.client.force_authenticate(user=self.user_seller_a)
        seller_res = self.client.get(f"/api/seller/orders/{order.order_number}/")
        self.assertEqual(seller_res.status_code, status.HTTP_200_OK)
        self.assertEqual(seller_res.data["status"], "CANCELLED")

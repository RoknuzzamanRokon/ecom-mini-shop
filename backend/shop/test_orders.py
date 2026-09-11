from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from cart.models import Cart, CartItem
from cart.services import CartService
from customers.models import Address
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.models import Shop
from shop.models import Category, Order, OrderItem, Product
from shop.services import OrderService

User = get_user_model()


class OrderTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        # Seller & Active Shop
        cls.seller_user = User.objects.create_user(
            username="order_seller",
            email="seller@example.com",
            password="Password123!",
        )
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Apex Electronics",
        )
        cls.shop = Shop.objects.create(
            owner=cls.seller,
            name="Apex Tech Store",
            slug="apex-tech-store",
            status=Shop.STATUS_ACTIVE,
        )

        # Categories
        cls.category = Category.objects.create(name="Peripherals", slug="peripherals", is_active=True)
        cls.inactive_category = Category.objects.create(name="Discontinued", slug="discontinued", is_active=False)

        # Products
        cls.product_1 = Product.objects.create(
            name="Mechanical Keyboard Pro",
            slug="mech-keyboard-pro",
            category=cls.category,
            shop=cls.shop,
            price=Decimal("150.00"),
            stock=50,
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )
        cls.product_2 = Product.objects.create(
            name="Wireless Mouse",
            slug="wireless-mouse",
            category=cls.category,
            shop=cls.shop,
            price=Decimal("60.00"),
            stock=30,
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )
        cls.draft_product = Product.objects.create(
            name="Draft Headset",
            slug="draft-headset",
            category=cls.category,
            shop=cls.shop,
            price=Decimal("80.00"),
            stock=10,
            status=Product.STATUS_DRAFT,
            is_active=True,
        )

        # Customers
        cls.customer_user = User.objects.create_user(
            username="customer_one",
            email="customer1@example.com",
            password="Password123!",
            first_name="Rahim",
            last_name="Uddin",
        )
        assign_user_role(cls.customer_user, Role.ROLE_CUSTOMER)

        cls.customer_user_2 = User.objects.create_user(
            username="customer_two",
            email="customer2@example.com",
            password="Password123!",
            first_name="Karim",
            last_name="Khan",
        )
        assign_user_role(cls.customer_user_2, Role.ROLE_CUSTOMER)

        cls.plain_user = User.objects.create_user(
            username="plain_no_roles",
            email="noroles@example.com",
            password="Password123!",
        )

        # Customer Address
        cls.address = Address.objects.create(
            user=cls.customer_user,
            label=Address.LABEL_HOME,
            recipient_name="Rahim Uddin",
            phone="+8801711223344",
            address_line_1="House 12, Road 4",
            area="Dhanmondi",
            city="Dhaka",
            postal_code="1209",
            country="Bangladesh",
            is_default=True,
        )

    # -------------------------------------------------------------------------
    # 1. Order Creation from Cart & Snapshots
    # -------------------------------------------------------------------------
    def test_create_order_from_cart_success(self):
        """Order is successfully created from user cart with full historical snapshots and cart cleared."""
        # 1. Add items to user's cart
        CartService.add_item(self.customer_user, self.product_1.id, quantity=2)
        CartService.add_item(self.customer_user, self.product_2.id, quantity=1)

        self.client.force_authenticate(user=self.customer_user)
        response = self.client.post("/api/orders/", {"address_id": self.address.id})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.data

        # Verify Order fields
        self.assertTrue(data["order_number"].startswith("ORD"))
        self.assertEqual(data["status"], Order.STATUS_PENDING)
        self.assertEqual(Decimal(str(data["subtotal"])), Decimal("360.00"))  # (150*2) + (60*1)
        self.assertEqual(Decimal(str(data["total_amount"])), Decimal("360.00"))
        self.assertEqual(data["total_items_count"], 3)

        # Verify Address Snapshot
        self.assertEqual(data["shipping_recipient_name"], "Rahim Uddin")
        self.assertEqual(data["shipping_phone"], "+8801711223344")
        self.assertEqual(data["shipping_address_line_1"], "House 12, Road 4")
        self.assertEqual(data["shipping_city"], "Dhaka")

        # Verify OrderItems snapshots
        self.assertEqual(len(data["items"]), 2)
        items = {item["product"]: item for item in data["items"]}

        item1 = items[self.product_1.id]
        self.assertEqual(item1["product_name"], "Mechanical Keyboard Pro")
        self.assertEqual(item1["product_slug"], "mech-keyboard-pro")
        self.assertEqual(item1["shop_name"], "Apex Tech Store")
        self.assertEqual(item1["seller_name"], "Apex Electronics")
        self.assertEqual(Decimal(str(item1["unit_price"])), Decimal("150.00"))
        self.assertEqual(item1["quantity"], 2)
        self.assertEqual(Decimal(str(item1["line_total"])), Decimal("300.00"))

        item2 = items[self.product_2.id]
        self.assertEqual(item2["product_name"], "Wireless Mouse")
        self.assertEqual(Decimal(str(item2["unit_price"])), Decimal("60.00"))
        self.assertEqual(item2["quantity"], 1)
        self.assertEqual(Decimal(str(item2["line_total"])), Decimal("60.00"))

        # Verify Cart is atomically cleared
        cart = CartService.get_or_create_cart(self.customer_user)
        self.assertEqual(cart.items.count(), 0)

        # Verify Audit Log
        audit = AuditLog.objects.filter(action="ORDER_CREATED", target_id=str(data["id"])).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor, self.customer_user)

    # -------------------------------------------------------------------------
    # 2. Server-Authoritative Pricing & Price Immutability
    # -------------------------------------------------------------------------
    def test_client_submitted_prices_strictly_ignored(self):
        """Client-provided prices/totals are ignored; prices are computed from Product."""
        CartService.add_item(self.customer_user, self.product_1.id, quantity=1)

        self.client.force_authenticate(user=self.customer_user)
        fake_payload = {
            "address_id": self.address.id,
            "total_amount": "5.00",
            "subtotal": "5.00",
            "items": [{"product_id": self.product_1.id, "price": "1.00", "quantity": 1}],
        }
        response = self.client.post("/api/orders/", fake_payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(str(response.data["total_amount"])), Decimal("150.00"))

    def test_product_price_change_does_not_affect_existing_order(self):
        """Modifying product price after order creation does not modify historical order totals."""
        CartService.add_item(self.customer_user, self.product_1.id, quantity=2)
        order = OrderService.create_order_from_cart(self.customer_user, address_id=self.address.id)
        self.assertEqual(order.total_amount, Decimal("300.00"))

        # Update product price in DB
        self.product_1.price = Decimal("250.00")
        self.product_1.save(update_fields=["price"])

        # Reload order
        order.refresh_from_db()
        self.assertEqual(order.total_amount, Decimal("300.00"))
        order_item = order.items.first()
        self.assertEqual(order_item.unit_price, Decimal("150.00"))
        self.assertEqual(order_item.line_total, Decimal("300.00"))

        # Restore product price
        self.product_1.price = Decimal("150.00")
        self.product_1.save(update_fields=["price"])

    # -------------------------------------------------------------------------
    # 3. Address Snapshot & Immutability
    # -------------------------------------------------------------------------
    def test_address_modification_does_not_affect_historical_order(self):
        """Editing customer's Address record does not modify the historical shipping snapshot in Order."""
        CartService.add_item(self.customer_user, self.product_1.id, quantity=1)
        order = OrderService.create_order_from_cart(self.customer_user, address_id=self.address.id)

        # Mutate the address record
        self.address.recipient_name = "Changed Name"
        self.address.address_line_1 = "Completely New Address"
        self.address.city = "Chittagong"
        self.address.save()

        # Reload order
        order.refresh_from_db()
        self.assertEqual(order.shipping_recipient_name, "Rahim Uddin")
        self.assertEqual(order.shipping_address_line_1, "House 12, Road 4")
        self.assertEqual(order.shipping_city, "Dhaka")

        # Restore address
        self.address.recipient_name = "Rahim Uddin"
        self.address.address_line_1 = "House 12, Road 4"
        self.address.city = "Dhaka"
        self.address.save()

    # -------------------------------------------------------------------------
    # 4. Cart Atomicity & Validation
    # -------------------------------------------------------------------------
    def test_empty_cart_order_creation_rejected(self):
        """Cannot create an order when the cart is empty."""
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.post("/api/orders/", {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cart", str(response.data))

    def test_stale_or_non_public_item_aborts_order_creation_and_preserves_cart(self):
        """If any cart item becomes non-public (draft/unpublished), order creation fails and cart is NOT cleared."""
        CartService.add_item(self.customer_user, self.product_1.id, quantity=1)

        # Make product unpublished
        self.product_1.status = Product.STATUS_DRAFT
        self.product_1.save(update_fields=["status"])

        self.client.force_authenticate(user=self.customer_user)
        response = self.client.post("/api/orders/", {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Verify no order created
        self.assertFalse(Order.objects.filter(user=self.customer_user).exists())

        # Verify cart items are NOT deleted
        cart = CartService.get_or_create_cart(self.customer_user)
        self.assertEqual(cart.items.count(), 1)

        # Restore product
        self.product_1.status = Product.STATUS_PUBLISHED
        self.product_1.save(update_fields=["status"])

    # -------------------------------------------------------------------------
    # 5. Security & User Isolation
    # -------------------------------------------------------------------------
    def test_unauthenticated_requests_rejected(self):
        """Unauthenticated requests return 401."""
        self.assertEqual(self.client.get("/api/orders/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post("/api/orders/", {}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get("/api/orders/1/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_without_permission_forbidden(self):
        """User without order permissions receives 403."""
        self.client.force_authenticate(user=self.plain_user)
        self.assertEqual(self.client.get("/api/orders/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post("/api/orders/", {}).status_code, status.HTTP_403_FORBIDDEN)

    def test_user_cannot_view_or_access_another_users_order(self):
        """Customer B receives 404 when attempting to access Customer A's order."""
        CartService.add_item(self.customer_user, self.product_1.id, quantity=1)
        order_a = OrderService.create_order_from_cart(self.customer_user, address_id=self.address.id)

        self.client.force_authenticate(user=self.customer_user_2)

        # List orders for User B returns empty list
        resp_list = self.client.get("/api/orders/")
        self.assertEqual(resp_list.status_code, status.HTTP_200_OK)
        order_numbers = [o["order_number"] for o in resp_list.data.get("results", resp_list.data)]
        self.assertNotIn(order_a.order_number, order_numbers)

        # Detail by pk for User B returns 404
        resp_pk = self.client.get(f"/api/orders/{order_a.id}/")
        self.assertEqual(resp_pk.status_code, status.HTTP_404_NOT_FOUND)

        # Detail by order_number for User B returns 404
        resp_num = self.client.get(f"/api/orders/{order_a.order_number}/")
        self.assertEqual(resp_num.status_code, status.HTTP_404_NOT_FOUND)

    # -------------------------------------------------------------------------
    # 6. Order Status Lifecycle State Machine
    # -------------------------------------------------------------------------
    def test_order_status_valid_transitions(self):
        """Order transitions follow valid state machine path."""
        CartService.add_item(self.customer_user, self.product_1.id, quantity=1)
        order = OrderService.create_order_from_cart(self.customer_user, address_id=self.address.id)
        self.assertEqual(order.status, Order.STATUS_PENDING)

        # PENDING -> CONFIRMED
        OrderService.transition_order_status(order, Order.STATUS_CONFIRMED, actor=self.seller_user)
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)

        # CONFIRMED -> PROCESSING
        OrderService.transition_order_status(order, Order.STATUS_PROCESSING, actor=self.seller_user)
        self.assertEqual(order.status, Order.STATUS_PROCESSING)

        # PROCESSING -> SHIPPED
        OrderService.transition_order_status(order, Order.STATUS_SHIPPED, actor=self.seller_user)
        self.assertEqual(order.status, Order.STATUS_SHIPPED)

        # SHIPPED -> DELIVERED
        OrderService.transition_order_status(order, Order.STATUS_DELIVERED, actor=self.seller_user)
        self.assertEqual(order.status, Order.STATUS_DELIVERED)

    def test_order_status_invalid_transitions_rejected(self):
        """Invalid state transitions raise ValidationError."""
        CartService.add_item(self.customer_user, self.product_1.id, quantity=1)
        order = OrderService.create_order_from_cart(self.customer_user, address_id=self.address.id)

        # PENDING -> SHIPPED is invalid (must go through CONFIRMED/PROCESSING)
        with self.assertRaises(ValidationError):
            OrderService.transition_order_status(order, Order.STATUS_SHIPPED)

        # PENDING -> DELIVERED is invalid
        with self.assertRaises(ValidationError):
            OrderService.transition_order_status(order, Order.STATUS_DELIVERED)

        # Transition to DELIVERED through valid path
        order.status = Order.STATUS_DELIVERED
        order.save()

        # DELIVERED is terminal: cannot go to PROCESSING or CANCELLED
        with self.assertRaises(ValidationError):
            OrderService.transition_order_status(order, Order.STATUS_PROCESSING)

        with self.assertRaises(ValidationError):
            OrderService.transition_order_status(order, Order.STATUS_CANCELLED)

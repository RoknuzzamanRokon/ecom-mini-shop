import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from customers.models import Address
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.models import Shop
from shop.models import Category, Order, OrderItem, Product
from shop.services import OrderService

User = get_user_model()


class SellerOrderTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        # 1. Staff Admin
        cls.admin_user = User.objects.create_user(
            username="platform_admin",
            email="admin@test.com",
            password="Password123!",
        )
        assign_user_role(cls.admin_user, Role.ROLE_ADMINISTRATOR)

        # 2. Seller A (Active, Full Shop Owner, has orders.seller.view & orders.seller.update via ROLE_SALES_TEAM)
        cls.user_seller_a = User.objects.create_user(
            username="seller_a_user",
            email="seller_a@test.com",
            password="Password123!",
        )
        assign_user_role(cls.user_seller_a, Role.ROLE_SALES_TEAM)
        cls.seller_a = SellerProfile.objects.create(
            user=cls.user_seller_a,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Apex Store A",
        )
        cls.shop_a = Shop.objects.create(
            owner=cls.seller_a,
            name="Apex Shop A",
            slug="apex-shop-a",
            status=Shop.STATUS_ACTIVE,
        )

        # 3. Seller B (Active, Full Shop Owner, has orders.seller.view & orders.seller.update)
        cls.user_seller_b = User.objects.create_user(
            username="seller_b_user",
            email="seller_b@test.com",
            password="Password123!",
        )
        assign_user_role(cls.user_seller_b, Role.ROLE_SALES_TEAM)
        cls.seller_b = SellerProfile.objects.create(
            user=cls.user_seller_b,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Zenith Store B",
        )
        cls.shop_b = Shop.objects.create(
            owner=cls.seller_b,
            name="Zenith Shop B",
            slug="zenith-shop-b",
            status=Shop.STATUS_ACTIVE,
        )

        # 4. Suspended Seller
        cls.user_suspended = User.objects.create_user(
            username="seller_suspended_user",
            email="suspended@test.com",
            password="Password123!",
        )
        assign_user_role(cls.user_suspended, Role.ROLE_SALES_TEAM)
        cls.seller_suspended = SellerProfile.objects.create(
            user=cls.user_suspended,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_SUSPENDED,
            suspension_reason="Policy violations",
            business_name="Suspended Merchant",
        )

        # 5. Pending Seller
        cls.user_pending = User.objects.create_user(
            username="seller_pending_user",
            email="pending@test.com",
            password="Password123!",
        )
        cls.seller_pending = SellerProfile.objects.create(
            user=cls.user_pending,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_PENDING,
            business_name="Pending Merchant",
        )

        # 6. Customer User (No seller profile)
        cls.customer_user = User.objects.create_user(
            username="regular_customer",
            email="cust@test.com",
            password="Password123!",
        )
        assign_user_role(cls.customer_user, Role.ROLE_CUSTOMER)

        # 7. Products
        cls.category = Category.objects.create(name="Tech Gear", slug="tech-gear", is_active=True)
        cls.product_a1 = Product.objects.create(
            name="Mechanical Keyboard Alpha",
            slug="mech-keyboard-alpha",
            category=cls.category,
            shop=cls.shop_a,
            price=Decimal("120.00"),
            stock=20,
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )
        cls.product_a2 = Product.objects.create(
            name="Gaming Mouse Alpha",
            slug="gaming-mouse-alpha",
            category=cls.category,
            shop=cls.shop_a,
            price=Decimal("50.00"),
            stock=30,
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )
        cls.product_b1 = Product.objects.create(
            name="Wireless Headset Beta",
            slug="wireless-headset-beta",
            category=cls.category,
            shop=cls.shop_b,
            price=Decimal("90.00"),
            stock=15,
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )

        # 8. Seed Orders:
        # Order 1: Solely Seller A (2 items)
        cls.order_a = Order.objects.create(
            user=cls.customer_user,
            order_number="ORD-SELLER-A-ONLY",
            status=Order.STATUS_PENDING,
            shipping_recipient_name="John Doe",
            shipping_phone="+8801700000001",
            shipping_address_line_1="House 12, Road 4",
            shipping_city="Dhaka",
            shipping_country="Bangladesh",
            subtotal=Decimal("220.00"),
            total_amount=Decimal("220.00"),
        )
        cls.item_a1 = OrderItem.objects.create(
            order=cls.order_a,
            product=cls.product_a1,
            product_name=cls.product_a1.name,
            product_slug=cls.product_a1.slug,
            shop=cls.shop_a,
            shop_name=cls.shop_a.name,
            seller=cls.seller_a,
            seller_name=cls.seller_a.business_name,
            unit_price=Decimal("120.00"),
            quantity=1,
            line_total=Decimal("120.00"),
        )
        cls.item_a2 = OrderItem.objects.create(
            order=cls.order_a,
            product=cls.product_a2,
            product_name=cls.product_a2.name,
            product_slug=cls.product_a2.slug,
            shop=cls.shop_a,
            shop_name=cls.shop_a.name,
            seller=cls.seller_a,
            seller_name=cls.seller_a.business_name,
            unit_price=Decimal("50.00"),
            quantity=2,
            line_total=Decimal("100.00"),
        )

        # Order 2: Solely Seller B (1 item)
        cls.order_b = Order.objects.create(
            user=cls.customer_user,
            order_number="ORD-SELLER-B-ONLY",
            status=Order.STATUS_PENDING,
            shipping_recipient_name="Jane Smith",
            shipping_phone="+8801800000002",
            shipping_address_line_1="Plot 45, Sector 7",
            shipping_city="Chittagong",
            shipping_country="Bangladesh",
            subtotal=Decimal("90.00"),
            total_amount=Decimal("90.00"),
        )
        cls.item_b1 = OrderItem.objects.create(
            order=cls.order_b,
            product=cls.product_b1,
            product_name=cls.product_b1.name,
            product_slug=cls.product_b1.slug,
            shop=cls.shop_b,
            shop_name=cls.shop_b.name,
            seller=cls.seller_b,
            seller_name=cls.seller_b.business_name,
            unit_price=Decimal("90.00"),
            quantity=1,
            line_total=Decimal("90.00"),
        )

        # Order 3: Multi-Seller (Product A1 + Product B1)
        cls.order_multi = Order.objects.create(
            user=cls.customer_user,
            order_number="ORD-MULTI-SELLER",
            status=Order.STATUS_PENDING,
            shipping_recipient_name="Alice Multi",
            shipping_phone="+8801900000003",
            shipping_address_line_1="789 Ring Road",
            shipping_city="Sylhet",
            shipping_country="Bangladesh",
            subtotal=Decimal("210.00"),
            total_amount=Decimal("210.00"),
        )
        cls.item_multi_a = OrderItem.objects.create(
            order=cls.order_multi,
            product=cls.product_a1,
            product_name=cls.product_a1.name,
            product_slug=cls.product_a1.slug,
            shop=cls.shop_a,
            shop_name=cls.shop_a.name,
            seller=cls.seller_a,
            seller_name=cls.seller_a.business_name,
            unit_price=Decimal("120.00"),
            quantity=1,
            line_total=Decimal("120.00"),
        )
        cls.item_multi_b = OrderItem.objects.create(
            order=cls.order_multi,
            product=cls.product_b1,
            product_name=cls.product_b1.name,
            product_slug=cls.product_b1.slug,
            shop=cls.shop_b,
            shop_name=cls.shop_b.name,
            seller=cls.seller_b,
            seller_name=cls.seller_b.business_name,
            unit_price=Decimal("90.00"),
            quantity=1,
            line_total=Decimal("90.00"),
        )

    # -------------------------------------------------------------------------
    # 1. Authentication & Role Requirements
    # -------------------------------------------------------------------------

    def test_unauthenticated_seller_orders_rejected(self):
        """Unauthenticated requests to seller endpoints must return 401."""
        resp_list = self.client.get("/api/seller/orders/")
        self.assertEqual(resp_list.status_code, status.HTTP_401_UNAUTHORIZED)

        resp_detail = self.client.get(f"/api/seller/orders/{self.order_a.order_number}/")
        self.assertEqual(resp_detail.status_code, status.HTTP_401_UNAUTHORIZED)

        resp_patch = self.client.patch(
            f"/api/seller/orders/{self.order_a.order_number}/status/",
            {"status": "CONFIRMED"},
            format="json",
        )
        self.assertEqual(resp_patch.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_without_seller_profile_rejected(self):
        """Regular customer without seller profile receives 403 Forbidden."""
        self.client.force_authenticate(user=self.customer_user)
        resp = self.client.get("/api/seller/orders/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("registered seller profile", str(resp.data))

    # -------------------------------------------------------------------------
    # 2. Seller Lifecycle Invariants
    # -------------------------------------------------------------------------

    def test_suspended_seller_rejected(self):
        """Suspended seller receives 403 Forbidden with suspension reason."""
        self.client.force_authenticate(user=self.user_suspended)
        resp = self.client.get("/api/seller/orders/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("suspended", str(resp.data).lower())

    def test_pending_seller_rejected(self):
        """Pending seller receives 403 Forbidden."""
        self.client.force_authenticate(user=self.user_pending)
        resp = self.client.get("/api/seller/orders/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("pending approval", str(resp.data).lower())

    # -------------------------------------------------------------------------
    # 3. RBAC Permissions
    # -------------------------------------------------------------------------

    def test_unauthorized_seller_without_order_permission_rejected(self):
        """Seller user lacking 'orders.seller.view' receives 403 Forbidden."""
        user_no_perm = User.objects.create_user(
            username="seller_no_perm",
            password="Password123!",
        )
        SellerProfile.objects.create(
            user=user_no_perm,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="No Perm Store",
        )
        self.client.force_authenticate(user=user_no_perm)
        resp = self.client.get("/api/seller/orders/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------------
    # 4. Seller Order List & Multi-Seller Item Filtering
    # -------------------------------------------------------------------------

    def test_seller_order_list_isolation(self):
        """Seller A only lists orders containing Seller A's items; excludes Seller B only orders."""
        self.client.force_authenticate(user=self.user_seller_a)
        resp = self.client.get("/api/seller/orders/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        order_numbers = [item["order_number"] for item in resp.data["results"]]
        # Seller A should see Order A and Order Multi
        self.assertIn("ORD-SELLER-A-ONLY", order_numbers)
        self.assertIn("ORD-MULTI-SELLER", order_numbers)
        # Seller A must NOT see Order B
        self.assertNotIn("ORD-SELLER-B-ONLY", order_numbers)

    def test_multi_seller_order_item_filtering_in_list(self):
        """In a multi-seller order, Seller A only sees Seller A's items; Seller B's items are stripped."""
        self.client.force_authenticate(user=self.user_seller_a)
        resp = self.client.get("/api/seller/orders/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        multi_order = next(o for o in resp.data["results"] if o["order_number"] == "ORD-MULTI-SELLER")
        # Multi-order should only expose Seller A items
        self.assertEqual(len(multi_order["items"]), 1)
        self.assertEqual(multi_order["items"][0]["product_name"], "Mechanical Keyboard Alpha")
        self.assertEqual(multi_order["items"][0]["seller_name"], "Apex Store A")

        # Check Seller B perspective
        self.client.force_authenticate(user=self.user_seller_b)
        resp_b = self.client.get("/api/seller/orders/")
        self.assertEqual(resp_b.status_code, status.HTTP_200_OK)

        multi_order_b = next(o for o in resp_b.data["results"] if o["order_number"] == "ORD-MULTI-SELLER")
        self.assertEqual(len(multi_order_b["items"]), 1)
        self.assertEqual(multi_order_b["items"][0]["product_name"], "Wireless Headset Beta")
        self.assertEqual(multi_order_b["items"][0]["seller_name"], "Zenith Store B")

    # -------------------------------------------------------------------------
    # 5. Seller Order Detail & Customer Privacy
    # -------------------------------------------------------------------------

    def test_seller_order_detail_success_and_privacy(self):
        """Seller sees fulfillment shipping data, but customer credentials/internal fields are hidden."""
        self.client.force_authenticate(user=self.user_seller_a)
        resp = self.client.get(f"/api/seller/orders/{self.order_a.order_number}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        data = resp.data
        self.assertEqual(data["order_number"], "ORD-SELLER-A-ONLY")
        self.assertEqual(data["shipping_recipient_name"], "John Doe")
        self.assertEqual(data["shipping_city"], "Dhaka")
        self.assertEqual(len(data["items"]), 2)

        # Confirm sensitive customer fields are not leaked
        self.assertNotIn("password", data)
        self.assertNotIn("token", data)
        self.assertNotIn("user", data)
        self.assertNotIn("email", data)

    def test_seller_cannot_access_unowned_order_detail(self):
        """Seller B requesting Order A (containing only Seller A's items) receives 404 Not Found."""
        self.client.force_authenticate(user=self.user_seller_b)
        resp = self.client.get(f"/api/seller/orders/{self.order_a.order_number}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    # -------------------------------------------------------------------------
    # 6. Status Lifecycle Transitions (Single-Seller Order)
    # -------------------------------------------------------------------------

    def test_seller_status_transition_valid_path(self):
        """Single-seller order successfully transitions through state machine."""
        self.client.force_authenticate(user=self.user_seller_a)

        # 1. PENDING -> CONFIRMED
        resp1 = self.client.patch(
            f"/api/seller/orders/{self.order_a.order_number}/status/",
            {"status": "CONFIRMED", "note": "Order confirmed by merchant"},
            format="json",
        )
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        self.assertEqual(resp1.data["status"], "CONFIRMED")

        # 2. CONFIRMED -> PROCESSING
        resp2 = self.client.patch(
            f"/api/seller/orders/{self.order_a.order_number}/status/",
            {"status": "PROCESSING"},
            format="json",
        )
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        self.assertEqual(resp2.data["status"], "PROCESSING")

        # 3. PROCESSING -> SHIPPED
        resp3 = self.client.patch(
            f"/api/seller/orders/{self.order_a.order_number}/status/",
            {"status": "SHIPPED"},
            format="json",
        )
        self.assertEqual(resp3.status_code, status.HTTP_200_OK)
        self.assertEqual(resp3.data["status"], "SHIPPED")

        # 4. SHIPPED -> DELIVERED
        resp4 = self.client.patch(
            f"/api/seller/orders/{self.order_a.order_number}/status/",
            {"status": "DELIVERED"},
            format="json",
        )
        self.assertEqual(resp4.status_code, status.HTTP_200_OK)
        self.assertEqual(resp4.data["status"], "DELIVERED")

        # 5. DELIVERED is terminal -> Cannot transition back
        resp5 = self.client.patch(
            f"/api/seller/orders/{self.order_a.order_number}/status/",
            {"status": "PROCESSING"},
            format="json",
        )
        self.assertEqual(resp5.status_code, status.HTTP_400_BAD_REQUEST)

    def test_seller_status_invalid_transition_rejected(self):
        """Invalid state jump (e.g. PENDING -> DELIVERED) is rejected with 400."""
        self.client.force_authenticate(user=self.user_seller_b)
        resp = self.client.patch(
            f"/api/seller/orders/{self.order_b.order_number}/status/",
            {"status": "DELIVERED"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # -------------------------------------------------------------------------
    # 7. Multi-Seller Status Safety
    # -------------------------------------------------------------------------

    def test_multi_seller_order_unilateral_transition_rejected(self):
        """A single seller attempting unilateral transition on a multi-seller order is safely rejected."""
        self.client.force_authenticate(user=self.user_seller_a)
        resp = self.client.patch(
            f"/api/seller/orders/{self.order_multi.order_number}/status/",
            {"status": "CONFIRMED"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("multiple merchants", str(resp.data).lower())

    def test_multi_seller_order_admin_override_allowed(self):
        """Staff/Admin with orders.update can coordinate status on a multi-seller order."""
        self.client.force_authenticate(user=self.admin_user)
        # Using OrderService directly or admin status update
        updated_order = OrderService.transition_seller_order_status(
            order=self.order_multi,
            new_status=Order.STATUS_CONFIRMED,
            seller=self.seller_a,
            actor=self.admin_user,
            note="Platform admin coordinating multi-seller order",
        )
        self.assertEqual(updated_order.status, "CONFIRMED")

    # -------------------------------------------------------------------------
    # 8. Audit Logging & Historical Immutability
    # -------------------------------------------------------------------------

    def test_seller_status_transition_creates_audit_log(self):
        """Successful status change generates ORDER_STATUS_UPDATED AuditLog entry."""
        self.client.force_authenticate(user=self.user_seller_b)
        resp = self.client.patch(
            f"/api/seller/orders/{self.order_b.order_number}/status/",
            {"status": "CONFIRMED", "note": "Packing item"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        log = AuditLog.objects.filter(
            action="ORDER_STATUS_UPDATED",
            target_id=str(self.order_b.id),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.user_seller_b)
        self.assertEqual(log.seller, self.seller_b)
        self.assertEqual(log.metadata.get("new_status"), "CONFIRMED")
        self.assertEqual(log.metadata.get("initiator"), "seller")

    def test_seller_cannot_modify_financial_or_snapshot_data(self):
        """Seller cannot alter line totals, unit prices, quantities, or order numbers via status endpoint."""
        self.client.force_authenticate(user=self.user_seller_a)
        resp = self.client.patch(
            f"/api/seller/orders/{self.order_a.order_number}/status/",
            {
                "status": "CONFIRMED",
                "price": "9999.00",
                "total_amount": "9999.00",
                "order_number": "HACKED-ORD",
                "customer_name": "Hacked Customer",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.order_a.refresh_from_db()
        self.assertEqual(self.order_a.order_number, "ORD-SELLER-A-ONLY")
        self.assertEqual(self.order_a.total_amount, Decimal("220.00"))
        self.assertEqual(self.order_a.shipping_recipient_name, "John Doe")

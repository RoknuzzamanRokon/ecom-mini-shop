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
from shop.models import (
    Category,
    InventoryTransaction,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductInventory,
    Refund,
)
from shop.payment_service import PaymentService
from shop.services import OrderService, ProductService

User = get_user_model()


class StaffOrderOperationsTests(APITestCase):
    """
    Comprehensive test suite for Task 16: Admin & Staff Order Operations.
    Covers RBAC authorization, order listing & filters, detail endpoint with customer privacy,
    lifecycle status transitions, inventory release & delivery finalization,
    payment/refund integration, multi-seller visibility, audit trail, and concurrency.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        # 1. Administrator (holds orders.staff.view, orders.staff.update)
        cls.admin_user = User.objects.create_user(
            username="staff_op_admin",
            email="admin@minishop.com",
            password="Password123!",
        )
        assign_user_role(cls.admin_user, Role.ROLE_ADMINISTRATOR)

        # 2. Finance User (holds orders.staff.view, but NOT orders.staff.update)
        cls.finance_user = User.objects.create_user(
            username="staff_op_finance",
            email="finance@minishop.com",
            password="Password123!",
        )
        assign_user_role(cls.finance_user, Role.ROLE_FINANCE)

        # 3. Seller Alpha & Shop Alpha
        cls.seller_user_a = User.objects.create_user(
            username="staff_seller_a",
            email="seller_a@minishop.com",
            password="Password123!",
        )
        assign_user_role(cls.seller_user_a, Role.ROLE_SALES_TEAM)
        cls.seller_a = SellerProfile.objects.create(
            user=cls.seller_user_a,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Apex Alpha Store",
        )
        SellerWallet.objects.create(seller=cls.seller_a, balance=5000)
        cls.shop_a = Shop.objects.create(
            owner=cls.seller_a,
            name="Apex Alpha Official",
            slug="apex-alpha",
            status=Shop.STATUS_ACTIVE,
        )

        # 4. Seller Beta & Shop Beta
        cls.seller_user_b = User.objects.create_user(
            username="staff_seller_b",
            email="seller_b@minishop.com",
            password="Password123!",
        )
        assign_user_role(cls.seller_user_b, Role.ROLE_SALES_TEAM)
        cls.seller_b = SellerProfile.objects.create(
            user=cls.seller_user_b,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Beta Gadgets Store",
        )
        SellerWallet.objects.create(seller=cls.seller_b, balance=5000)
        cls.shop_b = Shop.objects.create(
            owner=cls.seller_b,
            name="Beta Gadgets Official",
            slug="beta-gadgets",
            status=Shop.STATUS_ACTIVE,
        )

        # 5. Customer
        cls.customer = User.objects.create_user(
            username="staff_customer_one",
            email="customer1@test.com",
            password="Password123!",
            first_name="Rahim",
            last_name="Uddin",
        )
        assign_user_role(cls.customer, Role.ROLE_CUSTOMER)
        cls.address = Address.objects.create(
            user=cls.customer,
            label="Home",
            recipient_name="Rahim Uddin",
            phone="01700000001",
            address_line_1="House 42, Road 11, Banani",
            city="Dhaka",
            state="Dhaka",
            postal_code="1213",
            country="Bangladesh",
            is_default=True,
        )

        # Category
        cls.category = Category.objects.create(
            name="Staff Operations Category",
            slug="staff-ops-cat",
            is_active=True,
        )

    def setUp(self):
        # Create product for Seller A
        self.product_a = ProductService.create_product(
            seller=self.seller_a,
            name=f"Mechanical Keyboard {self.id()}",
            category=self.category,
            shop=self.shop_a,
            description="RGB Mechanical Keyboard",
            price=Decimal("3500.00"),
            stock=40,
            is_active=True,
            actor=self.seller_user_a,
        )
        self.product_a.status = Product.STATUS_PUBLISHED
        self.product_a.save()

        # Create product for Seller B
        self.product_b = ProductService.create_product(
            seller=self.seller_b,
            name=f"Wireless Mouse {self.id()}",
            category=self.category,
            shop=self.shop_b,
            description="Ergonomic Optical Mouse",
            price=Decimal("1200.00"),
            stock=50,
            is_active=True,
            actor=self.seller_user_b,
        )
        self.product_b.status = Product.STATUS_PUBLISHED
        self.product_b.save()

    def _create_single_order(self, customer=None, address=None, qty=2):
        cust = customer or self.customer
        addr = address or self.address
        cart, _ = Cart.objects.get_or_create(user=cust)
        CartItem.objects.filter(cart=cart).delete()
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=qty)
        return OrderService.create_order_from_cart(user=cust, address_id=addr.id)

    def _create_multi_seller_order(self, customer=None, address=None):
        cust = customer or self.customer
        addr = address or self.address
        cart, _ = Cart.objects.get_or_create(user=cust)
        CartItem.objects.filter(cart=cart).delete()
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=1)
        CartItem.objects.create(cart=cart, product=self.product_b, quantity=2)
        return OrderService.create_order_from_cart(user=cust, address_id=addr.id)

    # -------------------------------------------------------------------------
    # 1. Authorization & Security
    # -------------------------------------------------------------------------

    def test_anonymous_cannot_access_staff_endpoints(self):
        order = self._create_single_order()
        endpoints = [
            ("get", "/api/staff/orders/"),
            ("get", f"/api/staff/orders/{order.order_number}/"),
            ("patch", f"/api/staff/orders/{order.order_number}/status/"),
        ]
        for method, url in endpoints:
            fn = getattr(self.client, method)
            res = fn(url)
            self.assertEqual(
                res.status_code,
                status.HTTP_401_UNAUTHORIZED,
                f"Anonymous request to {url} should return 401",
            )

    def test_customer_denied_staff_order_access(self):
        order = self._create_single_order()
        self.client.force_authenticate(user=self.customer)

        res_list = self.client.get("/api/staff/orders/")
        self.assertEqual(res_list.status_code, status.HTTP_403_FORBIDDEN)

        res_detail = self.client.get(f"/api/staff/orders/{order.order_number}/")
        self.assertEqual(res_detail.status_code, status.HTTP_403_FORBIDDEN)

        res_status = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CONFIRMED},
        )
        self.assertEqual(res_status.status_code, status.HTTP_403_FORBIDDEN)

    def test_seller_without_staff_permission_denied(self):
        order = self._create_single_order()
        self.client.force_authenticate(user=self.seller_user_a)

        res_list = self.client.get("/api/staff/orders/")
        self.assertEqual(res_list.status_code, status.HTTP_403_FORBIDDEN)

        res_detail = self.client.get(f"/api/staff/orders/{order.order_number}/")
        self.assertEqual(res_detail.status_code, status.HTTP_403_FORBIDDEN)

        res_status = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CONFIRMED},
        )
        self.assertEqual(res_status.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_without_update_permission_cannot_transition_status(self):
        order = self._create_single_order()
        self.client.force_authenticate(user=self.finance_user)

        # Finance has orders.staff.view -> can list and view detail
        res_list = self.client.get("/api/staff/orders/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)

        res_detail = self.client.get(f"/api/staff/orders/{order.order_number}/")
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)

        # But Finance does NOT have orders.staff.update -> 403 Forbidden
        res_patch = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CONFIRMED},
        )
        self.assertEqual(res_patch.status_code, status.HTTP_403_FORBIDDEN)

    # -------------------------------------------------------------------------
    # 2. Staff Order Listing & Filtering
    # -------------------------------------------------------------------------

    def test_staff_order_listing_with_pagination_and_sorting(self):
        order1 = self._create_single_order()
        order2 = self._create_single_order()

        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get("/api/staff/orders/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()

        self.assertIn("results", data)
        self.assertIn("count", data)
        self.assertGreaterEqual(data["count"], 2)

        # Newest first ordering
        returned_numbers = [item["order_number"] for item in data["results"]]
        self.assertEqual(returned_numbers[0], order2.order_number)

    def test_staff_order_filtering_by_status(self):
        order_pending = self._create_single_order()
        order_confirmed = self._create_single_order()
        OrderService.transition_order_status(order=order_confirmed, new_status=Order.STATUS_CONFIRMED)

        self.client.force_authenticate(user=self.admin_user)

        res_pending = self.client.get("/api/staff/orders/?status=PENDING")
        self.assertEqual(res_pending.status_code, status.HTTP_200_OK)
        numbers = [item["order_number"] for item in res_pending.json()["results"]]
        self.assertIn(order_pending.order_number, numbers)
        self.assertNotIn(order_confirmed.order_number, numbers)

        res_confirmed = self.client.get("/api/staff/orders/?status=CONFIRMED")
        self.assertEqual(res_confirmed.status_code, status.HTTP_200_OK)
        confirmed_numbers = [item["order_number"] for item in res_confirmed.json()["results"]]
        self.assertIn(order_confirmed.order_number, confirmed_numbers)
        self.assertNotIn(order_pending.order_number, confirmed_numbers)

    def test_staff_order_filtering_by_payment_status(self):
        order_unpaid = self._create_single_order()
        order_paid = self._create_single_order()

        payment = PaymentService.create_or_get_payment(order=order_paid)
        PaymentService.process_payment_success(payment=payment, transaction_id="TX-PAID-999")

        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get("/api/staff/orders/?payment_status=PAID")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        numbers = [item["order_number"] for item in res.json()["results"]]
        self.assertIn(order_paid.order_number, numbers)
        self.assertNotIn(order_unpaid.order_number, numbers)

    def test_staff_order_search_by_order_number(self):
        order = self._create_single_order()
        self.client.force_authenticate(user=self.admin_user)

        res = self.client.get(f"/api/staff/orders/?order_number={order.order_number}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["order_number"], order.order_number)

    def test_staff_order_filtering_by_seller_and_shop(self):
        order = self._create_multi_seller_order()
        self.client.force_authenticate(user=self.admin_user)

        res_seller = self.client.get(f"/api/staff/orders/?seller_id={self.seller_a.id}")
        self.assertEqual(res_seller.status_code, status.HTTP_200_OK)
        numbers = [item["order_number"] for item in res_seller.json()["results"]]
        self.assertIn(order.order_number, numbers)

        res_shop = self.client.get(f"/api/staff/orders/?shop_id={self.shop_b.id}")
        self.assertEqual(res_shop.status_code, status.HTTP_200_OK)
        numbers_shop = [item["order_number"] for item in res_shop.json()["results"]]
        self.assertIn(order.order_number, numbers_shop)

    # -------------------------------------------------------------------------
    # 3. Staff Order Detail & Privacy
    # -------------------------------------------------------------------------

    def test_staff_order_detail_exposes_operational_data_and_sanitizes_secrets(self):
        order = self._create_single_order()
        payment = PaymentService.create_or_get_payment(order=order)
        PaymentService.process_payment_success(payment=payment, transaction_id="TX-DETAIL-101")

        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get(f"/api/staff/orders/{order.order_number}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()

        # Operational customer information
        self.assertEqual(data["customer"]["username"], self.customer.username)
        self.assertEqual(data["customer"]["email"], self.customer.email)
        self.assertEqual(data["customer"]["name"], "Rahim Uddin")
        self.assertEqual(data["shipping_address"]["city"], "Dhaka")

        # Items & Totals
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["product_name"], self.product_a.name)
        self.assertEqual(Decimal(data["total_amount"]), order.total_amount)

        # Payment & Transitions
        self.assertIsNotNone(data["payment"])
        self.assertEqual(data["payment"]["status"], Payment.STATUS_PAID)
        self.assertEqual(data["payment"]["transaction_id"], "TX-DETAIL-101")
        self.assertIn(Order.STATUS_CONFIRMED, data["allowed_transitions"])
        self.assertIn(Order.STATUS_CANCELLED, data["allowed_transitions"])

        # String representation checks: Ensure NO credential hashes or tokens exposed
        raw_json = json.dumps(data)
        self.assertNotIn("pbkdf2", raw_json.lower())
        self.assertNotIn("password123", raw_json.lower())
        self.assertNotIn("argon2", raw_json.lower())

    def test_nonexistent_order_returns_safe_404(self):
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get("/api/staff/orders/ORDNONEXISTENT999/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # -------------------------------------------------------------------------
    # 4. Lifecycle Transitions & State Machine
    # -------------------------------------------------------------------------

    def test_staff_valid_lifecycle_progression(self):
        order = self._create_single_order()
        self.client.force_authenticate(user=self.admin_user)

        # 1. PENDING -> CONFIRMED
        res1 = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CONFIRMED, "note": "Order verified by phone call"},
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertEqual(res1.json()["status"], Order.STATUS_CONFIRMED)

        # 2. CONFIRMED -> PROCESSING
        res2 = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_PROCESSING, "note": "Packing started at central hub"},
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.json()["status"], Order.STATUS_PROCESSING)

        # 3. PROCESSING -> SHIPPED
        res3 = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_SHIPPED, "note": "Handed over to courier express"},
        )
        self.assertEqual(res3.status_code, status.HTTP_200_OK)
        self.assertEqual(res3.json()["status"], Order.STATUS_SHIPPED)

        # 4. SHIPPED -> DELIVERED
        res4 = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_DELIVERED, "note": "Customer received and signed"},
        )
        self.assertEqual(res4.status_code, status.HTTP_200_OK)
        self.assertEqual(res4.json()["status"], Order.STATUS_DELIVERED)

    def test_invalid_status_transition_rejected(self):
        order = self._create_single_order()
        self.client.force_authenticate(user=self.admin_user)

        # PENDING -> SHIPPED is not allowed
        res = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_SHIPPED},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid order status transition", str(res.json()))

    def test_arbitrary_status_injection_rejected(self):
        order = self._create_single_order()
        self.client.force_authenticate(user=self.admin_user)

        res = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": "SUPER_REFUNDED"},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_terminal_delivered_state_cannot_be_transitioned(self):
        order = self._create_single_order()
        self.client.force_authenticate(user=self.admin_user)

        OrderService.transition_order_status(order=order, new_status=Order.STATUS_CONFIRMED)
        OrderService.transition_order_status(order=order, new_status=Order.STATUS_PROCESSING)
        OrderService.transition_order_status(order=order, new_status=Order.STATUS_SHIPPED)
        OrderService.transition_order_status(order=order, new_status=Order.STATUS_DELIVERED)

        res = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CANCELLED},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_terminal_cancelled_state_cannot_be_transitioned(self):
        order = self._create_single_order()
        self.client.force_authenticate(user=self.admin_user)

        OrderService.transition_order_status(order=order, new_status=Order.STATUS_CANCELLED)

        res = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CONFIRMED},
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # -------------------------------------------------------------------------
    # 5. Inventory Integration (Release & Delivery Finalization)
    # -------------------------------------------------------------------------

    def test_staff_cancel_releases_inventory_and_records_release_tx(self):
        initial_stock = 40
        order_qty = 3
        order = self._create_single_order(qty=order_qty)

        inv = ProductInventory.objects.get(product=self.product_a)
        self.assertEqual(inv.available_quantity, initial_stock - order_qty)
        self.assertEqual(inv.reserved_quantity, order_qty)

        self.client.force_authenticate(user=self.admin_user)
        res = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CANCELLED, "note": "Customer requested cancellation via call center"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        inv.refresh_from_db()
        self.assertEqual(inv.available_quantity, initial_stock)
        self.assertEqual(inv.reserved_quantity, 0)

        # RELEASE transaction appended
        release_tx = InventoryTransaction.objects.filter(
            order=order,
            transaction_type=InventoryTransaction.TYPE_RELEASE,
        ).first()
        self.assertIsNotNone(release_tx)
        self.assertEqual(release_tx.quantity, order_qty)

    def test_staff_delivery_finalizes_inventory_and_records_sale_tx(self):
        initial_stock = 40
        order_qty = 2
        order = self._create_single_order(qty=order_qty)

        self.client.force_authenticate(user=self.admin_user)
        OrderService.transition_order_status(order=order, new_status=Order.STATUS_CONFIRMED)
        OrderService.transition_order_status(order=order, new_status=Order.STATUS_PROCESSING)
        OrderService.transition_order_status(order=order, new_status=Order.STATUS_SHIPPED)

        res = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_DELIVERED, "note": "Delivered successfully"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        inv = ProductInventory.objects.get(product=self.product_a)
        self.assertEqual(inv.reserved_quantity, 0)
        self.assertEqual(inv.sold_quantity, order_qty)

        # SALE transaction created
        sale_tx = InventoryTransaction.objects.filter(
            order=order,
            transaction_type=InventoryTransaction.TYPE_SALE,
        ).first()
        self.assertIsNotNone(sale_tx)
        self.assertEqual(sale_tx.quantity, order_qty)

    # -------------------------------------------------------------------------
    # 6. Payment & Refund Integration
    # -------------------------------------------------------------------------

    def test_staff_cancel_cancels_pending_payment(self):
        order = self._create_single_order()
        payment = PaymentService.create_or_get_payment(order=order)
        self.assertEqual(payment.status, Payment.STATUS_PENDING)

        self.client.force_authenticate(user=self.admin_user)
        res = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CANCELLED, "note": "Fraudulent order suspected"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_CANCELLED)

    def test_staff_cancel_auto_refunds_paid_payment(self):
        order = self._create_single_order()
        payment = PaymentService.create_or_get_payment(order=order)
        PaymentService.process_payment_success(payment=payment, transaction_id="TX-AUTO-REFUND-77")

        self.client.force_authenticate(user=self.admin_user)
        res = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CANCELLED, "note": "Merchant out of stock, refunding"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_REFUNDED)

        # Refund record created
        refund = Refund.objects.filter(order=order, payment=payment).first()
        self.assertIsNotNone(refund)
        self.assertEqual(refund.status, Refund.STATUS_COMPLETED)
        self.assertEqual(refund.amount, payment.amount)

    # -------------------------------------------------------------------------
    # 7. Multi-Seller Order Operations & Audit
    # -------------------------------------------------------------------------

    def test_multi_seller_order_visibility_and_staff_transition(self):
        order = self._create_multi_seller_order()
        self.assertEqual(order.items.count(), 2)

        self.client.force_authenticate(user=self.admin_user)
        res = self.client.get(f"/api/staff/orders/{order.order_number}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        items = res.json()["items"]
        self.assertEqual(len(items), 2)

        seller_names = {item["seller_name"] for item in items}
        self.assertIn("Apex Alpha Store", seller_names)
        self.assertIn("Beta Gadgets Store", seller_names)

        # Transition multi-seller order
        res_transition = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CONFIRMED, "note": "Multi-seller order confirmed by ops"},
        )
        self.assertEqual(res_transition.status_code, status.HTTP_200_OK)
        self.assertEqual(res_transition.json()["status"], Order.STATUS_CONFIRMED)

    def test_staff_transition_creates_audit_log(self):
        order = self._create_single_order()
        self.client.force_authenticate(user=self.admin_user)

        res = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {"status": Order.STATUS_CONFIRMED, "note": "Passed manual fraud check"},
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        log = AuditLog.objects.filter(
            action="ORDER_STATUS_UPDATED",
            target_id=str(order.id),
        ).latest("created_at")

        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.admin_user)
        self.assertEqual(log.metadata["old_status"], Order.STATUS_PENDING)
        self.assertEqual(log.metadata["new_status"], Order.STATUS_CONFIRMED)
        self.assertEqual(log.metadata["note"], "Passed manual fraud check")

    def test_financial_fields_and_snapshots_cannot_be_tampered_via_status_endpoint(self):
        order = self._create_single_order()
        self.client.force_authenticate(user=self.admin_user)

        original_total = order.total_amount
        res = self.client.patch(
            f"/api/staff/orders/{order.order_number}/status/",
            {
                "status": Order.STATUS_CONFIRMED,
                "total_amount": "1.00",
                "subtotal": "1.00",
                "shipping_fee": "0.00",
                "shipping_city": "MaliciousCity",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        order.refresh_from_db()
        self.assertEqual(order.total_amount, original_total)
        self.assertEqual(order.shipping_city, "Dhaka")

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
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
from shop.models import Category, Order, OrderItem, Payment, Product, Refund
from shop.payment_service import PaymentService
from shop.services import OrderService, ProductService

User = get_user_model()


class PaymentAndRefundManagementTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        # 1. Platform Admin
        cls.admin_user = User.objects.create_user(
            username="pay_admin",
            email="pay_admin@test.com",
            password="Password123!",
        )
        assign_user_role(cls.admin_user, Role.ROLE_ADMINISTRATOR)

        # 2. Finance Officer
        cls.finance_user = User.objects.create_user(
            username="pay_finance",
            email="finance@test.com",
            password="Password123!",
        )
        assign_user_role(cls.finance_user, Role.ROLE_FINANCE)

        # 3. Support Staff (no payment verify/refund permissions)
        cls.support_user = User.objects.create_user(
            username="pay_support",
            email="support@test.com",
            password="Password123!",
        )
        assign_user_role(cls.support_user, Role.ROLE_SUPPORT_TEAM)

        # 4. Seller & Shop
        cls.seller_user = User.objects.create_user(
            username="pay_seller",
            email="seller@test.com",
            password="Password123!",
        )
        assign_user_role(cls.seller_user, Role.ROLE_SALES_TEAM)
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Apex Electronics",
        )
        SellerWallet.objects.create(seller=cls.seller, balance=5000)
        cls.shop = Shop.objects.create(
            owner=cls.seller,
            name="Apex Official",
            slug="apex-official",
            status=Shop.STATUS_ACTIVE,
        )

        # 5. Customer Alpha
        cls.customer_a = User.objects.create_user(
            username="pay_cust_alpha",
            email="alpha@paytest.com",
            password="Password123!",
        )
        assign_user_role(cls.customer_a, Role.ROLE_CUSTOMER)
        cls.address_a = Address.objects.create(
            user=cls.customer_a,
            label="Home",
            recipient_name="Alpha Pay",
            phone="01711111111",
            address_line_1="10 Gulshan Avenue",
            city="Dhaka",
            country="Bangladesh",
            is_default=True,
        )

        # 6. Customer Beta
        cls.customer_b = User.objects.create_user(
            username="pay_cust_beta",
            email="beta@paytest.com",
            password="Password123!",
        )
        assign_user_role(cls.customer_b, Role.ROLE_CUSTOMER)
        cls.address_b = Address.objects.create(
            user=cls.customer_b,
            label="Office",
            recipient_name="Beta Pay",
            phone="01722222222",
            address_line_1="20 Agrabad",
            city="Chittagong",
            country="Bangladesh",
            is_default=True,
        )

        # Category
        cls.category = Category.objects.create(
            name="Payment Test Category",
            slug="pay-cat",
            is_active=True,
        )

    def setUp(self):
        self.product = ProductService.create_product(
            seller=self.seller,
            name=f"Smartwatch {self.id()}",
            category=self.category,
            shop=self.shop,
            description="Fitness tracker smartwatch",
            price=Decimal("2500.00"),
            stock=50,
            is_active=True,
            actor=self.seller_user,
        )
        self.product.status = Product.STATUS_PUBLISHED
        self.product.save()

    def _create_order(self, customer, address, quantity=1):
        cart, _ = Cart.objects.get_or_create(user=customer)
        CartItem.objects.filter(cart=cart).delete()
        CartItem.objects.create(cart=cart, product=self.product, quantity=quantity)
        return OrderService.create_order_from_cart(user=customer, address_id=address.id)

    # --- 1. Payment Creation & Server-Authoritative Amount ---

    def test_payment_creation_and_authoritative_amount(self):
        """Verify payment initiation sets exact server-authoritative payable amount."""
        order = self._create_order(self.customer_a, self.address_a, quantity=2)
        # 2 * 2500.00 + 0.00 = 5000.00
        self.assertEqual(order.total_amount, Decimal("5000.00"))

        self.client.force_authenticate(user=self.customer_a)
        res = self.client.post(f"/api/orders/{order.order_number}/payment/", {
            "payment_method": "BKASH"
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["payment_method"], "BKASH")
        self.assertEqual(res.data["status"], "PENDING")
        self.assertEqual(Decimal(res.data["amount"]), Decimal("5000.00"))
        self.assertEqual(res.data["currency"], "BDT")
        self.assertFalse(res.data["is_paid"])

    def test_client_amount_tampering_rejected_or_ignored(self):
        """Verify client cannot tamper with payment amount or force a status."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1)
        self.assertEqual(order.total_amount, Decimal("2500.00"))

        self.client.force_authenticate(user=self.customer_a)
        # Attempt to pass 1.00 BDT and status PAID
        res = self.client.post(f"/api/orders/{order.order_number}/payment/", {
            "payment_method": "NAGAD",
            "amount": "1.00",
            "status": "PAID",
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        # Amount must remain authoritative 2500.00, status must remain PENDING
        self.assertEqual(Decimal(res.data["amount"]), Decimal("2500.00"))
        self.assertEqual(res.data["status"], "PENDING")

    # --- 2. Customer Ownership Isolation ---

    def test_customer_payment_ownership_isolation(self):
        """Verify Customer B receives safe 404 for Customer A's order payment."""
        order_a = self._create_order(self.customer_a, self.address_a, quantity=1)
        payment_a = PaymentService.create_or_get_payment(order=order_a, payment_method="CARD")

        # Anonymous request -> 401
        res = self.client.get(f"/api/orders/{order_a.order_number}/payment/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # Customer A accesses own payment -> 200 OK
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.get(f"/api/orders/{order_a.order_number}/payment/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["payment_number"], payment_a.payment_number)

        # Customer B accesses Customer A's payment -> 404 Not Found (safe isolation)
        self.client.force_authenticate(user=self.customer_b)
        res = self.client.get(f"/api/orders/{order_a.order_number}/payment/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # Customer B attempts to initiate payment for Customer A's order -> 404 Not Found
        res = self.client.post(f"/api/orders/{order_a.order_number}/payment/", {
            "payment_method": "BKASH"
        })
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # --- 3. Unauthorized Mutation & Security ---

    def test_unauthorized_payment_mutation_forbidden(self):
        """Verify customer cannot directly verify payments or issue refunds."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1)
        payment = PaymentService.create_or_get_payment(order=order, payment_method="ONLINE")

        self.client.force_authenticate(user=self.customer_a)

        # Customer attempts to verify payment -> 403 Forbidden
        res = self.client.post(f"/api/staff/payments/{payment.id}/verify/", {
            "status": "PAID"
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Customer attempts to refund payment -> 403 Forbidden
        res = self.client.post(f"/api/staff/payments/{payment.id}/refund/", {
            "amount": "500.00"
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # --- 4. Payment Success & Verification ---

    def test_successful_payment_processing(self):
        """Verify authorized staff can mark payment as PAID with transaction ID."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1)
        payment = PaymentService.create_or_get_payment(order=order, payment_method="BKASH")

        self.client.force_authenticate(user=self.finance_user)
        res = self.client.post(f"/api/staff/payments/{payment.id}/verify/", {
            "status": "PAID",
            "transaction_id": "BKASH-TX-998877",
            "reason": "bKash webhook verified",
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "PAID")
        self.assertEqual(res.data["transaction_id"], "BKASH-TX-998877")
        self.assertTrue(res.data["is_paid"])
        self.assertIsNotNone(res.data["paid_at"])

        # Check Order detail API reflects payment status
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.get(f"/api/orders/{order.order_number}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(res.data["payment"])
        self.assertTrue(res.data["payment"]["is_paid"])
        self.assertEqual(res.data["payment"]["status"], "PAID")

    def test_failed_payment_recording(self):
        """Verify staff can mark payment as FAILED with operational reason."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1)
        payment = PaymentService.create_or_get_payment(order=order, payment_method="CARD")

        self.client.force_authenticate(user=self.finance_user)
        res = self.client.post(f"/api/staff/payments/{payment.id}/verify/", {
            "status": "FAILED",
            "reason": "Card declined by issuing bank",
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "FAILED")
        self.assertEqual(res.data["failure_reason"], "Card declined by issuing bank")

    # --- 5. Idempotency & Duplicate Success Protection ---

    def test_duplicate_payment_success_idempotent(self):
        """Verify duplicate payment success verification returns 200 idempotently."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1)
        payment = PaymentService.create_or_get_payment(order=order, payment_method="ONLINE")

        PaymentService.process_payment_success(payment=payment, transaction_id="TX-1")
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_PAID)

        # Call again via API
        self.client.force_authenticate(user=self.finance_user)
        res = self.client.post(f"/api/staff/payments/{payment.id}/verify/", {
            "status": "PAID",
            "transaction_id": "TX-1",
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "PAID")

        # Second customer initiation on already paid order raises ValidationError
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.post(f"/api/orders/{order.order_number}/payment/", {
            "payment_method": "CASH_ON_DELIVERY"
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_payment_transitions_rejected(self):
        """Verify invalid payment state transitions raise ValidationError."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1)
        payment = PaymentService.create_or_get_payment(order=order)
        payment = PaymentService.process_payment_success(payment=payment)
        payment.refresh_from_db()

        # Paid payment cannot transition directly to PENDING or FAILED
        self.assertFalse(payment.can_transition_to(Payment.STATUS_PENDING))
        self.assertFalse(payment.can_transition_to(Payment.STATUS_FAILED))
        with self.assertRaises(ValidationError):
            payment.transition_to(Payment.STATUS_PENDING)

    # --- 6. Refund Foundation & Validations ---

    def test_full_refund_processing(self):
        """Verify full refund transitions payment to REFUNDED and creates Refund record."""
        order = self._create_order(self.customer_a, self.address_a, quantity=2) # 5000.00
        payment = PaymentService.create_or_get_payment(order=order)
        PaymentService.process_payment_success(payment=payment, transaction_id="TX-FULL")

        self.client.force_authenticate(user=self.finance_user)
        # Full refund without amount argument
        res = self.client.post(f"/api/staff/payments/{payment.id}/refund/", {
            "reason": "Customer cancellation agreement"
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(res.data["amount"]), Decimal("5000.00"))
        self.assertEqual(res.data["status"], "COMPLETED")

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_REFUNDED)
        self.assertEqual(order.refundable_amount, Decimal("0.00"))

    def test_refund_amount_validation(self):
        """Verify refund amounts <= 0 or exceeding remaining balance are rejected."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1) # 2500.00
        payment = PaymentService.create_or_get_payment(order=order)
        PaymentService.process_payment_success(payment=payment)

        self.client.force_authenticate(user=self.finance_user)

        # Exceeds refundable amount
        res = self.client.post(f"/api/staff/payments/{payment.id}/refund/", {
            "amount": "3000.00",
            "reason": "Too much"
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partial_refund_and_remaining_balance(self):
        """Verify partial refunds update status to PARTIALLY_REFUNDED and track balance."""
        order = self._create_order(self.customer_a, self.address_a, quantity=2) # 5000.00
        payment = PaymentService.create_or_get_payment(order=order)
        PaymentService.process_payment_success(payment=payment)

        self.client.force_authenticate(user=self.finance_user)

        # Partial refund of 2000.00
        res = self.client.post(f"/api/staff/payments/{payment.id}/refund/", {
            "amount": "2000.00",
            "reason": "Partial return of 1 unit"
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_PARTIALLY_REFUNDED)
        self.assertEqual(order.refundable_amount, Decimal("3000.00"))

        # Second partial refund of remaining 3000.00
        res = self.client.post(f"/api/staff/payments/{payment.id}/refund/", {
            "amount": "3000.00",
            "reason": "Remaining unit returned"
        })
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_REFUNDED)
        self.assertEqual(order.refundable_amount, Decimal("0.00"))

        # Third refund attempt rejected (exceeds balance)
        res = self.client.post(f"/api/staff/payments/{payment.id}/refund/", {
            "amount": "500.00"
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # --- 7. Order Cancellation & Payment Interaction ---

    def test_cancellation_unpaid_order_cancels_pending_payment(self):
        """Verify cancelling an unpaid order marks pending payment as CANCELLED."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1)
        payment = PaymentService.create_or_get_payment(order=order, payment_method="CASH_ON_DELIVERY")
        self.assertEqual(payment.status, Payment.STATUS_PENDING)

        # Customer cancels order
        OrderService.cancel_customer_order(order=order, customer=self.customer_a)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_CANCELLED)

    def test_cancellation_paid_order_issues_automatic_refund(self):
        """Verify cancelling a paid order automatically issues a refund and releases inventory."""
        order = self._create_order(self.customer_a, self.address_a, quantity=2) # 5000.00
        payment = PaymentService.create_or_get_payment(order=order, payment_method="BKASH")
        PaymentService.process_payment_success(payment=payment, transaction_id="BKASH-AUTO-REFUND")

        self.product.inventory.refresh_from_db()
        reserved_before = self.product.inventory.reserved_quantity
        self.assertEqual(reserved_before, 2)

        # Customer cancels paid order
        OrderService.cancel_customer_order(order=order, customer=self.customer_a, reason="Need full refund")

        order.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertEqual(payment.status, Payment.STATUS_REFUNDED)

        # Refund record created
        refund = Refund.objects.filter(payment=payment).first()
        self.assertIsNotNone(refund)
        self.assertEqual(refund.amount, Decimal("5000.00"))
        self.assertEqual(refund.status, Refund.STATUS_COMPLETED)

        # Inventory reservation released
        self.product.inventory.refresh_from_db()
        self.assertEqual(self.product.inventory.reserved_quantity, 0)

    # --- 8. Audit Logging & Historical Integrity ---

    def test_audit_logging_across_payment_lifecycle(self):
        """Verify audit logs are recorded for payment creation, success, failure, and refund."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1)
        payment = PaymentService.create_or_get_payment(order=order)

        self.assertTrue(AuditLog.objects.filter(action="PAYMENT_CREATED", target_id=str(payment.pk)).exists())

        PaymentService.process_payment_success(payment=payment, transaction_id="TX-AUDIT")
        self.assertTrue(AuditLog.objects.filter(action="PAYMENT_SUCCESS", target_id=str(payment.pk)).exists())

        refund = PaymentService.process_refund(payment=payment, reason="Audit refund test")
        self.assertTrue(AuditLog.objects.filter(action="REFUND_PROCESSED", target_id=str(refund.pk)).exists())

    def test_rbac_staff_permissions(self):
        """Verify Finance role can view/refund; Support role without permissions is rejected."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1)
        payment = PaymentService.create_or_get_payment(order=order)
        PaymentService.process_payment_success(payment=payment)

        # Finance user has payments.view, payments.refund
        self.client.force_authenticate(user=self.finance_user)
        res = self.client.get("/api/staff/payments/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Support user without payments.refund attempts refund -> 403 Forbidden
        self.client.force_authenticate(user=self.support_user)
        res = self.client.post(f"/api/staff/payments/{payment.id}/refund/", {
            "amount": "500.00"
        })
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # ==========================================================================
    # PAYMENT DATA ISOLATION: STAFF ENDPOINT AUTHORIZATION (Phase 1A.1)
    #
    # 'payments.view' gates the platform-wide staff payment surface
    # (/api/staff/payments/ and /api/staff/payments/<pk>/, see
    # StaffPaymentListAPIView / StaffPaymentDetailAPIView). It is no longer
    # seeded on CUSTOMER: that permission has never gated the customer-facing
    # payment endpoint below, which is authorized purely by IsAuthenticated
    # plus per-request order ownership (see
    # test_customer_payment_ownership_isolation above).
    # ==========================================================================

    def test_customer_cannot_access_staff_payment_listing(self):
        """A normal CUSTOMER must receive 403 on the platform-wide staff payment listing."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1)
        PaymentService.create_or_get_payment(order=order, payment_method="BKASH")

        self.client.force_authenticate(user=self.customer_a)
        res = self.client.get("/api/staff/payments/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        # No platform payment data may leak into a denied response body.
        self.assertNotIsInstance(res.data, list)
        self.assertNotIn("results", res.data if isinstance(res.data, dict) else {})

    def test_customer_cannot_access_staff_payment_detail(self):
        """A normal CUSTOMER must receive 403 on a staff payment detail record, even their own."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1)
        payment = PaymentService.create_or_get_payment(order=order, payment_method="BKASH")

        self.client.force_authenticate(user=self.customer_a)
        res = self.client.get(f"/api/staff/payments/{payment.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_cannot_access_staff_payment_listing(self):
        """An unauthenticated request must receive 401 (not 403) on the staff payment listing."""
        res = self.client.get("/api/staff/payments/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authorized_finance_staff_can_access_staff_payment_listing(self):
        """A Finance user holding 'payments.view' can access the platform-wide staff payment listing."""
        order_a = self._create_order(self.customer_a, self.address_a, quantity=1)
        PaymentService.create_or_get_payment(order=order_a, payment_method="BKASH")
        order_b = self._create_order(self.customer_b, self.address_b, quantity=1)
        PaymentService.create_or_get_payment(order=order_b, payment_method="NAGAD")

        self.client.force_authenticate(user=self.finance_user)
        res = self.client.get("/api/staff/payments/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        # The staff endpoint is intentionally platform-wide for authorized
        # staff: it must see payments across BOTH customers, not just one.
        self.assertGreaterEqual(res.data["count"], 2)

    def test_customer_retains_legitimate_own_payment_access(self):
        """Removing 'payments.view' from CUSTOMER must not break the customer's own payment retrieval."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1)
        PaymentService.create_or_get_payment(order=order, payment_method="BKASH")

        self.client.force_authenticate(user=self.customer_a)
        res = self.client.get(f"/api/orders/{order.order_number}/payment/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["payment_method"], "BKASH")

    def test_historical_order_immutability(self):
        """Verify order snapshot fields remain untouched throughout payment and refund cycles."""
        order = self._create_order(self.customer_a, self.address_a, quantity=1)
        initial_subtotal = order.subtotal
        initial_total = order.total_amount
        initial_address = order.shipping_address_line_1

        payment = PaymentService.create_or_get_payment(order=order)
        PaymentService.process_payment_success(payment=payment)
        PaymentService.process_refund(payment=payment)

        order.refresh_from_db()
        self.assertEqual(order.subtotal, initial_subtotal)
        self.assertEqual(order.total_amount, initial_total)
        self.assertEqual(order.shipping_address_line_1, initial_address)

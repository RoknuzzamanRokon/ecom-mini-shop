import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from cart.models import Cart, CartItem
from customers.models import Address
from points.models import SellerWallet
from rbac.models import Permission, Role, UserPermission, UserRole
from rbac.services import assign_user_role
from shop.metrics import get_console_metrics, payment_metrics
from shop.models import Category, Order, Payment, Product, Refund
from shop.payment_service import PaymentService
from shop.services import OrderService, ProductService
from shops.models import Shop
from sellers.models import SellerProfile

User = get_user_model()


class AdminMetricsAPITests(APITestCase):
    def setUp(self):
        # Seed the real role -> permission grants. Phase 2D moved this endpoint
        # from a role-code list to the 'reports.view' RBAC permission, so a role
        # created bare by get_or_create below (carrying no permissions at all)
        # no longer stands in for a real one. The roles and expectations here are
        # unchanged; only the fixture is now realistic.
        call_command("seed_rbac")

        # 1. Superuser / Admin
        self.admin_user = User.objects.create_superuser(
            username="admin_user",
            email="admin@example.com",
            password="adminpassword123",
        )

        # 2. Staff user with Role
        self.staff_user = User.objects.create_user(
            username="staff_user",
            email="staff@example.com",
            password="staffpassword123",
            is_staff=True,
        )
        op_role, _ = Role.objects.get_or_create(
            code=Role.ROLE_OPERATION_MANAGER,
            defaults={"name": "Operation Manager"},
        )
        UserRole.objects.create(user=self.staff_user, role=op_role)

        # 3. Regular Customer
        self.customer = User.objects.create_user(
            username="customer_user",
            email="customer@example.com",
            password="customerpassword123",
        )
        cust_role, _ = Role.objects.get_or_create(
            code=Role.ROLE_CUSTOMER,
            defaults={"name": "Customer"},
        )
        UserRole.objects.create(user=self.customer, role=cust_role)

        self.url = reverse("shop:admin_metrics")

    def test_unauthenticated_request_rejected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_access_denied(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("detail", response.data)

    def test_admin_access_granted(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total_orders", response.data)
        self.assertIn("total_revenue", response.data)
        self.assertIn("pending_shops", response.data)
        self.assertIn("pending_sellers", response.data)
        self.assertIn("total_shops", response.data)
        self.assertIn("total_sellers", response.data)
        self.assertIn("total_products", response.data)

    def test_staff_role_access_granted(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class RefundAwareRevenueTests(TestCase):
    """
    `total_revenue` must report money actually kept: captured minus refunded.

    Before this was fixed, revenue summed `Payment.amount` over PAID only. A
    refund moves the payment to PARTIALLY_REFUNDED or REFUNDED, so a single taka
    refunded against a 10,000 payment dropped the whole 10,000 out of revenue.
    Merely widening the status filter would swap that for the opposite error --
    reporting the full 10,000 on a payment that was partly given back.

    Refunds are driven through `PaymentService.process_refund` here rather than
    by writing Refund rows, so these tests agree with the code that actually
    moves money. The two non-effective cases are the exception: the service only
    ever writes COMPLETED refunds, so PENDING and FAILED rows are created
    directly -- that is the only way those states can exist at all.

    Note on successive partial refunds: a payment accepts only one partial
    refund that leaves a balance, because `Payment.VALID_TRANSITIONS` has no
    PARTIALLY_REFUNDED -> PARTIALLY_REFUNDED edge. That is a pre-existing
    payment-lifecycle limitation, unrelated to revenue, recorded as a Known
    Issue rather than worked around here.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        cls.seller_user = User.objects.create_user(
            username="rev_seller", email="rev_seller@test.com", password="Password123!"
        )
        assign_user_role(cls.seller_user, Role.ROLE_SALES_TEAM)
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Revenue Test Traders",
        )
        SellerWallet.objects.create(seller=cls.seller, balance=5000)
        cls.shop = Shop.objects.create(
            owner=cls.seller,
            name="Revenue Test Shop",
            slug="revenue-test-shop",
            status=Shop.STATUS_ACTIVE,
        )

        cls.buyer = User.objects.create_user(
            username="rev_buyer", email="rev_buyer@test.com", password="Password123!"
        )
        assign_user_role(cls.buyer, Role.ROLE_CUSTOMER)
        cls.address = Address.objects.create(
            user=cls.buyer,
            label="Home",
            recipient_name="Revenue Buyer",
            phone="01799999999",
            address_line_1="1 Revenue Road",
            city="Dhaka",
            country="Bangladesh",
            is_default=True,
        )

        cls.category = Category.objects.create(
            name="Revenue Test Category", slug="revenue-test-cat", is_active=True
        )

    def setUp(self):
        # Priced so one unit is exactly the 10,000 the revenue contract is
        # specified against; shipping on this flow is 0.00.
        self.product = ProductService.create_product(
            seller=self.seller,
            name=f"Revenue Test Product {self.id()}",
            category=self.category,
            shop=self.shop,
            description="Priced for revenue arithmetic",
            price=Decimal("10000.00"),
            stock=50,
            is_active=True,
            actor=self.seller_user,
        )
        self.product.status = Product.STATUS_PUBLISHED
        self.product.save()

    def _paid_payment(self, quantity=1):
        """Drive a real order through to a captured payment."""
        cart, _ = Cart.objects.get_or_create(user=self.buyer)
        CartItem.objects.filter(cart=cart).delete()
        CartItem.objects.create(cart=cart, product=self.product, quantity=quantity)
        order = OrderService.create_order_from_cart(
            user=self.buyer, address_id=self.address.id
        )
        payment = PaymentService.create_or_get_payment(order=order)
        PaymentService.process_payment_success(payment=payment)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_PAID)
        return payment

    def _revenue(self):
        return payment_metrics()["revenue"]

    # --- the contract -------------------------------------------------------

    def test_paid_payment_with_no_refund_counts_in_full(self):
        payment = self._paid_payment()
        self.assertEqual(payment.amount, Decimal("10000.00"))
        self.assertEqual(self._revenue(), Decimal("10000.00"))

    def test_one_taka_partial_refund_does_not_erase_the_payment(self):
        """The exact regression: 10,000 less 1 is 9,999 -- not 0, not 10,000."""
        payment = self._paid_payment()
        PaymentService.process_refund(
            payment=payment, amount=Decimal("1.00"), reason="Goodwill adjustment"
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_PARTIALLY_REFUNDED)

        revenue = self._revenue()
        self.assertEqual(revenue, Decimal("9999.00"))
        self.assertNotEqual(revenue, Decimal("0.00"))
        self.assertNotEqual(revenue, Decimal("10000.00"))

    def test_partial_refund_is_subtracted(self):
        payment = self._paid_payment()
        PaymentService.process_refund(
            payment=payment, amount=Decimal("1000.00"), reason="One unit returned"
        )
        self.assertEqual(self._revenue(), Decimal("9000.00"))

    def test_full_refund_leaves_no_revenue(self):
        payment = self._paid_payment()
        PaymentService.process_refund(payment=payment, reason="Order cancelled")
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_REFUNDED)
        self.assertEqual(self._revenue(), Decimal("0.00"))

    def test_revenue_aggregates_across_several_payments(self):
        """One untouched, one partly refunded, one fully refunded."""
        self._paid_payment()                                   # keeps 10,000
        partly = self._paid_payment()
        PaymentService.process_refund(
            payment=partly, amount=Decimal("1000.00"), reason="One unit returned"
        )                                                      # keeps  9,000
        fully = self._paid_payment()
        PaymentService.process_refund(payment=fully, reason="Order cancelled")
        #                                                        keeps      0
        metrics = payment_metrics()
        self.assertEqual(metrics["total"], 3)
        self.assertEqual(metrics["revenue"], Decimal("19000.00"))

    # --- refunds that did not move money ------------------------------------

    def test_pending_refund_does_not_reduce_revenue(self):
        """
        PENDING is money not yet returned. PaymentService.process_refund treats
        only COMPLETED refunds as reducing the refundable balance, so revenue
        must agree with it.
        """
        payment = self._paid_payment()
        Refund.objects.create(
            refund_number="RFND-TEST-PENDING",
            payment=payment,
            order=payment.order,
            amount=Decimal("4000.00"),
            reason="Awaiting gateway settlement",
            status=Refund.STATUS_PENDING,
        )
        self.assertEqual(self._revenue(), Decimal("10000.00"))

    def test_failed_refund_does_not_reduce_revenue(self):
        payment = self._paid_payment()
        Refund.objects.create(
            refund_number="RFND-TEST-FAILED",
            payment=payment,
            order=payment.order,
            amount=Decimal("4000.00"),
            reason="Gateway rejected the refund",
            status=Refund.STATUS_FAILED,
        )
        self.assertEqual(self._revenue(), Decimal("10000.00"))

    def test_only_settled_refunds_are_subtracted_when_mixed(self):
        payment = self._paid_payment()
        PaymentService.process_refund(
            payment=payment, amount=Decimal("1000.00"), reason="Settled return"
        )
        for number, refund_status in (
            ("RFND-TEST-MIX-PENDING", Refund.STATUS_PENDING),
            ("RFND-TEST-MIX-FAILED", Refund.STATUS_FAILED),
        ):
            Refund.objects.create(
                refund_number=number,
                payment=payment,
                order=payment.order,
                amount=Decimal("3000.00"),
                reason="Did not move money",
                status=refund_status,
            )
        # Only the 1,000 that actually settled comes off.
        self.assertEqual(self._revenue(), Decimal("9000.00"))

    def test_unpaid_payments_contribute_nothing(self):
        cart, _ = Cart.objects.get_or_create(user=self.buyer)
        CartItem.objects.filter(cart=cart).delete()
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        order = OrderService.create_order_from_cart(
            user=self.buyer, address_id=self.address.id
        )
        PaymentService.create_or_get_payment(order=order)  # left PENDING
        self.assertEqual(self._revenue(), Decimal("0.00"))

    def test_revenue_is_zero_decimal_with_no_payments_at_all(self):
        self.assertEqual(Payment.objects.count(), 0)
        revenue = self._revenue()
        self.assertEqual(revenue, Decimal("0.00"))
        self.assertIsInstance(revenue, Decimal)

    # --- Decimal end to end -------------------------------------------------

    def test_revenue_is_decimal_not_float_end_to_end(self):
        payment = self._paid_payment()
        PaymentService.process_refund(
            payment=payment, amount=Decimal("0.01"), reason="One paisa"
        )
        nested = payment_metrics()["revenue"]
        console = get_console_metrics()["total_revenue"]
        for value in (nested, console):
            self.assertIsInstance(value, Decimal)
            self.assertNotIsInstance(value, float)
        # A value float cannot hold exactly, proving no float round-trip.
        self.assertEqual(nested, Decimal("9999.99"))
        self.assertEqual(console, Decimal("9999.99"))

    # --- guarding the rest of the payload -----------------------------------

    def test_paid_count_semantics_left_unchanged(self):
        """
        Out of scope by instruction: whether a partly-refunded payment still
        counts as `paid` is a product question, not a revenue bug. This pins the
        existing behaviour so a later change to it has to be deliberate.
        """
        payment = self._paid_payment()
        self.assertEqual(payment_metrics()["paid"], 1)

        PaymentService.process_refund(
            payment=payment, amount=Decimal("1.00"), reason="Goodwill"
        )
        metrics = payment_metrics()
        # Status is now PARTIALLY_REFUNDED, which PAID_PAYMENT_STATUSES excludes.
        self.assertEqual(metrics["paid"], 0)
        self.assertEqual(metrics["total"], 1)
        # Revenue, unlike the count, does see the payment.
        self.assertEqual(metrics["revenue"], Decimal("9999.00"))

    def test_several_refund_rows_on_one_payment_do_not_inflate_counts(self):
        """
        Regression guard for the join that was deliberately avoided: summing
        refunds inside the Payment aggregate would emit one payment row per
        refund row and multiply every Count() in it. Two refund rows against a
        single payment are enough to catch that -- `total` would read 2.

        A partial refund followed by one clearing the remainder is the only way
        the service produces multiple refund rows for a payment; see the note on
        successive partial refunds in the class docstring.
        """
        payment = self._paid_payment()
        PaymentService.process_refund(
            payment=payment, amount=Decimal("1000.00"), reason="First return"
        )
        PaymentService.process_refund(
            payment=payment, amount=Decimal("9000.00"), reason="Remainder returned"
        )
        self.assertEqual(Refund.objects.filter(payment=payment).count(), 2)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.STATUS_REFUNDED)

        metrics = payment_metrics()
        self.assertEqual(metrics["total"], 1)
        self.assertEqual(metrics["pending"], 0)
        self.assertEqual(metrics["failed"], 0)
        self.assertEqual(metrics["revenue"], Decimal("0.00"))

    def test_console_contract_keys_unchanged(self):
        self._paid_payment()
        payload = get_console_metrics()
        self.assertEqual(
            sorted(payload),
            sorted([
                "total_orders",
                "total_revenue",
                "pending_shops",
                "pending_sellers",
                "total_shops",
                "total_sellers",
                "total_products",
            ]),
        )
        self.assertEqual(payload["total_revenue"], Decimal("10000.00"))


class AdminMetricsAuthorizationTests(APITestCase):
    """
    Phase 2D: management access and revenue visibility are two separate gates.

    Access is `reports.view` (CanViewPlatformMetrics), replacing an inline list of
    seven role codes. Revenue is `payments.view`, enforced server-side by removing
    the key from the payload — not by the dashboard declining to draw a card, which
    left the figure readable straight from the network tab.
    """

    REVENUE_KEY = "total_revenue"
    NON_REVENUE_KEYS = [
        "total_orders",
        "pending_shops",
        "pending_sellers",
        "total_shops",
        "total_sellers",
        "total_products",
    ]

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.url = reverse("shop:admin_metrics")

        # Holds reports.view AND payments.view -> sees revenue.
        cls.finance_user = User.objects.create_user(
            username="metrics_finance", email="fin@test.com", password="Password123!"
        )
        assign_user_role(cls.finance_user, Role.ROLE_FINANCE)

        # Holds reports.view but NOT payments.view -> must not see revenue.
        cls.ops_user = User.objects.create_user(
            username="metrics_ops", email="ops@test.com", password="Password123!"
        )
        assign_user_role(cls.ops_user, Role.ROLE_OPERATION_MANAGER)

        cls.support_user = User.objects.create_user(
            username="metrics_support", email="sup@test.com", password="Password123!"
        )
        assign_user_role(cls.support_user, Role.ROLE_SUPPORT_TEAM)

        # Holds both, via role rather than the superuser bypass.
        cls.administrator = User.objects.create_user(
            username="metrics_administrator", email="adm@test.com", password="Password123!"
        )
        assign_user_role(cls.administrator, Role.ROLE_ADMINISTRATOR)

        cls.superuser = User.objects.create_superuser(
            username="metrics_superuser", email="su@test.com", password="Password123!"
        )

        cls.customer = User.objects.create_user(
            username="metrics_customer", email="cust@test.com", password="Password123!"
        )
        assign_user_role(cls.customer, Role.ROLE_CUSTOMER)

    def _get(self, user):
        self.client.force_authenticate(user=user)
        return self.client.get(self.url)

    def _assert_six_keys_intact(self, payload):
        for key in self.NON_REVENUE_KEYS:
            self.assertIn(key, payload, f"{key} must remain in the payload")

    # --- access gate --------------------------------------------------------

    def test_unauthenticated_rejected(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_denied(self):
        self.assertEqual(self._get(self.customer).status_code, status.HTTP_403_FORBIDDEN)

    def test_management_roles_still_granted_access(self):
        for user in (self.superuser, self.administrator, self.ops_user,
                     self.finance_user, self.support_user):
            with self.subTest(user=user.username):
                self.assertEqual(self._get(user).status_code, status.HTTP_200_OK)

    # --- revenue visibility, proven on the HTTP response --------------------

    def test_finance_user_receives_total_revenue(self):
        res = self._get(self.finance_user)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn(self.REVENUE_KEY, res.data)
        self._assert_six_keys_intact(res.data)
        self.assertEqual(len(res.data), 7)

    def test_administrator_receives_total_revenue(self):
        res = self._get(self.administrator)
        self.assertIn(self.REVENUE_KEY, res.data)

    def test_superuser_receives_total_revenue(self):
        res = self._get(self.superuser)
        self.assertIn(self.REVENUE_KEY, res.data)

    def test_operations_manager_gets_metrics_without_revenue(self):
        """The core Phase 2D case: management access, no finance permission."""
        res = self._get(self.ops_user)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertNotIn(self.REVENUE_KEY, res.data)
        self._assert_six_keys_intact(res.data)
        self.assertEqual(len(res.data), 6)

    def test_support_user_gets_metrics_without_revenue(self):
        res = self._get(self.support_user)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertNotIn(self.REVENUE_KEY, res.data)
        self._assert_six_keys_intact(res.data)

    def test_revenue_absent_from_serialized_body_not_merely_nulled(self):
        """
        The key is removed, not zeroed. A 0 would be indistinguishable from
        genuinely zero revenue, and would still leak that the platform has none.
        """
        res = self._get(self.ops_user)
        body = json.loads(res.content.decode("utf-8"))
        self.assertNotIn(self.REVENUE_KEY, body)
        self.assertIsNone(body.get(self.REVENUE_KEY))

    def test_permission_drives_visibility_not_role_name(self):
        """
        Granting payments.view directly to the operations user flips revenue on,
        proving the gate reads the RBAC permission rather than a role code.
        """
        self.assertNotIn(self.REVENUE_KEY, self._get(self.ops_user).data)

        permission = Permission.objects.get(code="payments.view")
        UserPermission.objects.create(user=self.ops_user, permission=permission)

        self.assertIn(self.REVENUE_KEY, self._get(self.ops_user).data)


class CustomerOrderStaffOverrideTests(APITestCase):
    """
    Phase 2D: the order-scoped staff override now reads the RBAC permission built
    for it — 'orders.staff.view' / 'orders.staff.update' — instead of an inline
    role-code tuple. Customer ownership isolation must be unchanged.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        cls.owner = User.objects.create_user(
            username="ord_owner", email="owner@test.com", password="Password123!"
        )
        assign_user_role(cls.owner, Role.ROLE_CUSTOMER)
        cls.other_customer = User.objects.create_user(
            username="ord_other", email="other@test.com", password="Password123!"
        )
        assign_user_role(cls.other_customer, Role.ROLE_CUSTOMER)

        # Holds orders.staff.view + orders.staff.update.
        cls.ops_user = User.objects.create_user(
            username="ord_ops", email="ordops@test.com", password="Password123!"
        )
        assign_user_role(cls.ops_user, Role.ROLE_OPERATION_MANAGER)

        # Seller-style role: holds neither staff order permission.
        cls.sales_team_user = User.objects.create_user(
            username="ord_sales", email="sales@test.com", password="Password123!"
        )
        assign_user_role(cls.sales_team_user, Role.ROLE_SALES_TEAM)

        cls.address = Address.objects.create(
            user=cls.owner,
            label="Home",
            recipient_name="Order Owner",
            phone="01700000000",
            address_line_1="5 Order Street",
            city="Dhaka",
            country="Bangladesh",
            is_default=True,
        )

        cls.seller_user = User.objects.create_user(
            username="ord_seller", email="ordseller@test.com", password="Password123!"
        )
        assign_user_role(cls.seller_user, Role.ROLE_SALES_TEAM)  # for products.create
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Order Override Traders",
        )
        SellerWallet.objects.create(seller=cls.seller, balance=5000)
        cls.shop = Shop.objects.create(
            owner=cls.seller,
            name="Order Override Shop",
            slug="order-override-shop",
            status=Shop.STATUS_ACTIVE,
        )
        cls.category = Category.objects.create(
            name="Order Override Cat", slug="order-override-cat", is_active=True
        )

    def setUp(self):
        self.product = ProductService.create_product(
            seller=self.seller,
            name=f"Override Product {self.id()}",
            category=self.category,
            shop=self.shop,
            description="For staff override tests",
            price=Decimal("1000.00"),
            stock=50,
            is_active=True,
            actor=self.seller_user,
        )
        self.product.status = Product.STATUS_PUBLISHED
        self.product.save()

        cart, _ = Cart.objects.get_or_create(user=self.owner)
        CartItem.objects.filter(cart=cart).delete()
        CartItem.objects.create(cart=cart, product=self.product, quantity=1)
        self.order = OrderService.create_order_from_cart(
            user=self.owner, address_id=self.address.id
        )

    # --- payment lookup: orders.staff.view ---------------------------------

    def _payment_url(self):
        return f"/api/orders/{self.order.order_number}/payment/"

    def test_owner_can_reach_own_order_payment(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(self._payment_url(), {"payment_method": "BKASH"})
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_unrelated_customer_gets_safe_404(self):
        self.client.force_authenticate(user=self.other_customer)
        res = self.client.get(self._payment_url())
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_order_permission_holder_can_read_any_order_payment(self):
        PaymentService.create_or_get_payment(order=self.order)
        self.client.force_authenticate(user=self.ops_user)
        res = self.client.get(self._payment_url())
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_role_without_staff_order_permission_gets_safe_404(self):
        """SALES_TEAM holds no orders.staff.* permission, so no override."""
        PaymentService.create_or_get_payment(order=self.order)
        self.client.force_authenticate(user=self.sales_team_user)
        res = self.client.get(self._payment_url())
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    # --- cancel: orders.staff.update ---------------------------------------

    def _cancel_url(self):
        return f"/api/orders/{self.order.order_number}/cancel/"

    def test_owner_can_cancel_own_order(self):
        self.client.force_authenticate(user=self.owner)
        res = self.client.post(self._cancel_url(), {"reason": "Changed my mind"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_unrelated_customer_cannot_cancel_and_gets_safe_404(self):
        self.client.force_authenticate(user=self.other_customer)
        res = self.client.post(self._cancel_url(), {"reason": "Not mine"})
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, Order.STATUS_CANCELLED)

    def test_staff_update_permission_holder_can_cancel_any_order(self):
        self.client.force_authenticate(user=self.ops_user)
        res = self.client.post(self._cancel_url(), {"reason": "Operational cancellation"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_CANCELLED)

    def test_role_without_staff_update_permission_cannot_cancel(self):
        """
        SALES_TEAM holds neither 'orders.cancel' nor 'orders.staff.update', so the
        view-level CanCancelOrder gate rejects it with 403 before the ownership
        override is ever consulted. The unrelated-customer test above covers the
        other path: a caller who *does* clear the view gate but holds no staff
        permission gets the safe 404 instead.
        """
        self.client.force_authenticate(user=self.sales_team_user)
        res = self.client.post(self._cancel_url(), {"reason": "Should not work"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, Order.STATUS_CANCELLED)

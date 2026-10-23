"""
TASK-030: the Django admin dashboard and sidebar.

- BUG-038: revenue and the payment mix are shown only to accounts holding
  'payments.view', as the Console's metrics API already did.
- BUG-042: the sidebar carries the #nav-filter input Django's nav_sidebar.js
  looks up, so the script no longer throws on every admin page.
"""

from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from rbac.models import Role
from rbac.services import assign_user_role
from shop.models import Order, Payment

User = get_user_model()


class DashboardPaymentAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.support = User.objects.create_user(username="dash_support", password="Dash-Support-123", is_staff=True)
        assign_user_role(cls.support, Role.ROLE_SUPPORT_TEAM)
        cls.finance = User.objects.create_user(username="dash_finance", password="Dash-Finance-123", is_staff=True)
        assign_user_role(cls.finance, Role.ROLE_FINANCE)
        order = Order.objects.create(
            user=cls.support, order_number="ORD-DASH-1", subtotal=Decimal("4321.00"), total_amount=Decimal("4321.00"),
        )
        Payment.objects.create(
            order=order, user=cls.support, payment_number="PAY-DASH-1", status=Payment.STATUS_FAILED,
            payment_method=Payment.METHOD_CASH_ON_DELIVERY, amount=Decimal("4321.00"),
        )

    def dashboard(self, user):
        self.client.force_login(user)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        return response

    def test_staff_without_payments_view_see_no_finance_figures(self):
        response = self.dashboard(self.support)
        self.assertNotIn("payments", response.context["metrics"])
        self.assertNotContains(response, "Revenue collected")
        self.assertNotContains(response, "Failed or cancelled payments")
        # The rest of the dashboard is still there.
        self.assertContains(response, "Order mix")

    def test_finance_staff_see_them(self):
        response = self.dashboard(self.finance)
        self.assertIn("payments", response.context["metrics"])
        self.assertContains(response, "Revenue collected")
        self.assertContains(response, "Failed or cancelled payments")


class SidebarFilterInputTests(TestCase):
    def test_every_admin_page_has_the_input_nav_sidebar_js_needs(self):
        superuser = User.objects.create_superuser(username="dash_super", email="dash@example.com", password="Dash-Super-123")
        self.client.force_login(superuser)
        for url in (reverse("admin:index"), reverse("admin:shop_order_changelist")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "admin/js/nav_sidebar.js")
                self.assertContains(response, 'id="nav-filter"')

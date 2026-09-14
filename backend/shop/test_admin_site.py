"""
Smoke tests for the Django admin itself.

The suite previously exercised only the DRF API, so two admin classes shipped
referencing model fields that do not exist -- 7 admin.E108/E116 errors that
made manage.py check fail and runserver refuse to start. These tests walk the
registry so a broken list_display, or a newly registered model, is caught.
"""
from io import StringIO

from django.contrib import admin
from django.contrib.admin import helpers
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from audit.models import AuditLog
from sellers.models import SellerProfile
from shops.models import Shop

User = get_user_model()


class AdminSystemCheckTests(TestCase):
    def test_system_check_reports_no_issues(self):
        """manage.py check must stay clean -- this is the gate that was missing."""
        out, err = StringIO(), StringIO()
        call_command("check", stdout=out, stderr=err)
        self.assertIn("no issues", out.getvalue())


class AdminRegistrySmokeTests(TestCase):
    """Every registered changelist and add form must return 200."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="admin_smoke",
            email="admin_smoke@example.com",
            password="smokepassword123",
        )

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_every_changelist_loads(self):
        failures = []
        for model, model_admin in admin.site._registry.items():
            opts = model._meta
            url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
            response = self.client.get(url)
            if response.status_code != 200:
                failures.append(f"{opts.label} -> {response.status_code} ({url})")
        self.assertEqual(failures, [], f"Changelists did not return 200: {failures}")

    def test_every_add_form_loads(self):
        failures = []
        for model, model_admin in admin.site._registry.items():
            opts = model._meta
            if not model_admin.has_add_permission(self._request_for(model_admin)):
                continue
            url = reverse(f"admin:{opts.app_label}_{opts.model_name}_add")
            response = self.client.get(url)
            if response.status_code != 200:
                failures.append(f"{opts.label} -> {response.status_code} ({url})")
        self.assertEqual(failures, [], f"Add forms did not return 200: {failures}")

    def _request_for(self, model_admin):
        request = self.client.request().wsgi_request
        request.user = self.superuser
        return request

    def test_dashboard_exposes_platform_metrics(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        metrics = response.context["metrics"]
        for group in (
            "users",
            "sellers",
            "shops",
            "products",
            "orders",
            "payments",
            "inventory",
        ):
            self.assertIn(group, metrics)
        # Counts are real aggregates, and safe on a near-empty database.
        self.assertEqual(metrics["users"]["total"], User.objects.count())

    def test_dashboard_renders_taka_not_dollar(self):
        response = self.client.get(reverse("admin:index"))
        body = response.content.decode("utf-8")
        self.assertIn("৳", body)
        self.assertNotIn("$", body)


class ReasonRequiredActionTests(TestCase):
    """The suspend/reject actions must capture a real reason and audit it."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="admin_reason",
            email="admin_reason@example.com",
            password="reasonpassword123",
        )
        cls.seller_user = User.objects.create_user(
            username="reason_seller", email="reason_seller@example.com", password="x"
        )
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user,
            business_name="Reason Test Seller",
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
        )
        cls.url = reverse("admin:sellers_sellerprofile_changelist")

    def setUp(self):
        self.client.force_login(self.superuser)

    def _post(self, **extra):
        data = {
            "action": "suspend_sellers",
            helpers.ACTION_CHECKBOX_NAME: [str(self.seller.pk)],
        }
        data.update(extra)
        return self.client.post(self.url, data)

    def test_first_post_renders_the_reason_form(self):
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="reason"')
        self.assertContains(response, str(self.seller))
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.status, SellerProfile.STATUS_ACTIVE)

    def test_blank_reason_is_rejected_and_changes_nothing(self):
        response = self._post(apply_reason="1", reason="   ")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "at least")
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.status, SellerProfile.STATUS_ACTIVE)

    def test_short_reason_is_rejected(self):
        response = self._post(apply_reason="1", reason="bad")
        self.assertEqual(response.status_code, 200)
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.status, SellerProfile.STATUS_ACTIVE)

    def test_valid_reason_suspends_and_writes_one_audit_row(self):
        reason = "Repeated late dispatch on customer orders."
        response = self._post(apply_reason="1", reason=reason)
        self.assertEqual(response.status_code, 302)

        self.seller.refresh_from_db()
        self.assertEqual(self.seller.status, SellerProfile.STATUS_SUSPENDED)
        self.assertEqual(self.seller.suspension_reason, reason)

        logs = AuditLog.objects.filter(action="ADMIN_SELLER_SUSPEND")
        self.assertEqual(logs.count(), 1)
        log = logs.get()
        self.assertEqual(log.actor, self.superuser)
        self.assertEqual(log.target_id, str(self.seller.pk))
        self.assertEqual(log.metadata.get("reason"), reason)

    def test_reason_is_not_the_old_hardcoded_placeholder(self):
        self._post(apply_reason="1", reason="Genuine operator-supplied reason.")
        self.seller.refresh_from_db()
        self.assertNotEqual(self.seller.suspension_reason, "Suspended via admin action")


class ShopReasonActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="admin_shop_reason",
            email="admin_shop_reason@example.com",
            password="shoppassword123",
        )
        cls.seller_user = User.objects.create_user(
            username="shop_reason_seller",
            email="shop_reason_seller@example.com",
            password="x",
        )
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user,
            business_name="Shop Reason Seller",
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop = Shop.objects.create(
            owner=cls.seller,
            name="Reason Test Shop",
            status=Shop.STATUS_ACTIVE,
        )
        cls.url = reverse("admin:shops_shop_changelist")

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_valid_reason_suspends_shop_and_audits(self):
        reason = "Counterfeit goods reported by three customers."
        response = self.client.post(
            self.url,
            {
                "action": "suspend_shops",
                helpers.ACTION_CHECKBOX_NAME: [str(self.shop.pk)],
                "apply_reason": "1",
                "reason": reason,
            },
        )
        self.assertEqual(response.status_code, 302)

        self.shop.refresh_from_db()
        self.assertEqual(self.shop.status, Shop.STATUS_SUSPENDED)

        logs = AuditLog.objects.filter(action="ADMIN_SHOP_SUSPEND")
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.get().metadata.get("reason"), reason)

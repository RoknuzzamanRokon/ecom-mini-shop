"""
TASK-016: seller lifecycle transitions start only from their allowed statuses
(BUG-017), and a refused one is a 400 or an admin error message, never a 500
(BUG-050). Every action x status pair is tried on all three surfaces: the
/api/sellers/ staff routes, the Console status route and the Django admin
actions. A refused transition leaves the status and the audit log untouched.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from audit.admin_mixins import CONFIRM_FLAG, REASON_FIELD
from audit.models import AuditLog
from sellers.models import SellerProfile, SellerTransitionError

User = get_user_model()

S = SellerProfile
STATUSES = (S.STATUS_PENDING, S.STATUS_UNDER_REVIEW, S.STATUS_APPROVED,
            S.STATUS_ACTIVE, S.STATUS_SUSPENDED, S.STATUS_REJECTED)
ALLOWED = {
    "approve": {S.STATUS_PENDING, S.STATUS_UNDER_REVIEW, S.STATUS_REJECTED},
    "reject": {S.STATUS_PENDING, S.STATUS_UNDER_REVIEW},
    "suspend": {S.STATUS_APPROVED, S.STATUS_ACTIVE},
    "reactivate": {S.STATUS_SUSPENDED},
}
RESULT = {
    "approve": S.STATUS_ACTIVE,
    "reject": S.STATUS_REJECTED,
    "suspend": S.STATUS_SUSPENDED,
    "reactivate": S.STATUS_ACTIVE,
}
REASON = "Documents could not be verified."


class LifecycleCases:
    """Builds one seller per (action, status) case and checks the outcome."""

    def make_seller(self, start):
        n = SellerProfile.objects.count()
        user = User.objects.create_user(username=f"guard_seller_{n}", password="Guard-Seller-123")
        return SellerProfile.objects.create(
            user=user,
            business_name=f"Guard Seller {n}",
            status=start,
            suspension_reason="Under review." if start == S.STATUS_SUSPENDED else "",
            rejection_reason="Incomplete." if start == S.STATUS_REJECTED else "",
        )

    def audit_rows(self, seller, action):
        return AuditLog.objects.filter(
            action=f"ADMIN_SELLER_{action.upper()}", target_type="SellerProfile", target_id=str(seller.pk)
        ).count()

    def check_every_case(self, attempt):
        """`attempt(seller, action)` performs the action; it returns an HTTP status or None."""
        for action, allowed in ALLOWED.items():
            for start in STATUSES:
                with self.subTest(action=action, start=start):
                    seller = self.make_seller(start)
                    code = attempt(seller, action)
                    seller.refresh_from_db()
                    if start in allowed:
                        if code is not None:
                            self.assertEqual(code, status.HTTP_200_OK)
                        self.assertEqual(seller.status, RESULT[action])
                        self.assertEqual(self.audit_rows(seller, action), 1)
                    else:
                        if code is not None:
                            self.assertEqual(code, status.HTTP_400_BAD_REQUEST)
                        self.assertEqual(seller.status, start)
                        self.assertEqual(self.audit_rows(seller, action), 0)


class ModelGuardTests(TestCase):
    def test_refused_transition_is_a_typed_validation_error(self):
        seller = SellerProfile.objects.create(
            user=User.objects.create_user(username="guard_model", password="Guard-Model-123"),
            business_name="Guard Model",
            status=S.STATUS_SUSPENDED,
            suspension_reason="Under review.",
        )
        with self.assertRaises(SellerTransitionError) as caught:
            seller.approve(None)
        self.assertIn("Cannot approve a seller who is SUSPENDED", str(caught.exception))
        seller.refresh_from_db()
        self.assertEqual(seller.status, S.STATUS_SUSPENDED)


class StaffApiGuardTests(LifecycleCases, APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.staff = User.objects.create_superuser(
            username="guard_staff", email="guard@example.com", password="Guard-Staff-123"
        )

    def setUp(self):
        self.client.force_authenticate(user=self.staff)

    def test_sellers_routes(self):
        def attempt(seller, action):
            return self.client.post(f"/api/sellers/{seller.pk}/{action}/", {"reason": REASON}, format="json").status_code

        self.check_every_case(attempt)

    def test_console_status_route(self):
        def attempt(seller, action):
            return self.client.post(
                f"/api/admin/sellers/{seller.pk}/status/", {"action": action, "reason": REASON}, format="json"
            ).status_code

        self.check_every_case(attempt)


class DjangoAdminGuardTests(LifecycleCases, TestCase):
    ADMIN_ACTIONS = {
        "approve": "approve_and_activate",
        "reject": "reject_sellers",
        "suspend": "suspend_sellers",
        "reactivate": "reactivate_sellers",
    }

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            username="guard_admin", email="guard_admin@example.com", password="Guard-Admin-123"
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def test_admin_actions(self):
        def attempt(seller, action):
            response = self.client.post(
                reverse("admin:sellers_sellerprofile_changelist"),
                {
                    "action": self.ADMIN_ACTIONS[action],
                    "_selected_action": [str(seller.pk)],
                    CONFIRM_FLAG: "1",
                    REASON_FIELD: REASON,
                },
                follow=True,
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            if seller.status not in ALLOWED[action]:
                text = " ".join(str(m) for m in response.context["messages"])
                self.assertIn(f"Cannot {action} a seller who is {seller.status}", text)
            return None

        self.check_every_case(attempt)

"""
Turning one permission off for one account (rbac.UserPermissionBlock) and the
Console endpoint that does it (docs/SALES_TEAM_EDITS_PAYOUTS_PLAN.md §3).
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from audit.models import AuditLog
from .models import Permission, Role, UserPermission, UserPermissionBlock
from .services import assign_user_role, get_user_permissions, has_user_permission, users_with_permission

User = get_user_model()

CODE = "onboarding.products.view"


class PermissionBlockTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.sales = cls.make("block_sales", Role.ROLE_SALES_TEAM)
        cls.other_sales = cls.make("block_other_sales", Role.ROLE_SALES_TEAM)
        cls.admin = cls.make("block_admin", Role.ROLE_ADMINISTRATOR)
        cls.other_admin = cls.make("block_other_admin", Role.ROLE_ADMINISTRATOR)
        cls.superadmin = cls.make("block_superadmin", Role.ROLE_SUPER_ADMINISTRATOR)
        cls.operations = cls.make("block_operations", Role.ROLE_OPERATION_MANAGER)

    @classmethod
    def make(cls, username, role_code):
        user = User.objects.create_user(username=username, password="Block-Pass-123", is_staff=True)
        assign_user_role(user, role_code)
        return user

    def setUp(self):
        self.client = APIClient()

    def block(self, user, code=CODE):
        return UserPermissionBlock.objects.create(
            user=user, permission=Permission.objects.get(code=code), blocked_at=timezone.now(), reason="Test"
        )

    def post(self, actor, target, code=CODE, reason="Shared a product list outside the team", remove=False):
        self.client.force_authenticate(actor)
        suffix = "remove/" if remove else ""
        return self.client.post(
            f"/api/admin/users/{target.pk}/permission-blocks/{suffix}", {"code": code, "reason": reason}, format="json"
        )


class BlockResolutionTests(PermissionBlockTestCase):
    def test_a_block_takes_the_code_from_one_account_only(self):
        self.block(self.sales)
        self.assertNotIn(CODE, get_user_permissions(self.sales))
        self.assertFalse(has_user_permission(self.sales, CODE))
        self.assertIn("sellers.onboard", get_user_permissions(self.sales))
        self.assertIn(CODE, get_user_permissions(self.other_sales))

        holders = set(users_with_permission(CODE))
        self.assertNotIn(self.sales, holders)
        self.assertIn(self.other_sales, holders)

    def test_a_block_beats_a_direct_grant_too(self):
        UserPermission.objects.create(user=self.operations, permission=Permission.objects.get(code="reports.view"))
        self.block(self.operations, "reports.view")
        self.assertNotIn("reports.view", get_user_permissions(self.operations))

    def test_an_inactive_block_does_nothing(self):
        block = self.block(self.sales)
        block.is_active = False
        block.save()
        self.assertIn(CODE, get_user_permissions(self.sales))

    def test_the_wildcard_ignores_blocks(self):
        self.block(self.superadmin, "reports.view")
        self.assertTrue(has_user_permission(self.superadmin, "reports.view"))
        self.assertIn(self.superadmin, set(users_with_permission("reports.view")))


class ConsoleBlockTests(PermissionBlockTestCase):
    def test_an_administrator_turns_a_sales_team_permission_off_and_on(self):
        response = self.post(self.admin, self.sales)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertNotIn(CODE, response.data["permissions"])
        turned_off = response.data["turned_off_permissions"]
        self.assertEqual([(row["code"], row["blocked_by"]) for row in turned_off], [(CODE, "block_admin")])
        row = AuditLog.objects.get(action="USER_PERMISSION_BLOCKED")
        self.assertEqual((row.actor, row.metadata["permission"]), (self.admin, CODE))

        response = self.post(self.admin, self.sales, remove=True, reason="Back on the team")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn(CODE, response.data["permissions"])
        self.assertEqual(response.data["turned_off_permissions"], [])
        self.assertTrue(AuditLog.objects.filter(action="USER_PERMISSION_UNBLOCKED").exists())

        # Turning it off again reuses the row.
        self.post(self.admin, self.sales)
        self.assertEqual(UserPermissionBlock.objects.filter(user=self.sales).count(), 1)

    def test_who_may_be_limited(self):
        cases = (
            (self.admin, self.admin, status.HTTP_403_FORBIDDEN),  # oneself
            (self.admin, self.other_admin, status.HTTP_403_FORBIDDEN),  # a protected role
            (self.superadmin, self.other_admin, status.HTTP_200_OK),
            (self.operations, self.sales, status.HTTP_403_FORBIDDEN),  # no users.admin.manage
        )
        for actor, target, expected in cases:
            with self.subTest(actor=actor.username, target=target.username):
                code = CODE if target.username.endswith("sales") else "reports.view"
                self.assertEqual(self.post(actor, target, code=code).status_code, expected)

    def test_only_a_code_held_now_and_never_the_wildcard(self):
        response = self.post(self.admin, self.sales, code="payments.refund")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("does not hold", str(response.data["code"]))

        superuser = User.objects.create_superuser("block_root", password="Root-Pass-123")
        self.client.force_authenticate(superuser)
        response = self.client.post(
            f"/api/admin/users/{self.superadmin.pk}/permission-blocks/",
            {"code": "reports.view", "reason": "Test"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("full platform access", str(response.data["code"]))

    def test_a_reason_is_required_and_unknown_blocks_are_refused(self):
        self.assertEqual(self.post(self.admin, self.sales, reason=" ").status_code, status.HTTP_400_BAD_REQUEST)
        response = self.post(self.admin, self.sales, remove=True)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not turned off", str(response.data["code"]))

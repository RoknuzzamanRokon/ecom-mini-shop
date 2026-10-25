"""
BUG-101: switching a role on or off through the Console API needs the same
delegation rule as editing its permissions, as the Django admin already
enforces (rbac/test_admin_escalation.py): reactivating a role hands its
grants to every holder, deactivating one takes them away.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from rbac.models import Permission, Role, RolePermission, UserRole
from rbac.services import get_user_permissions

User = get_user_model()


class RoleActivationDelegationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())

        def role(code, *perms, active=True):
            made = Role.objects.create(code=code, name=code.title(), is_active=active)
            for perm in perms:
                RolePermission.objects.create(role=made, permission=Permission.objects.get(code=perm))
            return made

        manager_role = role("ROLE_MANAGER_101", "roles.admin.view", "roles.admin.manage", "orders.staff.view")
        cls.actor = User.objects.create_user(username="role_mgr_101", password="Role-Mgr-101", is_staff=True)
        UserRole.objects.create(user=cls.actor, role=manager_role, is_active=True)
        # Switched off to revoke refunds, which the actor cannot grant.
        cls.refunds = role("REFUND_DESK_101", "payments.refund", active=False)
        UserRole.objects.create(user=cls.actor, role=cls.refunds, is_active=True)
        cls.live_refunds = role("REFUND_LIVE_101", "payments.refund")
        cls.within_reach = role("ORDER_DESK_101", "orders.staff.view", active=False)

    def setUp(self):
        self.client.force_authenticate(user=self.actor)

    def patch(self, role, **data):
        return self.client.patch(f"/api/admin/roles/{role.pk}/", {**data, "reason": "Activation test"}, format="json")

    def test_reactivating_a_role_beyond_the_actor_is_refused(self):
        res = self.patch(self.refunds, is_active=True)

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.refunds.refresh_from_db()
        self.assertFalse(self.refunds.is_active)
        self.assertNotIn("payments.refund", get_user_permissions(self.actor))

    def test_deactivating_a_role_beyond_the_actor_is_refused(self):
        res = self.patch(self.live_refunds, is_active=False)

        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.live_refunds.refresh_from_db()
        self.assertTrue(self.live_refunds.is_active)

    def test_a_role_within_reach_can_be_switched_and_renamed_freely(self):
        self.assertEqual(self.patch(self.within_reach, is_active=True).status_code, status.HTTP_200_OK)
        # Renaming a role beyond reach, without touching is_active, stays allowed.
        self.assertEqual(self.patch(self.refunds, name="Refund desk (paused)").status_code, status.HTTP_200_OK)

    def test_a_superuser_may_do_either(self):
        root = User.objects.create_superuser(username="root_101", email="root101@example.com", password="Root-101-x")
        self.client.force_authenticate(user=root)
        self.assertEqual(self.patch(self.refunds, is_active=True).status_code, status.HTTP_200_OK)

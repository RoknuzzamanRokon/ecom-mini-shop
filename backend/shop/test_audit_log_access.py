"""
TASK-048 decision 8: only audit.view (or audit.admin.view) opens the full
audit log, which carries payment and refund details. Managing users or
roles no longer does. ADMINISTRATOR holds audit.view.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from rbac.models import Permission, Role, RolePermission, UserRole
from rbac.services import assign_user_role

User = get_user_model()
URL = "/api/admin/audit-logs/"


class AuditLogAccessTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())

    def user_with_role(self, username, *codes):
        role = Role.objects.create(code=f"AUDIT_TEST_{username.upper()}", name=f"Audit test {username}")
        for code in codes:
            RolePermission.objects.create(role=role, permission=Permission.objects.get(code=code))
        user = User.objects.create_user(username=username, password="Audit-Access-1", is_staff=True)
        UserRole.objects.create(user=user, role=role, is_active=True)
        return user

    def status_for(self, user):
        self.client.force_authenticate(user=user)
        return self.client.get(URL).status_code

    def test_user_and_role_managers_no_longer_read_the_log(self):
        manager = self.user_with_role("governance", "users.admin.view", "roles.admin.view")
        self.assertEqual(self.status_for(manager), status.HTTP_403_FORBIDDEN)

    def test_audit_view_opens_it(self):
        self.assertEqual(self.status_for(self.user_with_role("auditor", "audit.view")), status.HTTP_200_OK)

    def test_administrators_keep_access(self):
        admin = User.objects.create_user(username="audit_admin", password="Audit-Access-1", is_staff=True)
        assign_user_role(admin, Role.ROLE_ADMINISTRATOR)
        self.assertEqual(self.status_for(admin), status.HTTP_200_OK)
        self.assertTrue(
            RolePermission.objects.filter(role__code=Role.ROLE_ADMINISTRATOR, permission__code="audit.view").exists()
        )

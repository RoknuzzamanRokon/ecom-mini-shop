from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from rbac.models import Permission, Role, RolePermission

VIEW = "notifications.admin.view"
MANAGE = "notifications.admin.manage"
ALL_CODES = {VIEW, MANAGE}


class NotificationPermissionSeedTests(TestCase):
    """seed_rbac grants the notification codes as docs/NOTIFICATION_SYSTEM.md §7 says."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())

    def codes(self, role_code):
        return set(
            RolePermission.objects.filter(
                role__code=role_code, permission__code__startswith="notifications."
            ).values_list("permission__code", flat=True)
        )

    def test_both_codes_exist_under_the_notifications_resource(self):
        perms = Permission.objects.filter(code__in=ALL_CODES)
        self.assertEqual({p.code for p in perms}, ALL_CODES)
        self.assertTrue(all(p.resource == "notifications" for p in perms))

    def test_administrators_get_both_codes(self):
        for role_code in (Role.ROLE_ADMINISTRATOR, Role.ROLE_SUPER_ADMINISTRATOR):
            with self.subTest(role=role_code):
                self.assertEqual(self.codes(role_code), ALL_CODES)

    def test_operation_manager_can_view_only(self):
        self.assertEqual(self.codes(Role.ROLE_OPERATION_MANAGER), {VIEW})

    def test_other_roles_get_no_notification_codes(self):
        for role_code in (
            Role.ROLE_SALES_MANAGER, Role.ROLE_SALES_TEAM, Role.ROLE_FINANCE,
            Role.ROLE_SUPPORT_TEAM, Role.ROLE_CUSTOMER,
        ):
            with self.subTest(role=role_code):
                self.assertEqual(self.codes(role_code), set())

    def test_seed_revokes_notification_codes_granted_to_customer(self):
        customer_role = Role.objects.get(code=Role.ROLE_CUSTOMER)
        for code in ALL_CODES:
            RolePermission.objects.create(role=customer_role, permission=Permission.objects.get(code=code))

        call_command("seed_rbac", stdout=StringIO())

        self.assertEqual(self.codes(Role.ROLE_CUSTOMER), set())

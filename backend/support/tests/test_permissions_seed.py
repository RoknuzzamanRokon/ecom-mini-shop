from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from rbac.models import Permission, Role, RolePermission
from rbac.services import assign_user_role, has_user_permission

User = get_user_model()

CUSTOMER_CODES = {"support.view", "support.create"}
STAFF_CODES = {"support.staff.view", "support.staff.reply", "support.staff.manage"}
ALL_CODES = CUSTOMER_CODES | STAFF_CODES


class SupportPermissionSeedTests(TestCase):
    """seed_rbac grants the support codes exactly as docs/SUPPORT_SYSTEM.md §4 says."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())

    def support_codes(self, role_code):
        return set(
            RolePermission.objects.filter(
                role__code=role_code, permission__code__startswith="support."
            ).values_list("permission__code", flat=True)
        )

    def test_all_five_codes_exist(self):
        existing = set(
            Permission.objects.filter(code__in=ALL_CODES).values_list("code", flat=True)
        )
        self.assertEqual(existing, ALL_CODES)
        self.assertTrue(
            all(p.resource == "support" for p in Permission.objects.filter(code__in=ALL_CODES))
        )

    def test_customer_gets_own_ticket_codes_only(self):
        self.assertEqual(self.support_codes(Role.ROLE_CUSTOMER), CUSTOMER_CODES)

    def test_support_team_gets_every_staff_code(self):
        self.assertEqual(self.support_codes(Role.ROLE_SUPPORT_TEAM), STAFF_CODES)

    def test_administrator_gets_every_staff_code(self):
        self.assertEqual(self.support_codes(Role.ROLE_ADMINISTRATOR), STAFF_CODES)

    def test_operation_manager_can_view_and_reply_but_not_manage(self):
        self.assertEqual(
            self.support_codes(Role.ROLE_OPERATION_MANAGER),
            {"support.staff.view", "support.staff.reply"},
        )

    def test_other_roles_get_no_support_codes(self):
        for role_code in (Role.ROLE_SALES_MANAGER, Role.ROLE_SALES_TEAM, Role.ROLE_FINANCE):
            with self.subTest(role=role_code):
                self.assertEqual(self.support_codes(role_code), set())

    def test_super_administrator_gets_every_code(self):
        self.assertEqual(self.support_codes(Role.ROLE_SUPER_ADMINISTRATOR), ALL_CODES)

    def test_customer_user_resolves_to_customer_codes(self):
        user = User.objects.create_user(username="support_seed_customer", password="pw")
        assign_user_role(user, Role.ROLE_CUSTOMER)
        for code in CUSTOMER_CODES:
            self.assertTrue(has_user_permission(user, code), code)
        for code in STAFF_CODES:
            self.assertFalse(has_user_permission(user, code), code)

    def test_seed_revokes_staff_codes_granted_to_customer(self):
        customer_role = Role.objects.get(code=Role.ROLE_CUSTOMER)
        for code in STAFF_CODES:
            RolePermission.objects.create(
                role=customer_role, permission=Permission.objects.get(code=code)
            )
        self.assertEqual(self.support_codes(Role.ROLE_CUSTOMER), ALL_CODES)

        call_command("seed_rbac", stdout=StringIO())

        self.assertEqual(self.support_codes(Role.ROLE_CUSTOMER), CUSTOMER_CODES)
        # The guardrail only touches CUSTOMER.
        self.assertEqual(self.support_codes(Role.ROLE_SUPPORT_TEAM), STAFF_CODES)

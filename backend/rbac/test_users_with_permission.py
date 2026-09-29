"""
users_with_permission() is has_user_permission() run backwards, for choosing
who to notify (docs/NOTIFICATION_SYSTEM.md §3 D5). It must agree with it for
every active account, except that is_superuser alone doesn't count.
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from .models import Permission, Role, RolePermission, UserPermission, UserRole
from .services import assign_user_role, has_user_permission, users_with_permission

User = get_user_model()

CODE = "support.staff.manage"


class UsersWithPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        code = Permission.objects.get(code=CODE)
        other = Permission.objects.get(code="reports.view")
        wildcard = Permission.objects.create(code="*", name="Everything", resource="*", action="*")

        granting = Role.objects.create(code="UWP_GRANTING", name="Grants the code")
        RolePermission.objects.create(role=granting, permission=code)
        unrelated = Role.objects.create(code="UWP_UNRELATED", name="Grants something else")
        RolePermission.objects.create(role=unrelated, permission=other)
        retired = Role.objects.create(code="UWP_RETIRED", name="Retired role", is_active=False)
        RolePermission.objects.create(role=retired, permission=code)
        wildcard_role = Role.objects.create(code="UWP_WILDCARD", name="Wildcard role")
        RolePermission.objects.create(role=wildcard_role, permission=wildcard)

        def user(name, **flags):
            return User.objects.create_user(username=f"uwp_{name}", password="pw", **flags)

        def with_role(account, role, active=True):
            UserRole.objects.create(user=account, role=role, is_active=active)
            return account

        cls.expected = {
            "role": with_role(user("role"), granting),
            "direct": user("direct"),
            "super_admin_role": user("super_admin_role"),
            "wildcard_role": with_role(user("wildcard_role"), wildcard_role),
            "wildcard_direct": user("wildcard_direct"),
            "superuser_with_role": with_role(user("superuser_with_role", is_superuser=True), granting),
        }
        UserPermission.objects.create(user=cls.expected["direct"], permission=code)
        assign_user_role(cls.expected["super_admin_role"], Role.ROLE_SUPER_ADMINISTRATOR)
        UserPermission.objects.create(user=cls.expected["wildcard_direct"], permission=wildcard)

        cls.excluded = {
            "nobody": user("nobody"),
            "unrelated_role": with_role(user("unrelated_role"), unrelated),
            "inactive_assignment": with_role(user("inactive_assignment"), granting, active=False),
            "inactive_role": with_role(user("inactive_role"), retired),
            "revoked_direct": user("revoked_direct"),
            "superuser_only": user("superuser_only", is_superuser=True),
            "inactive_account": with_role(user("inactive_account", is_active=False), granting),
        }
        UserPermission.objects.create(user=cls.excluded["revoked_direct"], permission=code, is_active=False)

    def test_holders_through_roles_and_direct_grants(self):
        found = set(users_with_permission(CODE))
        for name, account in self.expected.items():
            with self.subTest(expected=name):
                self.assertIn(account, found)
        for name, account in self.excluded.items():
            with self.subTest(excluded=name):
                self.assertNotIn(account, found)

    def test_agrees_with_has_user_permission_for_active_accounts(self):
        """The one rule it drops is is_superuser, so compare with that flag cleared."""
        found = set(users_with_permission(CODE))
        for account in User.objects.filter(username__startswith="uwp_", is_active=True):
            with self.subTest(user=account.username):
                account.is_superuser = False  # in memory only
                self.assertEqual(account in found, has_user_permission(account, CODE))

    def test_superuser_flag_alone_is_not_enough(self):
        superuser = self.excluded["superuser_only"]
        self.assertTrue(has_user_permission(superuser, CODE))
        self.assertNotIn(superuser, users_with_permission(CODE))

    def test_each_holder_appears_once(self):
        account = self.expected["role"]
        UserPermission.objects.create(user=account, permission=Permission.objects.get(code=CODE))
        holders = list(users_with_permission(CODE))
        self.assertEqual(holders.count(account), 1)

    def test_revocation_takes_effect_immediately(self):
        account = self.expected["role"]
        UserRole.objects.filter(user=account).update(is_active=False)
        self.assertNotIn(account, users_with_permission(CODE))

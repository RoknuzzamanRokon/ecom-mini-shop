"""
Django-admin escalation paths (BUG-002) and locked direct grants (BUG-039).

Each test gives a non-wildcard staff account one Django model permission and
then tries to use it to raise its own MiniShop permissions. The actor's
effective permission set must come out unchanged.
"""

from io import StringIO

from django.contrib.auth.models import Group, Permission as AuthPermission, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Permission, Role, RolePermission, UserPermission, UserRole
from .services import assign_user_role, get_user_permissions

PASSWORD = "Escalation-Test-2026"


def django_perms(*labels):
    """AuthPermission rows for "app_label.codename" labels."""
    perms = []
    for label in labels:
        app_label, codename = label.split(".")
        perms.append(AuthPermission.objects.get(content_type__app_label=app_label, codename=codename))
    return perms


def user_form_payload(user, **overrides):
    """A valid POST for /admin/auth/user/<pk>/change/, role inline included."""
    data = {
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_active": "on",
        "last_login_0": "",
        "last_login_1": "",
        "date_joined_0": user.date_joined.strftime("%Y-%m-%d"),
        "date_joined_1": user.date_joined.strftime("%H:%M:%S"),
        "user_roles-MIN_NUM_FORMS": "0",
        "user_roles-MAX_NUM_FORMS": "1000",
        "_save": "Save",
    }
    rows = list(UserRole.objects.filter(user=user).order_by("pk"))
    for index, row in enumerate(rows):
        data[f"user_roles-{index}-id"] = str(row.pk)
        data[f"user_roles-{index}-user"] = str(user.pk)
        data[f"user_roles-{index}-role"] = str(row.role_id)
        if row.is_active:
            data[f"user_roles-{index}-is_active"] = "on"
    data["user_roles-TOTAL_FORMS"] = str(len(rows))
    data["user_roles-INITIAL_FORMS"] = str(len(rows))
    data.update(overrides)
    return data


class AdminEscalationTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.super_role = Role.objects.get(code=Role.ROLE_SUPER_ADMINISTRATOR)
        cls.held = Permission.objects.get(code="orders.staff.view")
        cls.not_held = Permission.objects.get(code="payments.refund")

        cls.own_role = Role.objects.create(code="OPS_LEAD", name="Ops Lead")
        RolePermission.objects.create(role=cls.own_role, permission=cls.held)

        cls.actor = User.objects.create_user(username="escalating_staff", password=PASSWORD, is_staff=True)
        UserRole.objects.create(user=cls.actor, role=cls.own_role)

        cls.superuser = User.objects.create_superuser(
            username="escalation_super", email="super@example.com", password=PASSWORD
        )

    def setUp(self):
        self.before = get_user_permissions(self.actor)
        self.client.force_login(self.actor)

    def give(self, *labels):
        self.actor.user_permissions.add(*django_perms(*labels))

    def assertNoEscalation(self):
        self.actor.refresh_from_db()
        self.assertFalse(self.actor.is_superuser)
        self.assertEqual(get_user_permissions(self.actor), self.before)
        self.assertNotIn("*", get_user_permissions(self.actor))


class RoleAdminPathTests(AdminEscalationTestCase):
    """(a) rbac.change_role"""

    def setUp(self):
        super().setUp()
        self.give("rbac.change_role", "rbac.view_role", "rbac.delete_role")

    def role_payload(self, role, **overrides):
        data = {
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "is_active": "on",
            "role_permissions": [str(pk) for pk in role.permissions.values_list("pk", flat=True)],
        }
        data.update(overrides)
        return data

    def test_cannot_rename_the_super_administrator_role(self):
        response = self.client.post(
            reverse("admin:rbac_role_change", args=[self.super_role.pk]),
            self.role_payload(self.super_role, code="RENAMED"),
        )
        self.assertEqual(response.status_code, 403)
        self.super_role.refresh_from_db()
        self.assertEqual(self.super_role.code, Role.ROLE_SUPER_ADMINISTRATOR)
        self.assertNoEscalation()

    def test_protected_role_is_shown_read_only(self):
        response = self.client.get(reverse("admin:rbac_role_change", args=[self.super_role.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="code"')

    def test_role_code_cannot_change_after_creation(self):
        response = self.client.post(
            reverse("admin:rbac_role_change", args=[self.own_role.pk]),
            self.role_payload(self.own_role, code=Role.ROLE_SUPER_ADMINISTRATOR),
        )
        self.assertEqual(response.status_code, 302)
        self.own_role.refresh_from_db()
        self.assertEqual(self.own_role.code, "OPS_LEAD")
        self.assertNoEscalation()

    def test_cannot_deactivate_a_protected_role_from_the_changelist(self):
        response = self.client.post(
            reverse("admin:rbac_role_changelist"),
            {
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(self.super_role.pk),
                # is_active left out: an unticked box
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.super_role.refresh_from_db()
        self.assertTrue(self.super_role.is_active)

    def test_cannot_reactivate_a_role_granting_permissions_the_actor_lacks(self):
        dormant = Role.objects.create(code="DORMANT", name="Dormant", is_active=False)
        RolePermission.objects.create(role=dormant, permission=self.not_held)
        UserRole.objects.create(user=self.actor, role=dormant)

        response = self.client.post(
            reverse("admin:rbac_role_change", args=[dormant.pk]),
            self.role_payload(dormant),
        )
        self.assertEqual(response.status_code, 403)
        dormant.refresh_from_db()
        self.assertFalse(dormant.is_active)
        self.assertNoEscalation()

    def test_cannot_create_a_role_with_a_protected_or_wildcard_code(self):
        self.give("rbac.add_role")
        for code in ("*", Role.ROLE_ADMINISTRATOR):
            with self.subTest(code=code):
                Role.objects.filter(code=code).exclude(pk__in=[self.super_role.pk]).delete()
                response = self.client.post(
                    reverse("admin:rbac_role_add"),
                    {"code": code, "name": "Crafted", "description": "", "is_active": "on"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "errorlist")
        self.assertNoEscalation()

    def test_protected_roles_are_never_deleted_here(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("admin:rbac_role_delete", args=[self.super_role.pk]), {"post": "yes"}
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("admin:rbac_role_changelist"),
            {"action": "delete_selected", "_selected_action": [str(self.super_role.pk)], "post": "yes"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Role.objects.filter(pk=self.super_role.pk).exists())


class PermissionAdminPathTests(AdminEscalationTestCase):
    """(b) rbac.change_permission"""

    def test_cannot_rename_a_held_permission_to_the_wildcard(self):
        self.give("rbac.change_permission", "rbac.view_permission")
        response = self.client.post(
            reverse("admin:rbac_permission_change", args=[self.held.pk]),
            {"code": "*", "name": self.held.name, "resource": self.held.resource,
             "action": self.held.action, "description": ""},
        )
        self.assertEqual(response.status_code, 403)
        self.held.refresh_from_db()
        self.assertEqual(self.held.code, "orders.staff.view")
        self.assertNoEscalation()

    def test_even_a_superuser_cannot_rename_or_mint_the_wildcard(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("admin:rbac_permission_change", args=[self.held.pk]),
            {"code": "*", "name": self.held.name, "resource": "x", "action": "y", "description": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.held.refresh_from_db()
        self.assertEqual(
            (self.held.code, self.held.resource, self.held.action), ("orders.staff.view", "orders", "view")
        )

        response = self.client.post(
            reverse("admin:rbac_permission_add"),
            {"code": "*", "name": "Everything", "resource": "all", "action": "all", "description": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Permission.objects.filter(code="*").exists())


class GrantRowAdminPathTests(AdminEscalationTestCase):
    """(c) add_userpermission, (d) add_rolepermission, (e) add/change_userrole"""

    def test_cannot_grant_oneself_a_permission(self):
        self.give("rbac.add_userpermission", "rbac.view_userpermission")
        response = self.client.post(
            reverse("admin:rbac_userpermission_add"),
            {"user": str(self.actor.pk), "permission": str(self.not_held.pk), "is_active": "on", "note": ""},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(UserPermission.objects.filter(user=self.actor).exists())
        self.assertNoEscalation()

    def test_cannot_add_a_permission_to_ones_own_role(self):
        self.give("rbac.add_rolepermission", "rbac.view_rolepermission")
        response = self.client.post(
            reverse("admin:rbac_rolepermission_add"),
            {"role": str(self.own_role.pk), "permission": str(self.not_held.pk)},
        )
        self.assertEqual(response.status_code, 403)
        self.assertNoEscalation()

    def test_cannot_assign_oneself_a_role(self):
        self.give("rbac.add_userrole", "rbac.view_userrole")
        response = self.client.post(
            reverse("admin:rbac_userrole_add"),
            {"user": str(self.actor.pk), "role": str(self.super_role.pk), "is_active": "on"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertNoEscalation()

    def test_cannot_reactivate_a_role_assignment_from_the_changelist(self):
        finance = Role.objects.get(code=Role.ROLE_FINANCE)
        row = UserRole.objects.create(user=self.actor, role=finance, is_active=False)
        self.give("rbac.change_userrole", "rbac.view_userrole")

        response = self.client.post(
            reverse("admin:rbac_userrole_changelist"),
            {
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-MIN_NUM_FORMS": "0",
                "form-MAX_NUM_FORMS": "1000",
                "form-0-id": str(row.pk),
                "form-0-is_active": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 403)
        row.refresh_from_db()
        self.assertFalse(row.is_active)
        self.assertNoEscalation()

    def test_role_inline_on_the_user_form_ignores_new_rows(self):
        self.give(
            "auth.change_user", "auth.view_user",
            "rbac.add_userrole", "rbac.change_userrole", "rbac.view_userrole",
        )
        page = self.client.get(reverse("admin:auth_user_change", args=[self.actor.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "OPS_LEAD")  # the cards still render, read-only
        self.assertNotContains(page, 'name="user_roles-0-is_active"')

        data = user_form_payload(self.actor)
        index = int(data["user_roles-TOTAL_FORMS"])
        data.update({
            f"user_roles-{index}-user": str(self.actor.pk),
            f"user_roles-{index}-role": str(self.super_role.pk),
            f"user_roles-{index}-is_active": "on",
            "user_roles-TOTAL_FORMS": str(index + 1),
        })
        response = self.client.post(reverse("admin:auth_user_change", args=[self.actor.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(UserRole.objects.filter(user=self.actor, role=self.super_role).exists())
        self.assertNoEscalation()

    def test_a_wildcard_holder_can_still_write_grant_rows(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("admin:rbac_userpermission_add"),
            {"user": str(self.actor.pk), "permission": str(self.not_held.pk), "is_active": "on", "note": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("payments.refund", get_user_permissions(self.actor))


class UserAdminPathTests(AdminEscalationTestCase):
    """(f) auth.change_user, plus auth.change_group"""

    def setUp(self):
        super().setUp()
        self.give("auth.change_user", "auth.view_user")
        self.django_perms_before = set(self.actor.user_permissions.values_list("pk", flat=True))

    def test_access_fields_on_ones_own_form_are_read_only(self):
        page = self.client.get(reverse("admin:auth_user_change", args=[self.actor.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'name="is_superuser"')
        self.assertNotContains(page, 'name="user_permissions"')

        group = Group.objects.create(name="Everything")
        group.permissions.set(AuthPermission.objects.all())
        data = user_form_payload(
            self.actor,
            first_name="Renamed",
            is_superuser="on",
            is_staff="on",
            user_permissions=[str(pk) for pk in AuthPermission.objects.values_list("pk", flat=True)],
            groups=[str(group.pk)],
        )
        response = self.client.post(reverse("admin:auth_user_change", args=[self.actor.pk]), data)
        self.assertEqual(response.status_code, 302)

        self.actor.refresh_from_db()
        self.assertEqual(self.actor.first_name, "Renamed")  # the save itself went through
        self.assertTrue(self.actor.is_staff)
        self.assertEqual(set(self.actor.user_permissions.values_list("pk", flat=True)), self.django_perms_before)
        self.assertFalse(self.actor.groups.exists())
        self.assertNoEscalation()

    def test_cannot_change_a_superusers_password(self):
        old_hash = self.superuser.password
        response = self.client.post(
            reverse("admin:auth_user_password_change", args=[self.superuser.pk]),
            {"password1": "Takeover-Pass-991", "password2": "Takeover-Pass-991"},
        )
        self.assertEqual(response.status_code, 403)
        self.superuser.refresh_from_db()
        self.assertEqual(self.superuser.password, old_hash)

    def test_cannot_edit_an_account_with_more_permissions(self):
        target = User.objects.create_user(username="finance_person", password=PASSWORD)
        assign_user_role(target, Role.ROLE_FINANCE)
        # Shown read-only, not hidden.
        self.assertEqual(self.client.get(reverse("admin:auth_user_change", args=[target.pk])).status_code, 200)
        response = self.client.post(
            reverse("admin:auth_user_change", args=[target.pk]),
            user_form_payload(target, is_active=""),
        )
        self.assertEqual(response.status_code, 403)
        target.refresh_from_db()
        self.assertTrue(target.is_active)

    def test_cannot_edit_an_account_holding_a_protected_role(self):
        target = User.objects.create_user(username="an_administrator", password=PASSWORD)
        assign_user_role(target, Role.ROLE_ADMINISTRATOR)
        response = self.client.post(
            reverse("admin:auth_user_password_change", args=[target.pk]),
            {"password1": "Takeover-Pass-991", "password2": "Takeover-Pass-991"},
        )
        self.assertEqual(response.status_code, 403)

    def test_can_still_edit_an_account_within_own_permissions(self):
        target = User.objects.create_user(username="plain_customer", password=PASSWORD)
        response = self.client.post(
            reverse("admin:auth_user_change", args=[target.pk]),
            user_form_payload(target, first_name="Edited"),
        )
        self.assertEqual(response.status_code, 302)
        target.refresh_from_db()
        self.assertEqual(target.first_name, "Edited")

    def test_can_edit_a_customer_account(self):
        """CUSTOMER's self-service codes do not count against the actor."""
        target = User.objects.create_user(username="a_customer", password=PASSWORD)
        assign_user_role(target, Role.ROLE_CUSTOMER)
        response = self.client.post(
            reverse("admin:auth_user_change", args=[target.pk]),
            user_form_payload(target, first_name="Edited"),
        )
        self.assertEqual(response.status_code, 302)

    def test_cannot_add_permissions_to_ones_own_group(self):
        group = Group.objects.create(name="Ops")
        self.actor.groups.add(group)
        self.give("auth.change_group", "auth.view_group")

        response = self.client.post(
            reverse("admin:auth_group_change", args=[group.pk]),
            {"name": "Ops", "permissions": [str(p.pk) for p in django_perms("rbac.add_userrole")]},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(group.permissions.exists())


class LockedDirectGrantTests(AdminEscalationTestCase):
    """BUG-039: saving a user form must not revoke the grants it rendered locked."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.superuser)

    def save_unchanged(self, target):
        # The locked checkboxes are disabled, so they post nothing at all.
        response = self.client.post(
            reverse("admin:auth_user_change", args=[target.pk]),
            user_form_payload(target),
        )
        self.assertEqual(response.status_code, 302)

    def test_grant_of_a_full_access_account_survives_a_save(self):
        target = User.objects.create_user(username="super_admin_holder", password=PASSWORD)
        assign_user_role(target, Role.ROLE_SUPER_ADMINISTRATOR)
        grant = UserPermission.objects.create(user=target, permission=self.not_held, granted_by=self.superuser)

        self.save_unchanged(target)

        grant.refresh_from_db()
        self.assertTrue(grant.is_active)

    def test_grant_also_given_by_a_role_survives_a_save(self):
        target = User.objects.create_user(username="ops_and_direct", password=PASSWORD)
        UserRole.objects.create(user=target, role=self.own_role)
        grant = UserPermission.objects.create(user=target, permission=self.held, granted_by=self.superuser)

        self.save_unchanged(target)

        grant.refresh_from_db()
        self.assertTrue(grant.is_active)

    def test_unlocked_grant_can_still_be_revoked(self):
        target = User.objects.create_user(username="plain_direct", password=PASSWORD)
        grant = UserPermission.objects.create(user=target, permission=self.not_held, granted_by=self.superuser)

        self.save_unchanged(target)  # its box is editable and unticked

        grant.refresh_from_db()
        self.assertFalse(grant.is_active)

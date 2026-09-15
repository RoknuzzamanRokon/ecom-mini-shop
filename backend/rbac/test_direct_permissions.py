"""
Direct per-user permission grants (rbac.UserPermission).

Roles remain the primary grant path; this table is the single-account
exception. These tests pin the two things that make that safe:

  1. get_user_permissions() returns role-derived UNION direct, and revoking a
     direct grant genuinely removes the access again.
  2. Only a superuser can create one. The Django admin fieldset swap is a UI
     affordance, so the server-side re-check in UserAdmin.save_related() is
     tested against a hand-crafted POST from a non-superuser.

Follows the conventions in tests.py: TestCase + seed_rbac in setUpTestData,
assign_user_role for role setup, assertions at both the service layer and over
HTTP.
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import Permission, Role, UserPermission, UserRole
from .services import assign_user_role, get_user_permissions, has_user_permission

User = get_user_model()

CUSTOMER_VIEW = "customers.admin.view"
REPORTS_VIEW = "reports.view"


class DirectPermissionResolutionTests(TestCase):
    """get_user_permissions() must union role-derived and direct grants."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.support = User.objects.create_user(
            username="direct_support", password="pass12345"
        )
        assign_user_role(cls.support, Role.ROLE_SUPPORT_TEAM)
        cls.roleless = User.objects.create_user(
            username="direct_roleless", password="pass12345"
        )
        cls.superadmin = User.objects.create_user(
            username="direct_superadmin", password="pass12345"
        )
        assign_user_role(cls.superadmin, Role.ROLE_SUPER_ADMINISTRATOR)

    def _grant(self, user, code, **kwargs):
        return UserPermission.objects.create(
            user=user, permission=Permission.objects.get(code=code), **kwargs
        )

    def test_direct_grant_adds_to_role_permissions(self):
        """A direct grant is unioned with, not substituted for, role permissions."""
        before = get_user_permissions(self.support)
        self.assertNotIn(CUSTOMER_VIEW, before)

        self._grant(self.support, CUSTOMER_VIEW)

        after = get_user_permissions(self.support)
        self.assertIn(CUSTOMER_VIEW, after)
        # Every role-derived permission survives the union.
        self.assertTrue(before.issubset(after))
        self.assertEqual(after - before, {CUSTOMER_VIEW})

    def test_direct_grant_works_without_any_role(self):
        """A user with no roles holds exactly their direct grants."""
        self._grant(self.roleless, REPORTS_VIEW)
        self.assertEqual(get_user_permissions(self.roleless), {REPORTS_VIEW})
        self.assertTrue(has_user_permission(self.roleless, REPORTS_VIEW))

    def test_inactive_grant_is_ignored(self):
        """Revoking flips is_active; the permission must stop resolving."""
        row = self._grant(self.roleless, REPORTS_VIEW)
        self.assertTrue(has_user_permission(self.roleless, REPORTS_VIEW))

        row.is_active = False
        row.save(update_fields=["is_active"])

        self.assertNotIn(REPORTS_VIEW, get_user_permissions(self.roleless))
        self.assertFalse(has_user_permission(self.roleless, REPORTS_VIEW))
        # The row itself survives, so the grant history is not lost.
        self.assertTrue(UserPermission.objects.filter(pk=row.pk).exists())

    def test_superadmin_wildcard_path_unchanged(self):
        """The superadmin short-circuit must not be affected by the union."""
        perms = get_user_permissions(self.superadmin)
        self.assertIn("*", perms)
        self.assertEqual(len(perms), Permission.objects.count() + 1)

    def test_duplicate_grant_is_rejected(self):
        """unique_together makes a second row for the same pair impossible."""
        self._grant(self.roleless, REPORTS_VIEW)
        with self.assertRaises(Exception):
            self._grant(self.roleless, REPORTS_VIEW)


class DirectPermissionEnforcementTests(TestCase):
    """A direct grant must be honoured by the real API permission classes."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        # SUPPORT_TEAM holds no customers.* permission of any kind.
        cls.support = User.objects.create_user(
            username="direct_api_support", password="pass12345"
        )
        assign_user_role(cls.support, Role.ROLE_SUPPORT_TEAM)

    def setUp(self):
        self.client = APIClient()

    def test_grant_then_revoke_flips_admin_customers_access(self):
        self.client.force_authenticate(user=self.support)

        # Before: the role grants nothing here.
        self.assertEqual(
            self.client.get("/api/admin/customers/").status_code,
            status.HTTP_403_FORBIDDEN,
        )

        row = UserPermission.objects.create(
            user=self.support,
            permission=Permission.objects.get(code=CUSTOMER_VIEW),
        )

        # After: CanViewAdminCustomers passes, with no role change at all.
        self.assertEqual(
            self.client.get("/api/admin/customers/").status_code,
            status.HTTP_200_OK,
        )

        # And /api/auth/me/ reports it, so the console unhides the module.
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertIn(CUSTOMER_VIEW, me.data["permissions"])
        self.assertEqual(me.data["roles"], [Role.ROLE_SUPPORT_TEAM])

        # Revoking returns the account to 403.
        row.is_active = False
        row.save(update_fields=["is_active"])
        self.assertEqual(
            self.client.get("/api/admin/customers/").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_grant_does_not_leak_neighbouring_permissions(self):
        """Granting the view code must not confer any mutation capability."""
        UserPermission.objects.create(
            user=self.support,
            permission=Permission.objects.get(code=CUSTOMER_VIEW),
        )
        perms = get_user_permissions(self.support)
        for code in (
            "users.admin.manage",
            "roles.admin.manage",
            "sellers.admin.manage",
            "products.admin.manage",
            "categories.admin.manage",
        ):
            self.assertNotIn(code, perms)


class DirectPermissionAdminFormTests(TestCase):
    """The user change form may only grant for superusers."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.superadmin = User.objects.create_superuser(
            username="direct_form_super", email="s@example.com", password="pass12345"
        )
        # Staff (so the admin site lets them in) but NOT a superuser.
        cls.staff = User.objects.create_user(
            username="direct_form_staff", password="pass12345", is_staff=True
        )
        assign_user_role(cls.staff, Role.ROLE_OPERATION_MANAGER)
        cls.staff.user_permissions.add(
            *__import__("django.contrib.auth.models", fromlist=["Permission"])
            .Permission.objects.filter(codename__in=["change_user", "view_user"])
        )

        cls.target = User.objects.create_user(
            username="direct_form_target", password="pass12345"
        )
        assign_user_role(cls.target, Role.ROLE_SUPPORT_TEAM)
        cls.customer_view = Permission.objects.get(code=CUSTOMER_VIEW)

    def _payload(self, **overrides):
        """Minimal valid POST for the user change form, incl. inline management form."""
        data = {
            "username": self.target.username,
            "password": self.target.password,
            "first_name": "",
            "last_name": "",
            "email": "",
            "last_login_0": "",
            "last_login_1": "",
            "date_joined_0": self.target.date_joined.strftime("%Y-%m-%d"),
            "date_joined_1": self.target.date_joined.strftime("%H:%M:%S"),
            "user_roles-TOTAL_FORMS": "0",
            "user_roles-INITIAL_FORMS": "0",
            "user_roles-MIN_NUM_FORMS": "0",
            "user_roles-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }
        data.update(overrides)
        return data

    def test_superuser_can_grant(self):
        self.client.force_login(self.superadmin)
        response = self.client.post(
            f"/admin/auth/user/{self.target.pk}/change/",
            self._payload(minishop_direct_permissions=[str(self.customer_view.pk)]),
        )
        self.assertEqual(response.status_code, 302)

        row = UserPermission.objects.get(user=self.target, permission=self.customer_view)
        self.assertTrue(row.is_active)
        self.assertEqual(row.granted_by, self.superadmin)
        self.assertIn(CUSTOMER_VIEW, get_user_permissions(self.target))

    def test_superuser_can_revoke_by_unticking(self):
        UserPermission.objects.create(
            user=self.target, permission=self.customer_view, granted_by=self.superadmin
        )
        self.client.force_login(self.superadmin)
        response = self.client.post(
            f"/admin/auth/user/{self.target.pk}/change/",
            self._payload(minishop_direct_permissions=[]),
        )
        self.assertEqual(response.status_code, 302)

        row = UserPermission.objects.get(user=self.target, permission=self.customer_view)
        self.assertFalse(row.is_active)
        self.assertNotIn(CUSTOMER_VIEW, get_user_permissions(self.target))

    def test_non_superuser_post_is_ignored(self):
        """
        The fieldset swap hides the field from non-superusers, so this is a
        hand-crafted POST -- exactly the case save_related() must reject.
        """
        self.client.force_login(self.staff)
        self.client.post(
            f"/admin/auth/user/{self.target.pk}/change/",
            self._payload(minishop_direct_permissions=[str(self.customer_view.pk)]),
        )
        self.assertFalse(
            UserPermission.objects.filter(user=self.target).exists(),
            "a non-superuser must not be able to create a direct grant",
        )
        self.assertNotIn(CUSTOMER_VIEW, get_user_permissions(self.target))

    def test_inherited_permission_is_not_duplicated_as_direct(self):
        """
        SUPPORT_TEAM already grants orders.staff.view. A POST asserting it must
        not create a direct row: the permission is not an exception.
        """
        inherited = Permission.objects.get(code="orders.staff.view")
        self.client.force_login(self.superadmin)
        self.client.post(
            f"/admin/auth/user/{self.target.pk}/change/",
            self._payload(minishop_direct_permissions=[str(inherited.pk)]),
        )
        self.assertFalse(
            UserPermission.objects.filter(
                user=self.target, permission=inherited
            ).exists()
        )
        # ...and it is of course still held, via the role.
        self.assertIn("orders.staff.view", get_user_permissions(self.target))

    def test_board_locks_inherited_rows_and_not_others(self):
        self.client.force_login(self.superadmin)
        html = self.client.get(
            f"/admin/auth/user/{self.target.pk}/change/"
        ).content.decode("utf-8", "replace")

        self.assertIn("minishop_direct_permissions", html)
        # Every catalogue entry is offered.
        self.assertEqual(
            html.count('name="minishop_direct_permissions"'),
            Permission.objects.count(),
        )
        # Inherited ones are disabled so the browser cannot submit them.
        self.assertIn("is-locked", html)

    def test_non_superuser_sees_read_only_board(self):
        self.client.force_login(self.staff)
        html = self.client.get(
            f"/admin/auth/user/{self.target.pk}/change/"
        ).content.decode("utf-8", "replace")
        self.assertNotIn('name="minishop_direct_permissions"', html)
        self.assertIn("ms-board", html)


class DirectPermissionEscalationCeilingTests(TestCase):
    """
    Interaction with the role-creation ceiling in shop/admin_views.py.

    AdminRoleListCreateAPIView refuses to mint a role carrying permissions the
    actor does not themselves possess ("Cannot assign permissions you do not
    possess"), and it measures possession with get_user_permissions(). Now that
    the resolver unions direct grants, a direct grant counts toward that ceiling.

    That is the intended reading, not an oversight: the rule is "you cannot hand
    out what you do not hold", and a direct grant is something the actor holds --
    deliberately given to them by a superuser, the only tier that can create one.
    These tests pin both halves so the behaviour cannot drift silently.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.actor = User.objects.create_user(
            username="ceiling_actor", password="pass12345"
        )
        assign_user_role(cls.actor, Role.ROLE_ADMINISTRATOR)
        cls.customer_view = Permission.objects.get(code=CUSTOMER_VIEW)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.actor)

    def test_cannot_mint_role_with_permission_actor_lacks(self):
        """Baseline: the ceiling still blocks a code the actor does not hold."""
        # Derived, not hardcoded: which codes ADMINISTRATOR lacks is a property
        # of seed_rbac.py and should not silently invalidate this test when the
        # seed changes.
        held = get_user_permissions(self.actor)
        missing = sorted(
            set(Permission.objects.values_list("code", flat=True)) - held
        )
        self.assertTrue(missing, "ADMINISTRATOR unexpectedly holds every permission")

        response = self.client.post(
            "/api/admin/roles/",
            {
                "code": "CEILING_TEST_A",
                "name": "Ceiling Test A",
                "permissions": [missing[0]],
                "reason": "test",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_direct_grant_raises_the_ceiling_for_that_code(self):
        """A directly-granted code becomes assignable, because the actor holds it."""
        # Strip it from the role so the ONLY source is the direct grant.
        role = Role.objects.get(code=Role.ROLE_ADMINISTRATOR)
        role.role_permissions.filter(permission=self.customer_view).delete()
        self.assertNotIn(CUSTOMER_VIEW, get_user_permissions(self.actor))

        UserPermission.objects.create(user=self.actor, permission=self.customer_view)
        self.assertIn(CUSTOMER_VIEW, get_user_permissions(self.actor))

        response = self.client.post(
            "/api/admin/roles/",
            {
                "code": "CEILING_TEST_B",
                "name": "Ceiling Test B",
                "permissions": [CUSTOMER_VIEW],
                "reason": "test",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class RoleAssignmentInlineTests(TestCase):
    """
    The role inline renders as cards (templates/admin/edit_inline/mp_role.html)
    instead of Django's stock table. These pin the formset plumbing that the
    custom markup has to keep emitting, and the assigned_by stamping that
    replaced the old unfiltered <select> of every user.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.superadmin = User.objects.create_superuser(
            username="inline_super", email="i@example.com", password="pass12345"
        )
        cls.target = User.objects.create_user(
            username="inline_target", password="pass12345"
        )
        cls.role = Role.objects.get(code=Role.ROLE_SUPPORT_TEAM)

    def setUp(self):
        self.client.force_login(self.superadmin)
        self.url = f"/admin/auth/user/{self.target.pk}/change/"

    def test_card_markup_keeps_formset_contract(self):
        html = self.client.get(self.url).content.decode("utf-8", "replace")

        # Stacked is the supported non-<tr> dispatch path in inlines.js.
        self.assertIn('data-inline-type="stacked"', html)
        self.assertIn('id="user_roles-group"', html)
        # inlines.js clones this node for "add another".
        self.assertIn('id="user_roles-empty"', html)
        self.assertIn('name="user_roles-TOTAL_FORMS"', html)
        self.assertIn('name="user_roles-INITIAL_FORMS"', html)
        self.assertIn("mp-role-card", html)
        # The stock table is gone.
        self.assertNotIn("<thead>", html)

    def test_assigned_by_is_stamped_not_chosen(self):
        """
        assigned_by is read-only in the card, so it must be filled in on save.
        It is an audit fact about who acted, not an operator choice.
        """
        html = self.client.get(self.url).content.decode("utf-8", "replace")
        self.assertNotIn('name="user_roles-0-assigned_by"', html)

        response = self.client.post(
            self.url,
            {
                "username": self.target.username,
                "password": self.target.password,
                "first_name": "",
                "last_name": "",
                "email": "",
                "last_login_0": "",
                "last_login_1": "",
                "date_joined_0": self.target.date_joined.strftime("%Y-%m-%d"),
                "date_joined_1": self.target.date_joined.strftime("%H:%M:%S"),
                "user_roles-TOTAL_FORMS": "1",
                "user_roles-INITIAL_FORMS": "0",
                "user_roles-MIN_NUM_FORMS": "0",
                "user_roles-MAX_NUM_FORMS": "1000",
                "user_roles-0-id": "",
                "user_roles-0-user": str(self.target.pk),
                "user_roles-0-role": str(self.role.pk),
                "user_roles-0-is_active": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)

        assignment = UserRole.objects.get(user=self.target, role=self.role)
        self.assertEqual(assignment.assigned_by, self.superadmin)
        self.assertTrue(assignment.is_active)
        # And the role's permissions are now live for that account.
        self.assertIn("orders.staff.view", get_user_permissions(self.target))

    def test_card_shows_what_the_role_grants(self):
        UserRole.objects.create(
            user=self.target, role=self.role, assigned_by=self.superadmin
        )
        html = self.client.get(self.url).content.decode("utf-8", "replace")
        expected = self.role.role_permissions.count()
        self.assertIn(f"<b>{expected}</b>&nbsp;Permissions", html)
        self.assertIn(self.role.code, html)
        self.assertIn(self.role.name, html)
        # The card links to where the role's permissions can actually be edited.
        self.assertIn(f"/admin/rbac/role/{self.role.pk}/change/", html)

    def test_status_and_remove_controls_keep_their_inputs(self):
        """
        The pill and the remove controls are labels over the real checkboxes.
        If the inputs ever stop rendering, the form silently stops round-tripping
        is_active and deletion, so both are pinned here.
        """
        UserRole.objects.create(
            user=self.target, role=self.role, assigned_by=self.superadmin
        )
        html = self.client.get(self.url).content.decode("utf-8", "replace")

        self.assertIn('name="user_roles-0-is_active"', html)
        self.assertIn('name="user_roles-0-DELETE"', html)
        self.assertIn("mp-role-status-pill", html)
        self.assertIn("mp-role-remove", html)
        # Both the header x and the footer link drive the same DELETE input.
        self.assertEqual(html.count('for="id_user_roles-0-DELETE"'), 2)

    def test_no_unrendered_template_syntax(self):
        """A multi-line {# #} comment renders as literal text; guard against it."""
        html = self.client.get(self.url).content.decode("utf-8", "replace")
        self.assertNotIn("{#", html)
        self.assertNotIn("{%", html)

    def test_deactivating_via_the_pill_round_trips(self):
        """Unticking the pill's checkbox must deactivate the assignment."""
        UserRole.objects.create(
            user=self.target, role=self.role, assigned_by=self.superadmin
        )
        response = self.client.post(
            self.url,
            {
                "username": self.target.username,
                "password": self.target.password,
                "first_name": "",
                "last_name": "",
                "email": "",
                "last_login_0": "",
                "last_login_1": "",
                "date_joined_0": self.target.date_joined.strftime("%Y-%m-%d"),
                "date_joined_1": self.target.date_joined.strftime("%H:%M:%S"),
                "user_roles-TOTAL_FORMS": "1",
                "user_roles-INITIAL_FORMS": "1",
                "user_roles-MIN_NUM_FORMS": "0",
                "user_roles-MAX_NUM_FORMS": "1000",
                "user_roles-0-id": str(
                    UserRole.objects.get(user=self.target, role=self.role).pk
                ),
                "user_roles-0-user": str(self.target.pk),
                "user_roles-0-role": str(self.role.pk),
                # is_active omitted == unchecked
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            UserRole.objects.get(user=self.target, role=self.role).is_active
        )
        # A deactivated role stops granting.
        self.assertNotIn("orders.staff.view", get_user_permissions(self.target))

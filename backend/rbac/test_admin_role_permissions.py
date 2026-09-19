"""
Contract tests for the role permission board.

The board (rbac.widgets.RolePermissionWidget + RoleAdminForm/RoleAdmin) replaces
the RolePermission TabularInline on /admin/rbac/role/add/ and .../change/. It is
a different way to edit the same RolePermission rows, so what these tests pin
down is the data contract: the whole catalogue is offered, a POST saves exactly
what was ticked, untouched grants are left alone, and the delegation boundary
the role API enforces is enforced here too.
"""
from django.contrib.auth.models import Permission as AuthPermission, User
from django.test import TestCase
from django.urls import reverse

from rbac.models import Permission, Role, RolePermission, UserRole


class RolePermissionBoardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(
            username="role_admin", email="role@example.com", password="pw-role-1"
        )
        cls.view_products = Permission.objects.create(
            code="products.view", name="View Products", resource="products", action="view"
        )
        cls.approve_products = Permission.objects.create(
            code="products.approve",
            name="Approve Products",
            resource="products",
            action="approve",
        )
        cls.view_orders = Permission.objects.create(
            code="orders.view", name="View Orders", resource="orders", action="view"
        )
        cls.refund_orders = Permission.objects.create(
            code="orders.refund", name="Refund Orders", resource="orders", action="refund"
        )
        cls.all_permissions = [
            cls.view_products,
            cls.approve_products,
            cls.view_orders,
            cls.refund_orders,
        ]

    def setUp(self):
        self.client.force_login(self.admin)
        self.add_url = reverse("admin:rbac_role_add")

    # -- payload ----------------------------------------------------------

    def _payload(self, permission_ids=(), **overrides):
        """A complete, valid POST for the role form. No inline formset keys:
        the board replaced the inline, so none are expected any more."""
        data = {
            "code": "OPS_REVIEW",
            "name": "Operations Review",
            "description": "",
            "is_active": "on",
            "role_permissions": [str(pk) for pk in permission_ids],
        }
        data.update(overrides)
        return data

    def _change_url(self, role):
        return reverse("admin:rbac_role_change", args=[role.pk])

    def _codes(self, role):
        return set(
            RolePermission.objects.filter(role=role).values_list(
                "permission__code", flat=True
            )
        )

    # -- rendering --------------------------------------------------------

    def test_add_page_offers_every_permission_unchecked(self):
        response = self.client.get(self.add_url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        for permission in self.all_permissions:
            self.assertInHTML(
                '<input type="checkbox" class="rp-input" name="role_permissions" '
                'value="%d" id="id_role_permissions_%d" data-pm-perm>'
                % (permission.pk, permission.pk),
                html,
            )

    def test_add_page_no_longer_renders_the_inline_formset(self):
        response = self.client.get(self.add_url)
        self.assertNotContains(response, "role_permissions-TOTAL_FORMS")

    def test_change_page_checks_the_roles_current_grants(self):
        role = Role.objects.create(code="OPS", name="Ops")
        RolePermission.objects.create(role=role, permission=self.view_orders)

        response = self.client.get(self._change_url(role))
        html = response.content.decode()

        self.assertInHTML(
            '<input type="checkbox" class="rp-input" name="role_permissions" '
            'value="%d" id="id_role_permissions_%d" data-pm-perm checked>'
            % (self.view_orders.pk, self.view_orders.pk),
            html,
        )
        self.assertInHTML(
            '<input type="checkbox" class="rp-input" name="role_permissions" '
            'value="%d" id="id_role_permissions_%d" data-pm-perm>'
            % (self.refund_orders.pk, self.refund_orders.pk),
            html,
        )

    def test_board_groups_permissions_by_resource(self):
        response = self.client.get(self.add_url)
        html = response.content.decode()

        self.assertIn('data-pm-section="products"', html)
        self.assertIn('data-pm-section="orders"', html)
        # RESOURCE_META weights orders (80) after products (50).
        self.assertLess(
            html.index('data-pm-section="products"'),
            html.index('data-pm-section="orders"'),
        )

    # -- saving -----------------------------------------------------------

    def test_add_saves_the_ticked_permissions(self):
        response = self.client.post(
            self.add_url,
            self._payload([self.view_products.pk, self.view_orders.pk]),
        )
        self.assertEqual(response.status_code, 302)

        role = Role.objects.get(code="OPS_REVIEW")
        self.assertEqual(self._codes(role), {"products.view", "orders.view"})

    def test_add_with_nothing_ticked_creates_a_role_without_grants(self):
        response = self.client.post(self.add_url, self._payload())
        self.assertEqual(response.status_code, 302)

        role = Role.objects.get(code="OPS_REVIEW")
        self.assertEqual(self._codes(role), set())

    def test_change_adds_and_removes_to_match_the_submission(self):
        role = Role.objects.create(code="OPS_REVIEW", name="Operations Review")
        RolePermission.objects.create(role=role, permission=self.view_products)
        RolePermission.objects.create(role=role, permission=self.refund_orders)

        response = self.client.post(
            self._change_url(role),
            self._payload([self.view_products.pk, self.view_orders.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._codes(role), {"products.view", "orders.view"})

    def test_change_with_nothing_ticked_clears_every_grant(self):
        role = Role.objects.create(code="OPS_REVIEW", name="Operations Review")
        RolePermission.objects.create(role=role, permission=self.view_products)

        response = self.client.post(self._change_url(role), self._payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._codes(role), set())

    def test_untouched_grants_keep_their_original_row(self):
        """The board diffs; it does not clear and recreate. An unchanged grant
        keeps its row, so `created_at` still records when it was really made."""
        role = Role.objects.create(code="OPS_REVIEW", name="Operations Review")
        kept = RolePermission.objects.create(role=role, permission=self.view_products)

        self.client.post(
            self._change_url(role),
            self._payload([self.view_products.pk, self.view_orders.pk]),
        )

        reloaded = RolePermission.objects.get(role=role, permission=self.view_products)
        self.assertEqual(reloaded.pk, kept.pk)
        self.assertEqual(reloaded.created_at, kept.created_at)


class RoleBoardDelegationTests(TestCase):
    """
    "You may only give away what you already hold."

    rbac.services.get_undelegatable_permission_codes is what the role API
    enforces; the board applies the same rule so the admin cannot be the shorter
    path to a permission the API would refuse to grant.
    """

    @classmethod
    def setUpTestData(cls):
        cls.view_orders = Permission.objects.create(
            code="orders.view", name="View Orders", resource="orders", action="view"
        )
        cls.refund_orders = Permission.objects.create(
            code="orders.refund", name="Refund Orders", resource="orders", action="refund"
        )

        # A staff operator who may edit roles in the admin, holds orders.view
        # through a role of their own, and is not a wildcard holder.
        cls.operator = User.objects.create_user(
            username="role_operator",
            email="operator@example.com",
            password="pw-operator-1",
            is_staff=True,
        )
        cls.operator.user_permissions.set(
            AuthPermission.objects.filter(
                content_type__app_label="rbac",
                codename__in=["add_role", "change_role", "view_role"],
            )
        )
        own_role = Role.objects.create(code="OPS_LEAD", name="Ops Lead")
        RolePermission.objects.create(role=own_role, permission=cls.view_orders)
        UserRole.objects.create(user=cls.operator, role=own_role)

    def setUp(self):
        self.client.force_login(self.operator)

    def _codes(self, role):
        return set(
            RolePermission.objects.filter(role=role).values_list(
                "permission__code", flat=True
            )
        )

    def test_undelegatable_permission_renders_locked(self):
        response = self.client.get(reverse("admin:rbac_role_add"))
        html = response.content.decode()

        self.assertInHTML(
            '<input type="checkbox" class="rp-input" name="role_permissions" '
            'value="%d" id="id_role_permissions_%d" data-pm-perm>'
            % (self.view_orders.pk, self.view_orders.pk),
            html,
        )
        self.assertInHTML(
            '<input type="checkbox" class="rp-input" name="role_permissions" '
            'value="%d" id="id_role_permissions_%d" data-pm-perm disabled>'
            % (self.refund_orders.pk, self.refund_orders.pk),
            html,
        )

    def test_crafted_post_cannot_grant_an_undelegatable_permission(self):
        response = self.client.post(
            reverse("admin:rbac_role_add"),
            {
                "code": "CRAFTED",
                "name": "Crafted",
                "description": "",
                "is_active": "on",
                "role_permissions": [
                    str(self.view_orders.pk),
                    str(self.refund_orders.pk),
                ],
            },
        )
        self.assertEqual(response.status_code, 302)

        role = Role.objects.get(code="CRAFTED")
        self.assertEqual(self._codes(role), {"orders.view"})

    def test_a_locked_grant_is_not_revoked_by_saving_the_form(self):
        """A locked checkbox is disabled, so it submits nothing. That must read
        as "leave it alone", never as "revoke it"."""
        role = Role.objects.create(code="FINANCE_OPS", name="Finance Ops")
        RolePermission.objects.create(role=role, permission=self.refund_orders)

        response = self.client.post(
            reverse("admin:rbac_role_change", args=[role.pk]),
            {
                "code": "FINANCE_OPS",
                "name": "Finance Ops",
                "description": "",
                "is_active": "on",
                "role_permissions": [str(self.view_orders.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._codes(role), {"orders.view", "orders.refund"})

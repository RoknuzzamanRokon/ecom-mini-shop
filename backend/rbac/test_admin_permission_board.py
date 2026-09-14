"""
Contract tests for the auth.User permission board.

The board (rbac.widgets.PermissionMatrixWidget +
templates/admin/auth/user/change_form.html) replaces the two
FilteredSelectMultiple panes BaseUserAdmin renders for `groups` and
`user_permissions`. It is only a different way to draw the same
CheckboxSelectMultiple inputs, so what these tests pin down is that the form
contract did not move: every permission is still offered, the POST still saves
exactly what was checked, and clearing every box still clears the M2M.
"""
import re

from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rbac.models import Role, UserRole
from rbac.widgets import GroupCardsWidget, PermissionMatrixWidget


class PermissionBoardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            username="board_admin", email="board@example.com", password="pw-board-1"
        )
        cls.target = User.objects.create_user(
            username="board_target", email="target@example.com", password="pw-target-1"
        )
        cls.role = Role.objects.create(code="BOARD_ROLE", name="Board Role")

    def setUp(self):
        self.client.force_login(self.staff)
        self.url = reverse("admin:auth_user_change", args=[self.target.pk])

    # -- form payload -----------------------------------------------------

    def _payload(self, permission_ids=(), **overrides):
        """A complete, valid POST for the user change form."""
        joined = timezone.localtime(self.target.date_joined)
        data = {
            "username": self.target.username,
            "first_name": "",
            "last_name": "",
            "email": self.target.email,
            "date_joined_0": joined.strftime("%Y-%m-%d"),
            "date_joined_1": joined.strftime("%H:%M:%S"),
            "last_login_0": "",
            "last_login_1": "",
            "is_active": "on",
            "user_permissions": [str(pk) for pk in permission_ids],
            "user_roles-TOTAL_FORMS": "0",
            "user_roles-INITIAL_FORMS": "0",
            "user_roles-MIN_NUM_FORMS": "0",
            "user_roles-MAX_NUM_FORMS": "1000",
        }
        data.update(overrides)
        return data

    # -- rendering --------------------------------------------------------

    def test_change_page_renders_the_board_not_the_filter_widget(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-pm-board")
        # SelectBox/selector-available are the FilteredSelectMultiple markup.
        self.assertNotContains(response, "selector-available")

    def test_every_permission_is_offered_as_a_checkbox(self):
        response = self.client.get(self.url)
        html = response.content.decode()

        total = Permission.objects.count()
        self.assertEqual(html.count('name="user_permissions"'), total)

        # Grouped by app, one <section> per app_label present.
        app_labels = set(
            Permission.objects.values_list("content_type__app_label", flat=True)
        )
        for label in app_labels:
            self.assertIn('data-pm-section="%s"' % label, html)

    def test_only_granted_permissions_render_checked(self):
        granted = list(Permission.objects.order_by("pk")[:3])
        self.target.user_permissions.set(granted)

        html = self.client.get(self.url).content.decode()
        checked = {
            int(pk)
            for pk in re.findall(
                r'id="id_user_permissions_(\d+)"[^>]*\schecked\b', html
            )
        }

        self.assertEqual(checked, {p.pk for p in granted})

    # -- round trip -------------------------------------------------------

    def test_posting_the_board_saves_exactly_what_was_checked(self):
        picks = list(Permission.objects.order_by("pk")[:4])

        response = self.client.post(self.url, self._payload([p.pk for p in picks]))

        self.assertEqual(response.status_code, 302, response.context["errors"] if response.status_code == 200 else "")
        self.assertQuerySetEqual(
            self.target.user_permissions.order_by("pk"), picks, transform=lambda p: p
        )

    def test_posting_with_no_boxes_checked_clears_the_permissions(self):
        self.target.user_permissions.set(Permission.objects.order_by("pk")[:4])

        response = self.client.post(self.url, self._payload([]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.target.user_permissions.count(), 0)

    def test_status_switches_still_save(self):
        response = self.client.post(
            self.url, self._payload([], is_staff="on", is_superuser="on")
        )

        self.assertEqual(response.status_code, 302)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_staff)
        self.assertTrue(self.target.is_superuser)

    def test_role_inline_still_saves_from_the_roles_tab(self):
        data = self._payload(
            [],
            **{
                "user_roles-TOTAL_FORMS": "1",
                "user_roles-0-role": str(self.role.pk),
                "user_roles-0-user": str(self.target.pk),
                "user_roles-0-is_active": "on",
            }
        )

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            UserRole.objects.filter(user=self.target, role=self.role, is_active=True).exists()
        )


class PermissionMatrixWidgetTests(TestCase):
    def _context(self, value=()):
        widget = PermissionMatrixWidget()
        widget.choices = _FakeChoices(
            Permission.objects.select_related("content_type").order_by(
                "content_type__app_label", "content_type__model", "codename"
            )
        )
        return widget.get_context("user_permissions", list(value), {"id": "id_user_permissions"})[
            "widget"
        ]

    def test_counts_match_the_queryset(self):
        context = self._context()

        self.assertEqual(context["total"], Permission.objects.count())
        self.assertEqual(context["granted"], 0)
        self.assertEqual(
            sum(section["total"] for section in context["sections"]), context["total"]
        )

    def test_selected_values_are_marked_granted(self):
        picks = list(Permission.objects.order_by("pk")[:5])

        context = self._context([p.pk for p in picks])

        self.assertEqual(context["granted"], len(picks))

    def test_crud_codenames_land_in_action_cells(self):
        context = self._context()
        rows = [row for section in context["sections"] for row in section["rows"]]
        by_key = {row["key"]: row for row in rows}

        user_row = by_key["auth.user"]
        actions = [cell["action"] for cell in user_row["cells"] if not cell["empty"]]

        self.assertEqual(actions, ["view", "add", "change", "delete"])
        self.assertEqual(user_row["extras"], [])

    def test_sections_are_ordered_by_the_rail_weighting(self):
        context = self._context()
        keys = [section["key"] for section in context["sections"]]

        # shop carries the storefront models and leads; the plumbing sinks.
        self.assertLess(keys.index("shop"), keys.index("auth"))
        self.assertLess(keys.index("auth"), keys.index("sessions"))


class WidgetTemplateResolutionTests(TestCase):
    """
    The board templates live in TEMPLATES["DIRS"], which settings.FORM_RENDERER
    (Django's default DjangoTemplates) never searches -- it sees only
    django/forms/templates plus each app's templates/ dir, from a list that is
    lru_cached for the life of the process. The widgets therefore override
    render() to go through django.template.loader. Calling render() directly is
    what pins that down: drop the override and these raise TemplateDoesNotExist.
    """

    def test_permission_matrix_renders_through_the_project_engine(self):
        widget = PermissionMatrixWidget()
        widget.choices = _FakeChoices(
            Permission.objects.select_related("content_type")
        )

        html = widget.render("user_permissions", [], {"id": "id_user_permissions"})

        self.assertIn("data-pm-board", html)
        self.assertEqual(
            html.count('name="user_permissions"'), Permission.objects.count()
        )

    def test_group_cards_render_through_the_project_engine(self):
        widget = GroupCardsWidget()
        widget.choices = _FakeChoices(Group.objects.all())

        html = widget.render("groups", [], {"id": "id_groups"})

        self.assertIn("gc-board", html)


class GroupCardsWidgetTests(TestCase):
    def test_groups_render_with_their_permission_count(self):
        group = Group.objects.create(name="Board Group")
        group.permissions.set(Permission.objects.order_by("pk")[:3])

        widget = GroupCardsWidget()
        widget.choices = _FakeChoices(Group.objects.all())
        context = widget.get_context("groups", [str(group.pk)], {"id": "id_groups"})["widget"]

        self.assertEqual(context["total"], 1)
        self.assertEqual(context["granted"], 1)
        self.assertEqual(context["groups"][0]["count"], 3)
        self.assertTrue(context["groups"][0]["checked"])


class _FakeChoices:
    """Stands in for ModelChoiceIterator: the widgets only read `.queryset`."""

    def __init__(self, queryset):
        self.queryset = queryset

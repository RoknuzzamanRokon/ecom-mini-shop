from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from notifications.models import Audience, Notification, NotificationEvent
from rbac.models import Role
from rbac.services import assign_user_role

User = get_user_model()

CHANGELISTS = (
    "admin:notifications_notificationevent_changelist",
    "admin:notifications_notification_changelist",
    "admin:notifications_notificationdelivery_changelist",
    "admin:notifications_notificationpreference_changelist",
)


class NotificationAdminAccessTests(TestCase):
    """The admin is read-only and gated by 'notifications.admin.view' (§7)."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.operator = User.objects.create_user(username="notif_ops", password="pw", is_staff=True)
        assign_user_role(cls.operator, Role.ROLE_OPERATION_MANAGER)
        cls.finance = User.objects.create_user(username="notif_finance", password="pw", is_staff=True)
        assign_user_role(cls.finance, Role.ROLE_FINANCE)
        event = NotificationEvent.objects.create(
            event_type="order.placed",
            schema_version=1,
            aggregate_type="Order",
            aggregate_id="7",
            idempotency_key="order:ORDADMIN7:placed",
        )
        cls.notification = Notification.objects.create(
            recipient=cls.finance,
            event=event,
            event_type="order.placed",
            category="ORDERS",
            audience=Audience.CUSTOMER,
            title="Order ORDADMIN7 placed",
            body="We have your order.",
            occurred_at=timezone.now(),
        )

    def test_holder_of_the_view_code_sees_every_changelist(self):
        self.client.force_login(self.operator)
        for name in CHANGELISTS:
            with self.subTest(changelist=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertContains(
            self.client.get(reverse("admin:notifications_notification_changelist")), "Order ORDADMIN7 placed"
        )

    def test_staff_without_the_code_is_refused(self):
        self.client.force_login(self.finance)
        for name in CHANGELISTS:
            with self.subTest(changelist=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
        self.assertNotContains(self.client.get(reverse("admin:index")), "notifications_notification")

    def test_change_page_is_view_only_and_add_is_refused(self):
        self.client.force_login(self.operator)
        change_url = reverse("admin:notifications_notification_change", args=[self.notification.pk])
        response = self.client.get(change_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="_save"')
        self.assertEqual(self.client.post(change_url, {"title": "Rewritten"}).status_code, 403)
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.title, "Order ORDADMIN7 placed")
        self.assertEqual(
            self.client.get(reverse("admin:notifications_notification_add")).status_code, 403
        )

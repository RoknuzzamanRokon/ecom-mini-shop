"""
Task 15: the admin's Requeue and Retry now, notification_health and
purge_notifications (docs/NOTIFICATION_SYSTEM.md §4.8, §3 D9, §17).
"""
import uuid
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditLog
from notifications.models import (
    Audience,
    Channel,
    Notification,
    NotificationDelivery,
    NotificationEvent,
)
from notifications.operations import format_duration, purge
from notifications.worker import DatabaseTransport
from rbac.models import Role
from rbac.services import assign_user_role

User = get_user_model()
Event = NotificationEvent.Status
Delivery = NotificationDelivery.Status


def make_event(status=Event.PENDING, *, attempts=0, age=None, **fields):
    event = NotificationEvent.objects.create(
        event_type="order.placed",
        schema_version=1,
        aggregate_type="Order",
        aggregate_id="1",
        idempotency_key=f"test:{uuid.uuid4()}",
        status=status,
        attempts=attempts,
        **fields,
    )
    if age is not None:
        NotificationEvent.objects.filter(pk=event.pk).update(created_at=timezone.now() - age)
    return event


def make_notification(recipient, *, event=None, age=None):
    notification = Notification.objects.create(
        recipient=recipient,
        event=event,
        event_type="order.placed",
        category="ORDERS",
        audience=Audience.CUSTOMER,
        title="Order placed",
        body="We have your order.",
        occurred_at=timezone.now(),
    )
    if age is not None:
        Notification.objects.filter(pk=notification.pk).update(created_at=timezone.now() - age)
    return notification


def make_delivery(notification, status=Delivery.PENDING, *, attempts=0, age=None, **fields):
    delivery = NotificationDelivery.objects.create(
        notification=notification,
        channel=Channel.EMAIL,
        destination="someone@example.com",
        status=status,
        attempts=attempts,
        **fields,
    )
    if age is not None:
        NotificationDelivery.objects.filter(pk=delivery.pk).update(created_at=timezone.now() - age)
    return delivery


class QueueActionTests(TestCase):
    """Requeue and Retry now: gated by notifications.admin.manage, audited per row."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.manager = User.objects.create_user(username="notif_admin", password="pw", is_staff=True)
        assign_user_role(cls.manager, Role.ROLE_ADMINISTRATOR)
        cls.viewer = User.objects.create_user(username="notif_viewer", password="pw", is_staff=True)
        assign_user_role(cls.viewer, Role.ROLE_OPERATION_MANAGER)
        cls.customer = User.objects.create_user(username="notif_customer", password="pw")

    def setUp(self):
        later = timezone.now() + timedelta(minutes=30)
        self.dead = make_event(Event.DEAD, attempts=5, last_error="boom")
        self.failed = make_event(Event.FAILED, attempts=2, available_at=later, last_error="flaky")
        self.routed = make_event(Event.ROUTED, attempts=1)
        self.pending = make_event(Event.PENDING)
        self.url = reverse("admin:notifications_notificationevent_changelist")

    def act(self, user, action, *rows, url=None):
        self.client.force_login(user)
        return self.client.post(
            url or self.url,
            {"action": action, "_selected_action": [str(row.pk) for row in rows], "index": 0},
            follow=True,
        )

    def test_actions_show_only_for_the_manage_code(self):
        self.client.force_login(self.manager)
        response = self.client.get(self.url)
        self.assertContains(response, "requeue_rows")
        self.assertContains(response, "retry_rows_now")
        self.client.force_login(self.viewer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "requeue_rows")
        self.assertNotContains(response, "retry_rows_now")

    def test_requeue_resets_dead_and_failed_and_leaves_the_rest(self):
        before = timezone.now()
        response = self.act(self.manager, "requeue_rows", self.dead, self.failed, self.routed, self.pending)
        self.assertContains(response, "Requeued 2 notification events with a fresh set of attempts.")
        self.assertContains(response, "2 selected row(s) weren&#x27;t DEAD or FAILED and were left alone.")

        for row in (self.dead, self.failed):
            row.refresh_from_db()
            self.assertEqual(row.status, Event.PENDING)
            self.assertEqual(row.attempts, 0)
            self.assertLessEqual(row.available_at, timezone.now())
            self.assertGreaterEqual(row.available_at, before)
            self.assertIsNone(row.locked_until)
        self.dead.refresh_from_db()
        self.assertEqual(self.dead.last_error, "boom")  # kept for the record
        self.routed.refresh_from_db()
        self.assertEqual((self.routed.status, self.routed.attempts), (Event.ROUTED, 1))

        logs = AuditLog.objects.filter(action="NOTIFICATION_REQUEUED").order_by("target_id")
        self.assertEqual(logs.count(), 2)
        by_target = {log.target_id: log for log in logs}
        dead_log = by_target[str(self.dead.pk)]
        self.assertEqual(dead_log.actor, self.manager)
        self.assertEqual(dead_log.target_type, "NotificationEvent")
        self.assertEqual(dead_log.metadata["previous_state"], {"status": "DEAD", "attempts": 5})
        self.assertEqual(dead_log.metadata["new_state"], {"status": "PENDING", "attempts": 0})

    def test_a_requeued_event_is_claimed_by_the_next_worker_pass(self):
        self.act(self.manager, "requeue_rows", self.dead)
        self.assertIn(self.dead.pk, DatabaseTransport().claim_events("test-worker", 10))

    def test_retry_now_makes_failed_rows_due_and_keeps_attempts(self):
        response = self.act(self.manager, "retry_rows_now", self.failed, self.dead)
        self.assertContains(response, "Made 1 notification event due now; each keeps its attempt count.")
        self.assertContains(response, "1 selected row(s) weren&#x27;t FAILED and were left alone.")
        self.failed.refresh_from_db()
        self.assertEqual((self.failed.status, self.failed.attempts), (Event.FAILED, 2))
        self.assertLessEqual(self.failed.available_at, timezone.now())
        self.dead.refresh_from_db()
        self.assertEqual(self.dead.status, Event.DEAD)
        log = AuditLog.objects.get(action="NOTIFICATION_RETRY_NOW")
        self.assertEqual(log.target_id, str(self.failed.pk))
        self.assertEqual(log.metadata["new_state"], {"status": "FAILED", "attempts": 2})

    def test_a_viewer_cannot_run_them(self):
        self.act(self.viewer, "requeue_rows", self.dead)
        self.act(self.viewer, "retry_rows_now", self.failed)
        self.dead.refresh_from_db()
        self.failed.refresh_from_db()
        self.assertEqual(self.dead.status, Event.DEAD)
        self.assertEqual(self.failed.attempts, 2)
        self.assertGreater(self.failed.available_at, timezone.now())
        self.assertFalse(AuditLog.objects.filter(action__startswith="NOTIFICATION_R").exists())

    def test_deliveries_have_the_same_actions(self):
        notification = make_notification(self.customer, event=self.routed)
        dead = make_delivery(notification, Delivery.DEAD, attempts=8, last_error="550")
        url = reverse("admin:notifications_notificationdelivery_changelist")
        response = self.act(self.manager, "requeue_rows", dead, url=url)
        self.assertContains(response, "Requeued 1 notification delivery with a fresh set of attempts.")
        dead.refresh_from_db()
        self.assertEqual((dead.status, dead.attempts), (Delivery.PENDING, 0))
        log = AuditLog.objects.get(action="NOTIFICATION_REQUEUED")
        self.assertEqual(log.target_type, "NotificationDelivery")


class HealthCommandTests(TestCase):
    def run_health(self, *args):
        out = StringIO()
        call_command("notification_health", *args, stdout=out)
        return out.getvalue()

    def assertUnhealthy(self, *args, says):
        out = StringIO()
        with self.assertRaises(CommandError) as caught:
            call_command("notification_health", *args, stdout=out)
        self.assertEqual(caught.exception.returncode, 1)
        self.assertIn(says, str(caught.exception))
        return out.getvalue()

    def test_an_empty_pipeline_is_healthy(self):
        out = self.run_health()
        self.assertIn("Healthy", out)
        self.assertIn("nothing waiting", out)
        self.assertIn("Deliveries\n  none", out)

    def test_counts_by_status_and_channel(self):
        user = User.objects.create_user(username="health_user", password="pw")
        routed = make_event(Event.ROUTED)
        make_delivery(make_notification(user, event=routed), Delivery.SENT)
        out = self.run_health()
        self.assertIn("ROUTED 1", out)
        self.assertIn("EMAIL: PENDING 0 · PROCESSING 0 · SENT 1", out)

    def test_an_event_waiting_too_long_is_unhealthy(self):
        make_event(Event.PENDING, available_at=timezone.now() - timedelta(minutes=10))
        self.assertUnhealthy(says="an event has waited 10m")
        self.assertIn("Healthy", self.run_health("--max-wait", "15"))

    def test_a_delivery_waiting_too_long_is_unhealthy(self):
        # The fast path routes events without a worker; emails only go out with one.
        user = User.objects.create_user(username="health_user", password="pw")
        notification = make_notification(user, event=make_event(Event.ROUTED))
        make_delivery(notification, available_at=timezone.now() - timedelta(minutes=8))
        self.assertUnhealthy(says="a delivery has waited 8m")

    def test_an_expired_lease_counts_as_waiting(self):
        make_event(Event.PROCESSING, attempts=1, locked_until=timezone.now() - timedelta(minutes=6), locked_by="w")
        self.assertUnhealthy(says="an event has waited 6m")

    def test_a_retry_still_in_backoff_is_not_waiting(self):
        make_event(Event.FAILED, attempts=1, available_at=timezone.now() + timedelta(minutes=20))
        out = self.run_health()
        self.assertIn("Healthy", out)
        self.assertIn("FAILED 1", out)

    def test_anything_dead_is_unhealthy(self):
        make_event(Event.DEAD, attempts=5)
        self.assertUnhealthy(says="1 dead event(s)")
        user = User.objects.create_user(username="health_user", password="pw")
        make_delivery(make_notification(user), Delivery.DEAD)
        self.assertUnhealthy(says="1 dead delivery(ies)")

    def test_bad_max_wait_is_refused(self):
        with self.assertRaisesMessage(CommandError, "--max-wait must be more than 0."):
            call_command("notification_health", "--max-wait", "0", stdout=StringIO())

    def test_format_duration(self):
        self.assertEqual(format_duration(timedelta(seconds=45)), "45s")
        self.assertEqual(format_duration(timedelta(minutes=7, seconds=3)), "7m 03s")
        self.assertEqual(format_duration(timedelta(hours=2, minutes=5)), "2h 05m")
        self.assertEqual(format_duration(timedelta(days=3, hours=4, minutes=9)), "3d 4h")


class PurgeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="purge_user", password="pw")

    def setUp(self):
        old, older = timedelta(days=100), timedelta(days=200)
        # Events: finished and old go; in flight or recent stay.
        self.old_routed = make_event(Event.ROUTED, age=old)
        self.old_dead = make_event(Event.DEAD, age=old)
        self.old_pending = make_event(Event.PENDING, age=old)
        self.old_failed = make_event(Event.FAILED, age=old)
        self.recent_routed = make_event(Event.ROUTED, age=timedelta(days=10))
        # Inbox: 200 days old goes with its finished email; one with an email
        # still in flight stays; a recent one outlives its purged event.
        self.old_inbox = make_notification(self.user, event=self.old_routed, age=older)
        self.old_inbox_email = make_delivery(self.old_inbox, Delivery.SENT, age=older)
        self.stuck_inbox = make_notification(self.user, age=older)
        self.stuck_email = make_delivery(self.stuck_inbox, Delivery.FAILED, age=older)
        self.recent_inbox = make_notification(self.user, event=self.old_dead, age=timedelta(days=100))
        # Deliveries on a recent inbox row: finished and old go; in flight stays.
        self.old_sent = make_delivery(self.recent_inbox, Delivery.SENT, age=old)

    def remaining(self):
        return (
            set(NotificationEvent.objects.values_list("pk", flat=True)),
            set(Notification.objects.values_list("pk", flat=True)),
            set(NotificationDelivery.objects.values_list("pk", flat=True)),
        )

    def test_purge_applies_d9_and_spares_rows_in_flight(self):
        out = StringIO()
        call_command("purge_notifications", stdout=out)
        self.assertIn(
            "Deleted 1 inbox notification(s) older than 180 day(s), 2 delivery(ies) and 2 event(s) older than 90 day(s).",
            out.getvalue(),
        )
        events, inbox, deliveries = self.remaining()
        self.assertEqual(events, {self.old_pending.pk, self.old_failed.pk, self.recent_routed.pk})
        self.assertEqual(inbox, {self.stuck_inbox.pk, self.recent_inbox.pk})
        self.assertEqual(deliveries, {self.stuck_email.pk})
        # The inbox row keeps what it shows; only the link to its event goes.
        self.recent_inbox.refresh_from_db()
        self.assertIsNone(self.recent_inbox.event_id)
        self.assertEqual(self.recent_inbox.title, "Order placed")

    def test_dry_run_counts_the_same_and_deletes_nothing(self):
        before = self.remaining()
        out = StringIO()
        call_command("purge_notifications", "--dry-run", stdout=out)
        self.assertIn(
            "Dry run: would delete 1 inbox notification(s) older than 180 day(s), "
            "2 delivery(ies) and 2 event(s) older than 90 day(s).",
            out.getvalue(),
        )
        self.assertEqual(self.remaining(), before)

    def test_retention_options(self):
        call_command("purge_notifications", "--days", "300", "--inbox-days", "365", stdout=StringIO())
        events, inbox, deliveries = self.remaining()
        self.assertEqual(len(events), 5)
        self.assertEqual(len(inbox), 3)
        self.assertEqual(len(deliveries), 3)

    def test_small_batches_still_delete_everything(self):
        result = purge(batch_size=1)
        self.assertEqual((result.notifications, result.deliveries, result.events), (1, 2, 2))

    def test_bad_retention_is_refused(self):
        for args in (["--days", "0"], ["--inbox-days", "-1"]):
            with self.subTest(args=args), self.assertRaises(CommandError):
                call_command("purge_notifications", *args, stdout=StringIO())
        self.assertEqual(len(self.remaining()[0]), 5)

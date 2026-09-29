from django.contrib.auth import get_user_model
from django.db import transaction
from django.template import TemplateDoesNotExist
from django.test import TestCase, override_settings

from notifications import categories as c
from notifications.handlers import Recipient
from notifications.models import (
    Audience,
    Channel,
    Notification,
    NotificationDelivery,
    NotificationEvent,
    NotificationPreference,
    Priority,
)
from notifications.publisher import publish
from notifications.routing import RoutingError, route_event

from .helpers import TEST_EVENT, TestEventMixin, tell, with_test_templates

User = get_user_model()


@with_test_templates
class RouterTests(TestEventMixin, TestCase):
    """The router list in docs/NOTIFICATION_SYSTEM.md §13."""

    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="rt_customer", email="customer@example.com", password="pw")
        cls.seller = User.objects.create_user(username="rt_seller", email="seller@example.com", password="pw")
        cls.staff = User.objects.create_user(username="rt_staff", email="", password="pw")

    def setUp(self):
        super().setUp()
        with transaction.atomic():
            self.event = publish(
                TEST_EVENT, payload={"thing": "T1"}, aggregate=self.customer, idempotency_key="test:T1"
            )

    def inbox(self, user):
        return Notification.objects.get(recipient=user, event=self.event)

    def deliveries(self, user=None):
        qs = NotificationDelivery.objects.filter(notification__event=self.event)
        return qs.filter(notification__recipient=user) if user else qs

    def test_routes_inbox_and_delivery_rows(self):
        self.handle(tell(
            Recipient(self.customer, Audience.CUSTOMER, context={"note": "first"}),
            Recipient(self.seller, Audience.SELLER),
        ))

        result = route_event(self.event.pk)

        self.assertEqual((result.status, result.notifications, result.deliveries), ("ROUTED", 2, 2))
        row = self.inbox(self.customer)
        self.assertEqual(row.title, "Thing T1 happened")
        self.assertEqual(row.body, "Hello rt_customer, T1 happened (first).")
        self.assertEqual(row.action_url, "/things/T1")
        self.assertEqual(row.event_type, TEST_EVENT)
        self.assertEqual(row.priority, Priority.HIGH)
        self.assertEqual(row.occurred_at, self.event.occurred_at)
        self.assertIsNone(row.read_at)
        delivery = self.deliveries(self.customer).get()
        self.assertEqual(delivery.channel, Channel.EMAIL)
        self.assertEqual(delivery.destination, "customer@example.com")
        self.assertEqual(delivery.status, NotificationDelivery.Status.PENDING)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, NotificationEvent.Status.ROUTED)
        self.assertIsNotNone(self.event.routed_at)

    def test_audience_decides_the_category(self):
        self.handle(tell(
            Recipient(self.customer, Audience.CUSTOMER),
            Recipient(self.seller, Audience.SELLER),
            Recipient(self.staff, Audience.STAFF),
        ))
        route_event(self.event.pk)
        for user, audience, category in (
            (self.customer, Audience.CUSTOMER, c.PAYMENTS),
            (self.seller, Audience.SELLER, c.SELLER_ORDERS),
            (self.staff, Audience.STAFF, c.STAFF_QUEUE),
        ):
            with self.subTest(audience=audience):
                row = self.inbox(user)
                self.assertEqual((row.audience, row.category), (audience, category))

    def test_an_audience_the_event_does_not_reach_is_refused(self):
        self.handle(tell(Recipient(self.customer, "PARTNER")))
        with self.assertRaisesMessage(RoutingError, "audience 'PARTNER'"):
            route_event(self.event.pk)
        self.assertFalse(Notification.objects.exists())
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, NotificationEvent.Status.PENDING)

    def test_rerouting_is_a_no_op(self):
        self.handle(tell(Recipient(self.customer, Audience.CUSTOMER)))
        route_event(self.event.pk)
        again = route_event(self.event.pk)
        self.assertEqual((again.status, again.notifications), ("ROUTED", 0))
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(NotificationDelivery.objects.count(), 1)

    def test_email_switched_off_gives_an_inbox_row_but_no_delivery(self):
        NotificationPreference.objects.create(
            user=self.seller, category=c.SELLER_ORDERS, channel=Channel.EMAIL, enabled=False
        )
        self.handle(tell(Recipient(self.seller, Audience.SELLER)))
        route_event(self.event.pk)
        self.assertTrue(Notification.objects.filter(recipient=self.seller).exists())
        self.assertFalse(self.deliveries(self.seller).exists())

    def test_a_locked_category_ignores_the_opt_out(self):
        NotificationPreference.objects.create(
            user=self.customer, category=c.PAYMENTS, channel=Channel.EMAIL, enabled=False
        )
        self.handle(tell(Recipient(self.customer, Audience.CUSTOMER)))
        route_event(self.event.pk)
        self.assertEqual(self.deliveries(self.customer).count(), 1)

    def test_a_handler_can_narrow_the_channels_but_in_app_always_stays(self):
        self.handle(tell(Recipient(self.customer, Audience.CUSTOMER, channels=frozenset())))
        route_event(self.event.pk)
        self.assertTrue(Notification.objects.filter(recipient=self.customer).exists())
        self.assertFalse(self.deliveries().exists())

    def test_no_email_address_is_recorded_as_skipped(self):
        self.handle(tell(Recipient(self.staff, Audience.STAFF)))
        route_event(self.event.pk)
        delivery = self.deliveries(self.staff).get()
        self.assertEqual(delivery.status, NotificationDelivery.Status.SKIPPED)
        self.assertEqual(delivery.destination, "")

    def test_deleted_and_deactivated_recipients_are_skipped(self):
        gone = User.objects.create_user(username="rt_gone", password="pw")
        idle = User.objects.create_user(username="rt_idle", password="pw", is_active=False)
        stale = User.objects.get(pk=gone.pk)
        gone.delete()
        self.handle(tell(
            Recipient(stale, Audience.CUSTOMER),
            Recipient(idle, Audience.CUSTOMER),
            Recipient(self.customer, Audience.CUSTOMER),
        ))
        result = route_event(self.event.pk)
        self.assertEqual(result.notifications, 1)
        self.assertEqual(list(Notification.objects.values_list("recipient_id", flat=True)), [self.customer.pk])

    def test_one_row_per_user_and_the_first_audience_wins(self):
        self.handle(
            tell(Recipient(self.seller, Audience.CUSTOMER)),
            tell(Recipient(self.seller, Audience.SELLER), Recipient(self.customer, Audience.CUSTOMER)),
        )
        route_event(self.event.pk)
        self.assertEqual(Notification.objects.count(), 2)
        self.assertEqual(self.inbox(self.seller).audience, Audience.CUSTOMER)

    @override_settings(NOTIFICATIONS={"FANOUT_CAP": 2})
    def test_fan_out_cap_holds(self):
        self.handle(tell(*(Recipient(u, Audience.STAFF) for u in (self.customer, self.seller, self.staff))))
        with self.assertLogs("notifications.routing", level="WARNING") as logs:
            result = route_event(self.event.pk)
        self.assertEqual(result.notifications, 2)
        self.assertEqual(Notification.objects.count(), 2)
        self.assertIn("only the first 2", logs.output[0])

    def test_a_failing_handler_rolls_everything_back(self):
        def broken(event):
            raise ValueError("handler bug")

        self.handle(tell(Recipient(self.customer, Audience.CUSTOMER)), broken)
        with self.assertRaises(ValueError):
            route_event(self.event.pk)
        self.assertFalse(Notification.objects.exists())
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, NotificationEvent.Status.PENDING)

    def test_a_missing_template_fails_the_event_loudly(self):
        NotificationEvent.objects.filter(pk=self.event.pk).update(schema_version=2)
        self.handle(tell(Recipient(self.customer, Audience.CUSTOMER)))
        with self.assertRaises(TemplateDoesNotExist):
            route_event(self.event.pk)
        self.assertFalse(Notification.objects.exists())

    def test_an_event_nobody_handles_is_routed_to_no_one(self):
        result = route_event(self.event.pk)
        self.assertEqual((result.status, result.notifications), ("ROUTED", 0))

    def test_dead_and_missing_events_are_left_alone(self):
        NotificationEvent.objects.filter(pk=self.event.pk).update(status=NotificationEvent.Status.DEAD)
        self.handle(tell(Recipient(self.customer, Audience.CUSTOMER)))
        self.assertEqual(route_event(self.event.pk).status, "DEAD")
        self.assertFalse(Notification.objects.exists())
        event_id = self.event.pk
        self.event.delete()
        self.assertEqual(route_event(event_id).status, "MISSING")


@with_test_templates
class FastPathTests(TestEventMixin, TestCase):
    """publish() routes the event in-process once the transaction commits."""

    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="fp_customer", email="fp@example.com", password="pw")

    def test_the_inbox_row_appears_after_commit(self):
        self.handle(tell(Recipient(self.customer, Audience.CUSTOMER)))
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                event = publish(TEST_EVENT, payload={"thing": "T2"}, aggregate=self.customer)
                self.assertFalse(Notification.objects.exists())
        event.refresh_from_db()
        self.assertEqual(event.status, NotificationEvent.Status.ROUTED)
        self.assertEqual(Notification.objects.get().title, "Thing T2 happened")

    def test_a_routing_failure_leaves_the_event_for_the_worker(self):
        def broken(event):
            raise ValueError("handler bug")

        self.handle(broken)
        with self.assertLogs("notifications.publisher", level="ERROR"):
            with self.captureOnCommitCallbacks(execute=True):
                with transaction.atomic():
                    event = publish(TEST_EVENT, payload={"thing": "T3"}, aggregate=self.customer)
        event.refresh_from_db()
        self.assertEqual(event.status, NotificationEvent.Status.PENDING)
        self.assertFalse(Notification.objects.exists())

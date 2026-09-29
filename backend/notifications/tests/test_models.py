from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from notifications.models import (
    Audience,
    Channel,
    Notification,
    NotificationDelivery,
    NotificationEvent,
    NotificationPreference,
)

User = get_user_model()


def make_event(key="order:ORD1:placed", **overrides):
    fields = {
        "event_type": "order.placed",
        "schema_version": 1,
        "aggregate_type": "Order",
        "aggregate_id": "1",
        "payload": {"order_number": "ORD1"},
        "idempotency_key": key,
        **overrides,
    }
    return NotificationEvent.objects.create(**fields)


def make_notification(recipient, event, **overrides):
    fields = {
        "recipient": recipient,
        "event": event,
        "event_type": "order.placed",
        "category": "ORDERS",
        "audience": Audience.CUSTOMER,
        "title": "Order placed",
        "body": "We have your order.",
        "occurred_at": timezone.now(),
        **overrides,
    }
    return Notification.objects.create(**fields)


class NotificationModelConstraintTests(TestCase):
    """The unique keys that make every hop idempotent (§4.5)."""

    @classmethod
    def setUpTestData(cls):
        cls.alice = User.objects.create_user(username="notif_alice", email="alice@example.com", password="pw")
        cls.bob = User.objects.create_user(username="notif_bob", email="bob@example.com", password="pw")

    def test_event_defaults(self):
        event = make_event()
        self.assertEqual(event.status, NotificationEvent.Status.PENDING)
        self.assertEqual(event.attempts, 0)
        self.assertIsNotNone(event.id)
        self.assertIsNotNone(event.occurred_at)
        self.assertIsNotNone(event.available_at)
        self.assertEqual(str(event), "order.placed Order:1 (PENDING)")

    def test_idempotency_key_is_unique(self):
        make_event()
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_event()
        self.assertEqual(NotificationEvent.objects.count(), 1)

    def test_one_inbox_row_per_recipient_per_event(self):
        event = make_event()
        make_notification(self.alice, event)
        make_notification(self.bob, event)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_notification(self.alice, event)
        self.assertEqual(Notification.objects.filter(event=event).count(), 2)

    def test_purged_events_leave_rows_that_do_not_collide(self):
        """After an event is purged its inbox rows keep event=NULL; NULLs never clash."""
        first = make_notification(self.alice, make_event("k1"))
        second = make_notification(self.alice, make_event("k2"))
        NotificationEvent.objects.all().delete()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(first.event)
        self.assertIsNone(second.event)
        make_notification(self.alice, None)
        self.assertEqual(Notification.objects.filter(recipient=self.alice, event__isnull=True).count(), 3)

    def test_one_delivery_per_channel_per_notification(self):
        notification = make_notification(self.alice, make_event())
        delivery = NotificationDelivery.objects.create(
            notification=notification, channel=Channel.EMAIL, destination="alice@example.com"
        )
        self.assertEqual(delivery.status, NotificationDelivery.Status.PENDING)
        with self.assertRaises(IntegrityError), transaction.atomic():
            NotificationDelivery.objects.create(notification=notification, channel=Channel.EMAIL)

    def test_a_delivery_is_never_in_app(self):
        notification = make_notification(self.alice, make_event())
        with self.assertRaises(IntegrityError), transaction.atomic():
            NotificationDelivery.objects.create(notification=notification, channel=Channel.IN_APP)

    def test_one_preference_per_user_category_channel(self):
        NotificationPreference.objects.create(user=self.alice, category="ORDERS", channel=Channel.EMAIL, enabled=False)
        NotificationPreference.objects.create(user=self.bob, category="ORDERS", channel=Channel.EMAIL, enabled=False)
        NotificationPreference.objects.create(user=self.alice, category="SUPPORT", channel=Channel.EMAIL, enabled=False)
        with self.assertRaises(IntegrityError), transaction.atomic():
            NotificationPreference.objects.create(
                user=self.alice, category="ORDERS", channel=Channel.EMAIL, enabled=True
            )

    def test_deleting_a_user_removes_their_inbox_and_preferences(self):
        make_notification(self.alice, make_event())
        NotificationPreference.objects.create(user=self.alice, category="ORDERS", channel=Channel.EMAIL, enabled=False)
        self.alice.delete()
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(NotificationPreference.objects.exists())
        self.assertEqual(NotificationEvent.objects.count(), 1)

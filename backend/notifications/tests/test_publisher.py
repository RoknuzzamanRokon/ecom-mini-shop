import datetime
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from notifications import events
from notifications.events import UnknownEventTypeError
from notifications.models import NotificationEvent
from notifications.publisher import InvalidPayloadError, PublishError, publish

User = get_user_model()

PAYMENT = {"payment_id": 9, "payment_number": "PAY9", "order_number": "ORD9", "amount": "1500.00"}


class Boom(Exception):
    pass


def publish_payment(aggregate, **overrides):
    kwargs = {"payload": dict(PAYMENT), "aggregate": aggregate, **overrides}
    return publish(events.PAYMENT_SUCCEEDED, **kwargs)


class PublisherWithoutDatabaseTests(SimpleTestCase):
    """Refusals that happen before any query."""

    def setUp(self):
        self.aggregate = User(pk=1, username="agg")

    def test_outside_a_transaction_is_refused(self):
        with self.assertRaisesMessage(PublishError, "inside the transaction"):
            publish_payment(self.aggregate)

    def test_unknown_event_type_is_refused(self):
        with self.assertRaises(UnknownEventTypeError):
            publish("order.teleported", payload={}, aggregate=self.aggregate)

    def test_missing_required_keys_are_named(self):
        payload = {"payment_id": 9, "amount": "1500.00"}
        with self.assertRaisesMessage(InvalidPayloadError, "missing order_number, payment_number"):
            publish(events.PAYMENT_SUCCEEDED, payload=payload, aggregate=self.aggregate)

    def test_payloads_that_are_not_plain_json_are_refused(self):
        for bad in (
            {**PAYMENT, "amount": Decimal("1500.00")},
            {**PAYMENT, "paid_at": timezone.now()},
            {**PAYMENT, "ratio": float("nan")},
            {**PAYMENT, "tags": {"a", "b"}},
        ):
            with self.subTest(payload=bad):
                with self.assertRaises(InvalidPayloadError):
                    publish(events.PAYMENT_SUCCEEDED, payload=bad, aggregate=self.aggregate)

    def test_payload_must_be_a_dict(self):
        with self.assertRaisesMessage(InvalidPayloadError, "must be a dict"):
            publish(events.PAYMENT_SUCCEEDED, payload=[PAYMENT], aggregate=self.aggregate)

    def test_unsaved_aggregate_is_refused(self):
        with self.assertRaisesMessage(PublishError, "saved model instance"):
            publish_payment(User(username="unsaved"))

    def test_overlong_idempotency_key_is_refused(self):
        with self.assertRaisesMessage(PublishError, "longer than 191"):
            publish_payment(self.aggregate, idempotency_key="k" * 192)

    def test_naive_occurred_at_is_refused(self):
        with self.assertRaisesMessage(PublishError, "timezone-aware"):
            publish_payment(self.aggregate, occurred_at=datetime.datetime(2026, 9, 29, 12, 0))


class PublisherTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pub_customer", password="pw")

    def test_commit_writes_one_pending_event(self):
        occurred = timezone.now() - datetime.timedelta(minutes=5)
        with transaction.atomic():
            event = publish_payment(
                self.user, actor=self.user, idempotency_key="payment:PAY9:succeeded", occurred_at=occurred
            )

        stored = NotificationEvent.objects.get()
        self.assertEqual(stored.pk, event.pk)
        self.assertEqual(stored.event_type, "payment.succeeded")
        self.assertEqual(stored.schema_version, 1)
        self.assertEqual(stored.aggregate_type, "User")
        self.assertEqual(stored.aggregate_id, str(self.user.pk))
        self.assertEqual(stored.actor, self.user)
        self.assertEqual(stored.payload, PAYMENT)
        self.assertEqual(stored.idempotency_key, "payment:PAY9:succeeded")
        self.assertEqual(stored.occurred_at, occurred)
        self.assertEqual(stored.status, NotificationEvent.Status.PENDING)
        self.assertEqual(stored.attempts, 0)

    def test_rollback_leaves_no_event(self):
        with self.assertRaises(Boom), transaction.atomic():
            publish_payment(self.user)
            raise Boom
        self.assertFalse(NotificationEvent.objects.exists())

    def test_duplicate_key_returns_the_first_event_and_the_transaction_survives(self):
        with transaction.atomic():
            first = publish_payment(self.user, idempotency_key="payment:PAY9:succeeded")
            second = publish_payment(self.user, idempotency_key="payment:PAY9:succeeded")
            # The failed insert rolled back only its savepoint.
            User.objects.create_user(username="pub_after_duplicate", password="pw")

        self.assertEqual(second.pk, first.pk)
        self.assertEqual(NotificationEvent.objects.count(), 1)
        self.assertTrue(User.objects.filter(username="pub_after_duplicate").exists())

    def test_duplicate_key_on_another_event_type_is_refused(self):
        with transaction.atomic():
            publish_payment(self.user, idempotency_key="shared-key")
            with self.assertRaisesMessage(PublishError, "already belongs to a 'payment.succeeded' event"):
                publish(events.PAYMENT_FAILED, payload=dict(PAYMENT), aggregate=self.user, idempotency_key="shared-key")
        self.assertEqual(NotificationEvent.objects.count(), 1)

    def test_default_keys_are_unique(self):
        with transaction.atomic():
            first = publish_payment(self.user)
            second = publish_payment(self.user)
        self.assertNotEqual(first.idempotency_key, second.idempotency_key)
        self.assertEqual(NotificationEvent.objects.count(), 2)

    def test_payload_is_a_snapshot(self):
        payload = dict(PAYMENT)
        with transaction.atomic():
            event = publish(events.PAYMENT_SUCCEEDED, payload=payload, aggregate=self.user)
        payload["amount"] = "1.00"
        event.refresh_from_db()
        self.assertEqual(event.payload["amount"], "1500.00")

    def test_anonymous_actor_is_stored_as_none(self):
        with transaction.atomic():
            event = publish_payment(self.user, actor=AnonymousUser())
        self.assertIsNone(event.actor)

    def test_a_refused_publish_writes_nothing(self):
        with transaction.atomic():
            with self.assertRaises(InvalidPayloadError):
                publish(events.PAYMENT_SUCCEEDED, payload={"amount": "1.00"}, aggregate=self.user)
        self.assertFalse(NotificationEvent.objects.exists())


class PublisherFastPathTests(TestCase):
    """publish() queues the in-process fast path for after the commit (§4.4 step 2)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pub_fast_path", password="pw")

    def test_fast_path_runs_after_commit_with_the_event_id(self):
        with mock.patch("notifications.publisher.route_after_commit") as route:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with transaction.atomic():
                    event = publish_payment(self.user)
                    route.assert_not_called()
        self.assertEqual(len(callbacks), 1)
        route.assert_called_once_with(event.pk)

    def test_fast_path_failure_does_not_reach_the_caller(self):
        with mock.patch("notifications.publisher.route_after_commit", side_effect=RuntimeError("router down")):
            with self.assertLogs("notifications.publisher", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    with transaction.atomic():
                        publish_payment(self.user)
        self.assertEqual(NotificationEvent.objects.get().status, NotificationEvent.Status.PENDING)

    def test_duplicate_publish_queues_no_second_fast_path(self):
        with self.captureOnCommitCallbacks() as callbacks:
            with transaction.atomic():
                publish_payment(self.user, idempotency_key="payment:PAY9:succeeded")
                publish_payment(self.user, idempotency_key="payment:PAY9:succeeded")
        self.assertEqual(len(callbacks), 1)

    @override_settings(NOTIFICATIONS={"ROUTE_ON_COMMIT": False})
    def test_fast_path_can_be_switched_off(self):
        with self.captureOnCommitCallbacks() as callbacks:
            with transaction.atomic():
                publish_payment(self.user)
        self.assertEqual(callbacks, [])
        self.assertEqual(NotificationEvent.objects.count(), 1)

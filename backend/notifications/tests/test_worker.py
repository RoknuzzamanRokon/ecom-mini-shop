import threading
import uuid
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from notifications.channels import PermanentSendError, SendResult, TransientSendError
from notifications.channels.base import ADAPTERS
from notifications.handlers import Recipient
from notifications.models import Audience, Channel, Notification, NotificationDelivery, NotificationEvent
from notifications.worker import (
    DatabaseTransport,
    NotificationWorker,
    TokenBucket,
    backoff_delay,
)

from .helpers import TEST_EVENT, TestEventMixin, tell, with_test_templates

User = get_user_model()


def make_event(**fields):
    fields.setdefault("event_type", TEST_EVENT)
    fields.setdefault("payload", {"thing": "W1"})
    fields.setdefault("idempotency_key", str(uuid.uuid4()))
    return NotificationEvent.objects.create(schema_version=1, aggregate_type="User", aggregate_id="1", **fields)


class BackoffAndRateTests(SimpleTestCase):
    def test_full_jitter_upper_bound_doubles_to_the_cap(self):
        upper = lambda low, high: high  # noqa: E731
        self.assertEqual([backoff_delay(n, rand=upper) for n in (1, 2, 3, 8)], [30, 60, 120, 3600])
        self.assertEqual(backoff_delay(3, rand=lambda low, high: low), 0)

    def test_token_bucket_limits_the_rate(self):
        now = [0.0]
        slept = []

        def sleep(seconds):
            slept.append(seconds)
            now[0] += seconds

        bucket = TokenBucket(2, clock=lambda: now[0], sleep=sleep)
        for _ in range(4):
            bucket.acquire()
        self.assertEqual(slept, [0.5, 0.5])

    def test_no_rate_means_no_limit(self):
        bucket = TokenBucket(0, sleep=mock.Mock(side_effect=AssertionError("slept")))
        for _ in range(100):
            bucket.acquire()


class ClaimTests(TestCase):
    def test_claims_only_due_rows_and_takes_a_lease(self):
        now = timezone.now()
        past, future = now - timedelta(minutes=1), now + timedelta(minutes=1)
        due = {
            make_event(),
            make_event(status=NotificationEvent.Status.FAILED, available_at=past),
            make_event(status=NotificationEvent.Status.PROCESSING, locked_until=past, locked_by="dead-worker"),
        }
        make_event(available_at=future)
        make_event(status=NotificationEvent.Status.FAILED, available_at=future)
        make_event(status=NotificationEvent.Status.PROCESSING, locked_until=future, locked_by="live-worker")
        make_event(status=NotificationEvent.Status.ROUTED)
        make_event(status=NotificationEvent.Status.DEAD)

        claimed = DatabaseTransport().claim_events("w1", 50)

        self.assertEqual(set(claimed), {e.pk for e in due})
        for event in NotificationEvent.objects.filter(pk__in=claimed):
            self.assertEqual(event.status, NotificationEvent.Status.PROCESSING)
            self.assertEqual(event.locked_by, "w1")
            self.assertEqual(event.attempts, 1)
            self.assertGreater(event.locked_until, now + timedelta(seconds=55))

    def test_batch_size_is_respected(self):
        for _ in range(5):
            make_event()
        self.assertEqual(len(DatabaseTransport().claim_events("w1", 3)), 3)
        self.assertEqual(len(DatabaseTransport().claim_events("w2", 3)), 2)

    def test_a_lease_that_expired_on_the_last_attempt_is_dead(self):
        event = make_event(
            status=NotificationEvent.Status.PROCESSING,
            attempts=5,
            locked_until=timezone.now() - timedelta(minutes=1),
            locked_by="crashed",
        )
        self.assertEqual(DatabaseTransport().claim_events("w1", 10), [])
        event.refresh_from_db()
        self.assertEqual(event.status, NotificationEvent.Status.DEAD)
        self.assertIn("lease expired", event.last_error)


@with_test_templates
class EventProcessingTests(TestEventMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="wk_customer", email="wk@example.com", password="pw")

    def test_routes_claimed_events(self):
        self.handle(tell(Recipient(self.customer, Audience.CUSTOMER)))
        event = make_event()
        result = NotificationWorker(worker_id="w1").run_once("events")
        self.assertEqual(result.events, 1)
        event.refresh_from_db()
        self.assertEqual(event.status, NotificationEvent.Status.ROUTED)
        self.assertEqual((event.locked_by, event.locked_until), ("", None))
        self.assertTrue(Notification.objects.filter(event=event, recipient=self.customer).exists())

    def test_a_failure_is_retried_later(self):
        self.handle(mock.Mock(side_effect=ValueError("handler bug")))
        event = make_event()
        before = timezone.now()
        with self.assertLogs("notifications.worker", level="WARNING"):
            NotificationWorker(worker_id="w1").run_once("events")
        event.refresh_from_db()
        self.assertEqual(event.status, NotificationEvent.Status.FAILED)
        self.assertEqual(event.attempts, 1)
        self.assertGreaterEqual(event.available_at, before)
        self.assertIn("ValueError: handler bug", event.last_error)
        self.assertLessEqual(len(event.last_error), 2048)
        self.assertEqual((event.locked_by, event.locked_until), ("", None))

    def test_the_last_attempt_goes_dead(self):
        self.handle(mock.Mock(side_effect=ValueError("still broken")))
        event = make_event(status=NotificationEvent.Status.FAILED, attempts=4, available_at=timezone.now())
        with self.assertLogs("notifications.worker", level="ERROR"):
            NotificationWorker(worker_id="w1").run_once("events")
        event.refresh_from_db()
        self.assertEqual((event.status, event.attempts), (NotificationEvent.Status.DEAD, 5))

    def test_a_row_whose_lease_was_taken_over_is_left_alone(self):
        self.handle(tell(Recipient(self.customer, Audience.CUSTOMER)))
        event = make_event()
        worker = NotificationWorker(worker_id="w1")
        claimed = worker.transport.claim_events("w1", 10)
        NotificationEvent.objects.filter(pk=event.pk).update(locked_by="w2")
        with mock.patch.object(worker.transport, "claim_events", return_value=claimed):
            with self.assertLogs("notifications.worker", level="WARNING"):
                worker.run_once("events")
        event.refresh_from_db()
        self.assertEqual((event.status, event.locked_by), (NotificationEvent.Status.PROCESSING, "w2"))

    def test_stopping_mid_batch_hands_the_rest_back(self):
        events = [make_event() for _ in range(3)]
        worker = NotificationWorker(worker_id="w1")
        self.handle(lambda event: worker.stop() or [])
        with self.assertLogs("notifications.worker", level="INFO"):
            handled = worker.process_events()
        self.assertEqual(handled, 1)
        statuses = sorted(
            NotificationEvent.objects.filter(pk__in=[e.pk for e in events]).values_list("status", "attempts")
        )
        self.assertEqual(statuses, [("PENDING", 0), ("PENDING", 0), ("ROUTED", 1)])

    def test_the_transport_is_a_seam(self):
        event = make_event(status=NotificationEvent.Status.PROCESSING, locked_by="w1",
                           locked_until=timezone.now() + timedelta(minutes=1))
        transport = mock.Mock()
        transport.claim_events.return_value = [event.pk]
        NotificationWorker(worker_id="w1", transport=transport).run_once("events")
        transport.claim_events.assert_called_once_with("w1", 50)
        event.refresh_from_db()
        self.assertEqual(event.status, NotificationEvent.Status.ROUTED)


class FakeAdapter:
    channel = Channel.EMAIL

    def __init__(self, outcome=None):
        self.outcome = outcome
        self.sent = []

    def send(self, delivery):
        self.sent.append(delivery.pk)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return SendResult(provider_message_id=f"<{delivery.pk}@minishop>")


class DeliveryProcessingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="wk_delivery", email="d@example.com", password="pw")

    def make_delivery(self, **fields):
        notification = Notification.objects.create(
            recipient=self.user, event=make_event(), event_type=TEST_EVENT, category="ORDERS",
            audience=Audience.CUSTOMER, title="T", body="B", occurred_at=timezone.now(),
        )
        return NotificationDelivery.objects.create(
            notification=notification, channel=Channel.EMAIL, destination="d@example.com", **fields
        )

    def run_with(self, adapter):
        with mock.patch.dict(ADAPTERS, {Channel.EMAIL: adapter}):
            return NotificationWorker(worker_id="w1").run_once("deliveries")

    def test_a_successful_send_is_recorded(self):
        delivery = self.make_delivery()
        adapter = FakeAdapter()
        self.assertEqual(self.run_with(adapter).deliveries, 1)
        delivery.refresh_from_db()
        self.assertEqual(adapter.sent, [delivery.pk])
        self.assertEqual(delivery.status, NotificationDelivery.Status.SENT)
        self.assertEqual(delivery.provider_message_id, f"<{delivery.pk}@minishop>")
        self.assertIsNotNone(delivery.sent_at)
        self.assertEqual(delivery.attempts, 1)

    def test_transient_and_unexpected_errors_are_retried(self):
        for error in (TransientSendError("421 try later"), OSError("connection refused")):
            with self.subTest(error=error):
                delivery = self.make_delivery()
                with self.assertLogs("notifications.worker", level="WARNING"):
                    self.run_with(FakeAdapter(error))
                delivery.refresh_from_db()
                self.assertEqual(delivery.status, NotificationDelivery.Status.FAILED)
                self.assertIn(str(error), delivery.last_error)

    def test_a_permanent_error_is_dead_at_once(self):
        delivery = self.make_delivery()
        with self.assertLogs("notifications.worker", level="ERROR"):
            self.run_with(FakeAdapter(PermanentSendError("550 no such user")))
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.attempts), (NotificationDelivery.Status.DEAD, 1))

    def test_a_permanent_error_can_mean_skipped(self):
        delivery = self.make_delivery()
        with self.assertLogs("notifications.worker", level="ERROR"):
            self.run_with(FakeAdapter(PermanentSendError("invalid address", skip=True)))
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, NotificationDelivery.Status.SKIPPED)

    def test_the_last_delivery_attempt_goes_dead(self):
        delivery = self.make_delivery(attempts=7)
        with self.assertLogs("notifications.worker", level="ERROR"):
            self.run_with(FakeAdapter(TransientSendError("timeout")))
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.attempts), (NotificationDelivery.Status.DEAD, 8))

    def test_channels_without_an_adapter_wait(self):
        delivery = self.make_delivery()
        with mock.patch.dict(ADAPTERS, clear=True):
            self.assertEqual(NotificationWorker(worker_id="w1").run_once("deliveries").deliveries, 0)
        delivery.refresh_from_db()
        self.assertEqual((delivery.status, delivery.attempts), (NotificationDelivery.Status.PENDING, 0))

    def test_skipped_deliveries_are_never_claimed(self):
        self.make_delivery(status=NotificationDelivery.Status.SKIPPED)
        adapter = FakeAdapter()
        self.assertEqual(self.run_with(adapter).deliveries, 0)
        self.assertEqual(adapter.sent, [])

    @override_settings(NOTIFICATIONS={"EMAIL_RATE_PER_SECOND": 3})
    def test_sends_go_through_the_channel_rate_limit(self):
        for _ in range(2):
            self.make_delivery()
        with mock.patch("notifications.worker.TokenBucket") as bucket:
            self.run_with(FakeAdapter())
        bucket.assert_called_once_with(3)
        self.assertEqual(bucket.return_value.acquire.call_count, 2)


class WorkerLoopAndCommandTests(TestEventMixin, TestCase):
    def test_run_stops_when_asked(self):
        worker = NotificationWorker(worker_id="w1")
        passes = []

        def one_pass(only=None):
            passes.append(only)
            worker.stop()
            return mock.Mock(events=0, deliveries=0, total=0)

        with mock.patch.object(worker, "run_once", side_effect=one_pass):
            worker.run(idle_sleep=60)
        self.assertEqual(passes, [None])

    def test_once_runs_one_pass_and_exits(self):
        make_event()
        out = StringIO()
        call_command("run_notification_worker", "--once", stdout=out)
        self.assertIn("Handled 1 event(s) and 0 delivery(ies).", out.getvalue())
        self.assertEqual(NotificationEvent.objects.get().status, NotificationEvent.Status.ROUTED)

    def test_only_deliveries_leaves_events(self):
        make_event()
        call_command("run_notification_worker", "--once", "--only", "deliveries", stdout=StringIO())
        self.assertEqual(NotificationEvent.objects.get().status, NotificationEvent.Status.PENDING)

    def test_bad_arguments_are_refused(self):
        for args in (("--batch", "0"), ("--idle-sleep", "-1")):
            with self.subTest(args=args):
                with self.assertRaises(CommandError):
                    call_command("run_notification_worker", "--once", *args, stdout=StringIO())


class ConcurrentClaimTests(TransactionTestCase):
    """Two workers on two connections never take the same row (§13, Worker)."""

    def setUp(self):
        self.events = [make_event() for _ in range(20)]

    def test_rows_locked_by_another_connection_are_skipped_not_waited_for(self):
        locked, release, errors = threading.Event(), threading.Event(), []
        held = []

        def hold_some_rows():
            try:
                with transaction.atomic():
                    # By primary key, so exactly these five rows are locked.
                    rows = NotificationEvent.objects.select_for_update().filter(
                        pk__in=[e.pk for e in self.events[:5]]
                    )
                    held.extend(rows.values_list("pk", flat=True))
                    locked.set()
                    release.wait(30)
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
                locked.set()
            finally:
                connection.close()

        holder = threading.Thread(target=hold_some_rows)
        holder.start()
        try:
            self.assertTrue(locked.wait(30))
            claimed = DatabaseTransport().claim_events("w2", 50)
        finally:
            release.set()
            holder.join(30)
        self.assertEqual(errors, [])
        self.assertEqual(len(held), 5)
        self.assertEqual(len(claimed), 15)
        self.assertFalse(set(held) & set(claimed))

    def test_two_racing_workers_never_share_a_row(self):
        start = threading.Barrier(2)
        results, errors = {}, []

        def work(worker_id):
            try:
                start.wait(30)
                mine = []
                while batch := DatabaseTransport().claim_events(worker_id, 3):
                    mine.extend(batch)
                results[worker_id] = mine
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=work, args=(f"w{n}",)) for n in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertEqual(errors, [])
        self.assertFalse(set(results["w1"]) & set(results["w2"]))
        self.assertEqual(set(results["w1"]) | set(results["w2"]), {e.pk for e in self.events})
        owners = dict(NotificationEvent.objects.values_list("pk", "locked_by"))
        for worker_id, claimed in results.items():
            self.assertTrue(all(owners[pk] == worker_id for pk in claimed))

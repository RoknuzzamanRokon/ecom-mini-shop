"""
Runs the notification worker (docs/NOTIFICATION_SYSTEM.md §4.4).

    python manage.py run_notification_worker            # until Ctrl+C / SIGTERM
    python manage.py run_notification_worker --once     # one pass, e.g. from a scheduler

Any number can run at once. On SIGINT or SIGTERM it finishes the row in hand,
hands the rest of its batch back, and exits.
"""
import signal

from django.core.management.base import BaseCommand, CommandError

from notifications.conf import notification_setting
from notifications.worker import IDLE_SLEEP_SECONDS, NotificationWorker


class Command(BaseCommand):
    help = "Route pending notification events and send pending deliveries."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run one pass, then exit.")
        parser.add_argument(
            "--only", choices=["events", "deliveries"], help="Handle only events or only deliveries."
        )
        parser.add_argument(
            "--batch", type=int, default=None,
            help=f"Rows claimed per pass (default NOTIFICATIONS['BATCH_SIZE'], {notification_setting('BATCH_SIZE')}).",
        )
        parser.add_argument(
            "--idle-sleep", type=float, default=IDLE_SLEEP_SECONDS,
            help=f"Seconds to wait after a pass that found nothing (default {IDLE_SLEEP_SECONDS:g}).",
        )

    def handle(self, *args, once=False, only=None, batch=None, idle_sleep=IDLE_SLEEP_SECONDS, **options):
        if batch is not None and batch < 1:
            raise CommandError("--batch must be at least 1.")
        if idle_sleep < 0:
            raise CommandError("--idle-sleep can't be negative.")
        worker = NotificationWorker(batch_size=batch)

        if once:
            result = worker.run_once(only)
            self.stdout.write(f"Handled {result.events} event(s) and {result.deliveries} delivery(ies).")
            return

        def stop(signum, frame):
            self.stdout.write(f"Received {signal.Signals(signum).name}; stopping after the current row.")
            worker.stop()

        previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
        self.stdout.write(f"Notification worker {worker.worker_id} running. Press Ctrl+C to stop.")
        try:
            worker.run(only=only, idle_sleep=idle_sleep)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        self.stdout.write("Notification worker stopped.")

"""
Reports the notification pipeline's health (docs/NOTIFICATION_SYSTEM.md §4.8, §17).

    python manage.py notification_health
    python manage.py notification_health --max-wait 15

Prints events by status, deliveries by channel and status, and how long the
oldest due row has waited for a worker. Exits with status 1 when anything is
DEAD, or when an event or a delivery has waited longer than --max-wait minutes
(default 5), so a scheduler can alert on it. Read-only.
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from notifications.operations import MAX_WAIT_MINUTES, format_duration, health_report


class Command(BaseCommand):
    help = "Report notification backlog, failures and dead letters; exit 1 when unhealthy."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-wait",
            type=float,
            default=MAX_WAIT_MINUTES,
            help=f"Minutes a due row may wait for a worker before it counts as unhealthy (default {MAX_WAIT_MINUTES}).",
        )

    def handle(self, *args, max_wait=MAX_WAIT_MINUTES, **options):
        if max_wait <= 0:
            raise CommandError("--max-wait must be more than 0.")
        report = health_report(max_wait_minutes=max_wait)

        self.stdout.write(f"Notification health at {timezone.localtime(report.checked_at):%Y-%m-%d %H:%M:%S %Z}")
        self.stdout.write("")
        self.stdout.write("Events")
        self.stdout.write("  " + _counts(report.events))
        self.stdout.write(f"  Oldest waiting: {_wait(report.event_wait)}")
        self.stdout.write("")
        self.stdout.write("Deliveries")
        if not report.deliveries:
            self.stdout.write("  none")
        for channel, by_status in sorted(report.deliveries.items()):
            self.stdout.write(f"  {channel}: {_counts(by_status)}")
        self.stdout.write(f"  Oldest waiting: {_wait(report.delivery_wait)}")
        self.stdout.write("")

        if report.healthy:
            self.stdout.write(self.style.SUCCESS(
                f"Healthy: nothing dead, and nothing has waited over {max_wait:g} minute(s)."
            ))
            return
        raise CommandError("Unhealthy: " + "; ".join(report.problems) + ".", returncode=1)


def _counts(by_status):
    return " · ".join(f"{status} {count}" for status, count in by_status.items())


def _wait(delta):
    return "nothing waiting" if delta is None else format_duration(delta)

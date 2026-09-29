"""
Deletes old notification rows (docs/NOTIFICATION_SYSTEM.md §3 D9, §17).

    python manage.py purge_notifications --dry-run
    python manage.py purge_notifications
    python manage.py purge_notifications --days 60 --inbox-days 120

Inbox notifications go after --inbox-days (default 180), unless an email of
theirs is still in flight. Finished deliveries (SENT, SKIPPED, DEAD) and
finished events (ROUTED, DEAD) go after --days (default 90). Rows still in
flight are never deleted, however old. Deletes run in batches of 1000, each in
its own short transaction. Run it once a day.
"""
from django.core.management.base import BaseCommand, CommandError

from notifications.conf import notification_setting
from notifications.operations import purge


class Command(BaseCommand):
    help = "Delete inbox notifications, events and deliveries past their retention (D9)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=None,
            help=(
                "Keep finished events and deliveries this many days "
                f"(default NOTIFICATIONS['EVENT_RETENTION_DAYS'], {notification_setting('EVENT_RETENTION_DAYS')})."
            ),
        )
        parser.add_argument(
            "--inbox-days",
            type=int,
            default=None,
            help=(
                "Keep inbox notifications this many days "
                f"(default NOTIFICATIONS['INBOX_RETENTION_DAYS'], {notification_setting('INBOX_RETENTION_DAYS')})."
            ),
        )
        parser.add_argument("--dry-run", action="store_true", help="Count what would be deleted; delete nothing.")

    def handle(self, *args, days=None, inbox_days=None, dry_run=False, **options):
        days = notification_setting("EVENT_RETENTION_DAYS") if days is None else days
        inbox_days = notification_setting("INBOX_RETENTION_DAYS") if inbox_days is None else inbox_days
        if days < 1 or inbox_days < 1:
            raise CommandError("--days and --inbox-days must be at least 1.")

        result = purge(inbox_days=inbox_days, event_days=days, dry_run=dry_run)
        counts = (
            f"{result.notifications} inbox notification(s) older than {inbox_days} day(s), "
            f"{result.deliveries} delivery(ies) and {result.events} event(s) older than {days} day(s)"
        )
        if dry_run:
            self.stdout.write(self.style.NOTICE(f"Dry run: would delete {counts}."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Deleted {counts}."))

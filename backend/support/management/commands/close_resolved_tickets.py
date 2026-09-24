"""
Closes support tickets that were resolved and then left quiet (D17).

A RESOLVED ticket is closed once it has had no public activity for --days
(default 7) and the customer hasn't written since it was resolved. Each close
goes through SupportTicketService like any other status change: a public
"Closed automatically…" line in the thread and an audit entry, with no actor.

The project has no scheduler; run this once a day from cron or Windows Task
Scheduler (see docs/SUPPORT_SYSTEM.md, Task 11).
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from support.services import AUTO_CLOSE_AFTER_DAYS, SupportTicketService


class Command(BaseCommand):
    help = "Close RESOLVED support tickets that have had no customer reply for N days (default 7)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=AUTO_CLOSE_AFTER_DAYS,
            help=f"How many quiet days after resolution before closing (default {AUTO_CLOSE_AFTER_DAYS}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List the tickets that would be closed, and change nothing.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        if days < 1:
            raise CommandError("--days must be at least 1.")

        candidates = list(
            SupportTicketService.stale_resolved_tickets(days)
            .order_by("resolved_at", "id")
            .values_list("ticket_number", "resolved_at")
        )

        if options["dry_run"]:
            for number, resolved_at in candidates:
                self.stdout.write(f"  would close {number} (resolved {_when(resolved_at)})")
            self.stdout.write(self.style.NOTICE(
                f"Dry run: {len(candidates)} resolved ticket(s) quiet for {days}+ day(s) would be closed."
            ))
            return

        closed = 0
        for number, resolved_at in candidates:
            if SupportTicketService.auto_close_resolved(number, days):
                closed += 1
                self.stdout.write(f"  closed {number} (resolved {_when(resolved_at)})")
        skipped = len(candidates) - closed
        summary = f"Closed {closed} resolved ticket(s) quiet for {days}+ day(s)."
        if skipped:
            summary += f" {skipped} changed while running and were left as they are."
        self.stdout.write(self.style.SUCCESS(summary))


def _when(value) -> str:
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M %Z")

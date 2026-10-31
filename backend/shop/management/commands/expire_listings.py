"""
Moves products whose listing period ended to EXPIRED.

The storefront already hides such a product, and the seller's own reads
expire it; this command writes the change for products nobody touches, so
statuses, the Console and the audit trail are current. The project has no
scheduler; run it once a day from cron or Windows Task Scheduler, like
expire_points.
"""
from django.core.management.base import BaseCommand

from shop.listing_service import ListingService


class Command(BaseCommand):
    help = "Expire published products whose listing period has ended."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count the products whose period has ended, and change nothing.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            self.stdout.write(f"{ListingService.due().count()} product listing(s) have ended.")
            return
        moved = ListingService.expire_due()
        self.stdout.write(self.style.SUCCESS(f"Expired {moved} product listing(s)."))

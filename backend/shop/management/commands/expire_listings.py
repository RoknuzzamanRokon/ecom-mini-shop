"""
Moves products whose listing period ended to EXPIRED, and tells sellers whose
products enter the ending-soon window.

The storefront already hides an ended product, and the seller's own reads
expire it; this command writes the change for products nobody touches, so
statuses, the Console and the audit trail are current. Each expiry sends the
seller a listing.expired notice, and each product within
ProductListingPolicy.ending_soon_days of its end date a listing.ending_soon
notice, once per period however often the command runs. The project has no
scheduler; run it once a day from cron (deploy/cron/minishop.crontab) or
Windows Task Scheduler, like expire_points.
"""
from django.core.management.base import BaseCommand

from shop.listing_service import ListingService
from shop.models import ProductListingPolicy


class Command(BaseCommand):
    help = "Expire published products whose listing period has ended, and send ending-soon notices."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count the ended and ending-soon listings, and change or send nothing.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            ending = ListingService.ending_soon(ProductListingPolicy.current()).count()
            self.stdout.write(f"{ListingService.due().count()} product listing(s) have ended.")
            self.stdout.write(f"{ending} product listing(s) end soon.")
            return
        moved = ListingService.expire_due()
        ending = ListingService.announce_ending_soon()
        self.stdout.write(self.style.SUCCESS(f"Expired {moved} product listing(s)."))
        self.stdout.write(
            self.style.SUCCESS(f"{ending} product listing(s) end soon; each seller hears once per period.")
        )

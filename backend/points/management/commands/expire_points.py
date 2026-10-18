"""
Expires due points in every wallet.

Points also expire whenever their wallet is read or used, so nothing expired
is ever spent; this command writes the expiry for wallets nobody touches, so
their balances and ledgers are current. The project has no scheduler; run it
once a day from cron or Windows Task Scheduler.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from points.models import SellerPointLot, StaffPointLot
from points.services import PointService


class Command(BaseCommand):
    help = "Expire due points in every seller and staff wallet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count the wallets holding due points, and change nothing.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            now = timezone.now()
            for label, lot_model in (("seller", SellerPointLot), ("staff", StaffPointLot)):
                count = (
                    lot_model.objects.filter(remaining__gt=0, expires_at__lte=now)
                    .values("wallet_id")
                    .distinct()
                    .count()
                )
                self.stdout.write(f"{count} {label} wallet(s) hold due points (exempt holders are skipped on a real run).")
            return

        result = PointService.expire_all_due_points()
        self.stdout.write(
            self.style.SUCCESS(
                f"Expired {result['points']} point(s): {result['seller_wallets']} seller wallet(s), "
                f"{result['staff_wallets']} staff wallet(s)."
            )
        )

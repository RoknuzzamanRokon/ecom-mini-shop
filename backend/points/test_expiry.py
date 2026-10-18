"""
Point expiry: every point a wallet receives lasts PointExpiryPolicy months
(default 2), spending takes the soonest-expiring points first, and a Full Shop
Owner's and a superuser's points never expire. A superuser can switch expiry
off and on for each other staff member. Also: a new product always costs at
least 1 point.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from audit.models import AuditLog
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from .models import (
    PointExpiryPolicy,
    PointTransaction,
    ProductCreationCost,
    StaffPointTransaction,
    add_months,
)
from .services import InsufficientPointsError, PointError, PointService

User = get_user_model()


def age_lots(wallet, days=1):
    """Moves every unspent lot in `wallet` past its expiry date."""
    wallet.lots.filter(remaining__gt=0).update(expires_at=timezone.now() - timedelta(days=days))


class AddMonthsTests(TestCase):
    def test_clamps_to_the_end_of_a_shorter_month(self):
        start = datetime(2026, 12, 31, 9, 30, tzinfo=dt_timezone.utc)
        self.assertEqual(add_months(start, 2), datetime(2027, 2, 28, 9, 30, tzinfo=dt_timezone.utc))
        self.assertEqual(add_months(start, 1), datetime(2027, 1, 31, 9, 30, tzinfo=dt_timezone.utc))


class PointExpiryTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        def seller(username, seller_type):
            user = User.objects.create_user(
                username=username, email=f"{username}@minishop.com", password="SellerPassword123!"
            )
            return SellerProfile.objects.create(
                user=user,
                seller_type=seller_type,
                business_name=f"{username} Co",
                status=SellerProfile.STATUS_ACTIVE,
            )

        cls.limited = seller("exp_limited", SellerProfile.TYPE_LIMITED_SHOP_OWNER)
        cls.full = seller("exp_full", SellerProfile.TYPE_FULL_SHOP_OWNER)
        cls.root = User.objects.create_superuser(
            username="exp_root", email="exp_root@minishop.com", password="RootPassword123!"
        )
        cls.admin = User.objects.create_user(
            username="exp_admin", email="exp_admin@minishop.com", password="AdminPassword123!", is_staff=True
        )
        assign_user_role(cls.admin, Role.ROLE_ADMINISTRATOR)

    def credit(self, seller, amount):
        return PointService.credit(
            seller=seller, amount=amount, transaction_type=PointTransaction.TYPE_BONUS, reason="Expiry test"
        )

    def fund_admin(self, amount):
        PointService.mint_points(self.root, amount, "Expiry test mint")
        PointService.transfer_to_staff(self.root, self.admin, amount, "Expiry test transfer")


class SellerPointExpiryTests(PointExpiryTestCase):
    def test_received_points_are_dated_two_months_ahead_by_default(self):
        txn = self.credit(self.limited, 10)
        lot = txn.lot
        self.assertEqual(lot.remaining, 10)
        self.assertEqual(lot.expires_at, add_months(lot.received_at, 2))

    def test_policy_change_applies_to_points_received_afterwards(self):
        first = self.credit(self.limited, 10).lot
        PointExpiryPolicy.objects.create(expiry_months=6)
        second = self.credit(self.limited, 10).lot

        self.assertEqual(first.expires_at, add_months(first.received_at, 2))
        self.assertEqual(second.expires_at, add_months(second.received_at, 6))

    def test_limited_owner_loses_expired_points_with_a_ledger_entry(self):
        self.credit(self.limited, 10)
        wallet = PointService.get_or_create_wallet(self.limited)
        age_lots(wallet)

        self.assertEqual(PointService.get_balance(self.limited), 0)
        expiry = PointTransaction.objects.get(seller=self.limited, transaction_type=PointTransaction.TYPE_EXPIRY)
        self.assertEqual((expiry.amount, expiry.balance_before, expiry.balance_after), (10, 10, 0))
        self.assertIsNone(expiry.actor)

        totals = PointService.get_ledger_totals(self.limited)
        self.assertEqual(totals["total_expired"], 10)
        # Lost, not spent.
        self.assertEqual(totals["total_spent"], 0)

    def test_full_owner_points_never_expire(self):
        self.credit(self.full, 10)
        age_lots(PointService.get_or_create_wallet(self.full), days=400)

        self.assertEqual(PointService.get_balance(self.full), 10)
        self.assertFalse(PointTransaction.objects.filter(transaction_type=PointTransaction.TYPE_EXPIRY).exists())

    def test_spending_takes_the_soonest_expiring_points_first(self):
        older = self.credit(self.limited, 10).lot
        newer = self.credit(self.limited, 10).lot
        older.expires_at = timezone.now() + timedelta(days=5)
        older.save()

        PointService.debit(
            seller=self.limited, amount=15, transaction_type=PointTransaction.TYPE_PRODUCT_CREATION, reason="Spend"
        )
        older.refresh_from_db()
        newer.refresh_from_db()
        self.assertEqual((older.remaining, newer.remaining), (0, 5))

        # The spent batch running out costs nothing more.
        older.expires_at = timezone.now() - timedelta(days=1)
        older.save()
        self.assertEqual(PointService.get_balance(self.limited), 5)

    def test_expired_points_cannot_be_spent(self):
        self.credit(self.limited, 10)
        age_lots(PointService.get_or_create_wallet(self.limited))

        with self.assertRaises(InsufficientPointsError):
            PointService.debit(
                seller=self.limited, amount=5, transaction_type=PointTransaction.TYPE_PRODUCT_CREATION, reason="Spend"
            )

    def test_only_the_due_batch_expires(self):
        self.credit(self.limited, 10)
        due = self.credit(self.limited, 4).lot
        due.expires_at = timezone.now() - timedelta(hours=1)
        due.save()

        self.assertEqual(PointService.get_balance(self.limited), 10)

    def test_wallet_payload_reports_expiry(self):
        self.credit(self.limited, 10)
        client = APIClient()
        client.force_authenticate(user=self.limited.user)

        data = client.get("/api/points/wallet/").data
        self.assertTrue(data["points_expire"])
        self.assertEqual(data["expiry_months"], 2)
        self.assertEqual([row["points"] for row in data["upcoming_expiries"]], [10])

        client.force_authenticate(user=self.full.user)
        self.credit(self.full, 10)
        data = client.get("/api/points/wallet/").data
        self.assertFalse(data["points_expire"])
        self.assertEqual(data["upcoming_expiries"], [])

    def test_reading_the_wallet_applies_due_expiry(self):
        self.credit(self.limited, 10)
        age_lots(PointService.get_or_create_wallet(self.limited))
        client = APIClient()
        client.force_authenticate(user=self.limited.user)

        data = client.get("/api/points/wallet/").data
        self.assertEqual(data["balance"], 0)
        self.assertEqual(data["total_expired"], 10)


class StaffPointExpiryTests(PointExpiryTestCase):
    def test_superuser_points_never_expire(self):
        PointService.mint_points(self.root, 100, "Mint")
        age_lots(PointService.get_or_create_staff_wallet(self.root), days=400)

        self.assertEqual(PointService.get_staff_balance(self.root), 100)

    def test_admin_points_expire(self):
        self.fund_admin(50)
        wallet = PointService.get_or_create_staff_wallet(self.admin)
        age_lots(wallet)

        # Any locked use expires them first, so the admin cannot hand them on.
        with self.assertRaises(PointError):
            PointService.adjust_points(self.limited, 10, "CREDIT", "Give", actor=self.admin)
        wallet = PointService.expire_due_staff_points(wallet)
        self.assertEqual(wallet.balance, 0)
        self.assertTrue(
            StaffPointTransaction.objects.filter(wallet=wallet, transaction_type=StaffPointTransaction.TYPE_EXPIRY).exists()
        )

    def test_admin_with_expiry_off_keeps_points(self):
        self.fund_admin(50)
        PointService.set_staff_points_expire(self.admin, False)
        age_lots(PointService.get_or_create_staff_wallet(self.admin), days=400)

        self.assertEqual(PointService.get_staff_balance(self.admin), 50)

    def test_turning_expiry_back_on_restarts_the_clock(self):
        self.fund_admin(50)
        PointService.set_staff_points_expire(self.admin, False)
        wallet = PointService.get_or_create_staff_wallet(self.admin)
        age_lots(wallet, days=400)

        PointService.set_staff_points_expire(self.admin, True)
        self.assertEqual(PointService.get_staff_balance(self.admin), 50)
        lot = wallet.lots.get(remaining__gt=0)
        self.assertGreater(lot.expires_at, timezone.now() + timedelta(days=55))

    def test_points_given_to_a_seller_start_a_fresh_clock(self):
        self.fund_admin(50)
        staff_lot = PointService.get_or_create_staff_wallet(self.admin).lots.get()
        staff_lot.expires_at = timezone.now() + timedelta(days=3)
        staff_lot.save()

        txn = PointService.adjust_points(self.limited, 20, "CREDIT", "Give", actor=self.admin)
        staff_lot.refresh_from_db()
        self.assertEqual(staff_lot.remaining, 30)
        self.assertEqual(txn.lot.expires_at, add_months(txn.lot.received_at, 2))

    def test_superuser_wallet_cannot_be_switched(self):
        with self.assertRaises(PointError):
            PointService.set_staff_points_expire(self.root, False)


class ExpiryToggleApiTests(PointExpiryTestCase):
    def setUp(self):
        self.client = APIClient()

    def _post(self, actor, target, enabled):
        self.client.force_authenticate(user=actor)
        return self.client.post(
            f"/api/points/staff/{target.pk}/expiry/",
            {"enabled": enabled, "reason": "Trusted admin"},
            format="json",
        )

    def test_superuser_switches_an_admin_with_an_audit_entry(self):
        res = self._post(self.root, self.admin, False)
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertFalse(res.data["points_expire"])
        self.assertTrue(
            AuditLog.objects.filter(action="SUPERUSER_POINTS_EXPIRY_DISABLED", actor=self.root).exists()
        )

        data = self.client.get(f"/api/points/staff/{self.admin.pk}/").data
        self.assertFalse(data["points_expire"])
        self.assertFalse(data["expiry_enabled"])

    def test_non_superuser_is_refused(self):
        self.assertEqual(self._post(self.admin, self.admin, False).status_code, status.HTTP_403_FORBIDDEN)

    def test_superuser_target_is_refused(self):
        other_root = User.objects.create_superuser(
            username="exp_root_two", email="exp_root_two@minishop.com", password="RootPassword123!"
        )
        res = self._post(self.root, other_root, False)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("never expire", res.data["error"])

    def test_staff_summary_reports_expiry(self):
        self.fund_admin(30)
        self.client.force_authenticate(user=self.admin)
        data = self.client.get("/api/points/staff/me/").data
        self.assertTrue(data["points_expire"])
        self.assertEqual([row["points"] for row in data["upcoming_expiries"]], [30])

        self.client.force_authenticate(user=self.root)
        data = self.client.get("/api/points/staff/me/").data
        self.assertFalse(data["points_expire"])
        self.assertEqual(data["upcoming_expiries"], [])


class ExpirePointsCommandTests(PointExpiryTestCase):
    def test_command_expires_untouched_wallets_and_skips_exempt_ones(self):
        self.credit(self.limited, 10)
        self.credit(self.full, 10)
        self.fund_admin(20)
        for wallet in (
            PointService.get_or_create_wallet(self.limited),
            PointService.get_or_create_wallet(self.full),
            PointService.get_or_create_staff_wallet(self.admin),
            PointService.get_or_create_staff_wallet(self.root),
        ):
            age_lots(wallet)

        out = StringIO()
        call_command("expire_points", stdout=out)
        self.assertIn("Expired 30 point(s): 1 seller wallet(s), 1 staff wallet(s).", out.getvalue())

        self.assertEqual(PointService.get_or_create_wallet(self.limited).balance, 0)
        self.assertEqual(PointService.get_or_create_wallet(self.full).balance, 10)
        self.assertEqual(PointService.get_or_create_staff_wallet(self.admin).balance, 0)

    def test_dry_run_changes_nothing(self):
        self.credit(self.limited, 10)
        age_lots(PointService.get_or_create_wallet(self.limited))

        call_command("expire_points", "--dry-run", stdout=StringIO())
        self.assertEqual(PointService.get_or_create_wallet(self.limited).balance, 10)


class SellerTypeChangeRestartsClockTests(PointExpiryTestCase):
    def test_full_owner_made_limited_keeps_old_points_for_a_full_period(self):
        self.credit(self.full, 10)
        wallet = PointService.get_or_create_wallet(self.full)
        age_lots(wallet, days=400)

        client = Client()
        client.force_login(self.root)
        response = client.post(
            reverse("admin:sellers_sellerprofile_change", args=[self.full.pk]),
            {
                "user": str(self.full.user_id),
                "seller_type": SellerProfile.TYPE_LIMITED_SHOP_OWNER,
                "business_name": self.full.business_name,
                "business_email": "",
                "business_phone": "",
                "tax_id": "",
                "description": "",
                "rejection_reason": "",
                "suspension_reason": "",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)

        self.assertEqual(PointService.get_balance(self.full), 10)
        self.assertGreater(wallet.lots.get().expires_at, timezone.now() + timedelta(days=55))


class ProductCreationCostFloorTests(TestCase):
    def test_cost_cannot_be_set_to_zero(self):
        with self.assertRaises(ValidationError):
            ProductCreationCost(required_points=0).full_clean()

    def test_a_zero_row_still_charges_one_point(self):
        ProductCreationCost.objects.filter(pk=1).delete()
        ProductCreationCost.objects.bulk_create([ProductCreationCost(pk=1, required_points=0)])
        self.assertEqual(PointService.get_product_creation_cost(), 1)

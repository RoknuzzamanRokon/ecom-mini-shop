import threading
import time
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, transaction
from django.db.utils import OperationalError
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient

from points.models import PointTransaction, SellerWallet
from points.services import (
    InsufficientPointsError,
    InvalidAmountError,
    InvalidTransactionError,
    PointService,
)
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile

User = get_user_model()


class PointSystemUnitAndAPITests(TestCase):
    def setUp(self):
        # Seed RBAC system
        call_command("seed_rbac")

        self.client = APIClient()

        # Regular user & active seller A
        self.user_a = User.objects.create_user(
            username="seller_a",
            email="seller_a@example.com",
            password="TestPassword123!",
        )
        self.seller_a = SellerProfile.objects.create(
            user=self.user_a,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Seller Alpha Store",
            status=SellerProfile.STATUS_ACTIVE,
        )

        # Regular user & active seller B
        self.user_b = User.objects.create_user(
            username="seller_b",
            email="seller_b@example.com",
            password="TestPassword123!",
        )
        self.seller_b = SellerProfile.objects.create(
            user=self.user_b,
            seller_type=SellerProfile.TYPE_LIMITED_SHOP_OWNER,
            business_name="Seller Beta Store",
            status=SellerProfile.STATUS_ACTIVE,
        )

        # Staff Admin user (has points.view, points.adjust, points.add, points.deduct)
        self.staff_admin = User.objects.create_user(
            username="staff_admin",
            email="admin@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        assign_user_role(self.staff_admin, Role.ROLE_ADMINISTRATOR)

        # Finance Staff user (has points.view, points.adjust, points.add, points.deduct)
        self.staff_finance = User.objects.create_user(
            username="staff_finance",
            email="finance@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        assign_user_role(self.staff_finance, Role.ROLE_FINANCE)

        # Unauthorized staff user (Support team has orders/tickets, but NO points permissions)
        self.staff_support = User.objects.create_user(
            username="staff_support",
            email="support@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        assign_user_role(self.staff_support, Role.ROLE_SUPPORT_TEAM)

    # 1. Seller wallet creation & 2. Initial balance
    def test_seller_wallet_creation_and_initial_balance(self):
        """A new seller wallet is created with 0 initial balance."""
        wallet = PointService.get_or_create_wallet(self.seller_a)
        self.assertIsNotNone(wallet)
        self.assertEqual(wallet.balance, 0)
        self.assertEqual(PointService.get_balance(self.seller_a), 0)
        self.assertEqual(str(wallet), f"{self.seller_a.business_name} Wallet (0 pts)")

    # 3. Credit transaction & 5. Ledger creation
    def test_credit_transaction_and_ledger_creation(self):
        """Crediting points increases wallet balance and creates an immutable ledger entry."""
        txn = PointService.credit(
            seller=self.seller_a,
            amount=100,
            transaction_type=PointTransaction.TYPE_BONUS,
            reason="Welcome onboarding bonus",
            actor=self.staff_admin,
            reference_type="CAMPAIGN",
            reference_id="ONBOARD-2026",
        )

        self.assertEqual(txn.amount, 100)
        self.assertEqual(txn.balance_before, 0)
        self.assertEqual(txn.balance_after, 100)
        self.assertEqual(txn.transaction_type, PointTransaction.TYPE_BONUS)
        self.assertEqual(txn.reason, "Welcome onboarding bonus")
        self.assertEqual(txn.reference_type, "CAMPAIGN")
        self.assertEqual(txn.reference_id, "ONBOARD-2026")
        self.assertEqual(txn.actor, self.staff_admin)

        # Check wallet
        self.assertEqual(PointService.get_balance(self.seller_a), 100)
        self.assertEqual(PointTransaction.objects.filter(seller=self.seller_a).count(), 1)

    # 4. Debit transaction & 6. Balance tracking
    def test_debit_transaction_and_sequential_balance_tracking(self):
        """Sequential credit and debit operations accurately track balances."""
        PointService.credit(
            seller=self.seller_a,
            amount=200,
            transaction_type=PointTransaction.TYPE_ADMIN_CREDIT,
            reason="Initial grant",
        )
        self.assertEqual(PointService.get_balance(self.seller_a), 200)

        txn_debit1 = PointService.debit(
            seller=self.seller_a,
            amount=50,
            transaction_type=PointTransaction.TYPE_PRODUCT_CREATION,
            reason="Product publishing fee",
            reference_type="PRODUCT",
            reference_id="PROD-101",
        )
        self.assertEqual(txn_debit1.balance_before, 200)
        self.assertEqual(txn_debit1.balance_after, 150)
        self.assertEqual(PointService.get_balance(self.seller_a), 150)

        txn_debit2 = PointService.debit(
            seller=self.seller_a,
            amount=100,
            transaction_type=PointTransaction.TYPE_ADMIN_DEBIT,
            reason="Adjustment penalty",
        )
        self.assertEqual(txn_debit2.balance_before, 150)
        self.assertEqual(txn_debit2.balance_after, 50)
        self.assertEqual(PointService.get_balance(self.seller_a), 50)

        # History order is newest first
        history = PointService.get_transaction_history(self.seller_a)
        self.assertEqual(history.count(), 3)
        self.assertEqual(history[0].id, txn_debit2.id)

    # 7. Insufficient points
    def test_insufficient_points_raises_exception_and_leaves_balance_intact(self):
        """Debiting more points than available balance raises InsufficientPointsError and makes no changes."""
        PointService.credit(
            seller=self.seller_a,
            amount=30,
            transaction_type=PointTransaction.TYPE_BONUS,
            reason="Small bonus",
        )

        with self.assertRaises(InsufficientPointsError):
            PointService.debit(
                seller=self.seller_a,
                amount=50,
                transaction_type=PointTransaction.TYPE_ADMIN_DEBIT,
                reason="Overdraft attempt",
            )

        # Balance remains 30, only 1 transaction exists
        self.assertEqual(PointService.get_balance(self.seller_a), 30)
        self.assertEqual(PointTransaction.objects.filter(seller=self.seller_a).count(), 1)

    # 8. Negative balance prevention
    def test_negative_balance_prevention_on_model(self):
        """Model validation prevents setting negative balance directly."""
        wallet = PointService.get_or_create_wallet(self.seller_a)
        wallet.balance = -10
        with self.assertRaises(ValidationError):
            wallet.clean()

    # 12. Transaction reason requirement
    def test_transaction_reason_mandatory(self):
        """Empty or whitespace reason must be rejected."""
        with self.assertRaises(InvalidTransactionError):
            PointService.credit(
                seller=self.seller_a,
                amount=10,
                transaction_type=PointTransaction.TYPE_BONUS,
                reason="   ",
            )

        with self.assertRaises(InvalidAmountError):
            PointService.credit(
                seller=self.seller_a,
                amount=0,
                transaction_type=PointTransaction.TYPE_BONUS,
                reason="Valid reason",
            )

    # 13. Reference object support
    def test_reference_object_support(self):
        """Transactions properly store and can be filtered by domain reference."""
        PointService.credit(
            seller=self.seller_a,
            amount=50,
            transaction_type=PointTransaction.TYPE_REFUND,
            reason="Refund for cancelled order",
            reference_type="ORDER",
            reference_id="ORD-998877",
        )

        txn = PointTransaction.objects.get(reference_type="ORDER", reference_id="ORD-998877")
        self.assertEqual(txn.amount, 50)
        self.assertEqual(txn.seller, self.seller_a)

    # 14. Atomic transaction rollback
    def test_atomic_transaction_rollback_on_failure(self):
        """If a failure occurs during a point operation, database state rolls back completely."""
        PointService.credit(
            seller=self.seller_a,
            amount=100,
            transaction_type=PointTransaction.TYPE_BONUS,
            reason="Initial points",
        )
        initial_balance = PointService.get_balance(self.seller_a)
        initial_txn_count = PointTransaction.objects.filter(seller=self.seller_a).count()

        # Simulate a transaction failure midway by wrapping in an atomic block that raises an error
        try:
            with transaction.atomic():
                PointService.credit(
                    seller=self.seller_a,
                    amount=50,
                    transaction_type=PointTransaction.TYPE_BONUS,
                    reason="Temporary grant",
                )
                # Deliberate failure inside the atomic block
                raise RuntimeError("Simulated system failure before commit")
        except RuntimeError:
            pass

        # Verify full rollback: balance and transaction count are strictly unchanged
        self.assertEqual(PointService.get_balance(self.seller_a), initial_balance)
        self.assertEqual(
            PointTransaction.objects.filter(seller=self.seller_a).count(),
            initial_txn_count,
        )

    # 11. Seller ownership/security API tests
    def test_seller_wallet_ownership_api(self):
        """A seller can view their own wallet and history, but cannot access others."""
        PointService.credit(self.seller_a, 75, PointTransaction.TYPE_BONUS, "Alpha bonus")
        PointService.credit(self.seller_b, 120, PointTransaction.TYPE_BONUS, "Beta bonus")

        # Seller A views own wallet
        self.client.force_authenticate(user=self.user_a)
        resp_a = self.client.get("/api/points/wallet/")
        self.assertEqual(resp_a.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_a.data["balance"], 75)
        self.assertEqual(resp_a.data["business_name"], self.seller_a.business_name)

        # Seller A views own history
        history_a = self.client.get("/api/points/history/")
        self.assertEqual(history_a.status_code, status.HTTP_200_OK)
        self.assertEqual(len(history_a.data["results"] if "results" in history_a.data else history_a.data), 1)

        # Seller A attempts to access staff endpoint for Seller B -> 403 Forbidden
        staff_access = self.client.get(f"/api/points/sellers/{self.seller_b.pk}/")
        self.assertEqual(staff_access.status_code, status.HTTP_403_FORBIDDEN)

        # User without seller profile calling wallet endpoint -> 403 Forbidden
        user_c = User.objects.create_user(username="no_seller_user", password="TestPassword123!")
        self.client.force_authenticate(user=user_c)
        no_wallet_resp = self.client.get("/api/points/wallet/")
        self.assertEqual(no_wallet_resp.status_code, status.HTTP_403_FORBIDDEN)

    # 9. Unauthorized staff adjustment & 10. Authorized staff adjustment
    def test_staff_point_adjustment_permissions(self):
        """Only staff with appropriate RBAC permission can adjust points."""
        PointService.credit(self.seller_a, 50, PointTransaction.TYPE_BONUS, "Initial")

        # 1. Anonymous user -> 401 Unauthorized
        self.client.force_authenticate(user=None)
        anon_resp = self.client.post(
            f"/api/points/sellers/{self.seller_a.pk}/adjust/",
            {"action": "CREDIT", "amount": 25, "reason": "Test"},
            format="json",
        )
        self.assertEqual(anon_resp.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Staff without points.adjust (Support) -> 403 Forbidden
        self.client.force_authenticate(user=self.staff_support)
        support_resp = self.client.post(
            f"/api/points/sellers/{self.seller_a.pk}/adjust/",
            {"action": "CREDIT", "amount": 25, "reason": "Unauthorized attempt"},
            format="json",
        )
        self.assertEqual(support_resp.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Authorized staff (Administrator) -> 200 OK
        self.client.force_authenticate(user=self.staff_admin)
        admin_resp = self.client.post(
            f"/api/points/sellers/{self.seller_a.pk}/adjust/",
            {
                "action": "CREDIT",
                "amount": 100,
                "reason": "Performance grant by Administrator",
                "reference_type": "AWARD",
                "reference_id": "AWD-2026",
            },
            format="json",
        )
        self.assertEqual(admin_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_resp.data["current_balance"], 150)
        self.assertEqual(PointService.get_balance(self.seller_a), 150)

        # 4. Authorized Finance user executing a debit -> 200 OK
        self.client.force_authenticate(user=self.staff_finance)
        finance_resp = self.client.post(
            f"/api/points/sellers/{self.seller_a.pk}/adjust/",
            {
                "action": "DEBIT",
                "amount": 40,
                "reason": "Audit correction fee",
            },
            format="json",
        )
        self.assertEqual(finance_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(finance_resp.data["current_balance"], 110)
        self.assertEqual(PointService.get_balance(self.seller_a), 110)

        # 5. Overdraft attempt by staff -> 400 Bad Request
        overdraft_resp = self.client.post(
            f"/api/points/sellers/{self.seller_a.pk}/adjust/",
            {
                "action": "DEBIT",
                "amount": 9999,
                "reason": "Excessive deduction",
            },
            format="json",
        )
        self.assertEqual(overdraft_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(PointService.get_balance(self.seller_a), 110)


class PointConcurrencyTests(TransactionTestCase):
    """
    Concurrency safety tests using TransactionTestCase (real DB transactions).
    Verifies that simultaneous deductions serialize properly and cannot cause negative balances.
    """

    def setUp(self):
        call_command("seed_rbac")
        self.user = User.objects.create_user(
            username="concurrency_seller",
            password="TestPassword123!",
        )
        self.seller = SellerProfile.objects.create(
            user=self.user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Concurrent Mart",
            status=SellerProfile.STATUS_ACTIVE,
        )

    def test_concurrent_deductions_prevent_race_conditions_and_negative_balance(self):
        """
        Start with 100 points.
        Spawn 5 threads each attempting to debit 40 points (total attempted: 200).
        Exactly 2 must succeed (80 deducted, final balance 20), and 3 must fail with InsufficientPointsError.
        Final balance must never be negative or corrupted.
        """
        PointService.credit(
            seller=self.seller,
            amount=100,
            transaction_type=PointTransaction.TYPE_BONUS,
            reason="Initial seed points",
        )

        success_count = [0]
        failure_count = [0]
        lock = threading.Lock()

        def attempt_deduction():
            connection.close()
            max_retries = 25
            for attempt in range(max_retries):
                try:
                    PointService.debit(
                        seller=self.seller,
                        amount=40,
                        transaction_type=PointTransaction.TYPE_PRODUCT_CREATION,
                        reason="Concurrent deduction test",
                    )
                    with lock:
                        success_count[0] += 1
                    break
                except InsufficientPointsError:
                    with lock:
                        failure_count[0] += 1
                    break
                except OperationalError as e:
                    if "locked" in str(e).lower() and attempt < max_retries - 1:
                        time.sleep(0.05 * (attempt + 1))
                        continue
                    raise
                finally:
                    connection.close()

        threads = [threading.Thread(target=attempt_deduction) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Re-fetch wallet
        final_balance = PointService.get_balance(self.seller)

        # Assertions
        self.assertEqual(success_count[0], 2, f"Expected exactly 2 successes, got {success_count[0]}")
        self.assertEqual(failure_count[0], 3, f"Expected exactly 3 failures, got {failure_count[0]}")
        self.assertEqual(final_balance, 20, f"Expected final balance 20, got {final_balance}")
        self.assertGreaterEqual(final_balance, 0, "Balance must never drop below zero")

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

from points.models import (
    PointTransaction,
    ProductCreationCost,
    SellerWallet,
    StaffPointTransaction,
    StaffWallet,
)
from points.services import (
    InsufficientPointsError,
    InsufficientStaffPointsError,
    InvalidAmountError,
    InvalidTransactionError,
    PointError,
    PointService,
)
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile

User = get_user_model()


def fund_staff_wallet(user, amount):
    """Fixture: points a staff member can hand out, since a staff credit comes out of their wallet."""
    wallet = PointService.get_or_create_staff_wallet(user)
    wallet.balance += amount
    wallet.save()


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
        fund_staff_wallet(self.staff_admin, 100)
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


class SellerWalletContractTests(TestCase):
    """
    Known Issues #3 and #11. The seller wallet page read `wallet.total_earned` /
    `wallet.total_spent`, which `SellerWalletSerializer` never returned, and
    `txn.description`, which `PointTransactionSerializer` never returned either --
    so the tiles showed +0/-0 forever and every ledger row read "Point transaction".
    The seller products page hardcoded a creation cost of 5 while the backend
    charged the configurable `ProductCreationCost`.

    These tests pin the API contract the frontend types now mirror.
    """

    def setUp(self):
        call_command("seed_rbac")
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="wallet_contract_seller",
            email="wallet_contract@example.com",
            password="TestPassword123!",
        )
        self.seller = SellerProfile.objects.create(
            user=self.user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Contract Traders",
            status=SellerProfile.STATUS_ACTIVE,
        )

    def _fund_and_spend(self):
        """Credits 100 + 40, debits 30 + 25. Balance 85, earned 140, spent 55."""
        PointService.credit(
            seller=self.seller, amount=100,
            transaction_type=PointTransaction.TYPE_BONUS,
            reason="Welcome bonus",
        )
        PointService.credit(
            seller=self.seller, amount=40,
            transaction_type=PointTransaction.TYPE_ADMIN_CREDIT,
            reason="Staff top-up for campaign",
        )
        PointService.debit(
            seller=self.seller, amount=30,
            transaction_type=PointTransaction.TYPE_PRODUCT_CREATION,
            reason="Listing fee for six products",
        )
        PointService.debit(
            seller=self.seller, amount=25,
            transaction_type=PointTransaction.TYPE_ADMIN_DEBIT,
            reason="Correction for a duplicate credit",
        )

    def _wallet_payload(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/points/wallet/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data

    # --- #3: wallet totals -------------------------------------------------

    def test_wallet_totals_are_zero_with_an_empty_ledger(self):
        payload = self._wallet_payload()
        self.assertEqual(payload["balance"], 0)
        self.assertEqual(payload["total_earned"], 0)
        self.assertEqual(payload["total_spent"], 0)

    def test_balance_is_unchanged_and_totals_come_from_the_ledger(self):
        self._fund_and_spend()
        payload = self._wallet_payload()
        self.assertEqual(payload["balance"], 85)
        self.assertEqual(payload["total_earned"], 140)
        self.assertEqual(payload["total_spent"], 55)
        # The wallet stores only the balance; the totals must reconcile with it.
        self.assertEqual(
            payload["total_earned"] - payload["total_spent"], payload["balance"]
        )

    def test_totals_are_aggregated_from_transactions_not_stored_on_the_wallet(self):
        """
        The decisive one: SellerWallet must carry no total columns, and deleting a
        ledger row must move the totals. A stored total would not budge.
        """
        self._fund_and_spend()

        wallet_columns = {f.name for f in SellerWallet._meta.get_fields()}
        self.assertNotIn("total_earned", wallet_columns)
        self.assertNotIn("total_spent", wallet_columns)

        self.assertEqual(self._wallet_payload()["total_spent"], 55)

        PointTransaction.objects.filter(
            seller=self.seller, transaction_type=PointTransaction.TYPE_ADMIN_DEBIT
        ).delete()

        payload = self._wallet_payload()
        self.assertEqual(payload["total_spent"], 30, "totals must follow the ledger")
        self.assertEqual(payload["total_earned"], 140)
        # Balance is the wallet's own column and is deliberately untouched by this.
        self.assertEqual(payload["balance"], 85)

    def test_totals_are_scoped_to_the_requesting_seller(self):
        self._fund_and_spend()
        other_user = User.objects.create_user(
            username="wallet_contract_other", password="TestPassword123!"
        )
        other_seller = SellerProfile.objects.create(
            user=other_user,
            seller_type=SellerProfile.TYPE_LIMITED_SHOP_OWNER,
            business_name="Unrelated Traders",
            status=SellerProfile.STATUS_ACTIVE,
        )
        PointService.credit(
            seller=other_seller, amount=999,
            transaction_type=PointTransaction.TYPE_BONUS,
            reason="Someone else's money",
        )
        payload = self._wallet_payload()
        self.assertEqual(payload["total_earned"], 140)
        self.assertEqual(payload["total_spent"], 55)

    def test_service_totals_classify_by_balance_direction_not_by_type(self):
        """
        A REFUND credits and an ADJUSTMENT can go either way, so the split is taken
        from balance_after vs balance_before rather than a list of type names.
        """
        PointService.credit(
            seller=self.seller, amount=10,
            transaction_type=PointTransaction.TYPE_REFUND,
            reason="Refund for a rejected product",
        )
        PointService.debit(
            seller=self.seller, amount=4,
            transaction_type=PointTransaction.TYPE_ADJUSTMENT,
            reason="Downward adjustment",
        )
        totals = PointService.get_ledger_totals(self.seller)
        self.assertEqual(totals["total_earned"], 10)
        self.assertEqual(totals["total_spent"], 4)

    # --- #3: transaction reason -------------------------------------------

    def test_history_exposes_reason_and_no_description_field(self):
        self._fund_and_spend()
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/points/history/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertIn("reason", row)
            self.assertNotIn("description", row)
            self.assertTrue(row["reason"].strip())
        self.assertEqual(
            {row["reason"] for row in rows},
            {
                "Welcome bonus",
                "Staff top-up for campaign",
                "Listing fee for six products",
                "Correction for a duplicate credit",
            },
        )

    # --- #11: configured product creation cost -----------------------------

    def test_wallet_exposes_the_configured_product_creation_cost(self):
        self.assertEqual(
            self._wallet_payload()["product_creation_cost"],
            PointService.get_product_creation_cost(),
        )

    def test_product_creation_cost_follows_the_admin_configured_value(self):
        """The UI must track ProductCreationCost, not a hardcoded 5."""
        config, _ = ProductCreationCost.objects.get_or_create(pk=1)
        config.required_points = 5
        config.save()
        self.assertEqual(self._wallet_payload()["product_creation_cost"], 5)

        config.required_points = 12
        config.save()
        self.assertEqual(self._wallet_payload()["product_creation_cost"], 12)
        self.assertEqual(PointService.get_product_creation_cost(), 12)

        config.required_points = 5
        config.save()

    # --- contract shape ----------------------------------------------------

    def test_wallet_payload_shape_matches_the_frontend_type(self):
        payload = self._wallet_payload()
        self.assertEqual(
            set(payload.keys()),
            {
                "id",
                "seller_id",
                "business_name",
                "balance",
                "total_earned",
                "total_spent",
                "total_expired",
                "product_creation_cost",
                "points_expire",
                "expiry_months",
                "upcoming_expiries",
                "created_at",
                "updated_at",
            },
        )
        # The TS type used to declare `seller_name`, which never existed.
        self.assertNotIn("seller_name", payload)
        self.assertEqual(payload["business_name"], "Contract Traders")

    def test_transaction_payload_shape_matches_the_frontend_type(self):
        self._fund_and_spend()
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/points/history/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(
            set(rows[0].keys()),
            {
                "id",
                "wallet_id",
                "seller_id",
                "business_name",
                "transaction_type",
                "transaction_type_display",
                "amount",
                "balance_before",
                "balance_after",
                "reason",
                "reference_type",
                "reference_id",
                "actor_id",
                "actor_username",
                "created_at",
            },
        )


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


class PointActionAuthorizationTests(TestCase):
    """
    Phase 1G-B: per-action authorization on the point adjustment endpoint.

    'points.add' and 'points.deduct' are one-way authorities. Before this phase
    the endpoint only checked that the actor held ONE of add/deduct/adjust and
    then performed whichever direction the body asked for, so an actor with
    'points.add' alone could debit a seller's balance.

    Every role below is an ISOLATED test-only fixture built from the real
    permission catalogue. No shipped role's permissions are modified — in
    particular this suite never grants OPERATION_MANAGER a points permission.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        from rbac.models import Permission, RolePermission

        cls.seller_user = User.objects.create_user(
            username="pa_seller", email="pa_seller@minishop.com", password="SellerPassword123!"
        )
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Point Action Shop",
            status=SellerProfile.STATUS_ACTIVE,
        )

        def make_actor(username, role_code, permission_codes):
            role = Role.objects.create(code=role_code, name=role_code.title())
            for code in permission_codes:
                RolePermission.objects.create(
                    role=role, permission=Permission.objects.get(code=code)
                )
            user = User.objects.create_user(
                username=username, email=f"{username}@minishop.com", password="ActorPassword123!"
            )
            assign_user_role(user, role_code)
            return user

        cls.adder = make_actor("pa_adder", "PA_ADD_ONLY", ["points.add"])
        cls.deducter = make_actor("pa_deducter", "PA_DEDUCT_ONLY", ["points.deduct"])
        cls.adjuster = make_actor("pa_adjuster", "PA_ADJUST_ONLY", ["points.adjust"])
        cls.viewer = make_actor("pa_viewer", "PA_VIEW_ONLY", ["points.view"])

        cls.wildcard = User.objects.create_superuser(
            username="pa_wildcard", email="pa_wildcard@minishop.com", password="WildPassword123!"
        )
        assign_user_role(cls.wildcard, Role.ROLE_SUPER_ADMINISTRATOR)

    def setUp(self):
        self.client = APIClient()
        self.url = f"/api/points/sellers/{self.seller.pk}/adjust/"
        # A starting balance so DEBIT attempts fail on AUTHORIZATION, never on
        # an empty wallet — otherwise a 400 could be mistaken for a 403. The
        # same goes for CREDIT, which comes out of the actor's own wallet.
        PointService.credit(self.seller, 500, PointTransaction.TYPE_BONUS, "Test float")
        for actor in (self.adder, self.deducter, self.adjuster, self.wildcard):
            fund_staff_wallet(actor, 500)

    def _adjust(self, actor, action, amount=10):
        self.client.force_authenticate(user=actor)
        return self.client.post(
            self.url,
            {"action": action, "amount": amount, "reason": f"{action} authorization test"},
            format="json",
        )

    # -- the 8 permission/action combinations --------------------------------

    def test_1_add_only_may_credit(self):
        res = self._adjust(self.adder, "CREDIT")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(PointService.get_balance(self.seller), 510)

    def test_2_add_only_may_not_debit(self):
        """The core gap this phase closes."""
        res = self._adjust(self.adder, "DEBIT")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(PointService.get_balance(self.seller), 500)

    def test_3_deduct_only_may_debit(self):
        res = self._adjust(self.deducter, "DEBIT")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(PointService.get_balance(self.seller), 490)

    def test_4_deduct_only_may_not_credit(self):
        res = self._adjust(self.deducter, "CREDIT")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(PointService.get_balance(self.seller), 500)

    def test_5_adjust_only_may_credit(self):
        res = self._adjust(self.adjuster, "CREDIT")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(PointService.get_balance(self.seller), 510)

    def test_6_adjust_only_may_debit(self):
        res = self._adjust(self.adjuster, "DEBIT")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(PointService.get_balance(self.seller), 490)

    def test_7_wildcard_may_credit(self):
        res = self._adjust(self.wildcard, "CREDIT")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(PointService.get_balance(self.seller), 510)

    def test_8_wildcard_may_debit(self):
        res = self._adjust(self.wildcard, "DEBIT")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(PointService.get_balance(self.seller), 490)

    # -- everything else -----------------------------------------------------

    def test_9_actor_without_any_point_permission_is_forbidden(self):
        """points.view opens the ledger, never the adjustment endpoint."""
        for action in ("CREDIT", "DEBIT"):
            res = self._adjust(self.viewer, action)
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, msg=action)
        self.assertEqual(PointService.get_balance(self.seller), 500)

    def test_9b_anonymous_is_unauthorized(self):
        self.client.force_authenticate(user=None)
        res = self.client.post(
            self.url, {"action": "CREDIT", "amount": 10, "reason": "anon"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_10_insufficient_balance_behaviour_preserved(self):
        res = self._adjust(self.deducter, "DEBIT", amount=99999)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(PointService.get_balance(self.seller), 500)

    def test_11_successful_mutation_writes_the_expected_ledger_entry(self):
        before = PointTransaction.objects.filter(seller=self.seller).count()
        res = self._adjust(self.adder, "CREDIT", amount=75)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.assertEqual(PointTransaction.objects.filter(seller=self.seller).count(), before + 1)
        txn = PointTransaction.objects.filter(seller=self.seller).order_by("-id").first()
        self.assertEqual(txn.transaction_type, PointTransaction.TYPE_ADMIN_CREDIT)
        self.assertEqual(txn.amount, 75)
        self.assertEqual(txn.balance_before, 500)
        self.assertEqual(txn.balance_after, 575)
        self.assertEqual(txn.actor, self.adder)
        self.assertTrue(txn.reason)

    def test_12_refused_action_writes_no_ledger_entry(self):
        before = PointTransaction.objects.filter(seller=self.seller).count()
        res = self._adjust(self.adder, "DEBIT")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(PointTransaction.objects.filter(seller=self.seller).count(), before)
        self.assertEqual(PointService.get_balance(self.seller), 500)

    def test_refusal_message_does_not_enumerate_permissions(self):
        """A caller must not be able to probe which point authorities exist."""
        res = self._adjust(self.adder, "DEBIT")
        detail = str(res.data.get("detail", "")).lower()
        for code in ("points.add", "points.deduct", "points.adjust"):
            self.assertNotIn(code, detail)

    def test_staff_adjustment_writes_a_central_audit_entry(self):
        from audit.models import AuditLog

        res = self._adjust(self.adder, "CREDIT", amount=25)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        entry = AuditLog.objects.filter(action="ADMIN_POINTS_CREDIT").order_by("-id").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, self.adder)
        self.assertEqual(entry.seller, self.seller)
        self.assertEqual(entry.metadata["amount"], 25)
        self.assertEqual(entry.metadata["previous_state"]["balance"], 500)
        self.assertEqual(entry.metadata["new_state"]["balance"], 525)


class SellerWalletAdminIntegrityTests(TestCase):
    """
    Phase 1G-B: the Django Admin wallet form must not be able to rewrite a
    balance, which would desynchronise it from its own PointTransaction ledger.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.seller_user = User.objects.create_user(
            username="wa_seller", email="wa_seller@minishop.com", password="SellerPassword123!"
        )
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Wallet Admin Shop",
            status=SellerProfile.STATUS_ACTIVE,
        )

    def _admin_request(self):
        """
        A real request bound to a superuser.

        ModelAdmin.get_form() builds the related-field widgets, which call
        has_add_permission(request) on the related admin — so request.user must
        exist. Passing None raises AttributeError inside Django rather than
        telling us anything about our own configuration.
        """
        from django.test import RequestFactory

        request = RequestFactory().get("/admin/")
        request.user = User.objects.create_superuser(
            username="wa_admin", email="wa_admin@minishop.com", password="AdminPassword123!"
        )
        return request

    def test_balance_is_readonly_on_the_wallet_admin_form(self):
        from django.contrib.admin.sites import site
        from points.admin import SellerWalletAdmin

        wallet = PointService.get_or_create_wallet(self.seller)
        request = self._admin_request()
        model_admin = SellerWalletAdmin(SellerWallet, site)

        self.assertIn("balance", model_admin.get_readonly_fields(request, obj=wallet))

        # A read-only field is excluded from the generated form entirely, so
        # even a hand-crafted POST has no field to smuggle a balance through.
        form_class = model_admin.get_form(request, obj=wallet)
        self.assertNotIn("balance", form_class.base_fields)

    def test_point_transaction_admin_remains_append_only(self):
        from django.contrib.admin.sites import site
        from points.admin import PointTransactionAdmin

        request = self._admin_request()
        model_admin = PointTransactionAdmin(PointTransaction, site)
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))

    def test_service_remains_the_only_balance_mutation_path(self):
        """The wallet model itself is untouched — only the admin form is locked."""
        wallet = PointService.get_or_create_wallet(self.seller)
        self.assertEqual(wallet.balance, 0)

        PointService.credit(self.seller, 40, PointTransaction.TYPE_ADMIN_CREDIT, "Service path")
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 40)
        self.assertEqual(PointTransaction.objects.filter(seller=self.seller).count(), 1)


class StaffWalletTests(TestCase):
    """
    A staff member gives a seller points out of their own StaffWallet and a
    debit returns them there; a superuser's mint_points (driven by
    utils/add_points.py) is where the points staff hand out come from.
    """

    PASSWORD = "RootPassword123!"

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        seller_user = User.objects.create_user(
            username="sw_seller", email="sw_seller@minishop.com", password="SellerPassword123!"
        )
        cls.seller = SellerProfile.objects.create(
            user=seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Staff Wallet Shop",
            status=SellerProfile.STATUS_ACTIVE,
        )
        cls.root = User.objects.create_superuser(
            username="sw_root", email="sw_root@minishop.com", password=cls.PASSWORD
        )
        cls.finance = User.objects.create_user(
            username="sw_finance", email="sw_finance@minishop.com", password="FinancePassword123!", is_staff=True
        )
        assign_user_role(cls.finance, Role.ROLE_FINANCE)
        cls.admin = User.objects.create_user(
            username="sw_admin", email="sw_admin@minishop.com", password=cls.PASSWORD, is_staff=True
        )
        assign_user_role(cls.admin, Role.ROLE_ADMINISTRATOR)
        cls.support = User.objects.create_user(
            username="sw_support", email="sw_support@minishop.com", password="SupportPassword123!", is_staff=True
        )
        assign_user_role(cls.support, Role.ROLE_SUPPORT_TEAM)

    def setUp(self):
        self.client = APIClient()
        self.url = f"/api/points/sellers/{self.seller.pk}/adjust/"

    def _adjust(self, actor, action, amount):
        self.client.force_authenticate(user=actor)
        return self.client.post(
            self.url, {"action": action, "amount": amount, "reason": "Staff wallet test"}, format="json"
        )

    # -- the rule: nobody gives what they do not have -------------------------

    def test_credit_from_an_empty_wallet_is_refused_and_changes_nothing(self):
        from audit.models import AuditLog
        from notifications.models import NotificationEvent

        res = self._adjust(self.finance, "CREDIT", 10)

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("your wallet", res.data["error"])
        self.assertEqual(res.data["available_balance"], 0)
        self.assertEqual(PointService.get_balance(self.seller), 0)
        self.assertFalse(PointTransaction.objects.filter(seller=self.seller).exists())
        self.assertFalse(StaffPointTransaction.objects.exists())
        self.assertFalse(AuditLog.objects.filter(action="ADMIN_POINTS_CREDIT").exists())
        self.assertFalse(NotificationEvent.objects.filter(event_type="points.adjusted").exists())

    def test_a_superuser_is_bound_by_the_same_rule(self):
        res = self._adjust(self.root, "CREDIT", 10)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(PointService.get_balance(self.seller), 0)

    def test_credit_cannot_exceed_the_wallet(self):
        fund_staff_wallet(self.finance, 30)
        res = self._adjust(self.finance, "CREDIT", 31)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["available_balance"], 30)
        self.assertEqual(PointService.get_staff_balance(self.finance), 30)
        self.assertEqual(PointService.get_balance(self.seller), 0)

    def test_credit_moves_points_from_the_actor_to_the_seller(self):
        fund_staff_wallet(self.finance, 100)
        res = self._adjust(self.finance, "CREDIT", 30)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["current_balance"], 30)
        self.assertEqual(res.data["actor_balance"], 70)
        self.assertIn("Your wallet now holds 70 points", res.data["message"])
        self.assertEqual(PointService.get_balance(self.seller), 30)
        self.assertEqual(PointService.get_staff_balance(self.finance), 70)

        staff_txn = StaffPointTransaction.objects.get()
        self.assertEqual(staff_txn.transaction_type, StaffPointTransaction.TYPE_SELLER_CREDIT)
        self.assertEqual((staff_txn.balance_before, staff_txn.balance_after), (100, 70))
        self.assertEqual(staff_txn.seller_transaction_id, res.data["transaction"]["id"])
        self.assertEqual(staff_txn.actor, self.finance)

    def test_debit_returns_the_points_to_the_actors_wallet(self):
        PointService.credit(self.seller, 50, PointTransaction.TYPE_BONUS, "Float")
        res = self._adjust(self.finance, "DEBIT", 20)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(PointService.get_balance(self.seller), 30)
        self.assertEqual(PointService.get_staff_balance(self.finance), 20)
        staff_txn = StaffPointTransaction.objects.get()
        self.assertEqual(staff_txn.transaction_type, StaffPointTransaction.TYPE_SELLER_DEBIT)
        self.assertEqual(staff_txn.seller_transaction_id, res.data["transaction"]["id"])

    def test_a_refused_debit_leaves_the_actors_wallet_alone(self):
        res = self._adjust(self.finance, "DEBIT", 5)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("available_balance", res.data)
        self.assertEqual(PointService.get_staff_balance(self.finance), 0)
        self.assertFalse(StaffPointTransaction.objects.exists())

    def test_an_adjustment_needs_an_actor(self):
        with self.assertRaises(InvalidTransactionError):
            PointService.adjust_points(self.seller, 5, "DEBIT", "No actor")

    # -- mint_points ----------------------------------------------------------

    def test_a_superuser_mints_into_their_own_wallet(self):
        txn = PointService.mint_points(self.root, 1000, "Opening float")
        self.assertEqual(txn.transaction_type, StaffPointTransaction.TYPE_MINT)
        self.assertEqual((txn.balance_before, txn.balance_after), (0, 1000))
        self.assertEqual(PointService.get_staff_balance(self.root), 1000)

    def test_only_a_superuser_can_mint(self):
        # ADMINISTRATOR holds every points permission, but is not a superuser.
        with self.assertRaises(PointError):
            PointService.mint_points(self.admin, 1000, "Not allowed")
        self.assertEqual(PointService.get_staff_balance(self.admin), 0)

    def test_mint_validates_amount_and_reason(self):
        for amount in (0, -5, "100"):
            with self.assertRaises(InvalidAmountError, msg=repr(amount)):
                PointService.mint_points(self.root, amount, "Bad amount")
        with self.assertRaises(InvalidTransactionError):
            PointService.mint_points(self.root, 10, "  ")
        self.assertFalse(StaffPointTransaction.objects.exists())

    # -- transfer_to_staff ----------------------------------------------------

    def test_a_superuser_hands_points_to_staff_who_can_then_credit(self):
        PointService.mint_points(self.root, 100, "Float")
        outgoing, incoming = PointService.transfer_to_staff(self.root, self.finance, 40, "Monthly budget")

        self.assertEqual((outgoing.transaction_type, outgoing.balance_after), (StaffPointTransaction.TYPE_TRANSFER_OUT, 60))
        self.assertEqual((incoming.transaction_type, incoming.balance_after), (StaffPointTransaction.TYPE_TRANSFER_IN, 40))
        self.assertEqual(outgoing.counterparty, self.finance)
        self.assertEqual(incoming.counterparty, self.root)

        res = self._adjust(self.finance, "CREDIT", 40)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(PointService.get_balance(self.seller), 40)
        self.assertEqual(PointService.get_staff_balance(self.finance), 0)

    def test_transfer_refusals(self):
        PointService.mint_points(self.root, 100, "Float")
        fund_staff_wallet(self.admin, 50)
        refused = [
            (InsufficientStaffPointsError, lambda: PointService.transfer_to_staff(self.root, self.finance, 101, "Too many")),
            (PointError, lambda: PointService.transfer_to_staff(self.root, self.root, 10, "To self")),
            # SUPPORT_TEAM cannot credit sellers, so the points would be stranded.
            (PointError, lambda: PointService.transfer_to_staff(self.root, self.support, 10, "Unusable")),
            # Only a superuser hands points on, even when the sender has some.
            (PointError, lambda: PointService.transfer_to_staff(self.admin, self.finance, 10, "Not a superuser")),
        ]
        for error, attempt in refused:
            with self.assertRaises(error):
                attempt()
        self.assertEqual(PointService.get_staff_balance(self.root), 100)
        self.assertEqual(PointService.get_staff_balance(self.finance), 0)
        self.assertEqual(PointService.get_staff_balance(self.admin), 50)

    # -- reclaim_from_staff ---------------------------------------------------

    def test_a_superuser_takes_points_back_from_staff(self):
        PointService.mint_points(self.root, 100, "Float")
        PointService.transfer_to_staff(self.root, self.finance, 40, "Monthly budget")
        outgoing, incoming = PointService.reclaim_from_staff(self.root, self.finance, 15, "Budget cut")

        self.assertEqual((outgoing.transaction_type, outgoing.balance_after), (StaffPointTransaction.TYPE_RECLAIM_OUT, 25))
        self.assertEqual((incoming.transaction_type, incoming.balance_after), (StaffPointTransaction.TYPE_RECLAIM_IN, 75))
        self.assertEqual(outgoing.wallet.user, self.finance)
        self.assertEqual(outgoing.counterparty, self.root)
        self.assertEqual(incoming.counterparty, self.finance)
        self.assertEqual((outgoing.actor, incoming.actor), (self.root, self.root))
        self.assertEqual(PointService.get_staff_balance(self.finance), 25)
        self.assertEqual(PointService.get_staff_balance(self.root), 75)

        totals = PointService.get_staff_ledger_totals(outgoing.wallet)
        self.assertEqual((totals["received"], totals["taken_back"]), (40, 15))
        self.assertEqual(PointService.get_staff_ledger_totals(incoming.wallet)["received"], 115)

    def test_points_come_back_from_staff_who_can_no_longer_use_them(self):
        # SUPPORT_TEAM cannot credit sellers, and an inactive account cannot
        # do anything: getting their points back is the point of a take-back.
        fund_staff_wallet(self.support, 30)
        fund_staff_wallet(self.finance, 20)
        self.finance.is_active = False
        self.finance.save(update_fields=["is_active"])

        PointService.reclaim_from_staff(self.root, self.support, 30, "Wrong wallet")
        PointService.reclaim_from_staff(self.root, self.finance, 20, "Left the company")
        self.assertEqual(PointService.get_staff_balance(self.support), 0)
        self.assertEqual(PointService.get_staff_balance(self.finance), 0)
        self.assertEqual(PointService.get_staff_balance(self.root), 50)

    def test_take_back_refusals(self):
        PointService.mint_points(self.root, 100, "Float")
        fund_staff_wallet(self.finance, 10)
        refused = [
            (InsufficientStaffPointsError, lambda: PointService.reclaim_from_staff(self.root, self.finance, 11, "Too many")),
            (PointError, lambda: PointService.reclaim_from_staff(self.root, self.root, 10, "From self")),
            # ADMINISTRATOR holds every points permission, but is not a superuser.
            (PointError, lambda: PointService.reclaim_from_staff(self.admin, self.finance, 5, "Not a superuser")),
            (InvalidAmountError, lambda: PointService.reclaim_from_staff(self.root, self.finance, 0, "Zero")),
            (InvalidTransactionError, lambda: PointService.reclaim_from_staff(self.root, self.finance, 5, "  ")),
        ]
        for error, attempt in refused:
            with self.assertRaises(error):
                attempt()
        self.assertEqual(PointService.get_staff_balance(self.root), 100)
        self.assertEqual(PointService.get_staff_balance(self.finance), 10)
        self.assertFalse(
            StaffPointTransaction.objects.filter(
                transaction_type__in=[StaffPointTransaction.TYPE_RECLAIM_OUT, StaffPointTransaction.TYPE_RECLAIM_IN]
            ).exists()
        )

    def test_a_refused_take_back_leaves_no_wallet_behind(self):
        with self.assertRaises(InsufficientStaffPointsError):
            PointService.reclaim_from_staff(self.root, self.support, 1, "Nothing there")
        self.assertFalse(StaffWallet.objects.filter(user=self.support).exists())

    # -- utils/add_points.py --------------------------------------------------

    def test_parse_points(self):
        from utils.add_points import parse_points

        for given, expected in (("1000", 1000), (1000, 1000), (" 25 ", 25), ("১০০", 100)):
            self.assertEqual(parse_points(given), expected, msg=repr(given))
        for bad in ("0", "-5", "10.5", "abc", "", "1e3"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                parse_points(bad)

    def test_add_points_mints_for_the_superuser_and_audits_it(self):
        from audit.models import AuditLog
        from utils.add_points import add_points

        self.assertEqual(add_points("1000", username="sw_root", password=self.PASSWORD), 1000)
        self.assertEqual(add_points("250", username="sw_root", password=self.PASSWORD), 1250)

        entry = AuditLog.objects.filter(action="SUPERUSER_POINTS_MINT").order_by("-id").first()
        self.assertEqual(entry.actor, self.root)
        self.assertEqual(entry.metadata["amount"], 250)
        self.assertEqual(entry.metadata["new_state"]["balance"], 1250)

    def test_add_points_refuses_bad_credentials_and_non_superusers(self):
        from utils.add_points import add_points

        with self.assertRaises(PermissionError):
            add_points("1000", username="sw_root", password="wrong")
        with self.assertRaises(PermissionError):
            add_points("1000", username="sw_admin", password=self.PASSWORD)
        self.assertFalse(StaffPointTransaction.objects.exists())

    def test_give_points_to_staff(self):
        from audit.models import AuditLog
        from utils.add_points import add_points, give_points_to_staff

        add_points("100", username="sw_root", password=self.PASSWORD)
        balances = give_points_to_staff("30", "sw_finance", username="sw_root", password=self.PASSWORD)

        self.assertEqual(balances, (70, 30))
        self.assertTrue(AuditLog.objects.filter(action="SUPERUSER_POINTS_TRANSFER", actor=self.root).exists())
        with self.assertRaises(LookupError):
            give_points_to_staff("5", "nobody", username="sw_root", password=self.PASSWORD)

    def test_the_command_line_entry_point(self):
        from contextlib import redirect_stderr, redirect_stdout
        from io import StringIO
        from utils.add_points import main

        out = StringIO()
        with redirect_stdout(out):
            code = main(["300", "--username", "sw_root", "--password", self.PASSWORD])
        self.assertEqual(code, 0)
        self.assertIn("sw_root's wallet: 300 points", out.getvalue())

        err = StringIO()
        with redirect_stderr(err):
            code = main(["300", "--to", "sw_support", "--username", "sw_root", "--password", self.PASSWORD])
        self.assertEqual(code, 1)
        self.assertIn("cannot credit sellers", err.getvalue())
        self.assertEqual(PointService.get_staff_balance(self.root), 300)


class StaffOwnWalletApiTests(TestCase):
    """
    GET /api/points/staff/me/ shows the caller their own staff wallet (the
    points tile on the Console profile) and never creates one.
    """

    URL = "/api/points/staff/me/"

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        seller_user = User.objects.create_user(
            username="me_seller", email="me_seller@minishop.com", password="SellerPassword123!"
        )
        cls.seller = SellerProfile.objects.create(
            user=seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="My Wallet Traders",
            status=SellerProfile.STATUS_ACTIVE,
        )
        cls.root = User.objects.create_superuser(
            username="me_root", email="me_root@minishop.com", password="RootPassword123!"
        )
        cls.finance = User.objects.create_user(
            username="me_finance", email="me_finance@minishop.com", password="FinancePassword123!", is_staff=True
        )
        assign_user_role(cls.finance, Role.ROLE_FINANCE)

    def setUp(self):
        self.client = APIClient()

    def _get(self, user):
        self.client.force_authenticate(user=user)
        res = self.client.get(self.URL)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return res.data

    def test_anonymous_is_unauthorized(self):
        self.assertEqual(self.client.get(self.URL).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_wallet_reads_zero_and_creates_none(self):
        data = self._get(self.finance)
        self.assertEqual(
            data,
            {
                "has_wallet": False,
                "balance": 0,
                "received": 0,
                "given_to_sellers": 0,
                "sent_to_staff": 0,
                "taken_back": 0,
                "expired": 0,
                "transaction_count": 0,
                "can_mint": False,
                "points_expire": True,
                "expiry_enabled": True,
                "expiry_months": 2,
                "upcoming_expiries": [],
                "recent": [],
            },
        )
        self.assertFalse(StaffWallet.objects.filter(user=self.finance).exists())
        self.assertTrue(self._get(self.root)["can_mint"])

    def test_balance_totals_and_newest_movements_first(self):
        PointService.mint_points(self.root, 1000, "Opening float")
        PointService.transfer_to_staff(self.root, self.finance, 300, "Monthly budget")
        PointService.adjust_points(self.seller, 120, "CREDIT", "Launch bonus", actor=self.root)
        PointService.adjust_points(self.seller, 20, "DEBIT", "Over-credited", actor=self.root)

        data = self._get(self.root)
        self.assertTrue(data["has_wallet"])
        self.assertEqual(data["balance"], 600)
        # Inflows are the mint and the debit taken back from the seller.
        self.assertEqual(data["received"], 1020)
        self.assertEqual(data["given_to_sellers"], 120)
        self.assertEqual(data["sent_to_staff"], 300)
        self.assertEqual(data["transaction_count"], 4)

        recent = data["recent"]
        self.assertEqual(
            [(row["transaction_type"], row["direction"], row["amount"]) for row in recent],
            [
                (StaffPointTransaction.TYPE_SELLER_DEBIT, "IN", 20),
                (StaffPointTransaction.TYPE_SELLER_CREDIT, "OUT", 120),
                (StaffPointTransaction.TYPE_TRANSFER_OUT, "OUT", 300),
                (StaffPointTransaction.TYPE_MINT, "IN", 1000),
            ],
        )
        self.assertEqual(recent[0]["transaction_type_display"], "Taken back from Seller")
        self.assertEqual(recent[1]["seller_business_name"], "My Wallet Traders")
        self.assertEqual(recent[2]["counterparty_username"], "me_finance")
        self.assertIsNone(recent[3]["counterparty_username"])
        self.assertIsNone(recent[3]["seller_business_name"])

    def test_only_the_callers_own_wallet_is_shown(self):
        PointService.mint_points(self.root, 1000, "Opening float")
        PointService.transfer_to_staff(self.root, self.finance, 300, "Monthly budget")

        data = self._get(self.finance)
        self.assertEqual(data["balance"], 300)
        self.assertEqual(data["received"], 300)
        self.assertEqual(data["transaction_count"], 1)
        self.assertEqual(data["recent"][0]["transaction_type"], StaffPointTransaction.TYPE_TRANSFER_IN)
        self.assertEqual(data["recent"][0]["counterparty_username"], "me_root")

    def test_recent_is_capped_and_shapes_match_the_frontend_type(self):
        for n in range(7):
            PointService.mint_points(self.root, 10 + n, f"Top-up {n}")

        data = self._get(self.root)
        self.assertEqual(data["transaction_count"], 7)
        self.assertEqual(len(data["recent"]), 5)
        self.assertEqual(data["recent"][0]["amount"], 16)
        # Keep in step with StaffWalletSummary / StaffPointMovement in admin-api.ts.
        self.assertEqual(
            set(data.keys()),
            {
                "has_wallet",
                "balance",
                "received",
                "given_to_sellers",
                "sent_to_staff",
                "taken_back",
                "expired",
                "transaction_count",
                "can_mint",
                "points_expire",
                "expiry_enabled",
                "expiry_months",
                "upcoming_expiries",
                "recent",
            },
        )
        self.assertEqual(
            set(data["recent"][0].keys()),
            {
                "id",
                "transaction_type",
                "transaction_type_display",
                "direction",
                "amount",
                "balance_before",
                "balance_after",
                "reason",
                "counterparty_username",
                "seller_business_name",
                "created_at",
            },
        )


class StaffUserWalletApiTests(TestCase):
    """
    GET /api/points/staff/<user_id>/ shows any account's staff wallet to a
    holder of 'points.view' and 'users.admin.view', for the Console's user
    page, and never creates one.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.root = User.objects.create_superuser(
            username="uw_root", email="uw_root@minishop.com", password="RootPassword123!"
        )
        cls.finance = User.objects.create_user(
            username="uw_finance", email="uw_finance@minishop.com", password="FinancePassword123!", is_staff=True
        )
        assign_user_role(cls.finance, Role.ROLE_FINANCE)
        cls.admin = User.objects.create_user(
            username="uw_admin", email="uw_admin@minishop.com", password="AdminPassword123!", is_staff=True
        )
        assign_user_role(cls.admin, Role.ROLE_ADMINISTRATOR)
        cls.support = User.objects.create_user(
            username="uw_support", email="uw_support@minishop.com", password="SupportPassword123!", is_staff=True
        )
        assign_user_role(cls.support, Role.ROLE_SUPPORT_TEAM)

    def setUp(self):
        self.client = APIClient()

    def _url(self, user):
        return f"/api/points/staff/{user.pk}/"

    def _get(self, actor, target):
        self.client.force_authenticate(user=actor)
        return self.client.get(self._url(target))

    def test_needs_points_view_and_the_user_directory(self):
        self.assertEqual(self.client.get(self._url(self.finance)).status_code, status.HTTP_401_UNAUTHORIZED)
        # SUPPORT_TEAM holds no points permission at all.
        self.assertEqual(self._get(self.support, self.finance).status_code, status.HTTP_403_FORBIDDEN)
        # FINANCE holds 'points.view' but not 'users.admin.view', so it cannot
        # use this endpoint to walk the user ids and list who is a superuser.
        self.assertEqual(self._get(self.finance, self.root).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._get(self.finance, self.finance).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self._get(self.admin, self.finance).status_code, status.HTTP_200_OK)
        self.assertEqual(self._get(self.root, self.finance).status_code, status.HTTP_200_OK)

    def test_unknown_user_is_404(self):
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(self.client.get("/api/points/staff/987654/").status_code, status.HTTP_404_NOT_FOUND)

    def test_another_accounts_wallet_and_totals(self):
        PointService.mint_points(self.root, 500, "Float")
        PointService.transfer_to_staff(self.root, self.finance, 200, "Monthly budget")
        PointService.reclaim_from_staff(self.root, self.finance, 50, "Budget cut")

        res = self._get(self.admin, self.finance)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data
        self.assertEqual((data["user_id"], data["username"]), (self.finance.pk, "uw_finance"))
        self.assertTrue(data["has_wallet"])
        self.assertEqual(data["balance"], 150)
        self.assertEqual(data["received"], 200)
        self.assertEqual(data["taken_back"], 50)
        self.assertEqual(data["transaction_count"], 2)
        self.assertTrue(data["can_receive_transfers"])
        self.assertFalse(data["can_mint"])
        self.assertEqual(
            [(row["transaction_type"], row["direction"]) for row in data["recent"]],
            [(StaffPointTransaction.TYPE_RECLAIM_OUT, "OUT"), (StaffPointTransaction.TYPE_TRANSFER_IN, "IN")],
        )
        self.assertEqual(data["recent"][0]["transaction_type_display"], "Taken back by Superuser")
        self.assertEqual(data["recent"][0]["counterparty_username"], "uw_root")
        # Keep in step with AdminStaffWallet in admin-api.ts.
        self.assertEqual(
            set(data.keys()),
            {
                "has_wallet",
                "balance",
                "received",
                "given_to_sellers",
                "sent_to_staff",
                "taken_back",
                "expired",
                "transaction_count",
                "can_mint",
                "points_expire",
                "expiry_enabled",
                "expiry_months",
                "upcoming_expiries",
                "recent",
                "user_id",
                "username",
                "can_receive_transfers",
            },
        )

    def test_no_wallet_reads_zero_and_creates_none(self):
        data = self._get(self.admin, self.support).data
        self.assertFalse(data["has_wallet"])
        self.assertEqual(data["balance"], 0)
        self.assertEqual(data["recent"], [])
        # SUPPORT_TEAM cannot credit sellers, so a superuser may not send them points.
        self.assertFalse(data["can_receive_transfers"])
        self.assertFalse(StaffWallet.objects.filter(user=self.support).exists())

    def test_an_inactive_account_cannot_receive_transfers(self):
        self.finance.is_active = False
        self.finance.save(update_fields=["is_active"])
        self.assertFalse(self._get(self.admin, self.finance).data["can_receive_transfers"])


class StaffPointTransferApiTests(TestCase):
    """
    POST /api/points/staff/<user_id>/transfer/: a superuser gives a staff member
    points from their own wallet (CREDIT) or takes them back into it (DEBIT).
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.root = User.objects.create_superuser(
            username="tr_root", email="tr_root@minishop.com", password="RootPassword123!"
        )
        cls.finance = User.objects.create_user(
            username="tr_finance", email="tr_finance@minishop.com", password="FinancePassword123!", is_staff=True
        )
        assign_user_role(cls.finance, Role.ROLE_FINANCE)
        cls.admin = User.objects.create_user(
            username="tr_admin", email="tr_admin@minishop.com", password="AdminPassword123!", is_staff=True
        )
        assign_user_role(cls.admin, Role.ROLE_ADMINISTRATOR)
        cls.support = User.objects.create_user(
            username="tr_support", email="tr_support@minishop.com", password="SupportPassword123!", is_staff=True
        )
        assign_user_role(cls.support, Role.ROLE_SUPPORT_TEAM)

    def setUp(self):
        self.client = APIClient()

    def _post(self, actor, target, action, amount, reason="Transfer test"):
        if actor is not None:
            self.client.force_authenticate(user=actor)
        return self.client.post(
            f"/api/points/staff/{target.pk}/transfer/",
            {"action": action, "amount": amount, "reason": reason},
            format="json",
        )

    def test_only_a_superuser_may_transfer(self):
        fund_staff_wallet(self.admin, 100)
        self.assertEqual(self._post(None, self.finance, "CREDIT", 10).status_code, status.HTTP_401_UNAUTHORIZED)
        # ADMINISTRATOR holds every points permission, but is not a superuser.
        for action in ("CREDIT", "DEBIT"):
            res = self._post(self.admin, self.finance, action, 10)
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, msg=action)
        self.assertEqual(PointService.get_staff_balance(self.admin), 100)
        self.assertFalse(StaffPointTransaction.objects.exclude(wallet__user=self.admin).exists())

    def test_give_moves_points_and_is_audited(self):
        from audit.models import AuditLog

        PointService.mint_points(self.root, 300, "Float")
        res = self._post(self.root, self.finance, "CREDIT", 120, reason="Monthly budget")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["staff_balance"], 120)
        self.assertEqual(res.data["actor_balance"], 180)
        self.assertEqual(
            res.data["message"], "Gave 120 points to tr_finance. Your wallet now holds 180 points."
        )
        self.assertEqual(res.data["transaction"]["transaction_type"], StaffPointTransaction.TYPE_TRANSFER_IN)
        self.assertEqual(PointService.get_staff_balance(self.finance), 120)
        self.assertEqual(PointService.get_staff_balance(self.root), 180)

        log = AuditLog.objects.get(action="SUPERUSER_POINTS_TRANSFER")
        self.assertEqual(log.actor, self.root)
        self.assertEqual(log.reason, "Monthly budget")
        self.assertEqual(log.metadata["staff_member"], "tr_finance")
        self.assertEqual(log.metadata["actor_balance_after"], 180)
        self.assertEqual(log.metadata["staff_balance_after"], 120)

    def test_take_back_moves_points_and_is_audited(self):
        from audit.models import AuditLog

        PointService.mint_points(self.root, 300, "Float")
        PointService.transfer_to_staff(self.root, self.finance, 100, "Monthly budget")
        res = self._post(self.root, self.finance, "DEBIT", 60, reason="Budget cut")

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["staff_balance"], 40)
        self.assertEqual(res.data["actor_balance"], 260)
        self.assertEqual(
            res.data["message"], "Took back 60 points from tr_finance. Your wallet now holds 260 points."
        )
        self.assertEqual(res.data["transaction"]["transaction_type"], StaffPointTransaction.TYPE_RECLAIM_OUT)

        log = AuditLog.objects.get(action="SUPERUSER_POINTS_RECLAIM")
        self.assertEqual(log.actor, self.root)
        self.assertEqual(log.metadata["previous_state"], {"balance": 100})
        self.assertEqual(log.metadata["new_state"], {"balance": 40})

        PointService.mint_points(self.root, 1000, "Top-up")
        res = self._post(self.root, self.finance, "DEBIT", 1)
        self.assertEqual(
            res.data["message"], "Took back 1 point from tr_finance. Your wallet now holds 1,261 points."
        )

    def test_give_cannot_exceed_the_superusers_wallet(self):
        from audit.models import AuditLog

        PointService.mint_points(self.root, 50, "Float")
        res = self._post(self.root, self.finance, "CREDIT", 51)

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["available_balance"], 50)
        self.assertIn("your wallet", res.data["error"])
        self.assertEqual(PointService.get_staff_balance(self.root), 50)
        self.assertFalse(StaffWallet.objects.filter(user=self.finance, balance__gt=0).exists())
        self.assertFalse(AuditLog.objects.filter(action="SUPERUSER_POINTS_TRANSFER").exists())

    def test_take_back_cannot_exceed_the_staff_wallet(self):
        fund_staff_wallet(self.finance, 30)
        res = self._post(self.root, self.finance, "DEBIT", 31)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["available_balance"], 30)
        self.assertIn("tr_finance's wallet", res.data["error"])
        self.assertEqual(PointService.get_staff_balance(self.finance), 30)

        # Someone who never held points: refused, and still no wallet.
        res = self._post(self.root, self.support, "DEBIT", 1)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["available_balance"], 0)
        self.assertFalse(StaffWallet.objects.filter(user=self.support).exists())

    def test_other_refusals(self):
        PointService.mint_points(self.root, 100, "Float")
        # SUPPORT_TEAM cannot credit sellers, and nobody sends points to themselves.
        for target in (self.support, self.root):
            res = self._post(self.root, target, "CREDIT", 10)
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg=target.username)
            self.assertIn("error", res.data)
        self.assertEqual(self._post(self.root, self.root, "DEBIT", 10).status_code, status.HTTP_400_BAD_REQUEST)

        for payload in (
            {"action": "CREDIT", "amount": 0, "reason": "Zero"},
            {"action": "CREDIT", "amount": 10, "reason": ""},
            {"action": "MINT", "amount": 10, "reason": "Not an action"},
        ):
            res = self.client.post(f"/api/points/staff/{self.finance.pk}/transfer/", payload, format="json")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg=payload)

        self.client.force_authenticate(user=self.root)
        res = self.client.post(
            "/api/points/staff/987654/transfer/", {"action": "CREDIT", "amount": 1, "reason": "Nobody"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(PointService.get_staff_balance(self.root), 100)

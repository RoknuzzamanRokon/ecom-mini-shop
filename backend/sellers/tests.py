import threading
import time
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.urls import NoReverseMatch, reverse
from rest_framework import status
from rest_framework.test import APIClient

from audit.models import AuditLog
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.models import Shop
from sellers.services import approve_seller, get_seller_capabilities

User = get_user_model()


class SellerSystemTests(TestCase):
    def setUp(self):
        # Seed RBAC roles and permissions
        call_command("seed_rbac")

        self.client = APIClient()

        # Regular user A
        self.user_a = User.objects.create_user(
            username="seller_a",
            email="seller_a@example.com",
            password="TestPassword123!",
        )

        # Regular user B
        self.user_b = User.objects.create_user(
            username="seller_b",
            email="seller_b@example.com",
            password="TestPassword123!",
        )

        # Staff user with ADMINISTRATOR role (has sellers.view, sellers.approve, sellers.suspend)
        self.staff_admin = User.objects.create_user(
            username="staff_admin",
            email="admin@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        assign_user_role(self.staff_admin, Role.ROLE_ADMINISTRATOR)

        # Super admin user
        self.super_admin = User.objects.create_user(
            username="super_admin",
            email="superadmin@example.com",
            password="TestPassword123!",
            is_superuser=True,
            is_staff=True,
        )
        assign_user_role(self.super_admin, Role.ROLE_SUPER_ADMINISTRATOR)

        # Staff user without seller permissions (e.g. FINANCE only)
        self.finance_user = User.objects.create_user(
            username="finance_staff",
            email="finance@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        assign_user_role(self.finance_user, Role.ROLE_FINANCE)

    def test_seller_self_registration_endpoint_is_gone(self):
        """
        Phase 2L (Known Issue #5): sellers are provisioned by authorized
        management, never by themselves. The route is removed outright rather
        than kept routed for an explicit 403 — unlike shop self-creation
        (invariant 4), nothing ever called this one, so there is no client to
        give a distinguishable answer to.
        """
        with self.assertRaises(NoReverseMatch):
            reverse("sellers:seller-register")

        self.client.force_authenticate(user=self.user_a)
        response = self.client.post(
            "/api/sellers/register/",
            {
                "seller_type": SellerProfile.TYPE_FULL_SHOP_OWNER,
                "business_name": "Apex Electronics",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(SellerProfile.objects.filter(user=self.user_a).exists())

    def test_seller_invalid_type(self):
        """
        Invalid seller type must be rejected by the model itself.

        This used to assert the same rejection twice — once through
        POST /api/sellers/register/ and once through the model. The endpoint
        was removed in Phase 2L; the API-level assertion now lives on the
        surviving creation path, in
        shop.test_admin_governance.AdminSellerCreationTests.
        """
        invalid_profile = SellerProfile(
            user=self.user_b,
            seller_type="INVALID_TYPE",
            business_name="Bad Business",
        )
        with self.assertRaises(ValidationError):
            invalid_profile.clean()

    def test_seller_approval_by_authorized_staff(self):
        """Authorized staff can approve a pending seller; seller becomes active."""
        # Create pending profile for user A
        seller = SellerProfile.objects.create(
            user=self.user_a,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Fashion Hub",
            status=SellerProfile.STATUS_PENDING,
        )

        self.client.force_authenticate(user=self.staff_admin)
        response = self.client.post(f"/api/sellers/{seller.pk}/approve/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        seller.refresh_from_db()
        self.assertEqual(seller.status, SellerProfile.STATUS_ACTIVE)
        self.assertTrue(seller.is_operational)
        self.assertIsNotNone(seller.approved_at)
        self.assertEqual(seller.reviewed_by, self.staff_admin)

    def test_unauthorized_approval(self):
        """Unauthorized staff or regular users cannot approve sellers."""
        seller = SellerProfile.objects.create(
            user=self.user_a,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Fashion Hub",
            status=SellerProfile.STATUS_PENDING,
        )

        # 1. Anonymous user -> 401 Unauthorized
        self.client.force_authenticate(user=None)
        response = self.client.post(f"/api/sellers/{seller.pk}/approve/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Regular user -> 403 Forbidden
        self.client.force_authenticate(user=self.user_b)
        response = self.client.post(f"/api/sellers/{seller.pk}/approve/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Staff without sellers.approve permission (Finance) -> 403 Forbidden
        self.client.force_authenticate(user=self.finance_user)
        response = self.client.post(f"/api/sellers/{seller.pk}/approve/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Ensure seller status remained PENDING
        seller.refresh_from_db()
        self.assertEqual(seller.status, SellerProfile.STATUS_PENDING)

    def test_seller_rejection(self):
        """Authorized staff can reject a seller with an explicit reason."""
        seller = SellerProfile.objects.create(
            user=self.user_a,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Suspicious Store",
            status=SellerProfile.STATUS_PENDING,
        )

        self.client.force_authenticate(user=self.staff_admin)

        # Rejection without reason fails
        empty_reason_resp = self.client.post(f"/api/sellers/{seller.pk}/reject/", {}, format="json")
        self.assertEqual(empty_reason_resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Rejection with valid reason
        response = self.client.post(
            f"/api/sellers/{seller.pk}/reject/",
            {"reason": "Incomplete trade license and invalid tax ID provided."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        seller.refresh_from_db()
        self.assertEqual(seller.status, SellerProfile.STATUS_REJECTED)
        self.assertEqual(seller.rejection_reason, "Incomplete trade license and invalid tax ID provided.")
        self.assertEqual(seller.reviewed_by, self.staff_admin)
        self.assertFalse(seller.is_operational)

    def test_seller_ownership(self):
        """Sellers can only modify their own profile."""
        seller_a = SellerProfile.objects.create(
            user=self.user_a,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="User A Shop",
            status=SellerProfile.STATUS_ACTIVE,
        )
        seller_b = SellerProfile.objects.create(
            user=self.user_b,
            seller_type=SellerProfile.TYPE_LIMITED_SHOP_OWNER,
            business_name="User B Shop",
            status=SellerProfile.STATUS_ACTIVE,
        )

        # User A updates their own profile via /api/sellers/me/
        self.client.force_authenticate(user=self.user_a)
        update_resp = self.client.patch(
            "/api/sellers/me/",
            {"business_name": "User A Updated Shop", "business_phone": "+8801711111111"},
            format="json",
        )
        self.assertEqual(update_resp.status_code, status.HTTP_200_OK)
        seller_a.refresh_from_db()
        self.assertEqual(seller_a.business_name, "User A Updated Shop")

        # User A attempts to view / update seller B's profile via detail endpoint
        # Regular sellers don't have 'sellers.view' staff permission
        view_b_resp = self.client.get(f"/api/sellers/{seller_b.pk}/")
        self.assertEqual(view_b_resp.status_code, status.HTTP_403_FORBIDDEN)

        # User without seller profile calling /api/sellers/me/
        user_c = User.objects.create_user(username="no_seller", password="TestPassword123!")
        self.client.force_authenticate(user=user_c)
        no_profile_resp = self.client.get("/api/sellers/me/")
        self.assertEqual(no_profile_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_suspended_seller_lifecycle_and_restrictions(self):
        """Suspension blocks operational actions and records reason and timestamp."""
        seller = SellerProfile.objects.create(
            user=self.user_a,
            seller_type=SellerProfile.TYPE_PRODUCT_OWNER,
            business_name="Gadget Lab",
            status=SellerProfile.STATUS_ACTIVE,
        )

        self.client.force_authenticate(user=self.staff_admin)

        # 1. Suspend seller without reason -> 400 Bad Request
        bad_suspend_resp = self.client.post(f"/api/sellers/{seller.pk}/suspend/", {}, format="json")
        self.assertEqual(bad_suspend_resp.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. Suspend seller with reason
        suspend_resp = self.client.post(
            f"/api/sellers/{seller.pk}/suspend/",
            {"reason": "Policy violation: counterfeit product reports."},
            format="json",
        )
        self.assertEqual(suspend_resp.status_code, status.HTTP_200_OK)

        seller.refresh_from_db()
        self.assertEqual(seller.status, SellerProfile.STATUS_SUSPENDED)
        self.assertTrue(seller.is_suspended)
        self.assertFalse(seller.is_operational)
        self.assertEqual(seller.suspension_reason, "Policy violation: counterfeit product reports.")
        self.assertIsNotNone(seller.suspended_at)

        # 3. Seller dashboard shows warning
        self.client.force_authenticate(user=self.user_a)
        dash_resp = self.client.get("/api/sellers/dashboard/")
        self.assertEqual(dash_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(dash_resp.data["is_suspended"])
        self.assertFalse(dash_resp.data["is_operational"])
        self.assertIn("Account suspended:", dash_resp.data.get("warning", ""))

        # 4. Reactivate seller
        self.client.force_authenticate(user=self.staff_admin)
        reactivate_resp = self.client.post(f"/api/sellers/{seller.pk}/reactivate/")
        self.assertEqual(reactivate_resp.status_code, status.HTTP_200_OK)

        seller.refresh_from_db()
        self.assertEqual(seller.status, SellerProfile.STATUS_ACTIVE)
        self.assertFalse(seller.is_suspended)
        self.assertTrue(seller.is_operational)
        self.assertEqual(seller.suspension_reason, "")

    def test_seller_dashboard_and_capabilities(self):
        """Dashboard returns capability matrix according to seller type."""
        # Test FULL_SHOP_OWNER
        seller_full = SellerProfile.objects.create(
            user=self.user_a,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Full Mart",
            status=SellerProfile.STATUS_ACTIVE,
        )
        caps_full = get_seller_capabilities(seller_full)
        # Known Issue #4: this asserted True until Phase 2H. Sellers do not create
        # shops -- SellerShopCreateView hard-denies with 403 -- so reporting True
        # here was the capability matrix contradicting the enforced policy.
        self.assertFalse(caps_full["can_create_shop"])
        self.assertTrue(caps_full["can_manage_products"])
        self.assertTrue(caps_full["has_full_catalog"])

        # Test LIMITED_SHOP_OWNER
        seller_limited = SellerProfile.objects.create(
            user=self.user_b,
            seller_type=SellerProfile.TYPE_LIMITED_SHOP_OWNER,
            business_name="Corner Kiosk",
            status=SellerProfile.STATUS_ACTIVE,
        )
        caps_limited = get_seller_capabilities(seller_limited)
        self.assertFalse(caps_limited["can_create_shop"])
        self.assertTrue(caps_limited["can_manage_products"])
        self.assertFalse(caps_limited["has_full_catalog"])

        # Test PRODUCT_OWNER
        user_c = User.objects.create_user(username="prod_owner", password="TestPassword123!")
        seller_prod = SellerProfile.objects.create(
            user=user_c,
            seller_type=SellerProfile.TYPE_PRODUCT_OWNER,
            business_name="Artisan Crafts",
            status=SellerProfile.STATUS_ACTIVE,
        )
        caps_prod = get_seller_capabilities(seller_prod)
        self.assertFalse(caps_prod["can_create_shop"])
        self.assertTrue(caps_prod["can_manage_products"])
        self.assertTrue(caps_prod["has_full_catalog"])

        # Verify dashboard endpoint response
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get("/api/sellers/dashboard/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["has_seller_profile"])
        self.assertEqual(response.data["capabilities"]["seller_type"], SellerProfile.TYPE_FULL_SHOP_OWNER)
        self.assertTrue(response.data["is_operational"])


class SellerLifecycleAuditTests(TestCase):
    """
    Known Issue #6: the seller lifecycle DRF endpoints (approve/reject/suspend/
    reactivate) previously performed no audit logging, unlike their Django-admin
    equivalents (sellers/admin.py) and the /api/admin/sellers/<pk>/status/
    endpoint (shop/admin_views.py:AdminSellerStatusAPIView), both of which log
    via AuditService.log(action="ADMIN_SELLER_<ACTION>", ...). These tests
    verify the same convention now applies to /api/sellers/<pk>/approve|reject|
    suspend|reactivate/, and that a rejected/failed request never creates a
    misleading "successful" audit record.
    """

    def setUp(self):
        call_command("seed_rbac")
        self.client = APIClient()

        self.applicant = User.objects.create_user(
            username="lifecycle_seller",
            email="lifecycle_seller@example.com",
            password="TestPassword123!",
        )
        self.other_user = User.objects.create_user(
            username="lifecycle_bystander",
            email="lifecycle_bystander@example.com",
            password="TestPassword123!",
        )
        self.staff_admin = User.objects.create_user(
            username="lifecycle_staff_admin",
            email="lifecycle_admin@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        assign_user_role(self.staff_admin, Role.ROLE_ADMINISTRATOR)
        self.finance_user = User.objects.create_user(
            username="lifecycle_finance",
            email="lifecycle_finance@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        assign_user_role(self.finance_user, Role.ROLE_FINANCE)

    def _create_seller(self, status_value=SellerProfile.STATUS_PENDING, **extra):
        return SellerProfile.objects.create(
            user=self.applicant,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Audit Trail Traders",
            status=status_value,
            **extra,
        )

    def _logs_for(self, seller, action):
        return AuditLog.objects.filter(
            action=action, target_type="SellerProfile", target_id=str(seller.pk)
        )

    def test_approve_creates_audit_record(self):
        seller = self._create_seller(status_value=SellerProfile.STATUS_PENDING)
        self.client.force_authenticate(user=self.staff_admin)

        response = self.client.post(f"/api/sellers/{seller.pk}/approve/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        logs = self._logs_for(seller, "ADMIN_SELLER_APPROVE")
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        seller.refresh_from_db()
        self.assertEqual(log.actor, self.staff_admin)
        self.assertEqual(log.seller_id, seller.pk)
        self.assertEqual(log.target_repr, str(seller))
        self.assertEqual(log.metadata["previous_state"], {"status": SellerProfile.STATUS_PENDING})
        self.assertEqual(log.metadata["new_state"], {"status": SellerProfile.STATUS_ACTIVE})

    def test_reject_creates_audit_record_with_reason(self):
        seller = self._create_seller(status_value=SellerProfile.STATUS_PENDING)
        self.client.force_authenticate(user=self.staff_admin)

        reason = "Incomplete trade license documentation."
        response = self.client.post(
            f"/api/sellers/{seller.pk}/reject/", {"reason": reason}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        logs = self._logs_for(seller, "ADMIN_SELLER_REJECT")
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.actor, self.staff_admin)
        self.assertEqual(log.seller_id, seller.pk)
        self.assertEqual(log.reason, reason)
        self.assertEqual(log.metadata["previous_state"], {"status": SellerProfile.STATUS_PENDING})
        self.assertEqual(log.metadata["new_state"], {"status": SellerProfile.STATUS_REJECTED})

    def test_suspend_creates_audit_record_with_reason(self):
        seller = self._create_seller(status_value=SellerProfile.STATUS_ACTIVE)
        self.client.force_authenticate(user=self.staff_admin)

        reason = "Policy violation: counterfeit product reports."
        response = self.client.post(
            f"/api/sellers/{seller.pk}/suspend/", {"reason": reason}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        logs = self._logs_for(seller, "ADMIN_SELLER_SUSPEND")
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.actor, self.staff_admin)
        self.assertEqual(log.seller_id, seller.pk)
        self.assertEqual(log.reason, reason)
        self.assertEqual(log.metadata["previous_state"], {"status": SellerProfile.STATUS_ACTIVE})
        self.assertEqual(log.metadata["new_state"], {"status": SellerProfile.STATUS_SUSPENDED})

    def test_reactivate_creates_audit_record(self):
        seller = self._create_seller(
            status_value=SellerProfile.STATUS_SUSPENDED,
            suspension_reason="Temporary hold pending review.",
        )
        self.client.force_authenticate(user=self.staff_admin)

        response = self.client.post(f"/api/sellers/{seller.pk}/reactivate/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        logs = self._logs_for(seller, "ADMIN_SELLER_REACTIVATE")
        self.assertEqual(logs.count(), 1)
        log = logs.first()
        self.assertEqual(log.actor, self.staff_admin)
        self.assertEqual(log.seller_id, seller.pk)
        self.assertEqual(log.metadata["previous_state"], {"status": SellerProfile.STATUS_SUSPENDED})
        self.assertEqual(log.metadata["new_state"], {"status": SellerProfile.STATUS_ACTIVE})

    def test_unauthorized_approve_creates_no_audit_record(self):
        """An unauthenticated/unauthorized/under-permissioned request must not be audited as a success."""
        seller = self._create_seller(status_value=SellerProfile.STATUS_PENDING)

        self.client.force_authenticate(user=None)
        anon_resp = self.client.post(f"/api/sellers/{seller.pk}/approve/")
        self.assertEqual(anon_resp.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.force_authenticate(user=self.other_user)
        forbidden_resp = self.client.post(f"/api/sellers/{seller.pk}/approve/")
        self.assertEqual(forbidden_resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.finance_user)
        no_permission_resp = self.client.post(f"/api/sellers/{seller.pk}/approve/")
        self.assertEqual(no_permission_resp.status_code, status.HTTP_403_FORBIDDEN)

        seller.refresh_from_db()
        self.assertEqual(seller.status, SellerProfile.STATUS_PENDING)
        self.assertEqual(self._logs_for(seller, "ADMIN_SELLER_APPROVE").count(), 0)

    def test_invalid_transition_creates_no_audit_record(self):
        """Reactivating a non-suspended seller is rejected before any mutation or audit write."""
        seller = self._create_seller(status_value=SellerProfile.STATUS_ACTIVE)
        self.client.force_authenticate(user=self.staff_admin)

        response = self.client.post(f"/api/sellers/{seller.pk}/reactivate/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        seller.refresh_from_db()
        self.assertEqual(seller.status, SellerProfile.STATUS_ACTIVE)
        self.assertEqual(self._logs_for(seller, "ADMIN_SELLER_REACTIVATE").count(), 0)

    def test_missing_reason_creates_no_audit_record(self):
        """Suspend/reject without a reason is rejected by the serializer before any audit write."""
        seller = self._create_seller(status_value=SellerProfile.STATUS_ACTIVE)
        self.client.force_authenticate(user=self.staff_admin)

        response = self.client.post(f"/api/sellers/{seller.pk}/suspend/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        seller.refresh_from_db()
        self.assertEqual(seller.status, SellerProfile.STATUS_ACTIVE)
        self.assertEqual(self._logs_for(seller, "ADMIN_SELLER_SUSPEND").count(), 0)

    def test_nonexistent_seller_creates_no_audit_record(self):
        """A 404 on a nonexistent seller must never reach the audit-logging step."""
        self.client.force_authenticate(user=self.staff_admin)
        before_count = AuditLog.objects.filter(action="ADMIN_SELLER_APPROVE").count()

        response = self.client.post("/api/sellers/999999/approve/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        after_count = AuditLog.objects.filter(action="ADMIN_SELLER_APPROVE").count()
        self.assertEqual(before_count, after_count)

    def test_full_lifecycle_produces_exactly_one_log_per_transition(self):
        """No duplicate logging anywhere in the call chain: one audit row per successful API call."""
        seller = self._create_seller(status_value=SellerProfile.STATUS_PENDING)
        self.client.force_authenticate(user=self.staff_admin)

        self.client.post(f"/api/sellers/{seller.pk}/approve/")
        self.client.post(
            f"/api/sellers/{seller.pk}/suspend/",
            {"reason": "Routine compliance check."},
            format="json",
        )
        self.client.post(f"/api/sellers/{seller.pk}/reactivate/")

        seller_logs = AuditLog.objects.filter(target_type="SellerProfile", target_id=str(seller.pk))
        self.assertEqual(seller_logs.count(), 3)
        self.assertEqual(
            list(seller_logs.order_by("created_at").values_list("action", flat=True)),
            ["ADMIN_SELLER_APPROVE", "ADMIN_SELLER_SUSPEND", "ADMIN_SELLER_REACTIVATE"],
        )


class SellerShopCapabilityTests(TestCase):
    """
    Known Issue #4. `get_seller_capabilities` claimed `can_create_shop: True` for
    FULL_SHOP_OWNER and LIMITED_SHOP_OWNER while `SellerShopCreateView` hard-denied
    every seller with 403. The capability matrix must describe the policy that is
    actually enforced; the fix is to report False, never to relax the restriction.
    """

    def setUp(self):
        call_command("seed_rbac")
        self.client = APIClient()

    def _seller(self, seller_type, username):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="TestPassword123!",
        )
        return user, SellerProfile.objects.create(
            user=user,
            seller_type=seller_type,
            business_name=f"{username} Trading",
            status=SellerProfile.STATUS_ACTIVE,
        )

    def test_every_seller_type_reports_can_create_shop_false(self):
        for seller_type, _label in SellerProfile.SELLER_TYPE_CHOICES:
            with self.subTest(seller_type=seller_type):
                _user, seller = self._seller(seller_type, f"cap_{seller_type.lower()}")
                caps = get_seller_capabilities(seller)
                self.assertFalse(
                    caps["can_create_shop"],
                    f"{seller_type} must not claim it can create a shop",
                )

    def test_shop_creation_is_still_hard_denied_for_every_seller_type(self):
        """The capability now tells the truth because the 403 is still there."""
        for seller_type, _label in SellerProfile.SELLER_TYPE_CHOICES:
            with self.subTest(seller_type=seller_type):
                user, _seller = self._seller(seller_type, f"denied_{seller_type.lower()}")
                self.client.force_authenticate(user=user)
                response = self.client.post(
                    "/api/shops/mine/create/", {"name": "Attempted Self-Service Shop"}
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(Shop.objects.filter(owner=_seller).count(), 0)

    def test_other_capability_flags_are_unchanged(self):
        """Only can_create_shop moved; the rest of the matrix is as it was."""
        expectations = {
            SellerProfile.TYPE_FULL_SHOP_OWNER: (True, True),
            SellerProfile.TYPE_LIMITED_SHOP_OWNER: (True, False),
            SellerProfile.TYPE_PRODUCT_OWNER: (True, True),
        }
        for seller_type, (manage_products, full_catalog) in expectations.items():
            with self.subTest(seller_type=seller_type):
                _user, seller = self._seller(seller_type, f"flags_{seller_type.lower()}")
                caps = get_seller_capabilities(seller)
                self.assertEqual(caps["can_manage_products"], manage_products)
                self.assertEqual(caps["has_full_catalog"], full_catalog)
                self.assertEqual(caps["seller_type"], seller_type)


class SellerLifecycleConcurrencyTests(TransactionTestCase):
    """
    Known Issue #23 -- the TOCTOU window on audited seller status transitions.

    The four lifecycle endpoints captured `previous_state = {"status": seller.status}`
    from an *unlocked* read. Two concurrent transitions on one seller could therefore
    both record the same `previous_state`, even though only one of them can actually
    have followed it -- and the later write silently clobbered the earlier one.

    This proves the row lock serialises the two requests and leaves an audit chain in
    which every entry's `previous_state` is the state its predecessor committed.

    Requires MySQL, per Phase 2A's testing boundary: the assertion is about real
    InnoDB row-lock behaviour across two connections, which SQLite cannot demonstrate.
    """

    def setUp(self):
        call_command("seed_rbac")
        self.applicant = User.objects.create_user(
            username="concurrent_applicant",
            email="concurrent_applicant@example.com",
            password="TestPassword123!",
        )
        self.staff_a = User.objects.create_user(
            username="concurrent_staff_a",
            email="concurrent_staff_a@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        assign_user_role(self.staff_a, Role.ROLE_ADMINISTRATOR)
        self.staff_b = User.objects.create_user(
            username="concurrent_staff_b",
            email="concurrent_staff_b@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        assign_user_role(self.staff_b, Role.ROLE_ADMINISTRATOR)

    @staticmethod
    def _post_in_thread(results, key, user, url, payload=None):
        """Runs one lifecycle request on its own DB connection."""
        connection.close()
        try:
            client = APIClient()
            client.force_authenticate(user=user)
            results[key] = client.post(url, payload or {}, format="json")
        except Exception as exc:  # surfaced in the main thread below
            results[key] = exc
        finally:
            connection.close()

    def test_concurrent_transitions_keep_the_audit_chain_consistent(self):
        if connection.vendor != "mysql":
            self.skipTest(
                f"Row-lock serialisation is only meaningful on MySQL; this run is on "
                f"'{connection.vendor}'. Not asserting concurrency correctness."
            )

        seller = SellerProfile.objects.create(
            user=self.applicant,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Concurrent Lifecycle Traders",
            status=SellerProfile.STATUS_PENDING,
        )

        holding_lock = threading.Event()
        may_proceed = threading.Event()
        real_approve_seller = approve_seller

        def approve_while_holding_the_lock(seller_obj, staff_user):
            # Called from inside SellerApproveView's atomic block, after the locked
            # read and after previous_state was captured. Blocking here keeps the
            # row lock held while the suspend request tries to take it.
            holding_lock.set()
            may_proceed.wait(timeout=30)
            return real_approve_seller(seller_obj, staff_user)

        results = {}
        with mock.patch("sellers.views.approve_seller", approve_while_holding_the_lock):
            approver = threading.Thread(
                target=self._post_in_thread,
                args=(results, "approve", self.staff_a, f"/api/sellers/{seller.pk}/approve/"),
            )
            approver.start()
            self.assertTrue(
                holding_lock.wait(timeout=30),
                "the approve request never reached the service call",
            )

            suspender = threading.Thread(
                target=self._post_in_thread,
                args=(
                    results,
                    "suspend",
                    self.staff_b,
                    f"/api/sellers/{seller.pk}/suspend/",
                    {"reason": "Concurrent suspension raised during review"},
                ),
            )
            suspender.start()
            # Long enough for the suspend request to reach the row lock and block on
            # it. The assertion below is order-independent, so an unlucky machine
            # changes which transition lands first, not whether the test passes.
            time.sleep(0.5)
            may_proceed.set()

            approver.join(timeout=30)
            suspender.join(timeout=30)

        self.assertFalse(approver.is_alive(), "the approve request never finished")
        self.assertFalse(suspender.is_alive(), "the suspend request never finished")

        for key in ("approve", "suspend"):
            outcome = results.get(key)
            self.assertNotIsInstance(outcome, Exception, f"{key} raised {outcome!r}")
            self.assertIsNotNone(outcome, f"{key} produced no response")
            self.assertEqual(outcome.status_code, status.HTTP_200_OK)

        logs = list(
            AuditLog.objects.filter(
                target_type="SellerProfile",
                target_id=str(seller.pk),
                action__in=("ADMIN_SELLER_APPROVE", "ADMIN_SELLER_SUSPEND"),
            ).order_by("id")
        )
        self.assertEqual(len(logs), 2, "expected exactly one audit entry per transition")

        # The real assertion: walk the chain. Every entry must claim a previous_state
        # equal to what the entry before it committed, starting from the seller's
        # initial status. Against the unlocked code both entries claim PENDING and
        # this fails on the second one.
        expected_previous = SellerProfile.STATUS_PENDING
        for position, entry in enumerate(logs):
            self.assertEqual(
                entry.metadata["previous_state"],
                {"status": expected_previous},
                f"audit entry {position} ({entry.action}) claims previous_state "
                f"{entry.metadata['previous_state']}, which was never the committed "
                f"state immediately before it; expected {{'status': "
                f"'{expected_previous}'}}",
            )
            expected_previous = entry.metadata["new_state"]["status"]

        # ...and the end of the chain must be what is actually in the database.
        seller.refresh_from_db()
        self.assertEqual(seller.status, expected_previous)

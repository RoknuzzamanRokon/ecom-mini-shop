from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from sellers.services import get_seller_capabilities

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

    def test_seller_creation(self):
        """Authenticated user can register as a seller; status defaults to PENDING."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            "seller_type": SellerProfile.TYPE_FULL_SHOP_OWNER,
            "business_name": "Apex Electronics",
            "business_email": "contact@apexelectronics.com",
            "business_phone": "+8801700000001",
            "tax_id": "TIN-987654321",
            "description": "Premium electronics and gadgets retailer.",
        }
        response = self.client.post("/api/sellers/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["business_name"], "Apex Electronics")
        self.assertEqual(response.data["seller_type"], SellerProfile.TYPE_FULL_SHOP_OWNER)
        self.assertEqual(response.data["status"], SellerProfile.STATUS_PENDING)
        self.assertFalse(response.data["is_operational"])
        self.assertFalse(response.data["is_suspended"])

        # Check DB state
        profile = SellerProfile.objects.get(user=self.user_a)
        self.assertEqual(profile.business_name, "Apex Electronics")
        self.assertEqual(profile.status, SellerProfile.STATUS_PENDING)

        # Disallow duplicate registration
        duplicate_response = self.client.post("/api/sellers/register/", payload, format="json")
        self.assertEqual(duplicate_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_seller_invalid_type(self):
        """Invalid seller type must be rejected by both API and Model clean()."""
        self.client.force_authenticate(user=self.user_a)
        payload = {
            "seller_type": "UNKNOWN_CUSTOM_TYPE",
            "business_name": "Invalid Seller Inc.",
        }
        response = self.client.post("/api/sellers/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("seller_type", response.data)

        # Direct model instantiation validation
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
        self.assertTrue(caps_full["can_create_shop"])
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
        self.assertTrue(caps_limited["can_create_shop"])
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

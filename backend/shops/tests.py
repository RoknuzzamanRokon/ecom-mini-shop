from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shop.models import Category, Product
from shops.models import Shop
from shops.services import (
    IneligibleSellerError,
    InvalidShopTransitionError,
    ShopLimitExceededError,
    ShopService,
)

User = get_user_model()


class ShopSystemTests(TestCase):
    def setUp(self):
        call_command("seed_rbac")
        self.client = APIClient()

        # Full Shop Owner User
        self.user_full = User.objects.create_user(
            username="full_owner",
            email="full@example.com",
            password="TestPassword123!",
        )
        self.seller_full = SellerProfile.objects.create(
            user=self.user_full,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Full Mart Ltd",
            status=SellerProfile.STATUS_ACTIVE,
        )

        # Limited Shop Owner User
        self.user_limited = User.objects.create_user(
            username="limited_owner",
            email="limited@example.com",
            password="TestPassword123!",
        )
        self.seller_limited = SellerProfile.objects.create(
            user=self.user_limited,
            seller_type=SellerProfile.TYPE_LIMITED_SHOP_OWNER,
            business_name="Limited Kiosk Ltd",
            status=SellerProfile.STATUS_ACTIVE,
        )

        # Product Owner User
        self.user_prod = User.objects.create_user(
            username="prod_owner",
            email="prod@example.com",
            password="TestPassword123!",
        )
        self.seller_prod = SellerProfile.objects.create(
            user=self.user_prod,
            seller_type=SellerProfile.TYPE_PRODUCT_OWNER,
            business_name="Artisan Solo Crafts",
            status=SellerProfile.STATUS_ACTIVE,
        )

        # Suspended Seller User
        self.user_suspended = User.objects.create_user(
            username="suspended_seller",
            email="suspended@example.com",
            password="TestPassword123!",
        )
        self.seller_suspended = SellerProfile.objects.create(
            user=self.user_suspended,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Suspended Biz",
            status=SellerProfile.STATUS_SUSPENDED,
            suspension_reason="Policy violation",
        )

        # Staff with shops.approve (Operation Manager)
        self.staff_op_manager = User.objects.create_user(
            username="op_manager",
            email="op@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        assign_user_role(self.staff_op_manager, Role.ROLE_OPERATION_MANAGER)

        # Staff without shops.approve (Support Team only has shops.view)
        self.staff_support = User.objects.create_user(
            username="support_user",
            email="support@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        assign_user_role(self.staff_support, Role.ROLE_SUPPORT_TEAM)

    # 1. Shop creation by eligible seller & 4. Full Shop Owner behavior
    def test_shop_creation_by_full_shop_owner(self):
        """Full shop owner can create a draft shop or submit directly for review."""
        self.client.force_authenticate(user=self.user_full)
        payload = {
            "name": "Apex Electronics Hub",
            "description": "Leading electronics store in Dhaka.",
            "phone": "+8801712345678",
            "address": "House 12, Road 5, Dhanmondi, Dhaka",
            "location": "Dhanmondi, Dhaka",
            "submit_for_review": False,
        }
        response = self.client.post("/api/shops/mine/create/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Apex Electronics Hub")
        self.assertEqual(response.data["status"], Shop.STATUS_DRAFT)
        self.assertEqual(response.data["slug"], "apex-electronics-hub")
        self.assertFalse(response.data["is_publicly_visible"])

        # Check DB
        shop = Shop.objects.get(name="Apex Electronics Hub")
        self.assertEqual(shop.owner, self.seller_full)
        self.assertEqual(shop.status, Shop.STATUS_DRAFT)

    # 2. Shop creation by unauthorized/ineligible seller
    def test_shop_creation_by_unauthorized_user(self):
        """Unauthenticated users or users without a seller profile cannot create shops."""
        # Unauthenticated
        self.client.force_authenticate(user=None)
        response = self.client.post("/api/shops/mine/create/", {"name": "Anon Shop"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # Authenticated non-seller
        non_seller = User.objects.create_user(username="regular_buyer", password="TestPassword123!")
        self.client.force_authenticate(user=non_seller)
        resp_non = self.client.post("/api/shops/mine/create/", {"name": "Buyer Shop"}, format="json")
        self.assertEqual(resp_non.status_code, status.HTTP_403_FORBIDDEN)

    # 3. Product Owner shop restriction
    def test_product_owner_cannot_create_shop(self):
        """Product Owner sellers are strictly barred from creating shops."""
        self.client.force_authenticate(user=self.user_prod)
        response = self.client.post("/api/shops/mine/create/", {"name": "Solo Shop Attempt"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Service-level validation
        with self.assertRaises(IneligibleSellerError):
            ShopService.create_shop(self.seller_prod, name="Direct Service Shop")

    # 5. Limited Shop Owner behavior (limit of 1 shop)
    def test_limited_shop_owner_single_shop_limit(self):
        """Limited Shop Owner can create 1 shop, but is blocked from creating a second."""
        self.client.force_authenticate(user=self.user_limited)

        # First shop succeeds
        resp1 = self.client.post("/api/shops/mine/create/", {"name": "Kiosk One"}, format="json")
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)

        # Second shop fails with 403
        resp2 = self.client.post("/api/shops/mine/create/", {"name": "Kiosk Two"}, format="json")
        self.assertEqual(resp2.status_code, status.HTTP_403_FORBIDDEN)

        # Direct service call also raises ShopLimitExceededError
        with self.assertRaises(ShopLimitExceededError):
            ShopService.create_shop(self.seller_limited, name="Kiosk Three")

    # 6. Seller ownership enforcement & 7. Cannot modify another seller's shop
    def test_seller_ownership_and_cross_modification_protection(self):
        """A seller can update their own shop, but cannot update another seller's shop."""
        shop_full = ShopService.create_shop(self.seller_full, name="Full Mart Main")
        shop_limited = ShopService.create_shop(self.seller_limited, name="Limited Mart Main")

        # Seller Full modifies own shop -> 200 OK
        self.client.force_authenticate(user=self.user_full)
        update_resp = self.client.patch(
            f"/api/shops/mine/{shop_full.pk}/update/",
            {"name": "Full Mart Updated Name", "phone": "+8801999999999"},
            format="json",
        )
        self.assertEqual(update_resp.status_code, status.HTTP_200_OK)
        shop_full.refresh_from_db()
        self.assertEqual(shop_full.name, "Full Mart Updated Name")

        # Seller Full attempts to modify Seller Limited's shop -> 404 / 403
        cross_resp = self.client.patch(
            f"/api/shops/mine/{shop_limited.pk}/update/",
            {"name": "Hijacked Name"},
            format="json",
        )
        self.assertEqual(cross_resp.status_code, status.HTTP_403_FORBIDDEN)
        shop_limited.refresh_from_db()
        self.assertEqual(shop_limited.name, "Limited Mart Main")

    # 8. Staff shop approval & 18. RBAC permission enforcement
    def test_staff_shop_approval_workflow(self):
        """Operation Manager (shops.approve) can approve a pending shop."""
        shop = ShopService.create_shop(
            self.seller_full,
            name="Pending Review Shop",
            submit_for_review=True,
        )
        self.assertEqual(shop.status, Shop.STATUS_PENDING)

        # Operation Manager approves shop
        self.client.force_authenticate(user=self.staff_op_manager)
        response = self.client.post(f"/api/shops/staff/{shop.pk}/approve/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        shop.refresh_from_db()
        self.assertEqual(shop.status, Shop.STATUS_ACTIVE)
        self.assertTrue(shop.is_publicly_visible)
        self.assertEqual(shop.reviewed_by, self.staff_op_manager)
        self.assertIsNotNone(shop.approved_at)

    # 9. Unauthorized shop approval
    def test_unauthorized_shop_approval(self):
        """Staff without 'shops.approve' (e.g. Support Team) cannot approve shops."""
        shop = ShopService.create_shop(
            self.seller_full,
            name="Pending Shop 2",
            submit_for_review=True,
        )

        self.client.force_authenticate(user=self.staff_support)
        response = self.client.post(f"/api/shops/staff/{shop.pk}/approve/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        shop.refresh_from_db()
        self.assertEqual(shop.status, Shop.STATUS_PENDING)

    # 10. Invalid status transitions
    def test_invalid_status_transitions(self):
        """Cannot reject or suspend invalid shop states."""
        shop = ShopService.create_shop(self.seller_full, name="Draft Only Shop")
        self.assertEqual(shop.status, Shop.STATUS_DRAFT)

        # Cannot reject a DRAFT shop (must be PENDING)
        with self.assertRaises(InvalidShopTransitionError):
            ShopService.reject_shop(shop, self.staff_op_manager, reason="Cannot reject draft")

        # Cannot suspend a DRAFT shop (must be ACTIVE or APPROVED)
        with self.assertRaises(InvalidShopTransitionError):
            ShopService.suspend_shop(shop, self.staff_op_manager, reason="Cannot suspend draft")

        # Cannot reactivate a non-suspended shop
        with self.assertRaises(InvalidShopTransitionError):
            ShopService.reactivate_shop(shop, self.staff_op_manager)

    # 11-15. Public visibility isolation
    def test_public_visibility_isolation(self):
        """Public users can ONLY see APPROVED or ACTIVE shops. All other states return 404."""
        # 1. Draft shop
        draft_shop = ShopService.create_shop(self.seller_full, name="Public Draft Shop")
        # 2. Pending shop
        pending_shop = ShopService.create_shop(self.seller_full, name="Public Pending Shop", submit_for_review=True)
        # 3. Active shop
        active_shop = ShopService.create_shop(self.seller_full, name="Public Active Shop", submit_for_review=True)
        ShopService.approve_shop(active_shop, self.staff_op_manager)
        # 4. Suspended shop
        suspended_shop = ShopService.create_shop(self.seller_full, name="Public Suspended Shop", submit_for_review=True)
        ShopService.approve_shop(suspended_shop, self.staff_op_manager)
        ShopService.suspend_shop(suspended_shop, self.staff_op_manager, reason="Violations")
        # 5. Rejected shop
        rejected_shop = ShopService.create_shop(self.seller_full, name="Public Rejected Shop", submit_for_review=True)
        ShopService.reject_shop(rejected_shop, self.staff_op_manager, reason="Incomplete documents")

        self.client.force_authenticate(user=None)

        # Public list only returns active_shop
        list_resp = self.client.get("/api/shops/")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        returned_slugs = [s["slug"] for s in (list_resp.data["results"] if "results" in list_resp.data else list_resp.data)]
        self.assertIn(active_shop.slug, returned_slugs)
        self.assertNotIn(draft_shop.slug, returned_slugs)
        self.assertNotIn(pending_shop.slug, returned_slugs)
        self.assertNotIn(suspended_shop.slug, returned_slugs)
        self.assertNotIn(rejected_shop.slug, returned_slugs)

        # Public detail checks
        self.assertEqual(self.client.get(f"/api/shops/{active_shop.slug}/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(f"/api/shops/{draft_shop.slug}/").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(f"/api/shops/{pending_shop.slug}/").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(f"/api/shops/{suspended_shop.slug}/").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(f"/api/shops/{rejected_shop.slug}/").status_code, status.HTTP_404_NOT_FOUND)

    # 16. Slug uniqueness
    def test_slug_uniqueness_and_auto_increment(self):
        """Creating shops with duplicate names automatically generates unique slugs."""
        shop1 = ShopService.create_shop(self.seller_full, name="Unique Name Store")
        shop2 = ShopService.create_shop(self.seller_full, name="Unique Name Store")
        self.assertEqual(shop1.slug, "unique-name-store")
        self.assertEqual(shop2.slug, "unique-name-store-1")

    # 17. Seller status restrictions
    def test_suspended_seller_cannot_create_or_modify_shop(self):
        """A suspended seller cannot create or update any shops."""
        self.client.force_authenticate(user=self.user_suspended)
        create_resp = self.client.post("/api/shops/mine/create/", {"name": "Suspended Shop"}, format="json")
        self.assertEqual(create_resp.status_code, status.HTTP_403_FORBIDDEN)

        # Service-level validation
        with self.assertRaises(IneligibleSellerError):
            ShopService.create_shop(self.seller_suspended, name="Direct Suspended Attempt")

    # Minimal Product Relationship Test
    def test_product_to_shop_relationship(self):
        """A Product can be linked to a Shop via foreign key."""
        shop = ShopService.create_shop(self.seller_full, name="Gadget Boutique", submit_for_review=True)
        ShopService.approve_shop(shop, self.staff_op_manager)

        category = Category.objects.create(name="Electronics", slug="electronics")
        product = Product.objects.create(
            category=category,
            shop=shop,
            name="Smart Fitness Tracker",
            price=1999.00,
            description="High precision fitness tracker.",
        )

        self.assertEqual(product.shop, shop)
        self.assertIn(product, shop.products.all())

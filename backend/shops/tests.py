import math
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shop.models import Category, Product
from shops.fields import Point
from shops.models import Shop
from shops.services import (
    IneligibleSellerError,
    InvalidShopTransitionError,
    ShopLimitExceededError,
    ShopService,
    validate_coordinates,
    validate_radius,
)

User = get_user_model()


class ShopSystemTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        # Full Shop Owner User
        cls.user_full = User.objects.create_user(
            username="full_owner",
            email="full@example.com",
            password="TestPassword123!",
        )
        cls.seller_full = SellerProfile.objects.create(
            user=cls.user_full,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Full Mart Ltd",
            status=SellerProfile.STATUS_ACTIVE,
        )

        # Limited Shop Owner User
        cls.user_limited = User.objects.create_user(
            username="limited_owner",
            email="limited@example.com",
            password="TestPassword123!",
        )
        cls.seller_limited = SellerProfile.objects.create(
            user=cls.user_limited,
            seller_type=SellerProfile.TYPE_LIMITED_SHOP_OWNER,
            business_name="Limited Kiosk Ltd",
            status=SellerProfile.STATUS_ACTIVE,
        )

        # Product Owner User
        cls.user_prod = User.objects.create_user(
            username="prod_owner",
            email="prod@example.com",
            password="TestPassword123!",
        )
        cls.seller_prod = SellerProfile.objects.create(
            user=cls.user_prod,
            seller_type=SellerProfile.TYPE_PRODUCT_OWNER,
            business_name="Artisan Solo Crafts",
            status=SellerProfile.STATUS_ACTIVE,
        )

        # Suspended Seller User
        cls.user_suspended = User.objects.create_user(
            username="suspended_seller",
            email="suspended@example.com",
            password="TestPassword123!",
        )
        cls.seller_suspended = SellerProfile.objects.create(
            user=cls.user_suspended,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Suspended Biz",
            status=SellerProfile.STATUS_SUSPENDED,
            suspension_reason="Policy violation",
        )

        # Staff with shops.approve (Operation Manager)
        cls.staff_op_manager = User.objects.create_user(
            username="op_manager",
            email="op@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.staff_op_manager, Role.ROLE_OPERATION_MANAGER)

        # Staff without shops.approve (Support Team only has shops.view)
        cls.staff_support = User.objects.create_user(
            username="support_user",
            email="support@example.com",
            password="TestPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.staff_support, Role.ROLE_SUPPORT_TEAM)

    def setUp(self):
        self.client = APIClient()

    # 1. Shop creation eligibility & 4. Full Shop Owner behavior (Admin-created Shop Owner model,
    # Phase 1H: shop creation is service-level / admin-only now — see AdminShopCreationTests
    # in shop/test_admin_governance.py for the HTTP-level admin-create-and-assign flow).
    def test_shop_creation_by_full_shop_owner(self):
        """A FULL_SHOP_OWNER seller is eligible for shop creation at the service level."""
        shop = ShopService.create_shop(
            self.seller_full,
            name="Apex Electronics Hub",
            description="Leading electronics store in Dhaka.",
            phone="+8801712345678",
            address="House 12, Road 5, Dhanmondi, Dhaka",
        )
        self.assertEqual(shop.name, "Apex Electronics Hub")
        self.assertEqual(shop.status, Shop.STATUS_DRAFT)
        self.assertEqual(shop.slug, "apex-electronics-hub")
        self.assertFalse(shop.is_publicly_visible)
        self.assertEqual(shop.owner, self.seller_full)

    # 1b. Seller self-service shop creation is hard-disabled (Phase 1H core rule).
    def test_seller_self_service_shop_creation_is_disabled(self):
        """No seller — regardless of type or eligibility — may create a shop via the API."""
        for user in (self.user_full, self.user_limited, self.user_prod, self.user_suspended):
            self.client.force_authenticate(user=user)
            response = self.client.post("/api/shops/mine/create/", {"name": "Attempted Shop"}, format="json")
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, f"Failed for {user.username}")
        self.assertFalse(Shop.objects.filter(name="Attempted Shop").exists())

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
        """Product Owner sellers are strictly barred from creating shops, at the service level."""
        with self.assertRaises(IneligibleSellerError):
            ShopService.create_shop(self.seller_prod, name="Direct Service Shop")

    # 5. Limited Shop Owner behavior (limit of 1 shop)
    def test_limited_shop_owner_single_shop_limit(self):
        """Limited Shop Owner is eligible for exactly 1 shop, at the service level."""
        ShopService.create_shop(self.seller_limited, name="Kiosk One")

        # A second shop for the same Limited Shop Owner is rejected.
        with self.assertRaises(ShopLimitExceededError):
            ShopService.create_shop(self.seller_limited, name="Kiosk Two")

    # 5b. Full Shop Owner is also capped at exactly 1 shop under the confirmed
    # single-Shop-per-owner business model (not just Limited Shop Owners).
    def test_full_shop_owner_single_shop_limit(self):
        """Full Shop Owner is eligible for exactly 1 shop, at the service level."""
        ShopService.create_shop(self.seller_full, name="Full Owner Shop One")

        with self.assertRaises(ShopLimitExceededError):
            ShopService.create_shop(self.seller_full, name="Full Owner Shop Two")

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
        # Each Shop Owner is capped at exactly one Shop under the confirmed business
        # model, so each status scenario below needs its own seller.
        def _make_full_shop_owner_seller(tag):
            user = User.objects.create_user(
                username=f"visibility_{tag}",
                email=f"visibility_{tag}@example.com",
                password="TestPassword123!",
            )
            return SellerProfile.objects.create(
                user=user,
                seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
                business_name=f"Visibility {tag.title()} Co",
                status=SellerProfile.STATUS_ACTIVE,
            )

        # 1. Draft shop
        draft_shop = ShopService.create_shop(_make_full_shop_owner_seller("draft"), name="Public Draft Shop")
        # 2. Pending shop
        pending_shop = ShopService.create_shop(
            _make_full_shop_owner_seller("pending"), name="Public Pending Shop", submit_for_review=True
        )
        # 3. Active shop
        active_shop = ShopService.create_shop(
            _make_full_shop_owner_seller("active"), name="Public Active Shop", submit_for_review=True
        )
        ShopService.approve_shop(active_shop, self.staff_op_manager)
        # 4. Suspended shop
        suspended_shop = ShopService.create_shop(
            _make_full_shop_owner_seller("suspended"), name="Public Suspended Shop", submit_for_review=True
        )
        ShopService.approve_shop(suspended_shop, self.staff_op_manager)
        ShopService.suspend_shop(suspended_shop, self.staff_op_manager, reason="Violations")
        # 5. Rejected shop
        rejected_shop = ShopService.create_shop(
            _make_full_shop_owner_seller("rejected"), name="Public Rejected Shop", submit_for_review=True
        )
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
        """Creating shops with duplicate names (for different owners) automatically generates unique slugs.

        Slug uniqueness is global across the Shop table, independent of ownership,
        so this is exercised across two distinct sellers (each capped at one shop).
        """
        second_user = User.objects.create_user(
            username="full_owner_two",
            email="full_two@example.com",
            password="TestPassword123!",
        )
        second_seller = SellerProfile.objects.create(
            user=second_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Full Mart Two Ltd",
            status=SellerProfile.STATUS_ACTIVE,
        )

        shop1 = ShopService.create_shop(self.seller_full, name="Unique Name Store")
        shop2 = ShopService.create_shop(second_seller, name="Unique Name Store")
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


class ShopSpatialAndNearbyTests(TestCase):
    """
    Task 6 Test Suite: MySQL 8 native spatial POINT location,
    axis-order handling, centralized coordinate validation,
    seller location updates, and nearby search with nearest-first sorting.
    """
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        cls.user_seller = User.objects.create_user(
            username="spatial_seller",
            email="spatial_seller@example.com",
            password="TestPassword123!",
        )
        cls.seller = SellerProfile.objects.create(
            user=cls.user_seller,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Spatial Mart Ltd",
            status=SellerProfile.STATUS_ACTIVE,
        )

        cls.user_other = User.objects.create_user(
            username="other_spatial_seller",
            email="other_spatial@example.com",
            password="TestPassword123!",
        )
        cls.other_seller = SellerProfile.objects.create(
            user=cls.user_other,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Other Spatial Mart",
            status=SellerProfile.STATUS_ACTIVE,
        )

        cls.user_suspended = User.objects.create_user(
            username="suspended_spatial_seller",
            email="suspended_spatial@example.com",
            password="TestPassword123!",
        )
        cls.seller_suspended = SellerProfile.objects.create(
            user=cls.user_suspended,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Suspended Spatial Mart",
            status=SellerProfile.STATUS_SUSPENDED,
            suspension_reason="Policy Violation",
        )

    def setUp(self):
        self.client = APIClient()

    # A. Database verification
    def test_database_is_mysql_and_spatial_index_exists(self):
        """Verify Django uses MySQL instead of SQLite, and the SPATIAL INDEX exists."""
        self.assertEqual(connection.vendor, "mysql")
        with connection.cursor() as cur:
            cur.execute("SELECT VERSION();")
            version = cur.fetchone()[0]
            self.assertTrue(version.startswith("8."))

            cur.execute("SHOW INDEX FROM shops_shop WHERE Index_type = 'SPATIAL';")
            indexes = cur.fetchall()
            self.assertTrue(len(indexes) >= 1)
            spatial_index_names = [idx[2] for idx in indexes]
            self.assertIn("shops_shop_location_spatial_idx", spatial_index_names)

    # B. Centralized Coordinate Validation
    def test_coordinate_validation_bounds(self):
        """Verify centralized coordinate validator enforces -90..90 lat and -180..180 lng."""
        # Valid coordinates (Dhaka)
        lat, lng = validate_coordinates(23.8103, 90.4125)
        self.assertEqual(lat, 23.8103)
        self.assertEqual(lng, 90.4125)

        # Exact boundary values
        self.assertEqual(validate_coordinates(90.0, 180.0), (90.0, 180.0))
        self.assertEqual(validate_coordinates(-90.0, -180.0), (-90.0, -180.0))

        # Latitude out of bounds
        with self.assertRaises(ValidationError):
            validate_coordinates(90.1, 90.0)
        with self.assertRaises(ValidationError):
            validate_coordinates(-90.001, 90.0)

        # Longitude out of bounds
        with self.assertRaises(ValidationError):
            validate_coordinates(23.0, 180.1)
        with self.assertRaises(ValidationError):
            validate_coordinates(23.0, -180.01)

        # Missing / None
        with self.assertRaises(ValidationError):
            validate_coordinates(None, 90.0)
        with self.assertRaises(ValidationError):
            validate_coordinates(23.0, None)

        # Non-numeric / malformed
        with self.assertRaises(ValidationError):
            validate_coordinates("invalid_lat", 90.0)
        with self.assertRaises(ValidationError):
            validate_coordinates(23.0, "invalid_lng")

        # NaN / Infinite
        with self.assertRaises(ValidationError):
            validate_coordinates(float("nan"), 90.0)
        with self.assertRaises(ValidationError):
            validate_coordinates(23.0, float("inf"))

    # B2. Centralized Radius Validation
    def test_radius_validation(self):
        """Verify centralized radius validator enforces positive values and max bounds."""
        self.assertEqual(validate_radius(5.0), 5.0)
        self.assertEqual(validate_radius("2.5"), 2.5)

        # Non-positive values
        with self.assertRaises(ValidationError):
            validate_radius(0)
        with self.assertRaises(ValidationError):
            validate_radius(-2.5)

        # Excessive radius (> 1000 km)
        with self.assertRaises(ValidationError):
            validate_radius(1001)

        # Missing / malformed
        with self.assertRaises(ValidationError):
            validate_radius(None)
        with self.assertRaises(ValidationError):
            validate_radius("bad_rad")
        with self.assertRaises(ValidationError):
            validate_radius(float("nan"))

    # C. MySQL Axis-Order & Storage Verification
    def test_mysql_axis_order_and_storage(self):
        """Verify lat=23.8103, lng=90.4125 are saved without coordinate swap."""
        shop = ShopService.create_shop(
            seller=self.seller,
            name="Axis Order Test Shop",
            latitude=23.8103,
            longitude=90.4125,
        )
        shop.refresh_from_db()
        self.assertTrue(shop.has_coordinates)
        self.assertAlmostEqual(shop.latitude, 23.8103, places=4)
        self.assertAlmostEqual(shop.longitude, 90.4125, places=4)

        # Direct SQL verification in MySQL
        with connection.cursor() as cur:
            cur.execute(
                "SELECT ST_Latitude(location), ST_Longitude(location) FROM shops_shop WHERE id = %s;",
                (shop.id,),
            )
            lat, lng = cur.fetchone()
            self.assertAlmostEqual(lat, 23.8103, places=4)
            self.assertAlmostEqual(lng, 90.4125, places=4)

    # D. Seller Location Update API
    def test_seller_can_update_own_shop_location(self):
        """Authenticated seller can update their own shop location."""
        shop = ShopService.create_shop(self.seller, name="Updatable Shop")
        self.client.force_authenticate(user=self.user_seller)

        response = self.client.patch(
            f"/api/shops/mine/{shop.id}/location/",
            {"latitude": 23.8103, "longitude": 90.4125},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["shop"]["latitude"], 23.8103)
        self.assertEqual(response.data["shop"]["longitude"], 90.4125)

        shop.refresh_from_db()
        self.assertAlmostEqual(shop.latitude, 23.8103, places=4)
        self.assertAlmostEqual(shop.longitude, 90.4125, places=4)

    def test_seller_cannot_update_other_seller_shop_location(self):
        """Seller cannot update another seller's shop location (returns 403 or 404)."""
        shop = ShopService.create_shop(self.seller, name="Other Protected Shop")
        self.client.force_authenticate(user=self.user_other)

        response = self.client.patch(
            f"/api/shops/mine/{shop.id}/location/",
            {"latitude": 23.8103, "longitude": 90.4125},
            format="json",
        )
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_unauthenticated_cannot_update_location(self):
        """Unauthenticated user receives 401 when attempting to update location."""
        shop = ShopService.create_shop(self.seller, name="Anon Location Shop")
        response = self.client.patch(
            f"/api/shops/mine/{shop.id}/location/",
            {"latitude": 23.8103, "longitude": 90.4125},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_suspended_seller_cannot_update_location(self):
        """Suspended seller receives 403 when attempting to update shop location."""
        shop = Shop.objects.create(owner=self.seller_suspended, name="Suspended Shop")
        self.client.force_authenticate(user=self.user_suspended)

        response = self.client.patch(
            f"/api/shops/mine/{shop.id}/location/",
            {"latitude": 23.8103, "longitude": 90.4125},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_invalid_coordinates_rejected_on_update(self):
        """Invalid coordinate values return 400 Bad Request."""
        shop = ShopService.create_shop(self.seller, name="Bad Coord Shop")
        self.client.force_authenticate(user=self.user_seller)

        response = self.client.patch(
            f"/api/shops/mine/{shop.id}/location/",
            {"latitude": 105.0, "longitude": 90.0},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # E. Public Nearby Search API
    def test_nearby_search_inside_and_outside_radius(self):
        """Shops inside radius are returned; shops outside radius are excluded."""
        # Origin: Dhaka Gulshan-1 (23.7788, 90.4172)
        # Shop 1: Center (23.7788, 90.4172) - 0.0 km (ACTIVE)
        shop1 = Shop.objects.create(
            owner=self.seller,
            name="Gulshan-1 Shop",
            status=Shop.STATUS_ACTIVE,
            location=Point(longitude=90.4172, latitude=23.7788),
        )
        # Shop 2: Gulshan-2 (23.7925, 90.4168) - ~1.52 km (APPROVED)
        shop2 = Shop.objects.create(
            owner=self.seller,
            name="Gulshan-2 Shop",
            status=Shop.STATUS_APPROVED,
            location=Point(longitude=90.4168, latitude=23.7925),
        )
        # Shop 3: Uttara (23.8728, 90.3978) - ~10.6 km (ACTIVE)
        shop3 = Shop.objects.create(
            owner=self.seller,
            name="Uttara Shop",
            status=Shop.STATUS_ACTIVE,
            location=Point(longitude=90.3978, latitude=23.8728),
        )

        response = self.client.get("/api/shops/nearby/?lat=23.7788&lng=90.4172&radius=2")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        result_ids = [r["id"] for r in results]

        self.assertIn(shop1.id, result_ids)
        self.assertIn(shop2.id, result_ids)
        self.assertNotIn(shop3.id, result_ids)

    def test_nearby_search_nearest_first_ordering(self):
        """Nearby search results must be ordered nearest-first (ascending distance)."""
        # Origin: (23.7788, 90.4172)
        shop_far = Shop.objects.create(
            owner=self.seller,
            name="Far Shop (~1.5 km)",
            status=Shop.STATUS_ACTIVE,
            location=Point(longitude=90.4168, latitude=23.7925),
        )
        shop_close = Shop.objects.create(
            owner=self.seller,
            name="Close Shop (0.0 km)",
            status=Shop.STATUS_ACTIVE,
            location=Point(longitude=90.4172, latitude=23.7788),
        )

        response = self.client.get("/api/shops/nearby/?lat=23.7788&lng=90.4172&radius=5")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertTrue(len(results) >= 2)

        # Nearest must be first
        self.assertEqual(results[0]["id"], shop_close.id)
        self.assertEqual(results[1]["id"], shop_far.id)
        self.assertLessEqual(results[0]["distance_km"], results[1]["distance_km"])
        self.assertAlmostEqual(results[0]["distance_km"], 0.0, places=1)
        self.assertGreater(results[1]["distance_km"], 1.0)

    def test_nearby_search_excludes_non_public_shops(self):
        """Only APPROVED and ACTIVE shops appear in nearby search; non-public states are excluded."""
        coords = Point(longitude=90.4125, latitude=23.8103)

        Shop.objects.create(owner=self.seller, name="Active Shop", status=Shop.STATUS_ACTIVE, location=coords)
        Shop.objects.create(owner=self.seller, name="Approved Shop", status=Shop.STATUS_APPROVED, location=coords)
        Shop.objects.create(owner=self.seller, name="Draft Shop", status=Shop.STATUS_DRAFT, location=coords)
        Shop.objects.create(owner=self.seller, name="Pending Shop", status=Shop.STATUS_PENDING, location=coords)
        Shop.objects.create(
            owner=self.seller,
            name="Suspended Shop",
            status=Shop.STATUS_SUSPENDED,
            location=coords,
            suspension_reason="Violation",
        )
        Shop.objects.create(
            owner=self.seller,
            name="Rejected Shop",
            status=Shop.STATUS_REJECTED,
            location=coords,
            rejection_reason="Violation",
        )

        response = self.client.get("/api/shops/nearby/?lat=23.8103&lng=90.4125&radius=5")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [r["name"] for r in response.data["results"]]

        self.assertIn("Active Shop", names)
        self.assertIn("Approved Shop", names)
        self.assertNotIn("Draft Shop", names)
        self.assertNotIn("Pending Shop", names)
        self.assertNotIn("Suspended Shop", names)
        self.assertNotIn("Rejected Shop", names)

    def test_nearby_search_parameter_validation(self):
        """Verify parameter validation for nearby search query."""
        # Missing lat
        r1 = self.client.get("/api/shops/nearby/?lng=90.4125&radius=5")
        self.assertEqual(r1.status_code, status.HTTP_400_BAD_REQUEST)

        # Missing lng
        r2 = self.client.get("/api/shops/nearby/?lat=23.8103&radius=5")
        self.assertEqual(r2.status_code, status.HTTP_400_BAD_REQUEST)

        # Missing radius
        r3 = self.client.get("/api/shops/nearby/?lat=23.8103&lng=90.4125")
        self.assertEqual(r3.status_code, status.HTTP_400_BAD_REQUEST)

        # Radius <= 0
        r4 = self.client.get("/api/shops/nearby/?lat=23.8103&lng=90.4125&radius=0")
        self.assertEqual(r4.status_code, status.HTTP_400_BAD_REQUEST)

        # Negative radius
        r5 = self.client.get("/api/shops/nearby/?lat=23.8103&lng=90.4125&radius=-5")
        self.assertEqual(r5.status_code, status.HTTP_400_BAD_REQUEST)

        # Excessive radius (> 1000 km)
        r6 = self.client.get("/api/shops/nearby/?lat=23.8103&lng=90.4125&radius=2000")
        self.assertEqual(r6.status_code, status.HTTP_400_BAD_REQUEST)

        # Malformed lat
        r7 = self.client.get("/api/shops/nearby/?lat=not_a_num&lng=90.4125&radius=5")
        self.assertEqual(r7.status_code, status.HTTP_400_BAD_REQUEST)

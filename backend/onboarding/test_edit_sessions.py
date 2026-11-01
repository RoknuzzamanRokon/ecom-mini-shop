"""
docs/SALES_TEAM_EDITS_PAYOUTS_PLAN.md §1 and §3: corrections need the seller's
code, and an onboarder sees only the products they added.
"""
from datetime import timedelta
from importlib import import_module

from django.apps import apps
from django.test import override_settings
from django.utils import timezone
from rest_framework import status

from audit.models import AuditLog
from notifications import events
from notifications.categories import ACCOUNT
from notifications.models import Notification, NotificationEvent
from notifications.routing import route_event
from points.services import PointService
from rbac.models import Permission, Role, RolePermission, StartingPassword, UserPermissionBlock
from rbac.services import get_user_permissions
from sellers.models import SellerProfile
from shop.models import Product
from shop.services import ProductService
from shops.models import Shop
from .models import EditSession, OnboardingSettings
from .tests import MEDIA_ROOT, OnboardingTestCase


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class EditSessionTestCase(OnboardingTestCase):
    """A seller with a shop and one product, all opened by `sales`."""

    def setUp(self):
        super().setUp()
        self.seller = self.onboard()
        self.shop = Shop.objects.get(pk=self.add_shop(self.seller).data["id"])
        self.product = Product.objects.get(pk=self.add_product(self.shop).data["id"])

    def session_url(self, seller=None):
        return f"/api/onboarding/sellers/{(seller or self.seller).pk}/edit-session/"

    def ask_code(self, user=None, seller=None):
        response = self.as_user(user or self.sales).post(self.session_url(seller))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        session = EditSession.objects.latest("created_at")
        return NotificationEvent.objects.get(idempotency_key=f"onboarding_edit_code:{session.pk}").payload["code"]

    def enter(self, code, user=None):
        return self.as_user(user or self.sales).post(f"{self.session_url()}verify/", {"code": code}, format="json")

    def open_session(self):
        response = self.enter(self.ask_code())
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response

    def wrong(self, code):
        return "000000" if code != "000000" else "111111"

    def allow_new_code(self):
        EditSession.objects.update(created_at=timezone.now() - timedelta(minutes=2))


class EditCodeTests(EditSessionTestCase):
    def test_the_code_reaches_the_seller_and_opens_thirty_minutes(self):
        response = self.as_user(self.sales).post(self.session_url())
        self.assertEqual(response.data["state"], "waiting")
        self.assertEqual(response.data["attempts_left"], 5)

        event = NotificationEvent.objects.get(event_type=events.ONBOARDING_EDIT_CODE)
        code = event.payload["code"]
        self.assertRegex(code, r"^\d{6}$")
        self.assertEqual((event.payload["valid_minutes"], event.payload["edit_minutes"]), (10, 30))
        route_event(event.pk)
        inbox = Notification.objects.get(event_type=events.ONBOARDING_EDIT_CODE)
        self.assertEqual((inbox.recipient, inbox.category), (self.seller.user, ACCOUNT))
        self.assertEqual(inbox.title, f"Your edit code: {code}")

        before = timezone.now()
        response = self.enter(f" {code} ")
        self.assertEqual(response.data["state"], "open")
        session = EditSession.objects.get()
        self.assertAlmostEqual(session.expires_at, before + timedelta(minutes=30), delta=timedelta(seconds=30))
        self.assertTrue(AuditLog.objects.filter(action="ONBOARDING_EDIT_SESSION_OPENED", seller=self.seller).exists())

    def test_the_seller_starts_on_the_onboarders_password(self):
        starting = StartingPassword.objects.get(user=self.seller.user)
        self.assertEqual((starting.set_by, starting.replaced_at), (self.sales, None))

        starting.delete()
        import_module("onboarding.migrations.0003_starting_passwords").backfill(apps, None)
        self.assertEqual(StartingPassword.objects.get(user=self.seller.user).set_by, self.sales)

    def test_the_code_is_kept_only_as_a_digest(self):
        code = self.ask_code()
        session = EditSession.objects.get()
        self.assertNotIn(code, session.code_digest)
        self.assertEqual(len(session.code_digest), 64)

    def test_the_settings_decide_the_minutes(self):
        OnboardingSettings.objects.create(edit_code_minutes=5, edit_window_minutes=45)
        before = timezone.now()
        self.enter(self.ask_code())
        session = EditSession.objects.get()
        self.assertAlmostEqual(session.code_expires_at, before + timedelta(minutes=5), delta=timedelta(seconds=30))
        self.assertAlmostEqual(session.expires_at, before + timedelta(minutes=45), delta=timedelta(seconds=30))

    def test_five_wrong_codes_void_it(self):
        code = self.ask_code()
        for left in (4, 3, 2, 1):
            response = self.enter(self.wrong(code))
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn(f"{left} tr", response.data["detail"])
        self.assertIn("too many times", self.enter(self.wrong(code)).data["detail"])
        self.assertIn("Ask for a new one", self.enter(code).data["detail"])
        self.assertEqual(self.as_user(self.sales).get(self.session_url()).data["state"], "ended")

    def test_an_expired_code_is_refused(self):
        code = self.ask_code()
        EditSession.objects.update(code_expires_at=timezone.now() - timedelta(seconds=1))
        response = self.enter(code)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expired", response.data["detail"])

    def test_a_new_code_waits_a_minute_and_replaces_the_old_one(self):
        old = self.ask_code()
        response = self.as_user(self.sales).post(self.session_url())
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertGreater(response.data["wait_seconds"], 0)

        self.allow_new_code()
        new = self.ask_code()
        if new != old:
            self.assertEqual(self.enter(old).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.enter(new).data["state"], "open")

    def test_an_open_session_is_closed_before_a_new_code(self):
        self.open_session()
        self.allow_new_code()
        response = self.as_user(self.sales).post(self.session_url())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already open until", response.data["detail"])

        self.assertEqual(self.as_user(self.sales).delete(self.session_url()).data["state"], "ended")
        self.assertEqual(self.as_user(self.sales).post(self.session_url()).status_code, status.HTTP_201_CREATED)

    def test_a_rejected_seller_gets_no_code(self):
        self.as_user(self.admin).post(f"/api/onboarding/review/{self.seller.pk}/reject/", {"reason": "Closed down"})
        response = self.as_user(self.sales).post(self.session_url())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("rejected", response.data["detail"])

    def test_another_onboarders_seller_is_not_found(self):
        self.assertEqual(self.as_user(self.other_sales).post(self.session_url()).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.as_user(self.other_sales).patch(f"/api/onboarding/shops/{self.shop.pk}/", {"name": "X"}).status_code,
            status.HTTP_404_NOT_FOUND,
        )


class EditTests(EditSessionTestCase):
    def test_without_an_open_session_every_edit_is_refused(self):
        urls_and_data = (
            (f"/api/onboarding/sellers/{self.seller.pk}/", {"business_name": "New Name"}),
            (f"/api/onboarding/shops/{self.shop.pk}/", {"name": "New Shop"}),
            (f"/api/onboarding/products/{self.product.pk}/", {"price": "500.00"}),
        )
        for url, data in urls_and_data:
            with self.subTest(url=url):
                response = self.as_user(self.sales).patch(url, data, format="json")
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(response.data["code"], "edit_session_required")

    def test_an_open_session_corrects_the_seller_shop_and_product(self):
        self.open_session()
        session = EditSession.objects.get()

        response = self.as_user(self.sales).patch(
            f"/api/onboarding/sellers/{self.seller.pk}/",
            {"business_name": "Karim Traders", "seller_type": SellerProfile.TYPE_LIMITED_SHOP_OWNER},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["business_name"], "Karim Traders")
        self.seller.refresh_from_db()
        self.assertEqual(self.seller.seller_type, SellerProfile.TYPE_FULL_SHOP_OWNER)
        row = AuditLog.objects.get(action="ONBOARDING_SELLER_UPDATED")
        self.assertEqual((row.actor, row.metadata["edit_session_id"]), (self.sales, session.pk))
        self.assertEqual(row.metadata["new_state"], {"business_name": "Karim Traders"})

        response = self.as_user(self.sales).patch(
            f"/api/onboarding/shops/{self.shop.pk}/",
            {"name": "Karim Corner", "phone": "01911111111", "additional_phones": ["01922222222"],
             "latitude": 23.81, "longitude": 90.37},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.shop.refresh_from_db()
        self.assertEqual((self.shop.name, self.shop.additional_phones), ("Karim Corner", ["01922222222"]))
        self.assertAlmostEqual(self.shop.latitude, 23.81, places=4)
        self.assertTrue(AuditLog.objects.filter(action="ONBOARDING_SHOP_UPDATED", shop=self.shop).exists())

        response = self.as_user(self.sales).patch(
            f"/api/onboarding/products/{self.product.pk}/",
            {"price": "480.00", "stock": 12, "expected_stock": 10},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data["price"], response.data["stock"]), ("480.00", 12))
        row = AuditLog.objects.filter(action="PRODUCT_UPDATED", target_id=str(self.product.pk)).latest("pk")
        self.assertEqual((row.actor, row.metadata["edited_via"]), (self.sales, "onboarding"))

    def test_a_stale_stock_figure_is_a_conflict(self):
        self.open_session()
        response = self.as_user(self.sales).patch(
            f"/api/onboarding/products/{self.product.pk}/", {"stock": 3, "expected_stock": 7}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["current_stock"], 10)

    def test_editing_stops_when_the_window_ends(self):
        self.open_session()
        EditSession.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        response = self.as_user(self.sales).patch(
            f"/api/onboarding/sellers/{self.seller.pk}/", {"business_name": "Late"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.as_user(self.sales).get(self.session_url()).data["state"], "ended")

    def test_an_approved_seller_is_corrected_too(self):
        self.as_user(self.admin).post(f"/api/onboarding/review/{self.seller.pk}/approve/")
        self.open_session()
        response = self.as_user(self.sales).patch(
            f"/api/onboarding/products/{self.product.pk}/", {"name": "Rice 10kg"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.product.refresh_from_db()
        self.assertEqual((self.product.name, self.product.status), ("Rice 10kg", Product.STATUS_PUBLISHED))

    def test_the_detail_reports_the_session(self):
        data = self.as_user(self.sales).get(f"/api/onboarding/sellers/{self.seller.pk}/").data
        self.assertEqual(data["edit_session"]["state"], "none")
        self.assertTrue(data["can_view_products"])
        self.open_session()
        data = self.as_user(self.sales).get(f"/api/onboarding/sellers/{self.seller.pk}/").data
        self.assertEqual(data["edit_session"]["state"], "open")


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ProductVisibilityTests(EditSessionTestCase):
    def seller_adds_own_product(self):
        self.as_user(self.admin).post(f"/api/onboarding/review/{self.seller.pk}/approve/")
        self.seller.refresh_from_db()
        PointService.adjust_points(
            seller=self.seller, amount=100, action="CREDIT", reason="Top up", actor=self.root
        )
        return ProductService.create_product(
            seller=self.seller, name="Own Oil", category=self.category, shop=Shop.objects.get(pk=self.shop.pk),
            description="Soybean", price="180.00", actor=self.seller.user,
        )

    def turn_off(self, user=None):
        UserPermissionBlock.objects.create(
            user=user or self.sales,
            permission=Permission.objects.get(code="onboarding.products.view"),
            blocked_at=timezone.now(),
            reason="Test",
        )

    def test_the_sales_team_lost_every_product_and_its_stock(self):
        held = get_user_permissions(self.sales)
        self.assertIn("onboarding.products.view", held)
        for code in ("products.view", "products.create", "products.update", "inventory.view", "inventory.adjust"):
            self.assertNotIn(code, held)
        self.assertEqual(self.as_user(self.sales).get("/api/admin/products/").status_code, status.HTTP_403_FORBIDDEN)

    def test_the_migration_moves_an_existing_sales_team_over(self):
        sales_team = Role.objects.get(code=Role.ROLE_SALES_TEAM)
        RolePermission.objects.filter(role=sales_team, permission__code="onboarding.products.view").delete()
        for code in ("products.view", "inventory.view"):
            RolePermission.objects.create(role=sales_team, permission=Permission.objects.get(code=code))

        import_module("rbac.migrations.0008_sales_team_own_products").apply(apps, None)

        codes = set(sales_team.permissions.values_list("code", flat=True))
        self.assertIn("onboarding.products.view", codes)
        self.assertFalse(codes & {"products.view", "inventory.view"})
        admin_codes = Role.objects.get(code=Role.ROLE_ADMINISTRATOR).permissions.values_list("code", flat=True)
        self.assertIn("onboarding.payouts.manage", admin_codes)

    def test_an_onboarder_sees_only_the_products_they_added(self):
        own = self.seller_adds_own_product()
        self.assertEqual(self.product.onboarded_by, self.sales)
        self.assertIsNone(own.onboarded_by)

        listed = self.as_user(self.sales).get("/api/onboarding/products/").data["results"]
        self.assertEqual([row["id"] for row in listed], [self.product.pk])
        self.assertEqual(listed[0]["seller_name"], self.seller.business_name)
        self.assertEqual(
            self.as_user(self.sales).get(f"/api/onboarding/products/{own.pk}/").status_code, status.HTTP_404_NOT_FOUND
        )
        detail = self.as_user(self.sales).get(f"/api/onboarding/sellers/{self.seller.pk}/").data
        self.assertEqual([p["id"] for p in detail["shops"][0]["products"]], [self.product.pk])
        self.assertEqual(detail["product_count"], 1)
        row = self.as_user(self.sales).get("/api/onboarding/sellers/").data["results"][0]
        self.assertEqual(row["product_count"], 1)

        # The approvers' queue still shows every product.
        review = self.as_user(self.admin).get(f"/api/onboarding/review/{self.seller.pk}/").data
        self.assertEqual(review["product_count"], 2)

    def test_without_the_permission_products_stay_hidden(self):
        self.turn_off()
        self.assertEqual(self.as_user(self.sales).get("/api/onboarding/products/").status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            self.as_user(self.sales).get(f"/api/onboarding/products/{self.product.pk}/").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        detail = self.as_user(self.sales).get(f"/api/onboarding/sellers/{self.seller.pk}/").data
        self.assertFalse(detail["can_view_products"])
        self.assertEqual((detail["shops"][0]["products"], detail["product_count"]), ([], None))
        # Adding a product is part of onboarding, and still works.
        self.assertEqual(self.add_product(self.shop, name="Lentils").status_code, status.HTTP_201_CREATED)
        # Another onboarder keeps the permission.
        self.assertIn("onboarding.products.view", get_user_permissions(self.other_sales))

    def test_the_backfill_finds_products_added_before_the_field(self):
        Product.objects.filter(pk=self.product.pk).update(onboarded_by=None)
        own = self.seller_adds_own_product()

        import_module("shop.migrations.0014_backfill_onboarded_by").backfill(apps, None)

        self.product.refresh_from_db()
        own.refresh_from_db()
        self.assertEqual((self.product.onboarded_by, own.onboarded_by), (self.sales, None))

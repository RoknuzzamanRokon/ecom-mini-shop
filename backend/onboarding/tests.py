import io
import tempfile
from decimal import Decimal
from importlib import import_module
from io import StringIO

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from audit.models import AuditLog
from points.models import PointTransaction, ProductCreationCost, SellerWallet, StaffWallet
from points.services import PointService
from rbac.models import LoginPhone, Permission, Role, RolePermission
from rbac.services import assign_user_role, get_user_permissions
from sellers.models import SellerProfile
from sellers.services import reject_seller
from shop.models import Category, Product
from shops.models import Shop
from .models import OnboardingSettings, SellerOnboarding, TokenTransaction, TokenWallet
from .services import OnboardingService

User = get_user_model()

MEDIA_ROOT = tempfile.mkdtemp(prefix="minishop-onboarding-")
PASSWORD = "Field-Seller-123"


def png(name="photo.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 6), (186, 134, 48)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def seller_payload(tag, **account):
    return {
        "account": {
            "username": f"{tag}_owner",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "first_name": "Karim",
            **account,
        },
        "business_name": f"{tag} Store",
        "business_phone": "01811111111",
    }


class OnboardingTestCase(TestCase):
    """
    A superuser who mints points, a Sales Team member holding 500 of them,
    a second one, an Administrator (who may approve an onboarding) and a
    Sales Manager (who may approve sellers, but not shops or products).
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.root = User.objects.create_superuser(username="root", password="Root-Pass-123")
        PointService.mint_points(cls.root, 10_000, "Field budget")
        cls.sales = cls.staff("sales", Role.ROLE_SALES_TEAM, points=500)
        cls.other_sales = cls.staff("other_sales", Role.ROLE_SALES_TEAM, points=500)
        cls.admin = cls.staff("admin", Role.ROLE_ADMINISTRATOR)
        cls.sales_manager = cls.staff("sales_manager", Role.ROLE_SALES_MANAGER)
        cls.category = Category.objects.create(name="Grocery", slug="grocery", is_active=True)

    @classmethod
    def staff(cls, username, role_code, points=0):
        user = User.objects.create_user(username=username, password="Staff-Pass-123", is_staff=True)
        assign_user_role(user, role_code)
        if points:
            PointService.transfer_to_staff(cls.root, user, points, "Field budget")
        return user

    def setUp(self):
        self.client = APIClient()

    def as_user(self, user):
        self.client.force_authenticate(user)
        return self.client

    def onboard(self, tag="corner", user=None, **account):
        account = account or {"phone": "01712345678"}
        response = self.as_user(user or self.sales).post(
            "/api/onboarding/sellers/", seller_payload(tag, **account), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return SellerProfile.objects.get(pk=response.data["id"])

    def add_shop(self, seller, user=None, **fields):
        response = self.as_user(user or self.sales).post(
            f"/api/onboarding/sellers/{seller.pk}/shops/",
            {"name": f"{seller.business_name} Shop", "address": "Mirpur 10", "latitude": 23.807, "longitude": 90.368, **fields},
            format="json",
        )
        return response

    def add_product(self, shop, user=None, **fields):
        return self.as_user(user or self.sales).post(
            f"/api/onboarding/shops/{shop.pk}/products/",
            {"name": "Rice 5kg", "category_id": self.category.pk, "description": "Miniket", "price": "450.00",
             "stock": 10, **fields},
            format="multipart" if "image" in fields else "json",
        )

    def staff_points(self, user):
        return StaffWallet.objects.get(user=user).balance

    def seller_points(self, seller):
        return SellerWallet.objects.get(seller=seller).balance

    def tokens(self, user):
        return TokenWallet.objects.filter(user=user).values_list("balance", flat=True).first() or 0


class SalesTeamPermissionTests(OnboardingTestCase):
    def test_sales_team_onboards_but_no_longer_sees_the_seller_directory(self):
        held = get_user_permissions(self.sales)
        self.assertIn("sellers.onboard", held)
        self.assertNotIn("sellers.view", held)
        self.assertNotIn("sellers.create", held)
        self.assertEqual(self.as_user(self.sales).get("/api/admin/sellers/").status_code, status.HTTP_403_FORBIDDEN)

    def test_the_migration_moves_an_existing_sales_team_over(self):
        sales_team = Role.objects.get(code=Role.ROLE_SALES_TEAM)
        RolePermission.objects.filter(role=sales_team, permission__code="sellers.onboard").delete()
        RolePermission.objects.create(role=sales_team, permission=Permission.objects.get(code="sellers.view"))

        import_module("rbac.migrations.0005_sellers_onboard_permission").grant_sellers_onboard(apps, None)

        codes = set(sales_team.permissions.values_list("code", flat=True))
        self.assertIn("sellers.onboard", codes)
        self.assertNotIn("sellers.view", codes)

    def test_a_superuser_can_send_the_sales_team_points(self):
        response = self.as_user(self.root).get(f"/api/points/staff/{self.sales.pk}/")
        self.assertTrue(response.data["can_receive_transfers"])
        self.assertEqual(self.staff_points(self.sales), 500)

    def test_onboarding_needs_the_permission(self):
        for url in ("/api/onboarding/me/", "/api/onboarding/sellers/", "/api/onboarding/tokens/"):
            with self.subTest(url=url):
                self.assertEqual(self.as_user(self.sales).get(url).status_code, status.HTTP_200_OK)
                for user in (self.admin, self.sales_manager):
                    self.assertEqual(self.as_user(user).get(url).status_code, status.HTTP_403_FORBIDDEN)


class OnboardSellerTests(OnboardingTestCase):
    def test_opening_a_seller_moves_points_and_earns_tokens(self):
        seller = self.onboard(phone="01712-345678")

        self.assertEqual(seller.status, SellerProfile.STATUS_PENDING)
        self.assertEqual(seller.created_by, self.sales)
        self.assertEqual(seller.user.email, "")
        self.assertEqual(seller.user.login_phone.number, "+8801712345678")
        self.assertEqual(self.staff_points(self.sales), 300)
        self.assertEqual(self.seller_points(seller), 200)
        self.assertEqual(self.tokens(self.sales), 51)
        onboarding = seller.onboarding
        self.assertEqual((onboarding.starting_points, onboarding.tokens_awarded), (200, 51))
        self.assertTrue(AuditLog.objects.filter(action="SELLER_ONBOARDED", target_id=str(seller.pk)).exists())

        # The shop owner signs in with the number.
        token = APIClient().post("/api/auth/token/", {"username": "01712345678", "password": PASSWORD}, format="json")
        self.assertEqual(token.status_code, status.HTTP_200_OK)

    def test_five_hundred_points_open_two_sellers(self):
        self.onboard("first", phone="01712345678")
        self.onboard("second", email="second@example.com")

        response = self.as_user(self.sales).post(
            "/api/onboarding/sellers/", seller_payload("third", phone="01912345678"), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual((response.data["required_points"], response.data["available_points"]), (200, 100))
        # Nothing of the refused seller is kept.
        self.assertFalse(User.objects.filter(username="third_owner").exists())
        self.assertFalse(LoginPhone.objects.filter(number="+8801912345678").exists())
        self.assertEqual(self.tokens(self.sales), 102)

    def test_the_settings_decide_what_an_onboarding_moves(self):
        OnboardingSettings.objects.create(starting_points=150, tokens_per_seller=10)
        seller = self.onboard()
        self.assertEqual(self.seller_points(seller), 150)
        self.assertEqual(self.staff_points(self.sales), 350)
        self.assertEqual(self.tokens(self.sales), 10)

    def test_the_account_needs_an_email_or_a_phone(self):
        response = self.as_user(self.sales).post("/api/onboarding/sellers/", seller_payload("bare"), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.staff_points(self.sales), 500)

    def test_a_username_cannot_be_a_phone_number(self):
        payload = seller_payload("x", phone="01712345678")
        payload["account"]["username"] = "01812345678"
        response = self.as_user(self.sales).post("/api/onboarding/sellers/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data["account"])

    def test_the_summary_counts_the_onboarders_sellers(self):
        approved = self.onboard("approved", phone="01712345678")
        self.onboard("waiting", phone="01812345678")
        self.as_user(self.admin).post(f"/api/onboarding/review/{approved.pk}/approve/")

        data = self.as_user(self.sales).get("/api/onboarding/me/").data
        self.assertEqual(data["points"], 100)
        self.assertEqual(data["tokens"], 102)
        self.assertEqual(data["starting_points"], 200)
        self.assertEqual(data["tokens_per_seller"], 51)
        self.assertEqual(data["product_creation_cost"], PointService.get_product_creation_cost())
        self.assertFalse(data["can_onboard"])
        self.assertEqual(data["sellers"], {"total": 2, "awaiting_approval": 1, "live": 1, "rejected": 0})

    def test_the_console_records_who_created_a_seller(self):
        response = self.as_user(self.admin).post(
            "/api/admin/sellers/",
            {"account": {"username": "console_owner", "email": "console@example.com", "password": PASSWORD,
                         "password_confirm": PASSWORD},
             "business_name": "Console Store", "reason": "Walk-in"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        seller = SellerProfile.objects.get(pk=response.data["id"])
        self.assertEqual(seller.created_by, self.admin)
        self.assertFalse(SellerOnboarding.objects.filter(seller=seller).exists())


class OnboarderScopeTests(OnboardingTestCase):
    def test_an_onboarder_reaches_only_their_own_sellers(self):
        mine = self.onboard("mine", phone="01712345678")
        theirs = self.onboard("theirs", user=self.other_sales, phone="01812345678")
        shop = Shop.objects.get(pk=self.add_shop(theirs, user=self.other_sales).data["id"])

        listed = self.as_user(self.sales).get("/api/onboarding/sellers/").data["results"]
        self.assertEqual([row["id"] for row in listed], [mine.pk])
        self.assertEqual(self.as_user(self.sales).get(f"/api/onboarding/sellers/{theirs.pk}/").status_code, 404)
        self.assertEqual(self.add_shop(theirs).status_code, 404)
        self.assertEqual(self.add_product(shop).status_code, 404)

    def test_sellers_opened_elsewhere_are_out_of_reach(self):
        seller = SellerProfile.objects.create(
            user=User.objects.create_user(username="direct", password=PASSWORD),
            business_name="Direct", created_by=self.sales,
        )
        self.assertEqual(self.as_user(self.sales).get(f"/api/onboarding/sellers/{seller.pk}/").status_code, 404)


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class CatalogBeforeApprovalTests(OnboardingTestCase):
    def test_a_shop_and_products_wait_for_approval(self):
        seller = self.onboard()
        response = self.add_shop(seller)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        shop = Shop.objects.get(pk=response.data["id"])
        self.assertEqual(shop.status, Shop.STATUS_PENDING)
        self.assertAlmostEqual(response.data["latitude"], 23.807)

        response = self.add_product(shop, image=png())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        product = Product.objects.get(pk=response.data["id"])
        self.assertEqual(product.status, Product.STATUS_SUBMITTED)
        self.assertIsNotNone(product.submitted_at)
        self.assertTrue(response.data["image_url"])
        self.assertEqual(self.seller_points(seller), 200 - PointService.get_product_creation_cost())
        self.assertFalse(Product.objects.public().filter(pk=product.pk).exists())

        detail = self.as_user(self.sales).get(f"/api/onboarding/sellers/{seller.pk}/").data
        self.assertEqual(detail["points_balance"], self.seller_points(seller))
        self.assertEqual([p["id"] for p in detail["shops"][0]["products"]], [product.pk])

    def test_a_limited_shop_owner_gets_one_shop(self):
        payload = seller_payload("limited", phone="01712345678")
        payload["seller_type"] = SellerProfile.TYPE_LIMITED_SHOP_OWNER
        seller = SellerProfile.objects.get(
            pk=self.as_user(self.sales).post("/api/onboarding/sellers/", payload, format="json").data["id"]
        )
        self.assertEqual(self.add_shop(seller).status_code, status.HTTP_201_CREATED)
        response = self.add_shop(seller, name="Second")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("1 shop", response.data["detail"])

    def test_the_sellers_points_pay_for_products(self):
        # Starting points enough for exactly one product (the 100-point minimum sale applies).
        ProductCreationCost.objects.update_or_create(pk=1, defaults={"required_points": 100})
        OnboardingSettings.objects.create(starting_points=100, tokens_per_seller=51)
        seller = self.onboard()
        shop = Shop.objects.get(pk=self.add_shop(seller).data["id"])
        self.assertEqual(self.add_product(shop).status_code, status.HTTP_201_CREATED)

        response = self.add_product(shop, name="Oil 1L")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["available_points"], 0)

    def test_a_rejected_seller_gets_nothing_more(self):
        seller = self.onboard()
        shop = Shop.objects.get(pk=self.add_shop(seller).data["id"])
        self.as_user(self.admin).post(f"/api/onboarding/review/{seller.pk}/reject/", {"reason": "Fake shop"})
        self.assertEqual(self.add_shop(seller, name="Again").status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.add_product(shop).status_code, status.HTTP_400_BAD_REQUEST)

    def test_after_approval_new_products_go_through_review(self):
        seller = self.onboard()
        shop = Shop.objects.get(pk=self.add_shop(seller).data["id"])
        self.as_user(self.admin).post(f"/api/onboarding/review/{seller.pk}/approve/")

        response = self.add_product(shop, name="Sugar 1kg")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["status"], Product.STATUS_SUBMITTED)


class ApprovalTests(OnboardingTestCase):
    def build(self):
        seller = self.onboard()
        shop = Shop.objects.get(pk=self.add_shop(seller).data["id"])
        products = [Product.objects.get(pk=self.add_product(shop, name=name).data["id"]) for name in ("Rice", "Dal")]
        return seller, shop, products

    def test_one_approval_puts_the_seller_shop_and_products_live(self):
        seller, shop, products = self.build()

        response = self.as_user(self.admin).post(f"/api/onboarding/review/{seller.pk}/approve/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data["shops_approved"], response.data["products_published"]), (1, 2))

        seller.refresh_from_db()
        shop.refresh_from_db()
        self.assertEqual(seller.status, SellerProfile.STATUS_ACTIVE)
        self.assertEqual(shop.status, Shop.STATUS_ACTIVE)
        self.assertEqual(
            set(Product.objects.public().values_list("pk", flat=True)), {product.pk for product in products}
        )
        self.assertEqual(seller.onboarding.approved_by, self.admin)
        for action in ("ADMIN_SELLER_APPROVE", "ADMIN_SHOP_APPROVE", "ADMIN_PRODUCT_PUBLISH", "SELLER_ONBOARDING_APPROVED"):
            with self.subTest(action=action):
                self.assertTrue(AuditLog.objects.filter(action=action, actor=self.admin).exists())

    def test_a_product_rejected_on_its_own_stays_rejected(self):
        seller, _shop, (kept, rejected) = self.build()
        rejected.status = Product.STATUS_REJECTED
        rejected.rejection_reason = "Blurry photo"
        rejected.save()

        self.as_user(self.admin).post(f"/api/onboarding/review/{seller.pk}/approve/")
        self.assertEqual(list(Product.objects.public().values_list("pk", flat=True)), [kept.pk])
        rejected.refresh_from_db()
        self.assertEqual(rejected.status, Product.STATUS_REJECTED)

    def test_approval_needs_every_approval_permission(self):
        seller, _shop, _products = self.build()
        for url in ("/api/onboarding/review/", f"/api/onboarding/review/{seller.pk}/"):
            self.assertEqual(self.as_user(self.sales_manager).get(url).status_code, status.HTTP_403_FORBIDDEN)
        for user in (self.sales_manager, self.sales):
            response = self.as_user(user).post(f"/api/onboarding/review/{seller.pk}/approve/")
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        seller.refresh_from_db()
        self.assertEqual(seller.status, SellerProfile.STATUS_PENDING)

    def test_only_a_waiting_seller_is_approved(self):
        seller, _shop, _products = self.build()
        self.assertEqual(self.as_user(self.admin).post(f"/api/onboarding/review/{seller.pk}/approve/").status_code, 200)
        response = self.as_user(self.admin).post(f"/api/onboarding/review/{seller.pk}/approve/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_the_queue_lists_waiting_onboardings(self):
        waiting = self.onboard("waiting", phone="01712345678")
        approved = self.onboard("approved", phone="01812345678")
        self.as_user(self.admin).post(f"/api/onboarding/review/{approved.pk}/approve/")

        rows = self.as_user(self.admin).get("/api/onboarding/review/").data["results"]
        self.assertEqual([row["id"] for row in rows], [waiting.pk])
        self.assertEqual(rows[0]["onboarded_by"], "sales")


class RejectionTests(OnboardingTestCase):
    def build(self):
        seller = self.onboard()
        shop = Shop.objects.get(pk=self.add_shop(seller).data["id"])
        self.add_product(shop)
        return seller

    def test_rejecting_returns_the_points_and_takes_back_the_tokens(self):
        seller = self.build()
        self.assertEqual(self.staff_points(self.sales), 300)

        response = self.as_user(self.admin).post(f"/api/onboarding/review/{seller.pk}/reject/", {"reason": "Fake shop"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        seller.refresh_from_db()
        self.assertEqual(seller.status, SellerProfile.STATUS_REJECTED)
        # The product fee came back to the seller first, so all 200 went home.
        self.assertEqual(self.staff_points(self.sales), 500)
        self.assertEqual(self.seller_points(seller), 0)
        self.assertEqual(self.tokens(self.sales), 0)
        onboarding = seller.onboarding
        self.assertEqual((onboarding.points_returned, onboarding.tokens_taken_back), (200, 51))
        self.assertIsNotNone(onboarding.reversed_at)
        self.assertTrue(
            TokenTransaction.objects.filter(transaction_type=TokenTransaction.TYPE_TAKEN_BACK, seller=seller).exists()
        )
        self.assertTrue(AuditLog.objects.filter(action="SELLER_ONBOARDING_REVERSED", actor=self.admin).exists())

    def test_the_console_reject_reverses_too(self):
        seller = self.build()
        response = self.as_user(self.sales_manager).post(
            f"/api/admin/sellers/{seller.pk}/status/", {"action": "reject", "reason": "Duplicate"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(self.staff_points(self.sales), 500)
        self.assertEqual(self.tokens(self.sales), 0)

    def test_points_from_elsewhere_stay_with_the_seller(self):
        seller = self.build()
        PointService.adjust_points(seller, 100, "CREDIT", "Promotion", actor=self.root)

        self.as_user(self.admin).post(f"/api/onboarding/review/{seller.pk}/reject/", {"reason": "Fake shop"})
        self.assertEqual(self.staff_points(self.sales), 500)
        self.assertEqual(self.seller_points(seller), 100)

    def test_rewards_are_reversed_once(self):
        seller = self.build()
        reject_seller(SellerProfile.objects.get(pk=seller.pk), self.admin, "Fake shop")
        self.assertIsNone(OnboardingService.reverse_rewards(seller, self.admin))
        self.assertEqual(self.staff_points(self.sales), 500)
        self.assertEqual(
            PointTransaction.objects.filter(seller=seller, transaction_type=PointTransaction.TYPE_ADMIN_DEBIT).count(), 1
        )

    def test_a_seller_not_onboarded_is_rejected_as_before(self):
        seller = SellerProfile.objects.create(
            user=User.objects.create_user(username="plain", password=PASSWORD), business_name="Plain"
        )
        reject_seller(seller, self.admin, "Incomplete")
        self.assertEqual(self.staff_points(self.sales), 500)

    def test_a_reason_is_required(self):
        seller = self.build()
        response = self.as_user(self.admin).post(f"/api/onboarding/review/{seller.pk}/reject/", {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        seller.refresh_from_db()
        self.assertEqual(seller.status, SellerProfile.STATUS_PENDING)


class TokenHistoryTests(OnboardingTestCase):
    def test_the_history_shows_each_movement(self):
        first = self.onboard("first", phone="01712345678")
        self.onboard("second", phone="01812345678")
        self.as_user(self.admin).post(f"/api/onboarding/review/{first.pk}/reject/", {"reason": "Closed down"})

        data = self.as_user(self.sales).get("/api/onboarding/tokens/").data
        self.assertEqual(data["balance"], 51)
        self.assertEqual(
            [(row["transaction_type"], row["amount"], row["seller_name"]) for row in data["results"]],
            [("TAKEN_BACK", 51, "first Store"), ("EARNED", 51, "second Store"), ("EARNED", 51, "first Store")],
        )

    def test_no_wallet_yet_reads_as_zero(self):
        data = self.as_user(self.other_sales).get("/api/onboarding/tokens/").data
        self.assertEqual((data["balance"], data["results"]), (0, []))


class PointSaleTests(OnboardingTestCase):
    """An onboarder sells points to their own approved sellers (decided 2026-11-01)."""

    def approved(self, tag="corner", phone="01712345678"):
        seller = self.onboard(tag, phone=phone)
        self.as_user(self.admin).post(f"/api/onboarding/review/{seller.pk}/approve/")
        seller.refresh_from_db()
        return seller

    def sell(self, seller, amount, user=None):
        return self.as_user(user or self.sales).post(
            f"/api/onboarding/sellers/{seller.pk}/points/", {"amount": amount}, format="json"
        )

    def test_an_onboarder_sells_points_from_their_wallet(self):
        seller = self.approved()
        response = self.sell(seller, 100)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data["points_balance"], response.data["your_points"]), (300, 200))
        self.assertEqual(self.seller_points(seller), 300)
        self.assertEqual(self.staff_points(self.sales), 200)
        entry = AuditLog.objects.get(action="ONBOARDING_POINTS_SOLD")
        self.assertEqual((entry.actor, entry.seller, entry.metadata["amount"]), (self.sales, seller, 100))
        txn = PointTransaction.objects.get(seller=seller, reference_type="POINT_SALE")
        self.assertEqual(txn.reason, "Points sold by sales")

    def test_a_sale_moves_the_date_of_every_point_the_seller_holds(self):
        seller = self.approved()
        response = self.sell(seller, 100)
        dates = set(seller.point_wallet.lots.filter(remaining__gt=0).values_list("expires_at", flat=True))
        self.assertEqual(len(dates), 1)
        self.assertEqual(dates.pop(), response.data["points_expire_at"])

    def test_fewer_than_the_minimum_is_refused(self):
        seller = self.approved()
        response = self.sell(seller, 99)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("at least 100", response.data["detail"])
        self.assertEqual(self.staff_points(self.sales), 300)

    def test_a_seller_awaiting_approval_cannot_buy(self):
        seller = self.onboard()
        response = self.sell(seller, 100)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("only to approved sellers", response.data["detail"])
        self.assertEqual(self.seller_points(seller), 200)

    def test_more_than_the_wallet_holds_is_refused(self):
        seller = self.approved()
        response = self.sell(seller, 301)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["available_points"], 300)

    def test_another_onboarders_seller_is_not_found(self):
        seller = self.approved()
        self.assertEqual(self.sell(seller, 100, user=self.other_sales).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.sell(seller, 100, user=self.admin).status_code, status.HTTP_403_FORBIDDEN)

    def test_the_summary_names_the_minimum(self):
        data = self.as_user(self.sales).get("/api/onboarding/me/").data
        self.assertEqual(data["minimum_point_sale"], 100)

    def test_starting_points_obey_the_minimum(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            OnboardingSettings(starting_points=50).full_clean()
        OnboardingSettings(starting_points=0).full_clean()
        OnboardingSettings(starting_points=100).full_clean()

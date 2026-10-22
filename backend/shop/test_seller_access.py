"""
TASK-005 / BUG-004: sellers are admitted to the Seller Center by seller
status, hold no staff role, and so are kept out of the staff Console.
"""

import importlib
from decimal import Decimal
from io import StringIO

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from points.models import PointTransaction
from points.services import PointService
from rbac.models import Role, UserRole
from rbac.services import assign_user_role, get_user_role_codes
from sellers.models import SellerProfile
from shop.models import Category, Product
from shops.fields import Point
from shops.models import Shop

User = get_user_model()

# Every parameter-free staff read a seller must not reach.
STAFF_READ_URLS = [
    "/api/admin/users/",
    "/api/admin/roles/",
    "/api/admin/permissions/",
    "/api/admin/sellers/",
    "/api/admin/shops/",
    "/api/admin/products/",
    "/api/admin/categories/",
    "/api/admin/customers/",
    "/api/admin/metrics/",
    "/api/admin/audit-logs/",
    "/api/sellers/",
    "/api/staff/orders/",
    "/api/staff/payments/",
]

leave_sales_team = importlib.import_module("sellers.migrations.0003_sellers_leave_sales_team")


class SellerWithoutRoleTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.category = Category.objects.create(name="Access Gadgets", slug="access-gadgets")

        cls.user = User.objects.create_user(username="roleless_seller", password="Roleless-Seller-1")
        # The CUSTOMER role is the most a seller account holds after TASK-005.
        assign_user_role(cls.user, Role.ROLE_CUSTOMER)
        cls.seller = SellerProfile.objects.create(
            user=cls.user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Roleless Goods",
            status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop = Shop.objects.create(
            owner=cls.seller,
            name="Roleless Shop",
            slug="roleless-shop",
            status=Shop.STATUS_ACTIVE,
            location=Point(90.4125, 23.8103),
        )
        PointService.credit(
            seller=cls.seller, amount=50, transaction_type=PointTransaction.TYPE_BONUS, reason="Initial grant"
        )
        cls.product = Product.objects.create(
            shop=cls.shop, category=cls.category, name="Existing Lamp", slug="existing-lamp",
            price=Decimal("120.00"), stock=5,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_seller_center_works_without_any_staff_code(self):
        self.assertEqual(get_user_role_codes(self.user), {Role.ROLE_CUSTOMER})

        res = self.client.post(
            "/api/products/mine/",
            {"name": "New Desk", "category_id": self.category.id, "shop_id": self.shop.id,
             "description": "Made by a role-less seller", "price": "250.00"},
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)

        res = self.client.patch(f"/api/products/mine/{self.product.id}/", {"description": "Edited"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)

        self.assertEqual(self.client.get("/api/seller/orders/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/seller/inventory/").status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.get(f"/api/seller/inventory/{self.product.id}/").status_code, status.HTTP_200_OK
        )
        res = self.client.post(
            f"/api/seller/inventory/{self.product.id}/adjust/", {"quantity": 2, "reason": "restock"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)

    def test_product_delete_still_needs_products_delete(self):
        res = self.client.delete(f"/api/products/mine/{self.product.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

    def test_seller_is_kept_out_of_every_staff_read(self):
        for url in STAFF_READ_URLS:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN)

    def test_suspended_seller_loses_inventory_access(self):
        self.seller.status = SellerProfile.STATUS_SUSPENDED
        self.seller.suspension_reason = "Access test"
        self.seller.save(update_fields=["status", "suspension_reason"])
        self.assertEqual(self.client.get("/api/seller/inventory/").status_code, status.HTTP_403_FORBIDDEN)
        res = self.client.post(f"/api/seller/inventory/{self.product.id}/adjust/", {"quantity": 1}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_keep_their_console_reads(self):
        manager = User.objects.create_user(username="access_sales_manager", password="Sales-Manager-1")
        assign_user_role(manager, Role.ROLE_SALES_MANAGER)
        self.client.force_authenticate(user=manager)
        for url in ("/api/admin/sellers/", "/api/admin/products/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, status.HTTP_200_OK)


class LeaveSalesTeamMigrationTests(APITestCase):
    """sellers/0003 switches SALES_TEAM off for plain seller accounts only."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())

    def make(self, username, roles=(), seller=True, **flags):
        user = User.objects.create_user(username=username, password="Migration-Test-1", **flags)
        for code in roles:
            assign_user_role(user, code)
        if seller:
            SellerProfile.objects.create(user=user, business_name=username, status=SellerProfile.STATUS_ACTIVE)
        return user

    def sales_team_active(self, user):
        return UserRole.objects.get(user=user, role__code=Role.ROLE_SALES_TEAM).is_active

    def test_only_plain_sellers_lose_sales_team(self):
        plain = self.make("mig_plain", [Role.ROLE_SALES_TEAM])
        shopper = self.make("mig_shopper", [Role.ROLE_SALES_TEAM, Role.ROLE_CUSTOMER])
        also_support = self.make("mig_support", [Role.ROLE_SALES_TEAM, Role.ROLE_SUPPORT_TEAM])
        django_staff = self.make("mig_staff_flag", [Role.ROLE_SALES_TEAM], is_staff=True)
        not_a_seller = self.make("mig_sales_staff", [Role.ROLE_SALES_TEAM], seller=False)

        leave_sales_team.deactivate_sales_team_for_sellers(apps, None)

        self.assertFalse(self.sales_team_active(plain))
        self.assertFalse(self.sales_team_active(shopper))
        self.assertIn(Role.ROLE_CUSTOMER, get_user_role_codes(shopper))
        self.assertTrue(self.sales_team_active(also_support))
        self.assertTrue(self.sales_team_active(django_staff))
        self.assertTrue(self.sales_team_active(not_a_seller))

"""
TASK-049 backend fixes:
- BUG-107: a category PATCH audits every field it can change, slug included.
- BUG-108: a category with products is never deleted, and products are
  protected from a cascade.
- BUG-115/116: the Console customer directory lists CUSTOMER-role accounts
  only, and finds them by first or last name too.
"""

from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from customers.models import CustomerProfile
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shop.models import Category, Product
from shops.models import Shop

User = get_user_model()


class CategoryAdminApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(username="cat_staff", email="cs@example.com", password="Cat-Staff-1")
        seller = SellerProfile.objects.create(
            user=User.objects.create_user(username="cat_seller", password="Cat-Seller-1"),
            business_name="Cat Seller", status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop = Shop.objects.create(owner=seller, name="Cat Shop", slug="cat-shop", status=Shop.STATUS_ACTIVE)

    def setUp(self):
        self.client.force_authenticate(user=self.staff)

    def test_a_slug_change_is_in_the_audit_row(self):
        category = Category.objects.create(name="Lamps", slug="lamps", icon="lightbulb")
        res = self.client.patch(f"/api/admin/categories/{category.pk}/", {"slug": "lighting"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        row = AuditLog.objects.get(action="ADMIN_CATEGORY_UPDATED", target_id=str(category.pk))
        self.assertEqual(row.metadata["previous_state"]["slug"], "lamps")
        self.assertEqual(row.metadata["new_state"]["slug"], "lighting")
        self.assertEqual(row.metadata["new_state"]["icon"], "lightbulb")

    def test_a_category_in_use_is_never_deleted(self):
        category = Category.objects.create(name="Kettles", slug="kettles")
        product = Product.objects.create(
            name="Kettle", slug="kettle", category=category, shop=self.shop, price=Decimal("10.00"),
            description="A kettle.",
        )
        res = self.client.delete(f"/api/admin/categories/{category.pk}/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())
        # Not even a direct delete takes the products along now.
        with self.assertRaises(ProtectedError):
            category.delete()

    def test_an_unused_category_is_deleted(self):
        category = Category.objects.create(name="Empty", slug="empty")
        self.assertEqual(self.client.delete(f"/api/admin/categories/{category.pk}/").status_code, status.HTTP_200_OK)
        self.assertFalse(Category.objects.filter(pk=category.pk).exists())


class CustomerDirectoryTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.staff = User.objects.create_superuser(username="dir_root", email="dr@example.com", password="Dir-Root-1")
        cls.shopper = User.objects.create_user(
            username="dir_shopper", password="Dir-Shop-1", first_name="Rahim", last_name="Uddin"
        )
        assign_user_role(cls.shopper, Role.ROLE_CUSTOMER)
        cls.shopper_profile = CustomerProfile.objects.create(user=cls.shopper, display_name="rahim99")
        # Reading their own profile gave the staff account a row as well.
        cls.staff_profile = CustomerProfile.objects.create(user=cls.staff)

    def setUp(self):
        self.client.force_authenticate(user=self.staff)

    def usernames(self, **params):
        res = self.client.get("/api/admin/customers/", params)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return [row["username"] for row in res.data["results"]]

    def test_only_customer_role_accounts_are_listed(self):
        self.assertEqual(self.usernames(), ["dir_shopper"])
        self.assertEqual(self.client.get(f"/api/admin/customers/{self.staff_profile.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/admin/customers/{self.shopper_profile.pk}/").status_code, 200)

    def test_customers_are_found_by_first_or_last_name(self):
        self.assertEqual(self.usernames(search="Uddin"), ["dir_shopper"])
        self.assertEqual(self.usernames(search="rahim"), ["dir_shopper"])

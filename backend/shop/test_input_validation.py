"""
TASK-031: bad input is a 400, never an accepted junk value or a 500.

- BUG-040: usernames follow Django's rules at registration and in the Console.
- BUG-060: profile photos, product images and shop logos/covers must be JPEG,
  PNG or WebP within a size cap; phone and date of birth follow the admin
  profile form's rules on the API too.
- BUG-066: malformed id/date/assigned query params and oversized stock or
  point amounts are 400s; audit-log date filters select Asia/Dhaka days.
"""

import shutil
import tempfile
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from io import BytesIO, StringIO
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from PIL import Image
from rest_framework import serializers, status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from config import validators
from customers.models import CustomerProfile
from points.models import SellerWallet
from rbac.models import Role
from rbac.serializers import create_login_account
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shop.models import Category, Product, ProductInventory
from shops.models import Shop

User = get_user_model()

TOO_BIG = 10 ** 10


def image_upload(name="pic.png", image_format="PNG"):
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (200, 120, 40)).save(buffer, image_format)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{image_format.lower()}")


class UsernameTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.superuser = User.objects.create_superuser(username="iv_super", email="iv@example.com", password="Iv-Super-123")

    def test_registration_refuses_a_username_django_would_refuse(self):
        response = self.client.post("/api/auth/register/", {
            "username": "john doe", "email": "john@example.com",
            "password": "Strong-Pass-482", "password_confirm": "Strong-Pass-482",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)
        self.assertFalse(User.objects.filter(email="john@example.com").exists())

    def test_console_account_creation_refuses_it_too(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post("/api/admin/users/", {
            "username": "jane doe", "email": "jane@example.com", "reason": "New staff member",
            "password": "Strong-Pass-482", "password_confirm": "Strong-Pass-482",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

    def test_a_username_taken_after_the_duplicate_check_is_a_400(self):
        User.objects.create_user(username="iv_taken", password="Iv-Taken-123")
        with self.assertRaises(serializers.ValidationError) as caught:
            create_login_account(username="IV_TAKEN", password="Iv-Taken-456")
        self.assertIn("username", caught.exception.detail)


class UploadAndProfileTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media = tempfile.mkdtemp(prefix="iv-media-")
        cls.media_override = override_settings(MEDIA_ROOT=cls.media)
        cls.media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.media_override.disable()
        shutil.rmtree(cls.media, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.customer = User.objects.create_user(username="iv_customer", password="Iv-Customer-123")
        assign_user_role(cls.customer, Role.ROLE_CUSTOMER)
        CustomerProfile.objects.create(user=cls.customer)
        cls.seller_user = User.objects.create_user(username="iv_seller", password="Iv-Seller-123")
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user, business_name="IV Seller", status=SellerProfile.STATUS_ACTIVE,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
        )
        SellerWallet.objects.create(seller=cls.seller, balance=1000)
        cls.shop = Shop.objects.create(owner=cls.seller, name="IV Shop", slug="iv-shop", status=Shop.STATUS_ACTIVE)
        cls.category = Category.objects.create(name="IV Category", slug="iv-category", is_active=True)
        cls.product = Product.objects.create(
            name="IV Product", slug="iv-product", category=cls.category, shop=cls.shop,
            description="An input-validation product.", price=Decimal("100.00"), stock=5, status=Product.STATUS_DRAFT, is_active=True,
        )
        ProductInventory.objects.create(product=cls.product, available_quantity=5)

    def patch_profile(self, data):
        self.client.force_authenticate(user=self.customer)
        return self.client.patch("/api/profile/me/", data, format="multipart")

    def as_seller(self):
        self.client.force_authenticate(user=User.objects.get(pk=self.seller_user.pk))

    def test_profile_photo_must_be_a_web_image_within_2_mb(self):
        response = self.patch_profile({"avatar": image_upload("me.gif", "GIF")})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("avatar", response.data)
        with mock.patch.object(validators, "AVATAR_MAX_BYTES", 10):
            response = self.patch_profile({"avatar": image_upload()})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CustomerProfile.objects.get(user=self.customer).avatar)

        self.assertEqual(self.patch_profile({"avatar": image_upload()}).status_code, status.HTTP_200_OK)

    def test_profile_phone_and_date_of_birth_follow_the_admin_form(self):
        for data in ({"date_of_birth": "2099-01-01"}, {"date_of_birth": "1850-05-05"}, {"phone": "call me"}):
            with self.subTest(data=data):
                response = self.patch_profile(data)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(next(iter(data)), response.data)
        response = self.patch_profile({"phone": " +880  1711-000000 ", "date_of_birth": "1990-05-05"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(CustomerProfile.objects.get(user=self.customer).phone, "+880 1711-000000")

    def test_product_images_must_be_web_images_within_5_mb(self):
        self.as_seller()
        response = self.client.post("/api/products/mine/", {
            "name": "IV New", "category_id": self.category.pk, "shop_id": self.shop.pk,
            "description": "A product", "price": "50.00", "image": image_upload("p.gif", "GIF"),
        }, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("image", response.data)

        with mock.patch.object(validators, "CATALOG_IMAGE_MAX_BYTES", 10):
            response = self.client.patch(
                f"/api/products/mine/{self.product.pk}/", {"image": image_upload()}, format="multipart"
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("image", response.data)

    def test_shop_logo_and_cover_must_be_web_images(self):
        self.as_seller()
        for field in ("logo", "cover_image"):
            with self.subTest(field=field):
                response = self.client.patch(
                    f"/api/shops/mine/{self.shop.pk}/update/", {field: image_upload("s.tiff", "TIFF")}, format="multipart"
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(field, response.data)

    def test_stock_amounts_are_bounded(self):
        self.as_seller()
        response = self.client.patch(
            f"/api/products/mine/{self.product.pk}/", {"stock": TOO_BIG, "expected_stock": 5}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("stock", response.data)
        response = self.client.post(
            f"/api/seller/inventory/{self.product.pk}/adjust/", {"quantity": TOO_BIG, "reason": "Typo"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("quantity", response.data)


class QueryParamTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.superuser = User.objects.create_superuser(username="iv_qp_super", email="qp@example.com", password="Iv-Qp-123")
        cls.seller_user = User.objects.create_user(username="iv_qp_seller", password="Iv-Qp-Seller-123")
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user, business_name="IV QP Seller", status=SellerProfile.STATUS_ACTIVE,
        )
        SellerWallet.objects.create(seller=cls.seller, balance=10)

    def get_400(self, url, params, field, user=None):
        self.client.force_authenticate(user=user or self.superuser)
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, (url, params, response.data))
        self.assertIn(field, response.data)

    def test_malformed_ids_dates_and_assignees_are_400s(self):
        cases = [
            ("/api/admin/products/", {"category": "abc"}, "category"),
            ("/api/admin/products/", {"shop": "abc"}, "shop"),
            ("/api/admin/audit-logs/", {"start_date": "2026-13-40"}, "start_date"),
            ("/api/admin/audit-logs/", {"end_date": "yesterday"}, "end_date"),
            ("/api/admin/audit-logs/", {"seller_id": "²"}, "seller_id"),
            ("/api/staff/orders/", {"shop_id": "abc"}, "shop_id"),
            ("/api/staff/orders/", {"start_date": "2026-02-30"}, "start_date"),
        ]
        for url, params, field in cases:
            with self.subTest(url=url, params=params):
                self.get_400(url, params, field)
        self.get_400("/api/products/mine/", {"shop_id": "abc"}, "shop_id",
                     user=User.objects.get(pk=self.seller_user.pk))

        self.client.force_authenticate(user=self.superuser)
        response = self.client.get("/api/support/staff/tickets/", {"assigned": "²"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_point_amounts_are_bounded(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(f"/api/points/sellers/{self.seller.pk}/adjust/", {
            "action": "CREDIT", "amount": TOO_BIG, "reason": "Typo in the amount",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("amount", response.data)
        self.assertEqual(SellerWallet.objects.get(seller=self.seller).balance, 10)

    def test_audit_log_days_are_dhaka_days(self):
        self.client.force_authenticate(user=self.superuser)
        row = AuditLog.objects.create(action="IV_DHAKA_DAY", target_type="Test", target_id="1")
        # 20:30 UTC on 23 October is 02:30 on 24 October in Dhaka (UTC+6).
        AuditLog.objects.filter(pk=row.pk).update(created_at=datetime(2026, 10, 23, 20, 30, tzinfo=dt_timezone.utc))

        def found(day):
            response = self.client.get("/api/admin/audit-logs/", {"start_date": day, "end_date": day, "search": "IV_DHAKA_DAY"})
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            return [r["id"] for r in response.data["results"]]

        self.assertEqual(settings.BUSINESS_TIME_ZONE, "Asia/Dhaka")
        self.assertEqual(found("2026-10-24"), [row.pk])
        self.assertEqual(found("2026-10-23"), [])

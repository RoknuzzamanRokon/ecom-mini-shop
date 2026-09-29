from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.models import Shop
from .models import Category, Product
from .services import ProductModerationError, ProductService

User = get_user_model()

ACTIONS = ("approve", "reject", "publish", "unpublish")


class ProductModerationFixtures:
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.staff = User.objects.create_user(
            username="pm_staff", email="pm_staff@minishop.com", password="StaffPassword123!", is_staff=True
        )
        assign_user_role(cls.staff, Role.ROLE_ADMINISTRATOR)
        seller_user = User.objects.create_user(
            username="pm_seller", email="pm_seller@minishop.com", password="SellerPassword123!"
        )
        cls.seller = SellerProfile.objects.create(
            user=seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Moderation Seller",
            status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop = Shop.objects.create(owner=cls.seller, name="Moderation Shop", status=Shop.STATUS_ACTIVE)
        cls.category = Category.objects.create(name="Moderation", slug="moderation")

    def setUp(self):
        self.product = Product.objects.create(
            name="Moderated Kettle",
            category=self.category,
            shop=self.shop,
            description="A kettle",
            price=Decimal("1200.00"),
            status=Product.STATUS_DRAFT,
        )

    def audit_rows(self):
        return AuditLog.objects.filter(action__startswith="ADMIN_PRODUCT_", target_id=str(self.product.id))


class ProductServiceModerationTests(ProductModerationFixtures, TestCase):
    """ProductService.approve / reject / publish / unpublish carry the Console's rules."""

    def moderate(self, action, reason=""):
        return getattr(ProductService, action)(self.product, self.staff, reason=reason, ip_address="10.0.0.9")

    def test_approve_marks_reviewed_and_clears_the_rejection_reason(self):
        self.product.status = Product.STATUS_REJECTED
        self.product.rejection_reason = "Blurry photo"
        self.product.save()

        self.moderate("approve")

        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_APPROVED)
        self.assertEqual(self.product.rejection_reason, "")
        self.assertEqual(self.product.reviewed_by, self.staff)
        self.assertIsNotNone(self.product.reviewed_at)

    def test_reject_stores_the_trimmed_reason(self):
        self.moderate("reject", reason="  Listing violates policy ")
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_REJECTED)
        self.assertEqual(self.product.rejection_reason, "Listing violates policy")
        self.assertEqual(self.product.reviewed_by, self.staff)
        self.assertIsNotNone(self.product.reviewed_at)

    def test_reject_without_a_reason_is_refused(self):
        for reason in ("", "   "):
            with self.subTest(reason=reason):
                with self.assertRaises(ValidationError):
                    self.moderate("reject", reason=reason)
                self.product.refresh_from_db()
                self.assertEqual(self.product.status, Product.STATUS_DRAFT)
                self.assertFalse(self.audit_rows().exists())

    def test_publish_activates_the_product(self):
        self.product.is_active = False
        self.product.save()
        self.moderate("publish")
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_PUBLISHED)
        self.assertTrue(self.product.is_active)

    def test_publish_is_refused_unless_the_shop_is_live(self):
        for shop_status in (Shop.STATUS_DRAFT, Shop.STATUS_PENDING, Shop.STATUS_REJECTED, Shop.STATUS_SUSPENDED):
            with self.subTest(shop_status=shop_status):
                Shop.objects.filter(pk=self.shop.pk).update(status=shop_status)
                self.product.refresh_from_db()
                with self.assertRaisesMessage(ProductModerationError, "unapproved or suspended shop"):
                    self.moderate("publish")
                self.product.refresh_from_db()
                self.assertEqual(self.product.status, Product.STATUS_DRAFT)
                self.assertFalse(self.audit_rows().exists())

        Shop.objects.filter(pk=self.shop.pk).update(status=Shop.STATUS_APPROVED)
        self.product.refresh_from_db()
        self.moderate("publish")
        self.assertEqual(self.product.status, Product.STATUS_PUBLISHED)

    def test_publish_is_refused_without_a_shop(self):
        Product.objects.filter(pk=self.product.pk).update(shop=None)
        self.product.refresh_from_db()
        with self.assertRaisesMessage(ProductModerationError, "unapproved or suspended shop"):
            self.moderate("publish")
        self.assertFalse(self.audit_rows().exists())

    def test_publish_is_refused_for_a_seller_who_is_not_operational(self):
        for seller_status in (SellerProfile.STATUS_PENDING, SellerProfile.STATUS_SUSPENDED):
            with self.subTest(seller_status=seller_status):
                SellerProfile.objects.filter(pk=self.seller.pk).update(status=seller_status)
                self.product.refresh_from_db()
                with self.assertRaisesMessage(ProductModerationError, "inoperational seller"):
                    self.moderate("publish")
                self.product.refresh_from_db()
                self.assertEqual(self.product.status, Product.STATUS_DRAFT)
                self.assertFalse(self.audit_rows().exists())

    def test_unpublish_sets_unpublished(self):
        self.product.status = Product.STATUS_PUBLISHED
        self.product.save()
        self.moderate("unpublish")
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_UNPUBLISHED)

    def test_every_action_applies_from_every_status(self):
        """There is no source-status rule, as there was none in the Console."""
        targets = {
            "approve": Product.STATUS_APPROVED,
            "reject": Product.STATUS_REJECTED,
            "publish": Product.STATUS_PUBLISHED,
            "unpublish": Product.STATUS_UNPUBLISHED,
        }
        for source, _label in Product.STATUS_CHOICES:
            for action in ACTIONS:
                with self.subTest(source=source, action=action):
                    Product.objects.filter(pk=self.product.pk).update(
                        status=source, rejection_reason="Earlier" if source == Product.STATUS_REJECTED else ""
                    )
                    self.product.refresh_from_db()
                    self.moderate(action, reason="Matrix check")
                    self.assertEqual(self.product.status, targets[action])

    def test_each_action_writes_exactly_one_audit_row(self):
        for action in ACTIONS:
            with self.subTest(action=action):
                AuditLog.objects.all().delete()
                previous = self.product.status
                self.moderate(action, reason="Audit check")
                entry = self.audit_rows().get()
                self.assertEqual(entry.action, f"ADMIN_PRODUCT_{action.upper()}")
                self.assertEqual(entry.actor, self.staff)
                self.assertEqual(entry.shop, self.shop)
                self.assertEqual(entry.seller, self.seller)
                self.assertEqual(entry.ip_address, "10.0.0.9")
                self.assertEqual(entry.metadata["reason"], "Audit check")
                self.assertEqual(entry.metadata["previous_state"], {"status": previous})
                self.assertEqual(entry.metadata["new_state"], {"status": self.product.status})

    def test_default_audit_reason_names_the_action(self):
        self.moderate("approve")
        self.assertEqual(self.audit_rows().get().metadata["reason"], "Product approved by staff")


class AdminProductStatusDelegationTests(ProductModerationFixtures, APITestCase):
    """POST /api/admin/products/<pk>/status/ delegates to ProductService."""

    def post(self, action, reason="Console check"):
        self.client.force_authenticate(user=self.staff)
        return self.client.post(
            f"/api/admin/products/{self.product.id}/status/",
            data={"action": action, "reason": reason},
            format="json",
        )

    def test_each_action_writes_exactly_one_audit_row(self):
        for action in ACTIONS:
            with self.subTest(action=action):
                AuditLog.objects.all().delete()
                res = self.post(action)
                self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
                self.assertEqual(self.audit_rows().count(), 1)
                self.assertEqual(self.audit_rows().get().action, f"ADMIN_PRODUCT_{action.upper()}")

    def test_publish_refusal_is_a_400_message_list(self):
        Shop.objects.filter(pk=self.shop.pk).update(status=Shop.STATUS_SUSPENDED)
        res = self.post("publish")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        # A bare list of messages, which the Console shows as-is.
        self.assertEqual(
            [str(message) for message in res.data],
            ["Cannot publish product belonging to an unapproved or suspended shop."],
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_DRAFT)
        self.assertFalse(self.audit_rows().exists())

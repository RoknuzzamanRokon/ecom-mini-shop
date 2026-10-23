"""
TASK-014 / BUG-011: a new product can go from DRAFT to PUBLISHED using only
the Seller Center and the Console (TASK-048 decision 2: the seller submits,
staff review and publish), with an audit row for each step.
"""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from points.models import PointTransaction
from points.services import PointService
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shop.models import Category, Product
from shops.fields import Point
from shops.models import Shop

User = get_user_model()


class ProductPublicationTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", verbosity=0)
        cls.category = Category.objects.create(name="Lamps", slug="pub-lamps")

        cls.seller_user = User.objects.create_user(username="pub_seller", password="Pub-Seller-123")
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Lamp House",
            status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop = Shop.objects.create(
            owner=cls.seller, name="Lamp House Shop", slug="pub-lamp-house",
            status=Shop.STATUS_ACTIVE, location=Point(90.4125, 23.8103),
        )
        PointService.credit(
            seller=cls.seller, amount=50, transaction_type=PointTransaction.TYPE_BONUS, reason="Test points",
        )

        cls.other_user = User.objects.create_user(username="pub_other", password="Pub-Other-123")
        cls.other_seller = SellerProfile.objects.create(
            user=cls.other_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Other House",
            status=SellerProfile.STATUS_ACTIVE,
        )

        cls.moderator = User.objects.create_user(username="pub_moderator", password="Pub-Moderator-123")
        assign_user_role(cls.moderator, Role.ROLE_OPERATION_MANAGER)

    def as_seller(self, user=None):
        # Freshly loaded, as a real request would be: the class-level object
        # keeps its seller profile cached from setUpTestData.
        self.client.force_authenticate(user=User.objects.get(pk=(user or self.seller_user).pk))

    def create_product(self):
        self.as_seller()
        response = self.client.post("/api/products/mine/", {
            "name": "Brass Desk Lamp", "category_id": self.category.pk, "shop_id": self.shop.pk,
            "description": "Warm light.", "price": "1500.00", "stock": 5,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["status"], Product.STATUS_DRAFT)
        return Product.objects.get(pk=response.data["id"])

    def submit(self, product, user=None):
        self.as_seller(user)
        return self.client.post(f"/api/products/mine/{product.pk}/submit/")

    def moderate(self, product, action, reason=""):
        self.client.force_authenticate(user=self.moderator)
        response = self.client.post(
            f"/api/admin/products/{product.pk}/status/", {"action": action, "reason": reason}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response

    def audit_actions(self, product):
        return list(
            AuditLog.objects.filter(target_type="Product", target_id=str(product.pk))
            .order_by("created_at", "pk")
            .values_list("action", flat=True)
        )

    def test_draft_to_published_through_the_seller_center_and_the_console(self):
        product = self.create_product()
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(f"/api/products/{product.slug}/").status_code, status.HTTP_404_NOT_FOUND)

        response = self.submit(product)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["status"], Product.STATUS_SUBMITTED)
        product.refresh_from_db()
        self.assertIsNotNone(product.submitted_at)

        self.moderate(product, "approve")
        self.moderate(product, "publish")

        product.refresh_from_db()
        self.assertEqual(product.status, Product.STATUS_PUBLISHED)
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get(f"/api/products/{product.slug}/").status_code, status.HTTP_200_OK)

        self.assertEqual(
            self.audit_actions(product),
            ["PRODUCT_CREATED", "PRODUCT_SUBMITTED", "ADMIN_PRODUCT_APPROVE", "ADMIN_PRODUCT_PUBLISH"],
        )
        submitted = AuditLog.objects.get(action="PRODUCT_SUBMITTED", target_id=str(product.pk))
        self.assertEqual(submitted.actor, self.seller_user)
        self.assertEqual(submitted.metadata["previous_state"]["status"], Product.STATUS_DRAFT)
        self.assertEqual(submitted.metadata["new_state"], {"status": Product.STATUS_SUBMITTED})

    def test_a_rejected_product_can_be_corrected_and_resubmitted(self):
        product = self.create_product()
        self.submit(product)
        self.moderate(product, "reject", reason="Photo is blurry.")

        response = self.submit(product)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        product.refresh_from_db()
        self.assertEqual(product.status, Product.STATUS_SUBMITTED)
        self.assertEqual(product.rejection_reason, "")
        resubmitted = AuditLog.objects.filter(action="PRODUCT_SUBMITTED", target_id=str(product.pk)).latest("pk")
        self.assertEqual(
            resubmitted.metadata["previous_state"],
            {"status": Product.STATUS_REJECTED, "rejection_reason": "Photo is blurry."},
        )

    def test_only_drafts_and_rejected_products_can_be_submitted(self):
        product = self.create_product()
        for current in (Product.STATUS_SUBMITTED, Product.STATUS_APPROVED,
                        Product.STATUS_PUBLISHED, Product.STATUS_UNPUBLISHED):
            with self.subTest(status=current):
                Product.objects.filter(pk=product.pk).update(status=current)
                response = self.submit(product)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                product.refresh_from_db()
                self.assertEqual(product.status, current)
        self.assertNotIn("PRODUCT_SUBMITTED", self.audit_actions(product))

    def test_another_seller_cannot_submit(self):
        product = self.create_product()
        response = self.submit(product, user=self.other_user)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        product.refresh_from_db()
        self.assertEqual(product.status, Product.STATUS_DRAFT)

    def test_a_suspended_seller_cannot_submit(self):
        product = self.create_product()
        SellerProfile.objects.filter(pk=self.seller.pk).update(
            status=SellerProfile.STATUS_SUSPENDED, suspension_reason="Review."
        )
        response = self.submit(product)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        product.refresh_from_db()
        self.assertEqual(product.status, Product.STATUS_DRAFT)

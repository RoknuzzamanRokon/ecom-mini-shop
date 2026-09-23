from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from audit.models import AuditLog
from customers.models import Review, ShopReview
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.models import Shop
from .models import Category, Product

User = get_user_model()


class BaseReviewModerationTestCase(TestCase):
    """
    One public product in one public shop. Customer A left a 1-star product
    review and a 1-star shop review (the "abusive" ones); customer B left 5 stars
    on both. Staff: SUPPORT_TEAM and ADMINISTRATOR hold reviews.moderate,
    SALES_TEAM does not.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        seller_user = User.objects.create_user(
            username="mod_seller", email="mod_seller@example.com", password="Password123!"
        )
        cls.seller = SellerProfile.objects.create(
            user=seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Moderation Test Co",
        )
        cls.shop = Shop.objects.create(
            owner=cls.seller, name="Moderated Shop", slug="moderated-shop", status=Shop.STATUS_ACTIVE
        )
        cls.category = Category.objects.create(name="Moderation Gadgets", slug="mod-gadgets")
        cls.product = Product.objects.create(
            name="Moderated Widget",
            slug="moderated-widget",
            category=cls.category,
            shop=cls.shop,
            description="Reviewed, then moderated",
            price=Decimal("30.00"),
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )

        def make_user(username, role=None, superuser=False):
            factory = User.objects.create_superuser if superuser else User.objects.create_user
            user = factory(username=username, email=f"{username}@example.com", password="Password123!")
            if role:
                assign_user_role(user, role)
            return user

        cls.customer_a = make_user("mod_customer_a", Role.ROLE_CUSTOMER)
        cls.customer_b = make_user("mod_customer_b", Role.ROLE_CUSTOMER)
        cls.support = make_user("mod_support", Role.ROLE_SUPPORT_TEAM)
        cls.administrator = make_user("mod_administrator", Role.ROLE_ADMINISTRATOR)
        cls.sales = make_user("mod_sales", Role.ROLE_SALES_TEAM)
        cls.superuser = make_user("mod_superuser", superuser=True)

    def setUp(self):
        self.client = APIClient()
        self.abusive_product_review = Review.objects.create(
            user=self.customer_a, product=self.product, rating=1, comment="Terrible, buy elsewhere!!!"
        )
        self.good_product_review = Review.objects.create(
            user=self.customer_b, product=self.product, rating=5, comment="Works great"
        )
        self.abusive_shop_review = ShopReview.objects.create(
            user=self.customer_a, shop=self.shop, rating=1, comment="Rude owner"
        )
        self.good_shop_review = ShopReview.objects.create(
            user=self.customer_b, shop=self.shop, rating=5, comment="Lovely shop"
        )

    def _hide(self, user, review_type, pk, reason="Abusive language"):
        self.client.force_authenticate(user=user)
        return self.client.post(f"/api/admin/reviews/{review_type}/{pk}/hide/", {"reason": reason})

    def _unhide(self, user, review_type, pk):
        self.client.force_authenticate(user=user)
        return self.client.post(f"/api/admin/reviews/{review_type}/{pk}/unhide/", {})

    def _as_guest(self):
        self.client.force_authenticate(user=None)


class ReviewModerationPermissionTests(BaseReviewModerationTestCase):
    def test_list_is_limited_to_review_moderators(self):
        cases = [
            (None, status.HTTP_401_UNAUTHORIZED),
            (self.customer_a, status.HTTP_403_FORBIDDEN),
            (self.sales, status.HTTP_403_FORBIDDEN),
            (self.support, status.HTTP_200_OK),
            (self.administrator, status.HTTP_200_OK),
            (self.superuser, status.HTTP_200_OK),
        ]
        for user, expected in cases:
            with self.subTest(user=getattr(user, "username", "guest")):
                self.client.force_authenticate(user=user)
                self.assertEqual(self.client.get("/api/admin/reviews/product/").status_code, expected)

    def test_hide_is_limited_to_review_moderators(self):
        for user in (self.customer_a, self.sales):
            with self.subTest(user=user.username):
                res = self._hide(user, "product", self.abusive_product_review.id)
                self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.abusive_product_review.refresh_from_db()
        self.assertFalse(self.abusive_product_review.is_hidden)


class ReviewModerationActionTests(BaseReviewModerationTestCase):
    def test_hide_requires_a_reason(self):
        res = self._hide(self.support, "product", self.abusive_product_review.id, reason="   ")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", res.data)
        self.abusive_product_review.refresh_from_db()
        self.assertFalse(self.abusive_product_review.is_hidden)

    def test_hide_product_review_sets_fields_and_audits(self):
        review = self.abusive_product_review
        updated_before = Review.objects.get(pk=review.pk).updated_at

        res = self._hide(self.support, "product", review.id, reason="Abusive language")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["is_hidden"])
        self.assertEqual(res.data["hidden_by_username"], "mod_support")
        self.assertEqual(res.data["review_type"], "product")

        review.refresh_from_db()
        self.assertTrue(review.is_hidden)
        self.assertEqual(review.hidden_reason, "Abusive language")
        self.assertEqual(review.hidden_by, self.support)
        self.assertIsNotNone(review.hidden_at)
        # Moderation is not an edit by the author.
        self.assertEqual(review.updated_at, updated_before)

        log = AuditLog.objects.get(action="REVIEW_HIDDEN", target_id=str(review.id))
        self.assertEqual(log.actor, self.support)
        self.assertEqual(log.shop, self.shop)
        self.assertEqual(log.metadata["reason"], "Abusive language")
        self.assertEqual(log.metadata["author_id"], self.customer_a.id)
        self.assertEqual(log.metadata["previous_state"], {"is_hidden": False})
        self.assertEqual(log.metadata["new_state"], {"is_hidden": True})

    def test_hiding_twice_is_rejected(self):
        self.assertEqual(self._hide(self.support, "product", self.abusive_product_review.id).status_code, 200)
        res = self._hide(self.support, "product", self.abusive_product_review.id)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unhide_restores_and_clears_the_moderation_fields(self):
        self._hide(self.support, "shop", self.abusive_shop_review.id)
        res = self._unhide(self.administrator, "shop", self.abusive_shop_review.id)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["is_hidden"])

        review = ShopReview.objects.get(pk=self.abusive_shop_review.id)
        self.assertEqual(
            (review.is_hidden, review.hidden_reason, review.hidden_by, review.hidden_at),
            (False, "", None, None),
        )
        self.assertTrue(
            AuditLog.objects.filter(action="SHOP_REVIEW_HIDDEN", target_id=str(review.id)).exists()
        )
        log = AuditLog.objects.get(action="SHOP_REVIEW_UNHIDDEN", target_id=str(review.id))
        self.assertEqual((log.actor, log.shop), (self.administrator, self.shop))

    def test_unhiding_a_visible_review_is_rejected(self):
        res = self._unhide(self.support, "product", self.good_product_review.id)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_type_or_id_is_404(self):
        self.client.force_authenticate(user=self.support)
        self.assertEqual(self.client.get("/api/admin/reviews/order/").status_code, 404)
        self.assertEqual(self._hide(self.support, "order", self.abusive_product_review.id).status_code, 404)
        self.assertEqual(self._hide(self.support, "product", 999999).status_code, 404)


class HiddenReviewPublicEffectTests(BaseReviewModerationTestCase):
    def _get(self, url):
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return res.data

    def _product_rating(self):
        data = self._get(f"/api/products/{self.product.id}/")
        return data["average_rating"], data["review_count"], data["rating_breakdown"]

    def _shop_rating(self):
        data = self._get(f"/api/shops/{self.shop.slug}/")
        return data["average_rating"], data["review_count"], data["rating_breakdown"]

    def test_hidden_product_review_leaves_list_and_every_rating(self):
        self.assertEqual(self._product_rating()[:2], (3.0, 2))
        self._hide(self.support, "product", self.abusive_product_review.id)
        self._as_guest()

        reviews = self._get(f"/api/products/{self.product.id}/reviews/")["results"]
        self.assertEqual([r["id"] for r in reviews], [self.good_product_review.id])
        self.assertEqual(
            self._product_rating(), (5.0, 1, {"5": 1, "4": 0, "3": 0, "2": 0, "1": 0})
        )
        row = next(p for p in self._get("/api/products/")["results"] if p["id"] == self.product.id)
        self.assertEqual((row["average_rating"], row["review_count"]), (5.0, 1))

        # Restoring it brings everything back
        self._unhide(self.support, "product", self.abusive_product_review.id)
        self._as_guest()
        self.assertEqual(self._product_rating()[:2], (3.0, 2))

    def test_hidden_shop_review_leaves_list_and_every_rating(self):
        self._hide(self.support, "shop", self.abusive_shop_review.id)
        self._as_guest()

        reviews = self._get(f"/api/shops/{self.shop.slug}/reviews/")["results"]
        self.assertEqual([r["id"] for r in reviews], [self.good_shop_review.id])
        self.assertEqual(self._shop_rating(), (5.0, 1, {"5": 1, "4": 0, "3": 0, "2": 0, "1": 0}))
        row = next(s for s in self._get("/api/shops/")["results"] if s["id"] == self.shop.id)
        self.assertEqual((row["average_rating"], row["review_count"]), (5.0, 1))

    def test_author_still_sees_their_hidden_reviews(self):
        self._hide(self.support, "product", self.abusive_product_review.id, reason="Abusive language")
        self._hide(self.support, "shop", self.abusive_shop_review.id, reason="Personal attack")
        self.client.force_authenticate(user=self.customer_a)

        mine = self._get(f"/api/reviews/mine/?product_id={self.product.id}")
        self.assertEqual((mine["is_hidden"], mine["hidden_reason"]), (True, "Abusive language"))
        mine_shop = self._get(f"/api/shop-reviews/mine/?shop_id={self.shop.id}")
        self.assertEqual((mine_shop["is_hidden"], mine_shop["hidden_reason"]), (True, "Personal attack"))

        profile = self._get("/api/profile/reviews/")
        self.assertEqual([r["is_hidden"] for r in profile["product_reviews"]], [True])
        self.assertEqual([r["is_hidden"] for r in profile["shop_reviews"]], [True])

    def test_public_rows_carry_no_moderation_detail(self):
        self._as_guest()
        for row in self._get(f"/api/products/{self.product.id}/reviews/")["results"]:
            self.assertEqual((row["is_hidden"], row["hidden_reason"]), (False, ""))


class AdminReviewListFilterTests(BaseReviewModerationTestCase):
    def _ids(self, review_type, query=""):
        self.client.force_authenticate(user=self.support)
        res = self.client.get(f"/api/admin/reviews/{review_type}/{query}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return {row["id"] for row in res.data["results"]}, res.data["results"]

    def test_each_type_lists_its_own_reviews_with_author_and_target(self):
        ids, rows = self._ids("product")
        self.assertEqual(ids, {self.abusive_product_review.id, self.good_product_review.id})
        row = next(r for r in rows if r["id"] == self.abusive_product_review.id)
        self.assertEqual(row["review_type"], "product")
        self.assertEqual(row["author"], {"id": self.customer_a.id, "username": "mod_customer_a"})
        self.assertEqual(row["target"], {"id": self.product.id, "name": "Moderated Widget", "slug": "moderated-widget"})

        ids, rows = self._ids("shop")
        self.assertEqual(ids, {self.abusive_shop_review.id, self.good_shop_review.id})
        self.assertEqual(rows[0]["target"]["slug"], "moderated-shop")

    def test_filters(self):
        self._hide(self.support, "product", self.abusive_product_review.id)
        cases = {
            "?hidden=true": {self.abusive_product_review.id},
            "?hidden=false": {self.good_product_review.id},
            "?rating=5": {self.good_product_review.id},
            "?search=buy%20elsewhere": {self.abusive_product_review.id},
            "?search=mod_customer_b": {self.good_product_review.id},
            "?search=moderated%20widget": {self.abusive_product_review.id, self.good_product_review.id},
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(self._ids("product", query)[0], expected)

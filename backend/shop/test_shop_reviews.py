from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from customers.models import ShopReview
from sellers.models import SellerProfile
from shops.models import Shop

User = get_user_model()


class BaseShopReviewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller_user = User.objects.create_user(
            username="shoprev_seller", email="shoprev_seller@example.com", password="Password123!"
        )
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Shop Review Test Co",
        )
        cls.shop = Shop.objects.create(
            owner=cls.seller,
            name="Shop Review Test Shop",
            slug="shop-review-test-shop",
            status=Shop.STATUS_ACTIVE,
        )
        cls.customer = User.objects.create_user(
            username="shoprev_customer", email="shoprev_customer@example.com", password="Password123!"
        )


class ShopReviewModelTests(BaseShopReviewTestCase):
    def test_one_review_per_user_per_shop(self):
        ShopReview.objects.create(user=self.customer, shop=self.shop, rating=4)
        with self.assertRaises(IntegrityError):
            # Savepoint, so the failed INSERT doesn't break the test's transaction.
            with transaction.atomic():
                ShopReview.objects.create(user=self.customer, shop=self.shop, rating=2)
        self.assertEqual(ShopReview.objects.filter(user=self.customer, shop=self.shop).count(), 1)

    def test_same_user_can_review_different_shops(self):
        other_shop = Shop.objects.create(
            owner=self.seller,
            name="Second Review Test Shop",
            slug="second-review-test-shop",
            status=Shop.STATUS_ACTIVE,
        )
        ShopReview.objects.create(user=self.customer, shop=self.shop, rating=4)
        ShopReview.objects.create(user=self.customer, shop=other_shop, rating=5)
        self.assertEqual(self.customer.shop_reviews.count(), 2)

    def test_rating_outside_one_to_five_is_rejected_on_save(self):
        for rating in (0, 6):
            with self.subTest(rating=rating):
                with self.assertRaises(ValidationError):
                    ShopReview.objects.create(user=self.customer, shop=self.shop, rating=rating)
        self.assertFalse(ShopReview.objects.exists())

    def test_reverse_relations_and_str(self):
        review = ShopReview.objects.create(
            user=self.customer, shop=self.shop, rating=5, comment="Fast delivery"
        )
        self.assertEqual(list(self.shop.customer_reviews.all()), [review])
        self.assertEqual(list(self.customer.shop_reviews.all()), [review])
        self.assertFalse(review.is_verified_purchase)
        self.assertEqual(str(review), "shoprev_customer rated shop Shop Review Test Shop: 5/5")

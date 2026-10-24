"""
TASK-036 / BUG-061: favourites show the product's real rating, from the
reviews a moderator has not hidden, like every other product card.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from customers.models import Favorite, Review
from sellers.models import SellerProfile
from shop.models import Category, Product
from shops.models import Shop

User = get_user_model()


class FavoriteRatingTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username="fav_customer", password="Fav-Customer-123")
        seller = SellerProfile.objects.create(
            user=User.objects.create_user(username="fav_seller", password="Fav-Seller-123"),
            business_name="Fav Seller", status=SellerProfile.STATUS_ACTIVE,
        )
        shop = Shop.objects.create(owner=seller, name="Fav Shop", slug="fav-shop", status=Shop.STATUS_ACTIVE)
        category = Category.objects.create(name="Fav Category", slug="fav-category", is_active=True)
        cls.product = Product.objects.create(
            name="Fav Product", slug="fav-product", category=category, shop=shop, price=Decimal("100.00"),
            stock=5, status=Product.STATUS_PUBLISHED, is_active=True,
        )
        for n, (rating, hidden) in enumerate(((5, False), (3, False), (1, True))):
            Review.objects.create(
                user=User.objects.create_user(username=f"fav_reviewer_{n}", password="Fav-Reviewer-123"),
                product=cls.product, rating=rating, is_hidden=hidden,
            )
        Favorite.objects.create(user=cls.customer, product=cls.product)

    def setUp(self):
        self.client.force_authenticate(user=self.customer)

    def test_the_list_shows_the_visible_review_rating(self):
        product = self.client.get("/api/favorites/").data[0]["product"]
        self.assertEqual(product["review_count"], 2)
        self.assertEqual(float(product["average_rating"]), 4.0)

    def test_adding_a_favourite_returns_it_with_its_rating(self):
        Favorite.objects.all().delete()
        product = self.client.post("/api/favorites/", {"product_id": self.product.pk}, format="json").data["product"]
        self.assertEqual(product["review_count"], 2)
        self.assertEqual(float(product["average_rating"]), 4.0)

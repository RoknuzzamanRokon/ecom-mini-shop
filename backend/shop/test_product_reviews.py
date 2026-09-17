from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from cart.models import Cart, CartItem
from customers.models import Address, Review
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.models import Shop
from .models import Category, Order, Product, ProductInventory
from .services import OrderService

User = get_user_model()


class BaseProductReviewTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        # Seller + Shop + published Product
        cls.seller_user = User.objects.create_user(
            username="review_seller", email="review_seller@example.com", password="Password123!"
        )
        assign_user_role(cls.seller_user, Role.ROLE_SALES_TEAM)
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Review Test Shop Co",
        )
        cls.shop = Shop.objects.create(
            owner=cls.seller,
            name="Review Test Shop",
            slug="review-test-shop",
            status=Shop.STATUS_ACTIVE,
        )
        cls.category = Category.objects.create(name="Gadgets", slug="gadgets-review-test")
        cls.product = Product.objects.create(
            name="Reviewable Widget",
            slug="reviewable-widget",
            category=cls.category,
            shop=cls.shop,
            description="A widget you can review",
            price=Decimal("49.99"),
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )
        ProductInventory.objects.create(product=cls.product, available_quantity=50)

        # Customer A: has the CUSTOMER role (can post reviews)
        cls.customer_a = User.objects.create_user(
            username="review_customer_a", email="review_a@example.com", password="Password123!"
        )
        assign_user_role(cls.customer_a, Role.ROLE_CUSTOMER)
        cls.address_a = Address.objects.create(
            user=cls.customer_a,
            recipient_name="Customer A",
            phone="01700000001",
            address_line_1="123 Test Road",
            city="Dhaka",
            postal_code="1200",
            is_default=True,
        )

        # Customer B: also has the CUSTOMER role, used for cross-ownership checks
        cls.customer_b = User.objects.create_user(
            username="review_customer_b", email="review_b@example.com", password="Password123!"
        )
        assign_user_role(cls.customer_b, Role.ROLE_CUSTOMER)

        # A plain user with no roles at all (lacks reviews.create)
        cls.no_role_user = User.objects.create_user(
            username="review_no_role", email="review_no_role@example.com", password="Password123!"
        )

    def setUp(self):
        self.client = APIClient()

    def _deliver_order_for(self, customer, address, product, quantity=1):
        """Creates and fully delivers an order for a customer/product, for verified-purchase tests."""
        cart, _ = Cart.objects.get_or_create(user=customer)
        CartItem.objects.filter(cart=cart).delete()
        CartItem.objects.create(cart=cart, product=product, quantity=quantity)
        order = OrderService.create_order_from_cart(user=customer, address_id=address.id)
        OrderService.transition_order_status(order, Order.STATUS_CONFIRMED, actor=customer)
        OrderService.transition_order_status(order, Order.STATUS_PROCESSING, actor=customer)
        OrderService.transition_order_status(order, Order.STATUS_SHIPPED, actor=customer)
        OrderService.transition_order_status(order, Order.STATUS_DELIVERED, actor=customer)
        return order


class ReviewCreationTests(BaseProductReviewTestCase):
    def test_authenticated_customer_can_create_review(self):
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.post(
            "/api/reviews/",
            {"product_id": self.product.id, "rating": 4, "comment": "Pretty good!"},
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["rating"], 4)
        self.assertEqual(res.data["comment"], "Pretty good!")
        self.assertFalse(res.data["is_verified_purchase"])
        self.assertEqual(Review.objects.filter(user=self.customer_a, product=self.product).count(), 1)

    def test_duplicate_review_for_same_product_rejected(self):
        self.client.force_authenticate(user=self.customer_a)
        first = self.client.post(
            "/api/reviews/", {"product_id": self.product.id, "rating": 5, "comment": "Great"}
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(
            "/api/reviews/", {"product_id": self.product.id, "rating": 2, "comment": "Changed my mind"}
        )
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Review.objects.filter(user=self.customer_a, product=self.product).count(), 1)

    def test_unauthenticated_user_cannot_create_review(self):
        res = self.client.post(
            "/api/reviews/", {"product_id": self.product.id, "rating": 3, "comment": "Ok"}
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_without_customer_role_cannot_create_review(self):
        self.client.force_authenticate(user=self.no_role_user)
        res = self.client.post(
            "/api/reviews/", {"product_id": self.product.id, "rating": 3, "comment": "Ok"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_rating_out_of_range_rejected(self):
        self.client.force_authenticate(user=self.customer_a)
        too_low = self.client.post("/api/reviews/", {"product_id": self.product.id, "rating": 0})
        self.assertEqual(too_low.status_code, status.HTTP_400_BAD_REQUEST)

        too_high = self.client.post("/api/reviews/", {"product_id": self.product.id, "rating": 6})
        self.assertEqual(too_high.status_code, status.HTTP_400_BAD_REQUEST)

    def test_is_verified_purchase_true_for_delivered_order(self):
        self._deliver_order_for(self.customer_a, self.address_a, self.product)

        self.client.force_authenticate(user=self.customer_a)
        res = self.client.post(
            "/api/reviews/", {"product_id": self.product.id, "rating": 5, "comment": "Bought and loved it"}
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data["is_verified_purchase"])

    def test_is_verified_purchase_false_without_delivered_order(self):
        self.client.force_authenticate(user=self.customer_b)
        res = self.client.post(
            "/api/reviews/", {"product_id": self.product.id, "rating": 3, "comment": "Never bought it"}
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertFalse(res.data["is_verified_purchase"])


class ReviewOwnershipTests(BaseProductReviewTestCase):
    def _create_review(self, user, rating=4, comment="Initial"):
        self.client.force_authenticate(user=user)
        res = self.client.post(
            "/api/reviews/", {"product_id": self.product.id, "rating": rating, "comment": comment}
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        return res.data["id"]

    def test_owner_can_update_own_review(self):
        review_id = self._create_review(self.customer_a)
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.patch(f"/api/reviews/{review_id}/", {"rating": 2, "comment": "Updated"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rating"], 2)
        self.assertEqual(res.data["comment"], "Updated")

    def test_owner_can_delete_own_review(self):
        review_id = self._create_review(self.customer_a)
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.delete(f"/api/reviews/{review_id}/")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Review.objects.filter(id=review_id).exists())

    def test_non_owner_cannot_update_review(self):
        review_id = self._create_review(self.customer_a)
        self.client.force_authenticate(user=self.customer_b)
        res = self.client.patch(f"/api/reviews/{review_id}/", {"rating": 1})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        review = Review.objects.get(id=review_id)
        self.assertEqual(review.rating, 4)

    def test_non_owner_cannot_delete_review(self):
        review_id = self._create_review(self.customer_a)
        self.client.force_authenticate(user=self.customer_b)
        res = self.client.delete(f"/api/reviews/{review_id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Review.objects.filter(id=review_id).exists())


class ReviewPublicListingTests(BaseProductReviewTestCase):
    def test_unauthenticated_can_list_product_reviews(self):
        self.client.force_authenticate(user=self.customer_a)
        self.client.post("/api/reviews/", {"product_id": self.product.id, "rating": 5, "comment": "Nice"})

        self.client.force_authenticate(user=None)
        res = self.client.get(f"/api/products/{self.product.id}/reviews/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data["results"] if "results" in res.data else res.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["rating"], 5)

    def test_reviews_list_404s_for_nonexistent_product(self):
        res = self.client.get("/api/products/999999/reviews/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class MyProductReviewTests(BaseProductReviewTestCase):
    def test_returns_404_when_no_review_exists(self):
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.get(f"/api/reviews/mine/?product_id={self.product.id}")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_returns_own_review_when_it_exists(self):
        self.client.force_authenticate(user=self.customer_a)
        self.client.post("/api/reviews/", {"product_id": self.product.id, "rating": 4, "comment": "Good"})

        res = self.client.get(f"/api/reviews/mine/?product_id={self.product.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rating"], 4)

    def test_requires_authentication(self):
        res = self.client.get(f"/api/reviews/mine/?product_id={self.product.id}")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class ProductRatingAggregateTests(BaseProductReviewTestCase):
    def _get_product_detail(self):
        return self.client.get(f"/api/products/{self.product.id}/")

    def test_no_reviews_gives_zero_rating_and_count(self):
        res = self._get_product_detail()
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["average_rating"], 0.0)
        self.assertEqual(res.data["review_count"], 0)

    def test_rating_and_count_update_after_create_update_delete(self):
        self.client.force_authenticate(user=self.customer_a)
        create_res = self.client.post(
            "/api/reviews/", {"product_id": self.product.id, "rating": 4, "comment": "Good"}
        )
        review_id = create_res.data["id"]

        detail_after_create = self._get_product_detail()
        self.assertEqual(detail_after_create.data["average_rating"], 4.0)
        self.assertEqual(detail_after_create.data["review_count"], 1)

        # Second reviewer brings the average to (4 + 2) / 2 = 3.0
        self.client.force_authenticate(user=self.customer_b)
        self.client.post("/api/reviews/", {"product_id": self.product.id, "rating": 2, "comment": "Meh"})

        detail_after_second = self._get_product_detail()
        self.assertEqual(detail_after_second.data["average_rating"], 3.0)
        self.assertEqual(detail_after_second.data["review_count"], 2)

        # Customer A updates their rating from 4 to 5: average becomes (5 + 2) / 2 = 3.5
        self.client.force_authenticate(user=self.customer_a)
        self.client.patch(f"/api/reviews/{review_id}/", {"rating": 5})

        detail_after_update = self._get_product_detail()
        self.assertEqual(detail_after_update.data["average_rating"], 3.5)
        self.assertEqual(detail_after_update.data["review_count"], 2)

        # Customer A deletes their review: only customer B's rating of 2 remains
        self.client.delete(f"/api/reviews/{review_id}/")

        detail_after_delete = self._get_product_detail()
        self.assertEqual(detail_after_delete.data["average_rating"], 2.0)
        self.assertEqual(detail_after_delete.data["review_count"], 1)

    def test_rating_and_count_present_on_list_endpoint(self):
        self.client.force_authenticate(user=self.customer_a)
        self.client.post("/api/reviews/", {"product_id": self.product.id, "rating": 4, "comment": "Good"})

        res = self.client.get("/api/products/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data["results"] if "results" in res.data else res.data
        product_row = next(p for p in results if p["id"] == self.product.id)
        self.assertEqual(product_row["average_rating"], 4.0)
        self.assertEqual(product_row["review_count"], 1)

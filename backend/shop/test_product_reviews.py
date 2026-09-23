from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from audit.models import AuditLog
from cart.models import Cart, CartItem
from customers.models import Address, CustomerProfile, Review
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


class MyProductReviewParamValidationTests(BaseProductReviewTestCase):
    def test_missing_product_id_returns_400(self):
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.get("/api/reviews/mine/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_product_id_returns_400_not_500(self):
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.get("/api/reviews/mine/?product_id=abc")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


class SelfReviewGuardTests(BaseProductReviewTestCase):
    def setUp(self):
        super().setUp()
        # The shop owner also shops as a customer, so they do hold reviews.create.
        assign_user_role(self.seller_user, Role.ROLE_CUSTOMER)

    def test_shop_owner_cannot_review_own_product(self):
        self.client.force_authenticate(user=self.seller_user)
        res = self.client.post(
            "/api/reviews/", {"product_id": self.product.id, "rating": 5, "comment": "Best ever"}
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Review.objects.filter(user=self.seller_user).exists())

    def test_shop_owner_can_review_another_shops_product(self):
        other_owner = User.objects.create_user(
            username="review_other_seller", email="review_other@example.com", password="Password123!"
        )
        other_seller = SellerProfile.objects.create(
            user=other_owner,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Other Review Shop Co",
        )
        other_shop = Shop.objects.create(
            owner=other_seller,
            name="Other Review Shop",
            slug="other-review-shop",
            status=Shop.STATUS_ACTIVE,
        )
        other_product = Product.objects.create(
            name="Someone Else's Widget",
            slug="someone-elses-widget",
            category=self.category,
            shop=other_shop,
            price=Decimal("19.99"),
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )

        self.client.force_authenticate(user=self.seller_user)
        res = self.client.post(
            "/api/reviews/", {"product_id": other_product.id, "rating": 4, "comment": "Solid"}
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)


class ReviewAuditActorTests(BaseProductReviewTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.admin = User.objects.create_superuser(
            username="review_admin", email="review_admin@example.com", password="Password123!"
        )

    def setUp(self):
        super().setUp()
        self.review = Review.objects.create(
            user=self.customer_a, product=self.product, rating=4, comment="Initial"
        )

    def _latest_log(self, action):
        return AuditLog.objects.filter(action=action, target_id=str(self.review.id)).latest("id")

    def test_owner_update_is_logged_as_owner(self):
        self.client.force_authenticate(user=self.customer_a)
        res = self.client.patch(f"/api/reviews/{self.review.id}/", {"rating": 2})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(self._latest_log("REVIEW_UPDATED").actor, self.customer_a)

    def test_admin_update_is_logged_as_admin(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(f"/api/reviews/{self.review.id}/", {"comment": "Moderated"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        log = self._latest_log("REVIEW_UPDATED")
        self.assertEqual(log.actor, self.admin)
        self.assertEqual(log.metadata["author_id"], self.customer_a.id)

    def test_admin_delete_is_logged_as_admin(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(f"/api/reviews/{self.review.id}/")
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        log = self._latest_log("REVIEW_DELETED")
        self.assertEqual(log.actor, self.admin)
        self.assertEqual(log.metadata["author_id"], self.customer_a.id)


class ReviewerNameTests(BaseProductReviewTestCase):
    def _list_results(self):
        res = self.client.get(f"/api/products/{self.product.id}/reviews/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return res.data["results"] if "results" in res.data else res.data

    def test_profile_display_name_is_shown(self):
        CustomerProfile.objects.update_or_create(
            user=self.customer_a, defaults={"display_name": "Ayesha K."}
        )
        Review.objects.create(user=self.customer_a, product=self.product, rating=5)
        self.assertEqual(self._list_results()[0]["reviewer_name"], "Ayesha K.")

    def test_blank_display_name_falls_back_to_username(self):
        CustomerProfile.objects.update_or_create(
            user=self.customer_b, defaults={"display_name": "   "}
        )
        Review.objects.create(user=self.customer_b, product=self.product, rating=3)
        self.assertEqual(self._list_results()[0]["reviewer_name"], "review_customer_b")

    def test_list_query_count_does_not_grow_per_review(self):
        Review.objects.create(user=self.customer_a, product=self.product, rating=5)
        with CaptureQueriesContext(connection) as one_review:
            self._list_results()

        CustomerProfile.objects.update_or_create(
            user=self.customer_b, defaults={"display_name": "Bilal"}
        )
        Review.objects.create(user=self.customer_b, product=self.product, rating=4)
        Review.objects.create(user=self.no_role_user, product=self.product, rating=3)
        with CaptureQueriesContext(connection) as three_reviews:
            self.assertEqual(len(self._list_results()), 3)

        self.assertEqual(len(three_reviews), len(one_review))


class RatingBreakdownTests(BaseProductReviewTestCase):
    def _breakdown(self):
        res = self.client.get(f"/api/products/{self.product.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return res.data["rating_breakdown"]

    def test_no_reviews_gives_all_five_keys_at_zero(self):
        self.assertEqual(self._breakdown(), {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0})

    def test_breakdown_tracks_create_update_delete(self):
        self.client.force_authenticate(user=self.customer_a)
        review_a = self.client.post(
            "/api/reviews/", {"product_id": self.product.id, "rating": 5}
        ).data["id"]
        self.client.force_authenticate(user=self.customer_b)
        self.client.post("/api/reviews/", {"product_id": self.product.id, "rating": 5})
        self.assertEqual(self._breakdown(), {"5": 2, "4": 0, "3": 0, "2": 0, "1": 0})

        # Customer A moves from 5 to 2 stars
        self.client.force_authenticate(user=self.customer_a)
        self.client.patch(f"/api/reviews/{review_a}/", {"rating": 2})
        self.assertEqual(self._breakdown(), {"5": 1, "4": 0, "3": 0, "2": 1, "1": 0})

        # ...then deletes it
        self.client.delete(f"/api/reviews/{review_a}/")
        self.assertEqual(self._breakdown(), {"5": 1, "4": 0, "3": 0, "2": 0, "1": 0})

    def test_list_endpoint_does_not_include_breakdown(self):
        res = self.client.get("/api/products/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data["results"] if "results" in res.data else res.data
        product_row = next(p for p in results if p["id"] == self.product.id)
        self.assertNotIn("rating_breakdown", product_row)


class ReviewListOrderingTests(BaseProductReviewTestCase):
    def setUp(self):
        super().setUp()
        # Oldest is rated 3, middle 5, newest 1, so every ordering gives a distinct result.
        self.oldest = Review.objects.create(user=self.customer_a, product=self.product, rating=3)
        self.middle = Review.objects.create(user=self.customer_b, product=self.product, rating=5)
        self.newest = Review.objects.create(user=self.no_role_user, product=self.product, rating=1)
        self._age(self.oldest, days=3)
        self._age(self.middle, days=2)
        self._age(self.newest, days=1)

    def _age(self, review, days):
        Review.objects.filter(pk=review.pk).update(created_at=timezone.now() - timedelta(days=days))

    def _ids(self, ordering=None):
        url = f"/api/products/{self.product.id}/reviews/"
        if ordering is not None:
            url += f"?ordering={ordering}"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data["results"] if "results" in res.data else res.data
        return [r["id"] for r in results]

    def test_each_ordering_value(self):
        expected = {
            "newest": [self.newest.id, self.middle.id, self.oldest.id],
            "oldest": [self.oldest.id, self.middle.id, self.newest.id],
            "highest": [self.middle.id, self.oldest.id, self.newest.id],
            "lowest": [self.newest.id, self.oldest.id, self.middle.id],
        }
        for ordering, ids in expected.items():
            with self.subTest(ordering=ordering):
                self.assertEqual(self._ids(ordering), ids)

    def test_missing_or_unknown_ordering_falls_back_to_newest(self):
        newest_first = [self.newest.id, self.middle.id, self.oldest.id]
        self.assertEqual(self._ids(), newest_first)
        self.assertEqual(self._ids("price"), newest_first)

    def test_equal_ratings_are_broken_by_newest_first(self):
        tie_user = User.objects.create_user(
            username="review_tie", email="review_tie@example.com", password="Password123!"
        )
        tie = Review.objects.create(user=tie_user, product=self.product, rating=5)
        self._age(tie, days=0)
        self.assertEqual(
            self._ids("highest"), [tie.id, self.middle.id, self.oldest.id, self.newest.id]
        )

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from audit.models import AuditLog
from cart.models import Cart, CartItem
from customers.models import Address, ShopReview
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.models import Shop
from .models import Category, Order, Product, ProductInventory
from .services import OrderService

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


class BaseShopReviewAPITestCase(BaseShopReviewTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        call_command("seed_rbac")
        assign_user_role(cls.customer, Role.ROLE_CUSTOMER)

        cls.other_customer = User.objects.create_user(
            username="shoprev_other", email="shoprev_other@example.com", password="Password123!"
        )
        assign_user_role(cls.other_customer, Role.ROLE_CUSTOMER)

        # No roles at all, so no reviews.create
        cls.no_role_user = User.objects.create_user(
            username="shoprev_no_role", email="shoprev_no_role@example.com", password="Password123!"
        )
        cls.admin = User.objects.create_superuser(
            username="shoprev_admin", email="shoprev_admin@example.com", password="Password123!"
        )

        # A product sold by the shop, for verified-purchase orders
        cls.category = Category.objects.create(name="Shop Review Gadgets", slug="shoprev-gadgets")
        cls.product = Product.objects.create(
            name="Shop Review Widget",
            slug="shoprev-widget",
            category=cls.category,
            shop=cls.shop,
            description="Sold by the reviewed shop",
            price=Decimal("25.00"),
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )
        ProductInventory.objects.create(product=cls.product, available_quantity=50)
        cls.address = Address.objects.create(
            user=cls.customer,
            recipient_name="Shop Review Customer",
            phone="01700000002",
            address_line_1="1 Review Lane",
            city="Dhaka",
            postal_code="1200",
            is_default=True,
        )

    def setUp(self):
        self.client = APIClient()

    def _post(self, user, **payload):
        self.client.force_authenticate(user=user)
        return self.client.post("/api/shop-reviews/", {"shop_id": self.shop.id, **payload})

    def _deliver_order_for(self, customer, address, product):
        cart, _ = Cart.objects.get_or_create(user=customer)
        CartItem.objects.filter(cart=cart).delete()
        CartItem.objects.create(cart=cart, product=product, quantity=1)
        order = OrderService.create_order_from_cart(user=customer, address_id=address.id)
        for next_status in (
            Order.STATUS_CONFIRMED,
            Order.STATUS_PROCESSING,
            Order.STATUS_SHIPPED,
            Order.STATUS_DELIVERED,
        ):
            OrderService.transition_order_status(order, next_status, actor=customer)
        return order


class ShopReviewCreateAPITests(BaseShopReviewAPITestCase):
    def test_customer_can_create_review(self):
        res = self._post(self.customer, rating=4, comment="Friendly seller")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["rating"], 4)
        self.assertEqual(res.data["comment"], "Friendly seller")
        self.assertEqual(res.data["reviewer_name"], "shoprev_customer")
        self.assertFalse(res.data["is_verified_purchase"])
        self.assertTrue(ShopReview.objects.filter(user=self.customer, shop=self.shop).exists())

    def test_comment_is_optional(self):
        res = self._post(self.customer, rating=5)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["comment"], "")

    def test_duplicate_review_rejected_with_409(self):
        self.assertEqual(self._post(self.customer, rating=5).status_code, status.HTTP_201_CREATED)
        second = self._post(self.customer, rating=1)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(ShopReview.objects.filter(user=self.customer, shop=self.shop).count(), 1)

    def test_guest_cannot_create_review(self):
        res = self.client.post("/api/shop-reviews/", {"shop_id": self.shop.id, "rating": 3})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_without_customer_role_cannot_create_review(self):
        res = self._post(self.no_role_user, rating=3)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_rating_out_of_range_rejected(self):
        for rating in (0, 6):
            with self.subTest(rating=rating):
                self.assertEqual(
                    self._post(self.customer, rating=rating).status_code,
                    status.HTTP_400_BAD_REQUEST,
                )
        self.assertFalse(ShopReview.objects.exists())

    def test_non_public_or_missing_shop_rejected(self):
        pending = Shop.objects.create(
            owner=self.seller, name="Pending Shop", slug="shoprev-pending", status=Shop.STATUS_PENDING
        )
        suspended = Shop.objects.create(
            owner=self.seller,
            name="Suspended Shop",
            slug="shoprev-suspended",
            status=Shop.STATUS_SUSPENDED,
            suspension_reason="Under investigation",
        )
        self.client.force_authenticate(user=self.customer)
        for shop_id in (pending.id, suspended.id, 999999):
            with self.subTest(shop_id=shop_id):
                res = self.client.post("/api/shop-reviews/", {"shop_id": shop_id, "rating": 4})
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("shop_id", res.data)
        self.assertFalse(ShopReview.objects.exists())

    def test_owner_cannot_review_own_shop(self):
        assign_user_role(self.seller_user, Role.ROLE_CUSTOMER)
        res = self._post(self.seller_user, rating=5, comment="Best shop ever")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ShopReview.objects.filter(user=self.seller_user).exists())

    def test_verified_purchase_true_after_delivered_order_from_this_shop(self):
        self._deliver_order_for(self.customer, self.address, self.product)
        res = self._post(self.customer, rating=5)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(res.data["is_verified_purchase"])

    def test_verified_purchase_false_without_delivered_order(self):
        res = self._post(self.other_customer, rating=3)
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertFalse(res.data["is_verified_purchase"])

    def test_create_is_audited_against_the_shop(self):
        res = self._post(self.customer, rating=4)
        log = AuditLog.objects.get(action="SHOP_REVIEW_CREATED", target_id=str(res.data["id"]))
        self.assertEqual(log.actor, self.customer)
        self.assertEqual(log.shop, self.shop)
        self.assertEqual(log.metadata["rating"], 4)


class ShopReviewOwnershipAPITests(BaseShopReviewAPITestCase):
    def setUp(self):
        super().setUp()
        self.review = ShopReview.objects.create(
            user=self.customer, shop=self.shop, rating=4, comment="Initial"
        )
        self.url = f"/api/shop-reviews/{self.review.id}/"

    def test_owner_can_update_review(self):
        self.client.force_authenticate(user=self.customer)
        res = self.client.patch(self.url, {"rating": 2, "comment": "Slower lately"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual((res.data["rating"], res.data["comment"]), (2, "Slower lately"))
        log = AuditLog.objects.get(action="SHOP_REVIEW_UPDATED", target_id=str(self.review.id))
        self.assertEqual(log.actor, self.customer)

    def test_owner_can_delete_review(self):
        self.client.force_authenticate(user=self.customer)
        res = self.client.delete(self.url)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ShopReview.objects.filter(pk=self.review.id).exists())
        self.assertTrue(
            AuditLog.objects.filter(action="SHOP_REVIEW_DELETED", target_id=str(self.review.id)).exists()
        )

    def test_non_owner_cannot_update_review(self):
        self.client.force_authenticate(user=self.other_customer)
        res = self.client.patch(self.url, {"rating": 1})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.review.refresh_from_db()
        self.assertEqual(self.review.rating, 4)

    def test_non_owner_cannot_delete_review(self):
        self.client.force_authenticate(user=self.other_customer)
        res = self.client.delete(self.url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(ShopReview.objects.filter(pk=self.review.id).exists())

    def test_admin_delete_is_logged_as_admin(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.delete(self.url)
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        log = AuditLog.objects.get(action="SHOP_REVIEW_DELETED", target_id=str(self.review.id))
        self.assertEqual(log.actor, self.admin)
        self.assertEqual(log.metadata["author_id"], self.customer.id)


class MyShopReviewAPITests(BaseShopReviewAPITestCase):
    def _mine(self, user, query):
        if user is not None:
            self.client.force_authenticate(user=user)
        return self.client.get(f"/api/shop-reviews/mine/{query}")

    def test_returns_own_review(self):
        ShopReview.objects.create(user=self.customer, shop=self.shop, rating=5)
        res = self._mine(self.customer, f"?shop_id={self.shop.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["rating"], 5)

    def test_404_when_caller_has_no_review_even_if_others_do(self):
        ShopReview.objects.create(user=self.customer, shop=self.shop, rating=5)
        res = self._mine(self.other_customer, f"?shop_id={self.shop.id}")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_missing_or_non_numeric_shop_id_returns_400(self):
        for query in ("", "?shop_id=abc"):
            with self.subTest(query=query):
                self.assertEqual(
                    self._mine(self.customer, query).status_code, status.HTTP_400_BAD_REQUEST
                )

    def test_requires_authentication(self):
        res = self._mine(None, f"?shop_id={self.shop.id}")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

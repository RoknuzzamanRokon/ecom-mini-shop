"""
TASK-020 / BUG-018: a shop is public only while its seller is operational.
Suspending or rejecting the seller removes their shops from the list, the
detail page, nearby search and the review endpoints, as it already did for
their products.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from customers.serializers import ShopReviewCreateSerializer
from sellers.models import SellerProfile
from shops.fields import Point
from shops.models import Shop

User = get_user_model()

NEAR = {"lat": "23.8103", "lng": "90.4125", "radius": "5"}


class PublicShopVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.seller = SellerProfile.objects.create(
            user=User.objects.create_user(username="vis_seller", password="Vis-Seller-123"),
            business_name="Vis Seller",
            status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop = Shop.objects.create(
            owner=cls.seller, name="Vis Shop", slug="vis-shop", status=Shop.STATUS_ACTIVE,
            location=Point(90.4125, 23.8103),
        )

    def setUp(self):
        self.client = APIClient()

    def set_seller_status(self, new_status):
        reasons = {
            SellerProfile.STATUS_SUSPENDED: {"suspension_reason": "Under review."},
            SellerProfile.STATUS_REJECTED: {"rejection_reason": "Incomplete."},
        }
        SellerProfile.objects.filter(pk=self.seller.pk).update(status=new_status, **reasons.get(new_status, {}))

    def listed(self):
        data = self.client.get("/api/shops/", {"q": "Vis Shop"}).data
        rows = data["results"] if "results" in data else data
        return self.shop.slug in [row["slug"] for row in rows]

    def nearby(self):
        response = self.client.get("/api/shops/nearby/", NEAR)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return self.shop.slug in [row["slug"] for row in response.data["results"]]

    def reviewable(self):
        return ShopReviewCreateSerializer(data={"shop_id": self.shop.pk, "rating": 5}).is_valid()

    def shop_record(self):
        return Shop.objects.select_related("owner").get(pk=self.shop.pk)

    def test_an_operational_sellers_shop_is_public(self):
        self.assertTrue(self.listed())
        self.assertTrue(self.nearby())
        self.assertEqual(self.client.get(f"/api/shops/{self.shop.slug}/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(f"/api/shops/{self.shop.slug}/reviews/").status_code, status.HTTP_200_OK)
        self.assertTrue(self.reviewable())
        self.assertTrue(self.shop_record().is_publicly_visible)

    def test_a_suspended_or_rejected_sellers_shop_is_hidden(self):
        for seller_status in (SellerProfile.STATUS_SUSPENDED, SellerProfile.STATUS_REJECTED,
                              SellerProfile.STATUS_PENDING):
            with self.subTest(seller=seller_status):
                self.set_seller_status(seller_status)
                self.assertFalse(self.listed())
                self.assertFalse(self.nearby())
                self.assertEqual(
                    self.client.get(f"/api/shops/{self.shop.slug}/").status_code, status.HTTP_404_NOT_FOUND
                )
                self.assertEqual(
                    self.client.get(f"/api/shops/{self.shop.slug}/reviews/").status_code, status.HTTP_404_NOT_FOUND
                )
                self.assertFalse(self.reviewable())
                self.assertFalse(self.shop_record().is_publicly_visible)

    def test_reactivating_the_seller_brings_the_shop_back(self):
        self.set_seller_status(SellerProfile.STATUS_SUSPENDED)
        self.set_seller_status(SellerProfile.STATUS_ACTIVE)
        self.assertTrue(self.listed())
        self.assertEqual(self.client.get(f"/api/shops/{self.shop.slug}/").status_code, status.HTTP_200_OK)

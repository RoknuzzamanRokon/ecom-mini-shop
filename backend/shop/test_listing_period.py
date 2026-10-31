"""
Listing periods (docs/LISTING_VALIDITY_PLAN.md, decided 2026-11-01): a Limited
Shop Owner's product is live for 4 months from its first publication, then
EXPIRED until the seller renews it for 5 points, 2 months at a time. While a
period runs the seller cannot take the product off the storefront; stock still
changes freely. A Full Shop Owner's products have no end date.
"""
from datetime import timedelta
from decimal import Decimal
from importlib import import_module
from io import StringIO

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from audit.models import AuditLog
from cart.models import Cart, CartItem
from points.models import PointTransaction, add_months
from points.services import PointService
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shop.listing_service import ListingError, ListingService
from shop.models import Category, Product, ProductListingPolicy
from shop.services import ProductModerationError, ProductService
from shops.fields import Point
from shops.models import Shop

User = get_user_model()


def near(moment, expected, slack=timedelta(minutes=1)):
    return abs(moment - expected) < slack


class ListingTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", verbosity=0)
        cls.category = Category.objects.create(name="Tea", slug="listing-tea")
        cls.root = User.objects.create_superuser(username="listing_root", password="Listing-Root-123")
        cls.moderator = User.objects.create_user(username="listing_mod", password="Listing-Mod-123")
        assign_user_role(cls.moderator, Role.ROLE_OPERATION_MANAGER)
        cls.limited, cls.limited_shop = cls.seller("limited", SellerProfile.TYPE_LIMITED_SHOP_OWNER)
        cls.full, cls.full_shop = cls.seller("full", SellerProfile.TYPE_FULL_SHOP_OWNER)

    @classmethod
    def seller(cls, tag, seller_type):
        user = User.objects.create_user(username=f"listing_{tag}", password="Listing-Seller-123")
        seller = SellerProfile.objects.create(
            user=user, seller_type=seller_type, business_name=f"{tag} Tea House",
            status=SellerProfile.STATUS_ACTIVE,
        )
        shop = Shop.objects.create(
            owner=seller, name=f"{tag} Tea Shop", slug=f"listing-{tag}",
            status=Shop.STATUS_ACTIVE, location=Point(90.41, 23.81),
        )
        return seller, shop

    def setUp(self):
        self.client = APIClient()

    def product(self, shop=None, name="Assam Tea", publish=True):
        product = Product.objects.create(
            name=name, category=self.category, shop=shop or self.limited_shop, description="Strong.",
            price=Decimal("250.00"), stock=5, status=Product.STATUS_APPROVED,
        )
        if publish:
            ProductService.publish(product, self.moderator)
            product.refresh_from_db()
        return product

    def end_period(self, product, status_=Product.STATUS_PUBLISHED):
        Product.objects.filter(pk=product.pk).update(live_until=timezone.now() - timedelta(hours=1), status=status_)
        product.refresh_from_db()

    def as_seller(self, seller):
        # Freshly loaded, as a real request would be.
        self.client.force_authenticate(user=User.objects.get(pk=seller.user_id))
        return self.client

    def give_points(self, seller, amount):
        PointService.credit(seller, amount, PointTransaction.TYPE_BONUS, "Listing test")


class FirstPeriodTests(ListingTestCase):
    def test_first_publication_starts_four_months(self):
        product = self.product()
        self.assertTrue(near(product.live_until, add_months(timezone.now(), 4)))
        self.assertTrue(product.listing_locked)

    def test_full_owner_products_have_no_end_date(self):
        product = self.product(shop=self.full_shop)
        self.assertIsNone(product.live_until)
        self.assertFalse(product.listing_locked)
        self.assertTrue(product.is_publicly_visible)

    def test_republishing_keeps_the_running_clock(self):
        product = self.product()
        started = product.live_until
        ProductService.unpublish(product, self.moderator)
        ProductService.publish(product, self.moderator)
        product.refresh_from_db()
        self.assertEqual(product.live_until, started)

    def test_staff_cannot_publish_an_ended_listing(self):
        product = self.product()
        self.end_period(product, Product.STATUS_UNPUBLISHED)
        with self.assertRaises(ProductModerationError):
            ProductService.publish(product, self.moderator)

    def test_the_policy_is_configurable(self):
        ProductListingPolicy.objects.create(first_period_months=6)
        product = self.product()
        self.assertTrue(near(product.live_until, add_months(timezone.now(), 6)))


class VisibilityTests(ListingTestCase):
    def test_an_ended_period_leaves_the_storefront_before_the_sweep(self):
        product = self.product()
        self.assertIn(product, Product.objects.public())

        self.end_period(product)
        self.assertEqual(product.status, Product.STATUS_PUBLISHED)
        self.assertNotIn(product, Product.objects.public())
        self.assertFalse(product.is_publicly_visible)
        category = ProductService.get_public_categories_queryset().get(pk=self.category.pk)
        self.assertEqual(category.products_count, 0)
        self.assertEqual(self.client.get(f"/api/products/{product.pk}/").status_code, status.HTTP_404_NOT_FOUND)

    def test_the_cart_explains_an_ended_listing(self):
        product = self.product()
        self.end_period(product)
        cart = Cart.objects.create(user=self.root)
        item = CartItem.objects.create(cart=cart, product=product, quantity=1)
        self.assertEqual(item.unavailable_reason, "This product's listing has ended.")


class ExpiryTests(ListingTestCase):
    def test_the_command_expires_ended_listings_with_an_audit_row(self):
        ended, running = self.product(name="Ended"), self.product(name="Running")
        self.end_period(ended)

        out = StringIO()
        call_command("expire_listings", "--dry-run", stdout=out)
        self.assertIn("1 product listing(s) have ended.", out.getvalue())
        ended.refresh_from_db()
        self.assertEqual(ended.status, Product.STATUS_PUBLISHED)

        call_command("expire_listings", stdout=StringIO())
        ended.refresh_from_db()
        running.refresh_from_db()
        self.assertEqual((ended.status, running.status), (Product.STATUS_EXPIRED, Product.STATUS_PUBLISHED))
        entry = AuditLog.objects.get(action="PRODUCT_LISTING_EXPIRED")
        self.assertEqual((entry.target_id, entry.seller), (str(ended.pk), self.limited))

    def test_the_sellers_own_reads_expire_their_products(self):
        product = self.product()
        self.end_period(product)
        rows = self.as_seller(self.limited).get("/api/products/mine/").data["results"]
        self.assertEqual(rows[0]["status"], Product.STATUS_EXPIRED)

    def test_an_expired_product_counts_as_having_gone_live(self):
        product = self.product()
        self.end_period(product, Product.STATUS_EXPIRED)
        self.assertTrue(ProductService.has_gone_live(product))
        self.assertIsNone(ProductService.refund_creation_fee(product))


class RenewalTests(ListingTestCase):
    def renew(self, product, seller=None):
        return self.as_seller(seller or self.limited).post(f"/api/products/mine/{product.pk}/renew/")

    def test_renewal_costs_five_points_and_lasts_two_months(self):
        product = self.product()
        self.end_period(product, Product.STATUS_EXPIRED)
        self.give_points(self.limited, 12)

        response = self.renew(product)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        product.refresh_from_db()
        self.assertEqual((product.status, product.renewal_count), (Product.STATUS_PUBLISHED, 1))
        self.assertTrue(near(product.live_until, add_months(timezone.now(), 2)))
        self.assertIn(product, Product.objects.public())
        self.assertEqual(PointService.get_balance(self.limited), 7)
        fee = PointTransaction.objects.get(transaction_type=PointTransaction.TYPE_LISTING_RENEWAL)
        self.assertEqual((fee.amount, fee.reference_id), (5, str(product.pk)))
        self.assertTrue(AuditLog.objects.filter(action="PRODUCT_LISTING_RENEWED", actor=self.limited.user).exists())

        # Every later renewal is the same.
        self.end_period(product, Product.STATUS_EXPIRED)
        self.assertEqual(self.renew(product).status_code, status.HTTP_200_OK)
        product.refresh_from_db()
        self.assertEqual(product.renewal_count, 2)
        self.assertTrue(near(product.live_until, add_months(timezone.now(), 2)))
        self.assertEqual(PointService.get_balance(self.limited), 2)

    def test_a_period_that_just_ended_can_be_renewed_before_the_sweep(self):
        product = self.product()
        self.end_period(product)
        self.give_points(self.limited, 5)
        self.assertEqual(self.renew(product).status_code, status.HTTP_200_OK)

    def test_renewal_needs_the_points(self):
        product = self.product()
        self.end_period(product, Product.STATUS_EXPIRED)
        response = self.renew(product)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual((response.data["required_points"], response.data["available_points"]), (5, 0))
        product.refresh_from_db()
        self.assertEqual(product.status, Product.STATUS_EXPIRED)

    def test_only_an_expired_product_is_renewed(self):
        product = self.product()
        self.give_points(self.limited, 5)
        response = self.renew(product)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only an expired product", response.data["error"])
        self.assertEqual(PointService.get_balance(self.limited), 5)

    def test_a_closed_shop_cannot_renew(self):
        product = self.product()
        self.end_period(product, Product.STATUS_EXPIRED)
        Shop.objects.filter(pk=self.limited_shop.pk).update(status=Shop.STATUS_SUSPENDED)
        self.give_points(self.limited, 5)
        self.assertEqual(self.renew(product).status_code, status.HTTP_400_BAD_REQUEST)

    def test_another_sellers_product_is_refused(self):
        product = self.product()
        self.end_period(product, Product.STATUS_EXPIRED)
        self.assertEqual(self.renew(product, seller=self.full).status_code, status.HTTP_403_FORBIDDEN)

    def test_a_full_owner_has_nothing_to_renew(self):
        product = self.product(shop=self.full_shop)
        with self.assertRaises(ListingError):
            ListingService.renew(product, self.full)


class LockTests(ListingTestCase):
    def patch(self, product, data):
        return self.as_seller(self.limited).patch(f"/api/products/mine/{product.pk}/", data, format="json")

    def test_a_live_product_cannot_be_hidden(self):
        product = self.product()
        response = self.patch(product, {"is_active": False})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("cannot be hidden", response.data["error"])
        product.refresh_from_db()
        self.assertTrue(product.is_active)

    def test_stock_still_changes_down_to_zero_for_free(self):
        product = self.product()
        self.give_points(self.limited, 5)
        response = self.patch(product, {"stock": 0, "expected_stock": 5})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        # Still on the storefront, shown as out of stock.
        self.assertIn(product, Product.objects.public())
        self.client.force_authenticate(user=None)
        self.assertFalse(self.client.get(f"/api/products/{product.pk}/").data["in_stock"])
        self.assertEqual(PointService.get_balance(self.limited), 5)

        self.assertEqual(self.patch(product, {"stock": 30, "expected_stock": 0}).status_code, status.HTTP_200_OK)

    def test_other_edits_still_work(self):
        product = self.product()
        self.assertEqual(self.patch(product, {"price": "275.00"}).status_code, status.HTTP_200_OK)

    def test_a_live_product_cannot_move_shop(self):
        product = self.product()
        second = Shop.objects.create(
            owner=self.limited, name="Second Tea Shop", slug="listing-second",
            status=Shop.STATUS_ACTIVE, location=Point(90.41, 23.81),
        )
        with self.assertRaises(ListingError):
            ProductService.update_product(product, self.limited, {"shop": second})

    def test_a_live_product_cannot_be_deleted(self):
        product = self.product()
        with self.assertRaises(ListingError):
            ProductService.delete_product(product, self.limited)
        self.assertTrue(Product.objects.filter(pk=product.pk).exists())

    def test_an_expired_product_can_be_hidden(self):
        product = self.product()
        self.end_period(product, Product.STATUS_EXPIRED)
        self.assertEqual(self.patch(product, {"is_active": False}).status_code, status.HTTP_200_OK)

    def test_a_full_owners_product_can_still_be_hidden(self):
        product = self.product(shop=self.full_shop)
        response = self.as_seller(self.full).patch(
            f"/api/products/mine/{product.pk}/", {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class SellerTypeChangeTests(ListingTestCase):
    def change_type(self, seller, seller_type):
        client = Client()
        client.force_login(self.root)
        response = client.post(
            reverse("admin:sellers_sellerprofile_change", args=[seller.pk]),
            {
                "user": str(seller.user_id),
                "seller_type": seller_type,
                "business_name": seller.business_name,
                "business_email": "",
                "business_phone": "",
                "tax_id": "",
                "description": "",
                "rejection_reason": "",
                "suspension_reason": "",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)

    def test_full_made_limited_gets_a_first_period_from_now(self):
        product = self.product(shop=self.full_shop)
        self.change_type(self.full, SellerProfile.TYPE_LIMITED_SHOP_OWNER)
        product.refresh_from_db()
        self.assertTrue(near(product.live_until, add_months(timezone.now(), 4)))
        self.assertTrue(AuditLog.objects.filter(action="SELLER_LISTING_PERIODS_CHANGED").exists())

    def test_limited_made_full_clears_dates_and_restores_expired(self):
        expired, live = self.product(name="Expired"), self.product(name="Live")
        self.end_period(expired, Product.STATUS_EXPIRED)
        self.change_type(self.limited, SellerProfile.TYPE_FULL_SHOP_OWNER)

        expired.refresh_from_db()
        live.refresh_from_db()
        self.assertEqual((expired.status, expired.live_until), (Product.STATUS_PUBLISHED, None))
        self.assertIsNone(live.live_until)
        self.assertIn(expired, Product.objects.public())


class SellerListingApiTests(ListingTestCase):
    def test_the_summary_counts_each_state(self):
        self.product(name="Live")
        soon = self.product(name="Soon")
        Product.objects.filter(pk=soon.pk).update(live_until=timezone.now() + timedelta(days=3))
        self.end_period(self.product(name="Ended"))
        self.product(name="Waiting", publish=False)

        data = self.as_seller(self.limited).get("/api/products/mine/listings/").data
        self.assertEqual(
            {key: data[key] for key in ("total", "live", "ending_soon", "expired", "in_review", "not_live")},
            {"total": 4, "live": 2, "ending_soon": 1, "expired": 1, "in_review": 1, "not_live": 0},
        )
        self.assertTrue(data["has_end_date"])
        self.assertEqual(
            (data["first_period_months"], data["renewal_period_months"], data["renewal_points"]), (4, 2, 5)
        )

    def test_the_list_filters_by_listing_state(self):
        live = self.product(name="Live")
        soon = self.product(name="Soon")
        Product.objects.filter(pk=soon.pk).update(live_until=timezone.now() + timedelta(days=3))
        ended = self.product(name="Ended")
        self.end_period(ended)
        client = self.as_seller(self.limited)

        def ids(listing):
            return [row["id"] for row in client.get(f"/api/products/mine/?listing={listing}").data["results"]]

        self.assertEqual(ids("live"), [soon.pk, live.pk])
        self.assertEqual(ids("ending_soon"), [soon.pk])
        self.assertEqual(ids("expired"), [ended.pk])
        self.assertEqual(client.get("/api/products/mine/?listing=bogus").status_code, status.HTTP_400_BAD_REQUEST)

    def test_seller_rows_carry_the_listing_fields(self):
        product = self.product()
        row = self.as_seller(self.limited).get(f"/api/products/mine/{product.pk}/").data
        self.assertEqual((row["renewal_count"], row["listing_locked"]), (0, True))
        self.assertIsNotNone(row["live_until"])


class BackfillMigrationTests(ListingTestCase):
    def test_live_products_of_limited_owners_get_four_months_from_today(self):
        limited = self.product(name="Limited")
        full = self.product(shop=self.full_shop, name="Full")
        Product.objects.filter(pk=limited.pk).update(live_until=None)

        migration = import_module("shop.migrations.0011_product_listing_period")
        migration.date_live_listings(apps, None)

        limited.refresh_from_db()
        full.refresh_from_db()
        self.assertTrue(near(limited.live_until, add_months(timezone.now(), 4)))
        self.assertIsNone(full.live_until)

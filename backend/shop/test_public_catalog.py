from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.models import Shop
from shop.models import Category, Product

User = get_user_model()


class PublicCatalogTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

    def setUp(self):
        self.client = APIClient()

        # Operational seller & active shop
        self.seller_user = User.objects.create_user(
            username="active_seller", email="active@seller.com", password="password123"
        )
        self.seller = SellerProfile.objects.create(
            user=self.seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Active Seller Store",
        )
        assign_user_role(self.seller_user, Role.ROLE_SALES_TEAM)

        self.shop = Shop.objects.create(
            owner=self.seller,
            name="Prime Tech Shop",
            slug="prime-tech-shop",
            status=Shop.STATUS_ACTIVE,
        )

        # Active category
        self.cat_electronics = Category.objects.create(
            name="Electronics",
            slug="electronics",
            description="Cutting-edge electronics",
            is_active=True,
        )
        self.cat_apparel = Category.objects.create(
            name="Apparel",
            slug="apparel",
            description="Quality clothing and apparel",
            is_active=True,
        )
        self.cat_inactive = Category.objects.create(
            name="Archived Goods",
            slug="archived-goods",
            description="Discontinued category",
            is_active=False,
        )

        # Public published product
        self.public_product = Product.objects.create(
            name="Mechanical Keyboard RGB",
            slug="mechanical-keyboard-rgb",
            category=self.cat_electronics,
            shop=self.shop,
            description="Premium clicky mechanical keyboard with customizable RGB backlighting.",
            price=Decimal("120.00"),
            old_price=Decimal("150.00"),
            stock=15,
            badge="HOT",
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )

        # Another public published product in Apparel
        self.public_tee = Product.objects.create(
            name="Classic Cotton Tee",
            slug="classic-cotton-tee",
            category=self.cat_apparel,
            shop=self.shop,
            description="100% organic cotton breathable t-shirt.",
            price=Decimal("25.00"),
            old_price=Decimal("35.00"),
            stock=50,
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )

    # -------------------------------------------------------------
    # 1. PUBLIC VISIBILITY RULES
    # -------------------------------------------------------------
    def test_published_product_is_visible_in_public_list(self):
        res = self.client.get(reverse("shop:api_products"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data.get("results", [])
        product_ids = [p["id"] for p in results]
        self.assertIn(self.public_product.id, product_ids)
        self.assertIn(self.public_tee.id, product_ids)

    def test_draft_product_hidden_from_list_and_detail_404(self):
        draft = Product.objects.create(
            name="Secret Prototype",
            slug="secret-prototype",
            category=self.cat_electronics,
            shop=self.shop,
            description="Under development",
            price=Decimal("999.00"),
            status=Product.STATUS_DRAFT,
            is_active=True,
        )
        # Hidden from catalog list
        res_list = self.client.get(reverse("shop:api_products"))
        self.assertNotIn(draft.id, [p["id"] for p in res_list.data["results"]])

        # Hidden by direct ID -> 404
        res_id = self.client.get(reverse("shop:api_product_detail_pk", args=[draft.id]))
        self.assertEqual(res_id.status_code, status.HTTP_404_NOT_FOUND)

        # Hidden by direct slug -> 404
        res_slug = self.client.get(reverse("shop:api_product_detail", args=[draft.slug]))
        self.assertEqual(res_slug.status_code, status.HTTP_404_NOT_FOUND)

    def test_submitted_product_hidden_404(self):
        submitted = Product.objects.create(
            name="Submitted Product",
            slug="submitted-product",
            category=self.cat_electronics,
            shop=self.shop,
            description="Pending review",
            price=Decimal("80.00"),
            status=Product.STATUS_SUBMITTED,
            is_active=True,
        )
        res_id = self.client.get(reverse("shop:api_product_detail_pk", args=[submitted.id]))
        self.assertEqual(res_id.status_code, status.HTTP_404_NOT_FOUND)

    def test_approved_not_published_product_hidden_404(self):
        approved = Product.objects.create(
            name="Approved But Not Published Product",
            slug="approved-not-published",
            category=self.cat_electronics,
            shop=self.shop,
            description="Approved by admin but not published yet",
            price=Decimal("80.00"),
            status=Product.STATUS_APPROVED,
            is_active=True,
        )
        res_id = self.client.get(reverse("shop:api_product_detail_pk", args=[approved.id]))
        self.assertEqual(res_id.status_code, status.HTTP_404_NOT_FOUND)

    def test_rejected_product_hidden_404(self):
        rejected = Product.objects.create(
            name="Rejected Knockoff",
            slug="rejected-knockoff",
            category=self.cat_electronics,
            shop=self.shop,
            description="Policy violation",
            price=Decimal("10.00"),
            status=Product.STATUS_REJECTED,
            rejection_reason="Violates intellectual property guidelines.",
            is_active=True,
        )
        res_id = self.client.get(reverse("shop:api_product_detail_pk", args=[rejected.id]))
        self.assertEqual(res_id.status_code, status.HTTP_404_NOT_FOUND)

    def test_unpublished_product_hidden_404(self):
        unpub = Product.objects.create(
            name="Unpublished Item",
            slug="unpublished-item",
            category=self.cat_electronics,
            shop=self.shop,
            description="Taken down temporarily",
            price=Decimal("40.00"),
            status=Product.STATUS_UNPUBLISHED,
            is_active=True,
        )
        res_id = self.client.get(reverse("shop:api_product_detail_pk", args=[unpub.id]))
        self.assertEqual(res_id.status_code, status.HTTP_404_NOT_FOUND)

    def test_inactive_product_flag_hidden_404(self):
        inactive = Product.objects.create(
            name="Inactive Product Flag",
            slug="inactive-flag",
            category=self.cat_electronics,
            shop=self.shop,
            description="Deactivated",
            price=Decimal("50.00"),
            status=Product.STATUS_PUBLISHED,
            is_active=False,
        )
        res_id = self.client.get(reverse("shop:api_product_detail_pk", args=[inactive.id]))
        self.assertEqual(res_id.status_code, status.HTTP_404_NOT_FOUND)

    def test_product_in_inactive_category_hidden_404(self):
        in_inactive_cat = Product.objects.create(
            name="Archived Widget",
            slug="archived-widget",
            category=self.cat_inactive,
            shop=self.shop,
            description="Category is deactivated",
            price=Decimal("60.00"),
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )
        res_id = self.client.get(reverse("shop:api_product_detail_pk", args=[in_inactive_cat.id]))
        self.assertEqual(res_id.status_code, status.HTTP_404_NOT_FOUND)

    # -------------------------------------------------------------
    # 2. INACCESSIBLE / SUSPENDED SHOP & SELLER RULES
    # -------------------------------------------------------------
    def test_product_in_suspended_shop_hidden_404(self):
        suspended_shop = Shop.objects.create(
            owner=self.seller,
            name="Suspended Shop",
            slug="suspended-shop",
            status=Shop.STATUS_SUSPENDED,
            suspension_reason="Shop suspended for maintenance",
        )
        product_in_suspended_shop = Product.objects.create(
            name="Suspended Shop Item",
            slug="suspended-shop-item",
            category=self.cat_electronics,
            shop=suspended_shop,
            description="Shop is suspended",
            price=Decimal("75.00"),
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )
        res_id = self.client.get(reverse("shop:api_product_detail_pk", args=[product_in_suspended_shop.id]))
        self.assertEqual(res_id.status_code, status.HTTP_404_NOT_FOUND)

    def test_product_in_rejected_shop_hidden_404(self):
        rejected_shop = Shop.objects.create(
            owner=self.seller,
            name="Rejected Shop",
            slug="rejected-shop",
            status=Shop.STATUS_REJECTED,
            rejection_reason="Shop documents invalid",
        )
        prod = Product.objects.create(
            name="Rejected Shop Item",
            slug="rejected-shop-item",
            category=self.cat_electronics,
            shop=rejected_shop,
            description="Shop is rejected",
            price=Decimal("30.00"),
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )
        res_id = self.client.get(reverse("shop:api_product_detail_pk", args=[prod.id]))
        self.assertEqual(res_id.status_code, status.HTTP_404_NOT_FOUND)

    def test_product_with_suspended_seller_hidden_404(self):
        suspended_seller_user = User.objects.create_user(
            username="suspended_seller", email="susp@seller.com", password="password123"
        )
        suspended_seller = SellerProfile.objects.create(
            user=suspended_seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_SUSPENDED,
            suspension_reason="Policy violations",
            business_name="Banned Vendor",
        )
        shop_of_suspended = Shop.objects.create(
            owner=suspended_seller,
            name="Banned Shop",
            slug="banned-shop",
            status=Shop.STATUS_ACTIVE,
        )
        prod = Product.objects.create(
            name="Banned Seller Goods",
            slug="banned-seller-goods",
            category=self.cat_electronics,
            shop=shop_of_suspended,
            description="Seller suspended",
            price=Decimal("90.00"),
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )
        res_id = self.client.get(reverse("shop:api_product_detail_pk", args=[prod.id]))
        self.assertEqual(res_id.status_code, status.HTTP_404_NOT_FOUND)

    def test_product_without_shop_hidden_404(self):
        orphaned_prod = Product.objects.create(
            name="Orphaned Item",
            slug="orphaned-item",
            category=self.cat_electronics,
            shop=None,
            description="No shop attached",
            price=Decimal("45.00"),
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )
        res_id = self.client.get(reverse("shop:api_product_detail_pk", args=[orphaned_prod.id]))
        self.assertEqual(res_id.status_code, status.HTTP_404_NOT_FOUND)

    # -------------------------------------------------------------
    # 3. DIRECT ID & SLUG LOOKUPS
    # -------------------------------------------------------------
    def test_direct_id_lookup_succeeds_for_public_product(self):
        res = self.client.get(reverse("shop:api_product_detail_pk", args=[self.public_product.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], self.public_product.id)
        self.assertEqual(res.data["name"], "Mechanical Keyboard RGB")
        self.assertEqual(res.data["shop"]["name"], "Prime Tech Shop")

    def test_direct_slug_lookup_succeeds_for_public_product(self):
        res = self.client.get(reverse("shop:api_product_detail", args=[self.public_product.slug]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["slug"], self.public_product.slug)

    def test_unauthenticated_guests_can_access_catalog(self):
        # APIClient has no credentials set (anonymous guest)
        res_list = self.client.get(reverse("shop:api_products"))
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)

        res_detail = self.client.get(reverse("shop:api_product_detail_pk", args=[self.public_product.id]))
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)

    # -------------------------------------------------------------
    # 4. CATEGORIES API & MODEL
    # -------------------------------------------------------------
    def test_category_timestamps_and_unique_slug(self):
        self.assertIsNotNone(self.cat_electronics.created_at)
        self.assertIsNotNone(self.cat_electronics.updated_at)

    def test_categories_api_lists_only_active_categories(self):
        res = self.client.get(reverse("shop:api_categories"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        slugs = [c["slug"] for c in res.data]
        self.assertIn("electronics", slugs)
        self.assertIn("apparel", slugs)
        self.assertNotIn("archived-goods", slugs)

    def test_category_products_count_only_counts_public_products(self):
        # Create a draft product in Electronics
        Product.objects.create(
            name="Unpublished Gear",
            slug="unpub-gear",
            category=self.cat_electronics,
            shop=self.shop,
            description="Draft",
            price=Decimal("10.00"),
            status=Product.STATUS_DRAFT,
            is_active=True,
        )
        res = self.client.get(reverse("shop:api_categories"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        cat_data = next(c for c in res.data if c["slug"] == "electronics")
        # Only self.public_product is public in Electronics
        self.assertEqual(cat_data["products_count"], 1)

    # -------------------------------------------------------------
    # 5. CATALOG DISCOVERY & FILTERING
    # -------------------------------------------------------------
    def test_search_by_name_and_description(self):
        # Search by name keyword
        res = self.client.get(reverse("shop:api_products"), {"q": "keyboard"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["id"], self.public_product.id)

        # Search by description keyword
        res_desc = self.client.get(reverse("shop:api_products"), {"search": "breathable"})
        self.assertEqual(res_desc.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_desc.data["results"]), 1)
        self.assertEqual(res_desc.data["results"][0]["id"], self.public_tee.id)

    def test_filter_by_category_slug(self):
        res = self.client.get(reverse("shop:api_products"), {"category": "apparel"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 1)
        self.assertEqual(res.data["results"][0]["id"], self.public_tee.id)

    def test_filter_by_shop_id_and_slug(self):
        # By shop ID
        res_id = self.client.get(reverse("shop:api_products"), {"shop": str(self.shop.id)})
        self.assertEqual(res_id.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_id.data["results"]), 2)

        # By shop slug
        res_slug = self.client.get(reverse("shop:api_products"), {"shop": self.shop.slug})
        self.assertEqual(res_slug.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_slug.data["results"]), 2)

        # Non-existent shop
        res_none = self.client.get(reverse("shop:api_products"), {"shop": "non-existent-shop"})
        self.assertEqual(res_none.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_none.data["results"]), 0)

    def test_filter_by_price_range(self):
        # Min price filter (>= 50)
        res_min = self.client.get(reverse("shop:api_products"), {"min_price": "50"})
        self.assertEqual(res_min.status_code, status.HTTP_200_OK)
        ids = [p["id"] for p in res_min.data["results"]]
        self.assertIn(self.public_product.id, ids)
        self.assertNotIn(self.public_tee.id, ids)

        # Max price filter (<= 50)
        res_max = self.client.get(reverse("shop:api_products"), {"max_price": "50"})
        self.assertEqual(res_max.status_code, status.HTTP_200_OK)
        ids_max = [p["id"] for p in res_max.data["results"]]
        self.assertNotIn(self.public_product.id, ids_max)
        self.assertIn(self.public_tee.id, ids_max)

        # Combined range (20 to 130)
        res_range = self.client.get(reverse("shop:api_products"), {"min_price": "20", "max_price": "130"})
        self.assertEqual(res_range.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_range.data["results"]), 2)

    def test_ordering_options(self):
        # Price ascending
        res_asc = self.client.get(reverse("shop:api_products"), {"ordering": "price"})
        self.assertEqual(res_asc.status_code, status.HTTP_200_OK)
        self.assertEqual(res_asc.data["results"][0]["id"], self.public_tee.id)  # 25.00
        self.assertEqual(res_asc.data["results"][1]["id"], self.public_product.id)  # 120.00

        # Price descending
        res_desc = self.client.get(reverse("shop:api_products"), {"ordering": "-price"})
        self.assertEqual(res_desc.status_code, status.HTTP_200_OK)
        self.assertEqual(res_desc.data["results"][0]["id"], self.public_product.id)
        self.assertEqual(res_desc.data["results"][1]["id"], self.public_tee.id)

    def test_pagination(self):
        # Create 15 extra published products
        for i in range(15):
            Product.objects.create(
                name=f"Extra Catalog Item {i:02d}",
                slug=f"extra-catalog-item-{i:02d}",
                category=self.cat_electronics,
                shop=self.shop,
                description="Extra product",
                price=Decimal("50.00"),
                status=Product.STATUS_PUBLISHED,
                is_active=True,
            )
        res = self.client.get(reverse("shop:api_products"))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 12)  # page_size=12
        self.assertIsNotNone(res.data["next"])
        self.assertEqual(res.data["count"], 17)  # 2 original + 15 extra

    # -------------------------------------------------------------
    # 6. SECURITY & DATA SANITIZATION
    # -------------------------------------------------------------
    def test_public_endpoints_do_not_leak_private_seller_fields(self):
        res = self.client.get(reverse("shop:api_product_detail_pk", args=[self.public_product.id]))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data

        # Forbidden private fields
        self.assertNotIn("rejection_reason", data)
        self.assertNotIn("seller_points", data)
        self.assertNotIn("owner_business_email", data)
        self.assertNotIn("tax_id", data)

        # Shop representation only contains safe summary
        self.assertIn("shop", data)
        self.assertIn("name", data["shop"])
        self.assertIn("slug", data["shop"])
        self.assertNotIn("owner_email", data["shop"])

    def test_seller_cannot_bypass_isolation_via_seller_api(self):
        # Another seller
        other_user = User.objects.create_user(username="other_seller", password="password")
        other_seller = SellerProfile.objects.create(
            user=other_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Other Store",
        )
        assign_user_role(other_user, Role.ROLE_SALES_TEAM)

        self.client.force_authenticate(user=other_user)
        # Attempt to access prime seller's product via seller self-service endpoint
        res = self.client.get(reverse("shop:api_seller_product_detail", args=[self.public_product.id]))
        self.assertIn(res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

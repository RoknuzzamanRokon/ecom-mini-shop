from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from rest_framework import status
from rest_framework.test import APITestCase

from cart.models import Cart, CartItem
from cart.services import CartService
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.models import Shop
from shop.models import Category, Product

User = get_user_model()


class CartTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        # Create seller & active shop
        cls.seller_user = User.objects.create_user(
            username="cart_seller",
            email="seller@example.com",
            password="Password123!",
        )
        cls.seller = SellerProfile.objects.create(
            user=cls.seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Cart Test Merchant",
        )
        cls.shop = Shop.objects.create(
            owner=cls.seller,
            name="Cart Test Shop",
            slug="cart-test-shop",
            status=Shop.STATUS_ACTIVE,
        )

        # Categories
        cls.active_cat = Category.objects.create(name="Active Category", slug="active-cat", is_active=True)
        cls.inactive_cat = Category.objects.create(name="Inactive Category", slug="inactive-cat", is_active=False)

        # Products
        cls.product_1 = Product.objects.create(
            name="Mechanical Keyboard",
            slug="mech-keyboard",
            category=cls.active_cat,
            shop=cls.shop,
            price=Decimal("150.00"),
            stock=20,
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )
        cls.product_2 = Product.objects.create(
            name="Gaming Mouse",
            slug="gaming-mouse",
            category=cls.active_cat,
            shop=cls.shop,
            price=Decimal("50.00"),
            stock=15,
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )
        cls.draft_product = Product.objects.create(
            name="Unpublished Headset",
            slug="unpub-headset",
            category=cls.active_cat,
            shop=cls.shop,
            price=Decimal("80.00"),
            stock=5,
            status=Product.STATUS_DRAFT,
            is_active=True,
        )
        cls.inactive_cat_product = Product.objects.create(
            name="Old Monitor",
            slug="old-monitor",
            category=cls.inactive_cat,
            shop=cls.shop,
            price=Decimal("200.00"),
            stock=5,
            status=Product.STATUS_PUBLISHED,
            is_active=True,
        )

        # Customers
        cls.customer_user = User.objects.create_user(
            username="customer_user",
            email="customer@example.com",
            password="Password123!",
        )
        assign_user_role(cls.customer_user, Role.ROLE_CUSTOMER)

        cls.other_customer = User.objects.create_user(
            username="other_customer",
            email="other@example.com",
            password="Password123!",
        )
        assign_user_role(cls.other_customer, Role.ROLE_CUSTOMER)

        cls.plain_user = User.objects.create_user(
            username="plain_user",
            email="plain@example.com",
            password="Password123!",
        )

    # -------------------------------------------------------------------------
    # 1. Empty Cart & Auto Initialization
    # -------------------------------------------------------------------------
    def test_get_empty_cart_auto_initialization(self):
        """Authenticated customer can retrieve empty cart; cart is automatically initialized."""
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.get("/api/cart/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["total_items_count"], 0)
        self.assertEqual(Decimal(str(response.data["total_amount"])), Decimal("0.00"))
        self.assertFalse(response.data["has_unavailable_items"])

        # Check DB Cart created
        self.assertTrue(Cart.objects.filter(user=self.customer_user).exists())

    # -------------------------------------------------------------------------
    # 2. Adding Items & Duplicate Handling
    # -------------------------------------------------------------------------
    def test_add_item_to_cart_success(self):
        """Customer can add a published product to their cart."""
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.post("/api/cart/items/", {"product_id": self.product_1.id, "quantity": 2})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["total_items_count"], 2)
        self.assertEqual(Decimal(str(response.data["total_amount"])), Decimal("300.00"))
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["quantity"], 2)
        self.assertEqual(Decimal(str(response.data["items"][0]["unit_price"])), Decimal("150.00"))
        self.assertEqual(Decimal(str(response.data["items"][0]["line_total"])), Decimal("300.00"))
        self.assertTrue(response.data["items"][0]["is_available"])

    def test_add_item_increments_existing_quantity(self):
        """Adding an existing product in the cart increments its quantity rather than creating duplicates."""
        self.client.force_authenticate(user=self.customer_user)
        self.client.post("/api/cart/items/", {"product_id": self.product_1.id, "quantity": 2})
        response = self.client.post("/api/cart/items/", {"product_id": self.product_1.id, "quantity": 3})

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["total_items_count"], 5)
        self.assertEqual(len(response.data["items"]), 1)
        self.assertEqual(response.data["items"][0]["quantity"], 5)
        self.assertEqual(Decimal(str(response.data["items"][0]["line_total"])), Decimal("750.00"))
        self.assertEqual(CartItem.objects.filter(cart__user=self.customer_user).count(), 1)

    # -------------------------------------------------------------------------
    # 3. Authoritative Pricing
    # -------------------------------------------------------------------------
    def test_authoritative_pricing_ignores_client_input(self):
        """Client-provided prices in the payload are strictly ignored; price is derived from Product."""
        self.client.force_authenticate(user=self.customer_user)
        payload = {
            "product_id": self.product_1.id,
            "quantity": 1,
            "price": "1.00",
            "unit_price": "1.00",
            "line_total": "1.00",
        }
        response = self.client.post("/api/cart/items/", payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item = response.data["items"][0]
        self.assertEqual(Decimal(str(item["unit_price"])), Decimal("150.00"))
        self.assertEqual(Decimal(str(item["line_total"])), Decimal("150.00"))
        self.assertEqual(Decimal(str(response.data["total_amount"])), Decimal("150.00"))

    def test_dynamic_price_recalculation_on_product_change(self):
        """When product price is updated in DB, cart reflects the new price dynamically."""
        self.client.force_authenticate(user=self.customer_user)
        self.client.post("/api/cart/items/", {"product_id": self.product_1.id, "quantity": 2})

        # Update product price in DB
        self.product_1.price = Decimal("175.50")
        self.product_1.save(update_fields=["price"])

        response = self.client.get("/api/cart/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data["items"][0]
        self.assertEqual(Decimal(str(item["unit_price"])), Decimal("175.50"))
        self.assertEqual(Decimal(str(item["line_total"])), Decimal("351.00"))
        self.assertEqual(Decimal(str(response.data["total_amount"])), Decimal("351.00"))

        # Restore product price
        self.product_1.price = Decimal("150.00")
        self.product_1.save(update_fields=["price"])

    # -------------------------------------------------------------------------
    # 4. Product Eligibility Checks
    # -------------------------------------------------------------------------
    def test_add_non_public_draft_product_rejected(self):
        """Cannot add a DRAFT product to cart."""
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.post("/api/cart/items/", {"product_id": self.draft_product.id, "quantity": 1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product_id", response.data)

    def test_add_product_from_inactive_category_rejected(self):
        """Cannot add a product whose category is inactive."""
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.post("/api/cart/items/", {"product_id": self.inactive_cat_product.id, "quantity": 1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product_id", response.data)

    def test_add_non_existent_product_rejected(self):
        """Cannot add a product that does not exist."""
        self.client.force_authenticate(user=self.customer_user)
        response = self.client.post("/api/cart/items/", {"product_id": 999999, "quantity": 1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product_id", response.data)

    # -------------------------------------------------------------------------
    # 5. Stale Item Handling
    # -------------------------------------------------------------------------
    def test_stale_item_handling_when_product_becomes_unavailable(self):
        """
        If an item in the cart becomes non-public later (e.g. unpublished),
        it is marked is_available=False, has_unavailable_items=True, and
        excluded from total_amount and total_items_count.
        """
        self.client.force_authenticate(user=self.customer_user)
        # Add product_1 (150.00 x 2 = 300.00) and product_2 (50.00 x 1 = 50.00)
        self.client.post("/api/cart/items/", {"product_id": self.product_1.id, "quantity": 2})
        self.client.post("/api/cart/items/", {"product_id": self.product_2.id, "quantity": 1})

        # Unpublish product_1
        self.product_1.status = Product.STATUS_DRAFT
        self.product_1.save(update_fields=["status"])

        response = self.client.get("/api/cart/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["has_unavailable_items"])
        self.assertEqual(response.data["total_items_count"], 1)  # Only product_2
        self.assertEqual(Decimal(str(response.data["total_amount"])), Decimal("50.00"))

        # Verify items
        items = {item["product"]["id"]: item for item in response.data["items"]}
        self.assertFalse(items[self.product_1.id]["is_available"])
        self.assertIn("no longer published", items[self.product_1.id]["unavailable_reason"])
        self.assertTrue(items[self.product_2.id]["is_available"])

        # Restore product_1
        self.product_1.status = Product.STATUS_PUBLISHED
        self.product_1.save(update_fields=["status"])

    # -------------------------------------------------------------------------
    # 6. Quantity Updates & Limits
    # -------------------------------------------------------------------------
    def test_update_item_quantity_success(self):
        """Customer can update the quantity of an item in their cart."""
        self.client.force_authenticate(user=self.customer_user)
        add_resp = self.client.post("/api/cart/items/", {"product_id": self.product_1.id, "quantity": 2})
        item_id = add_resp.data["items"][0]["id"]

        patch_resp = self.client.patch(f"/api/cart/items/{item_id}/", {"quantity": 5})
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_resp.data["total_items_count"], 5)
        self.assertEqual(Decimal(str(patch_resp.data["total_amount"])), Decimal("750.00"))

    def test_quantity_boundary_validation(self):
        """Quantities <= 0 or > 99 are rejected."""
        self.client.force_authenticate(user=self.customer_user)
        add_resp = self.client.post("/api/cart/items/", {"product_id": self.product_1.id, "quantity": 2})
        item_id = add_resp.data["items"][0]["id"]

        # 0 is rejected
        resp_zero = self.client.patch(f"/api/cart/items/{item_id}/", {"quantity": 0})
        self.assertEqual(resp_zero.status_code, status.HTTP_400_BAD_REQUEST)

        # Negative is rejected
        resp_neg = self.client.patch(f"/api/cart/items/{item_id}/", {"quantity": -1})
        self.assertEqual(resp_neg.status_code, status.HTTP_400_BAD_REQUEST)

        # > 99 is rejected
        resp_max = self.client.patch(f"/api/cart/items/{item_id}/", {"quantity": 100})
        self.assertEqual(resp_max.status_code, status.HTTP_400_BAD_REQUEST)

    # -------------------------------------------------------------------------
    # 7. Item Removal & Cart Clearing
    # -------------------------------------------------------------------------
    def test_remove_item_from_cart(self):
        """Customer can remove a specific item from their cart."""
        self.client.force_authenticate(user=self.customer_user)
        add_resp = self.client.post("/api/cart/items/", {"product_id": self.product_1.id, "quantity": 1})
        item_id = add_resp.data["items"][0]["id"]

        del_resp = self.client.delete(f"/api/cart/items/{item_id}/")
        self.assertEqual(del_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(del_resp.data["items"], [])
        self.assertEqual(del_resp.data["total_items_count"], 0)
        self.assertFalse(CartItem.objects.filter(pk=item_id).exists())

    def test_clear_entire_cart(self):
        """Customer can clear all items from their cart via DELETE /api/cart/."""
        self.client.force_authenticate(user=self.customer_user)
        self.client.post("/api/cart/items/", {"product_id": self.product_1.id, "quantity": 1})
        self.client.post("/api/cart/items/", {"product_id": self.product_2.id, "quantity": 2})

        clear_resp = self.client.delete("/api/cart/")
        self.assertEqual(clear_resp.status_code, status.HTTP_204_NO_CONTENT)

        get_resp = self.client.get("/api/cart/")
        self.assertEqual(get_resp.data["items"], [])
        self.assertEqual(get_resp.data["total_items_count"], 0)

    # -------------------------------------------------------------------------
    # 8. Security & User Isolation
    # -------------------------------------------------------------------------
    def test_unauthenticated_requests_rejected(self):
        """Unauthenticated requests to cart endpoints return 401."""
        self.assertEqual(self.client.get("/api/cart/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.post("/api/cart/items/", {}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.patch("/api/cart/items/1/", {}).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.delete("/api/cart/items/1/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.delete("/api/cart/").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_without_cart_permission_forbidden(self):
        """User without cart permissions receives 403."""
        self.client.force_authenticate(user=self.plain_user)
        response = self.client.get("/api/cart/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_cannot_access_or_modify_another_users_cart(self):
        """User B cannot see or modify User A's cart items."""
        # Customer User adds item
        self.client.force_authenticate(user=self.customer_user)
        add_resp = self.client.post("/api/cart/items/", {"product_id": self.product_1.id, "quantity": 2})
        user_a_item_id = add_resp.data["items"][0]["id"]

        # Other Customer logs in
        self.client.force_authenticate(user=self.other_customer)
        other_cart = self.client.get("/api/cart/")
        self.assertEqual(other_cart.data["items"], [])

        # Attempt to patch User A's item
        patch_resp = self.client.patch(f"/api/cart/items/{user_a_item_id}/", {"quantity": 10})
        self.assertEqual(patch_resp.status_code, status.HTTP_404_NOT_FOUND)

        # Attempt to delete User A's item
        del_resp = self.client.delete(f"/api/cart/items/{user_a_item_id}/")
        self.assertEqual(del_resp.status_code, status.HTTP_404_NOT_FOUND)

        # Verify User A's item unchanged
        item = CartItem.objects.get(pk=user_a_item_id)
        self.assertEqual(item.quantity, 2)

    # -------------------------------------------------------------------------
    # 9. Database-level Constraints
    # -------------------------------------------------------------------------
    def test_database_level_unique_constraint(self):
        """Database enforces unique constraint on (cart, product)."""
        cart = CartService.get_or_create_cart(self.customer_user)
        CartItem.objects.create(cart=cart, product=self.product_1, quantity=1)
        with self.assertRaises(IntegrityError):
            CartItem.objects.create(cart=cart, product=self.product_1, quantity=2)

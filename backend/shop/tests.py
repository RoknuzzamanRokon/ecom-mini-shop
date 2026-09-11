from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from sellers.models import SellerProfile
from shops.models import Shop
from .models import Category, Order, OrderItem, Product

User = get_user_model()


class ShopTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test_merchant", password="password")
        self.seller = SellerProfile.objects.create(
            user=self.user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Tech Merchant",
        )
        self.shop = Shop.objects.create(
            owner=self.seller,
            name="Tech Shop",
            slug="tech-shop",
            status=Shop.STATUS_ACTIVE,
        )

        self.electronics = Category.objects.create(name="Electronics", icon="devices")
        self.clothing = Category.objects.create(name="Clothing", icon="checkroom")

        self.keyboard = Product.objects.create(
            name="Custom Mechanical Keyboard",
            category=self.electronics,
            shop=self.shop,
            description="A great keyboard.",
            price=Decimal("148.00"),
            old_price=Decimal("180.00"),
            stock=10,
            badge="NEW",
            status=Product.STATUS_PUBLISHED,
        )
        self.tee = Product.objects.create(
            name="Organic Heavyweight Tee",
            category=self.clothing,
            shop=self.shop,
            description="A soft tee.",
            price=Decimal("42.00"),
            stock=0,
            status=Product.STATUS_PUBLISHED,
        )


class ProductListViewTests(ShopTestCase):
    def test_homepage_loads(self):
        response = self.client.get(reverse("shop:product_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Custom Mechanical Keyboard")

    def test_products_come_from_database(self):
        response = self.client.get(reverse("shop:product_list"))
        product_ids = {product.id for product in response.context["products"]}
        self.assertEqual(product_ids, set(Product.objects.values_list("id", flat=True)))

    def test_category_filter(self):
        response = self.client.get(reverse("shop:category", args=[self.electronics.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Custom Mechanical Keyboard")
        self.assertNotContains(response, "Organic Heavyweight Tee")

    def test_search_by_name(self):
        response = self.client.get(reverse("shop:product_list"), {"q": "keyboard"})
        self.assertContains(response, "Custom Mechanical Keyboard")
        self.assertNotContains(response, "Organic Heavyweight Tee")

    def test_search_by_category_name(self):
        response = self.client.get(reverse("shop:product_list"), {"q": "clothing"})
        product_ids = {product.id for product in response.context["products"]}
        self.assertEqual(product_ids, {self.tee.id})

    def test_pagination(self):
        for i in range(15):
            Product.objects.create(
                name=f"Extra Product {i}",
                category=self.electronics,
                shop=self.shop,
                description="x",
                price=Decimal("10.00"),
                stock=5,
                status=Product.STATUS_PUBLISHED,
            )
        response = self.client.get(reverse("shop:product_list"))
        self.assertEqual(len(response.context["page_obj"].object_list), 12)
        self.assertTrue(response.context["page_obj"].has_next())


class ProductDetailViewTests(ShopTestCase):
    def test_product_detail_loads(self):
        response = self.client.get(reverse("shop:product_detail", args=[self.keyboard.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Custom Mechanical Keyboard")
        self.assertContains(response, "148.00")


class CartTests(ShopTestCase):
    def test_add_to_cart(self):
        response = self.client.post(
            reverse("shop:cart_add", args=[self.keyboard.id]), {"quantity": 2}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["cart"], {str(self.keyboard.id): 2})

    def test_cart_page_shows_items_and_total(self):
        self.client.post(reverse("shop:cart_add", args=[self.keyboard.id]), {"quantity": 2})
        response = self.client.get(reverse("shop:cart"))
        self.assertContains(response, "Custom Mechanical Keyboard")
        self.assertEqual(response.context["total"], Decimal("296.00"))

    def test_increase_quantity(self):
        self.client.post(reverse("shop:cart_add", args=[self.keyboard.id]), {"quantity": 1})
        self.client.post(reverse("shop:cart_increase", args=[self.keyboard.id]))
        self.assertEqual(self.client.session["cart"][str(self.keyboard.id)], 2)

    def test_decrease_quantity_removes_at_zero(self):
        self.client.post(reverse("shop:cart_add", args=[self.keyboard.id]), {"quantity": 1})
        self.client.post(reverse("shop:cart_decrease", args=[self.keyboard.id]))
        self.assertNotIn(str(self.keyboard.id), self.client.session.get("cart", {}))

    def test_remove_from_cart(self):
        self.client.post(reverse("shop:cart_add", args=[self.keyboard.id]), {"quantity": 3})
        self.client.post(reverse("shop:cart_remove", args=[self.keyboard.id]))
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_empty_cart_message(self):
        response = self.client.get(reverse("shop:cart"))
        self.assertContains(response, "Your cart is empty")


class CheckoutTests(ShopTestCase):
    def test_checkout_redirects_when_cart_empty(self):
        response = self.client.get(reverse("shop:checkout"))
        self.assertRedirects(response, reverse("shop:cart"))

    def test_checkout_requires_fields(self):
        self.client.post(reverse("shop:cart_add", args=[self.keyboard.id]), {"quantity": 1})
        response = self.client.post(reverse("shop:checkout"), {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())
        self.assertContains(response, "This field is required")

    def test_successful_checkout_creates_order_and_clears_cart(self):
        self.client.post(reverse("shop:cart_add", args=[self.keyboard.id]), {"quantity": 2})
        response = self.client.post(
            reverse("shop:checkout"),
            {
                "full_name": "Jane Doe",
                "phone": "+1234567890",
                "address": "123 Main St",
                "city": "Springfield",
            },
        )
        order = Order.objects.get()
        self.assertRedirects(response, reverse("shop:order_success", args=[order.id]))
        self.assertEqual(order.total_amount, Decimal("296.00"))
        self.assertEqual(OrderItem.objects.filter(order=order).count(), 1)
        self.assertEqual(self.client.session.get("cart", {}), {})

    def test_order_success_page(self):
        self.client.post(reverse("shop:cart_add", args=[self.keyboard.id]), {"quantity": 1})
        self.client.post(
            reverse("shop:checkout"),
            {
                "full_name": "Jane Doe",
                "phone": "+1234567890",
                "address": "123 Main St",
                "city": "Springfield",
            },
        )
        order = Order.objects.get()
        response = self.client.get(reverse("shop:order_success", args=[order.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, order.order_number)
        self.assertContains(response, "Jane Doe")


class APITests(ShopTestCase):
    def test_api_categories(self):
        response = self.client.get(reverse("shop:api_categories"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        cat_names = [c["name"] for c in data]
        self.assertIn("Electronics", cat_names)
        self.assertIn("Clothing", cat_names)

    def test_api_products_list(self):
        response = self.client.get(reverse("shop:api_products"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 2)

    def test_api_products_filter_category(self):
        response = self.client.get(reverse("shop:api_products"), {"category": self.electronics.slug})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["name"], "Custom Mechanical Keyboard")

    def test_api_products_search(self):
        response = self.client.get(reverse("shop:api_products"), {"q": "tee"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["name"], "Organic Heavyweight Tee")

    def test_api_product_detail(self):
        response = self.client.get(reverse("shop:api_product_detail", args=[self.keyboard.slug]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Custom Mechanical Keyboard")
        self.assertEqual(float(data["price"]), 148.0)
        self.assertIn("related_products", data)

    def test_api_hot_deal(self):
        response = self.client.get(reverse("shop:api_hot_deal"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Custom Mechanical Keyboard")
        self.assertIn("deal_ends_in_hours", data)

    def test_api_order_create_and_retrieve(self):
        payload = {
            "customer_name": "Alice Smith",
            "phone": "+1987654321",
            "address": "456 Elm St",
            "city": "Metropolis",
            "items": [
                {"product_id": self.keyboard.id, "quantity": 1}
            ]
        }
        create_resp = self.client.post(
            reverse("shop:api_order_create"),
            payload,
            content_type="application/json"
        )
        self.assertEqual(create_resp.status_code, 201)
        order_data = create_resp.json()
        self.assertEqual(order_data["customer_name"], "Alice Smith")
        self.assertEqual(float(order_data["total_amount"]), 148.0)
        self.assertEqual(len(order_data["items"]), 1)

        # Retrieve order
        order_num = order_data["order_number"]
        get_resp = self.client.get(reverse("shop:api_order_detail", args=[order_num]))
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["order_number"], order_num)

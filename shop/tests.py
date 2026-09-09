from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from .models import Category, Order, OrderItem, Product


class ShopTestCase(TestCase):
    def setUp(self):
        self.electronics = Category.objects.create(name="Electronics", icon="devices")
        self.clothing = Category.objects.create(name="Clothing", icon="checkroom")

        self.keyboard = Product.objects.create(
            name="Custom Mechanical Keyboard",
            category=self.electronics,
            description="A great keyboard.",
            price=Decimal("148.00"),
            old_price=Decimal("180.00"),
            stock=10,
            badge="NEW",
        )
        self.tee = Product.objects.create(
            name="Organic Heavyweight Tee",
            category=self.clothing,
            description="A soft tee.",
            price=Decimal("42.00"),
            stock=0,
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
                description="x",
                price=Decimal("10.00"),
                stock=5,
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

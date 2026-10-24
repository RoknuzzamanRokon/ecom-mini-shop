"""
TASK-027: a list page costs the same number of queries however many rows it
shows, and checkout locks only the rows it changes.

- BUG-022: the staff orders, staff payments and customer orders lists read the
  latest payment and the refunds from what the page already fetched, and the
  cart reads each product's stock the same way.
- BUG-067: the Console users, customers and categories lists look up roles,
  profiles and counts in the page query, not once per row; the sellers and
  shops lists count shops and products without loading them.
- BUG-023: checkout's cart lock does not also lock the product, category,
  shop and seller rows joined to the cart items (MySQL locks every joined row).
- TASK-043: every list page here also stays within a query budget, and the
  public catalogue, Console products, seller orders and favourites are
  covered too.
"""

import itertools
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.management import call_command
from django.test import TransactionTestCase
from rest_framework.test import APITestCase

from cart.models import Cart, CartItem
from customers.models import Address, CustomerProfile, Favorite
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shop.inventory_service import InventoryService
from shop.models import Category, Order, OrderItem, Payment, Product, ProductInventory, Refund
from shop.services import OrderService
from shops.models import Shop
from utils.testing import QueryCountMixin, page_rows, share_lock_states

User = get_user_model()

SERIAL = itertools.count(1)


rows = page_rows

#: Queries each list page may take (TASK-043), whatever its row count. Raise
#: a budget only for a query the page really needs, never for one per row.
QUERY_BUDGETS = {
    "/api/staff/orders/": 4,
    "/api/staff/payments/": 3,
    "/api/orders/": 9,
    "/api/cart/": 7,
    "/api/admin/users/": 3,
    "/api/admin/customers/": 2,
    "/api/admin/categories/": 2,
    "/api/admin/sellers/": 2,
    "/api/admin/shops/": 2,
    "/api/admin/products/": 2,
    "/api/products/": 4,
    "/api/seller/orders/": 3,
    "/api/favorites/": 3,
}


class QueryCountTests(QueryCountMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.staff = User.objects.create_superuser(username="qc_staff", email="qc@example.com", password="Qc-Staff-123")
        cls.customer = User.objects.create_user(username="qc_customer", password="Qc-Customer-123")
        assign_user_role(cls.customer, Role.ROLE_CUSTOMER)
        CustomerProfile.objects.create(user=cls.customer, display_name="QC Customer")
        cls.seller = SellerProfile.objects.create(
            user=User.objects.create_user(username="qc_seller", password="Qc-Seller-123"),
            business_name="QC Seller", status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop = Shop.objects.create(owner=cls.seller, name="QC Shop", slug="qc-shop", status=Shop.STATUS_ACTIVE)
        cls.category = Category.objects.create(name="QC Category", slug="qc-category", is_active=True)

    def make_product(self, category=None, shop=None):
        n = next(SERIAL)
        product = Product.objects.create(
            name=f"QC Product {n}", slug=f"qc-product-{n}", category=category or self.category,
            shop=shop or self.shop, price=Decimal("100.00"), stock=5,
            status=Product.STATUS_PUBLISHED, is_active=True,
        )
        ProductInventory.objects.create(product=product, available_quantity=5)
        return product

    def make_order(self):
        n = next(SERIAL)
        order = Order.objects.create(
            user=self.customer, order_number=f"ORD-QC-{n:03d}", status=Order.STATUS_PENDING,
            subtotal=Decimal("100.00"), total_amount=Decimal("100.00"), shipping_city="Dhaka",
        )
        OrderItem.objects.create(
            order=order, product_name="QC Product", shop=self.shop, shop_name=self.shop.name,
            seller=self.seller, seller_name=self.seller.business_name, unit_price=Decimal("100.00"),
            price=Decimal("100.00"), quantity=1, line_total=Decimal("100.00"), subtotal=Decimal("100.00"),
        )
        payment = Payment.objects.create(
            order=order, user=self.customer, payment_number=f"PAY-QC-{n:03d}",
            payment_method=Payment.METHOD_CASH_ON_DELIVERY, status=Payment.STATUS_PARTIALLY_REFUNDED,
            amount=Decimal("100.00"),
        )
        Refund.objects.create(
            payment=payment, order=order, refund_number=f"REF-QC-{n:03d}", amount=Decimal("10.00"),
            status=Refund.STATUS_COMPLETED, processed_by=self.staff,
        )
        return order

    def assert_constant_queries(self, url, add_rows, user=None):
        return super().assert_constant_queries(url, add_rows, user or self.staff, budget=QUERY_BUDGETS[url])

    def assert_rows_not_loaded(self, url, table):
        super().assert_rows_not_loaded(url, table, self.staff)

    # --- BUG-022 ---

    def test_staff_orders(self):
        self.make_order()
        response = self.assert_constant_queries("/api/staff/orders/", lambda: [self.make_order() for _ in range(3)])
        self.assertEqual({row["payment_status"] for row in rows(response)}, {Payment.STATUS_PARTIALLY_REFUNDED})

    def test_staff_payments(self):
        self.make_order()
        response = self.assert_constant_queries("/api/staff/payments/", lambda: [self.make_order() for _ in range(3)])
        for row in rows(response):
            self.assertEqual(Decimal(str(row["refundable_amount"])), Decimal("90.00"))
            self.assertEqual(row["refunds"][0]["processed_by_name"], "qc_staff")
            self.assertEqual(row["refunds"][0]["order_number"], row["order_number"])

    def test_customer_orders(self):
        self.make_order()
        response = self.assert_constant_queries(
            "/api/orders/", lambda: [self.make_order() for _ in range(3)], user=self.customer
        )
        self.assertTrue(all(row["payment"]["status"] == Payment.STATUS_PARTIALLY_REFUNDED for row in rows(response)))

    def test_the_latest_payment_wins_with_or_without_a_prefetch(self):
        order = self.make_order()
        newer = Payment.objects.create(
            order=order, user=self.customer, payment_number="PAY-QC-NEWER",
            payment_method=Payment.METHOD_CASH_ON_DELIVERY, status=Payment.STATUS_PENDING, amount=Decimal("100.00"),
        )
        self.assertEqual(Order.objects.get(pk=order.pk).current_payment, newer)
        prefetched = Order.objects.prefetch_related("payments").get(pk=order.pk)
        with self.assertNumQueries(0):
            self.assertEqual(prefetched.current_payment, newer)

    def test_cart(self):
        cart = Cart.objects.create(user=self.customer)
        CartItem.objects.create(cart=cart, product=self.make_product())

        def add_items():
            for _ in range(3):
                CartItem.objects.create(cart=cart, product=self.make_product())

        response = self.assert_constant_queries("/api/cart/", add_items, user=self.customer)
        self.assertTrue(all(item["product"]["in_stock"] for item in rows(response)))

    # --- BUG-067 ---

    def test_console_users(self):
        def add_users():
            for _ in range(3):
                n = next(SERIAL)
                user = User.objects.create_user(username=f"qc_user_{n}", password="Qc-User-123")
                CustomerProfile.objects.create(user=user)
                SellerProfile.objects.create(user=user, business_name=f"QC User Seller {n}")
                assign_user_role(user, Role.ROLE_CUSTOMER)

        response = self.assert_constant_queries("/api/admin/users/", add_users)
        by_name = {row["username"]: row for row in rows(response)}
        self.assertEqual(by_name["qc_customer"]["roles"], [Role.ROLE_CUSTOMER])
        self.assertEqual(by_name["qc_customer"]["customer_profile_id"], self.customer.customer_profile.id)
        self.assertIsNone(by_name["qc_customer"]["seller_profile_id"])
        self.assertEqual(by_name["qc_seller"]["seller_profile_id"], self.seller.id)

    def test_console_customers(self):
        self.make_order()

        def add_customers():
            for _ in range(3):
                n = next(SERIAL)
                CustomerProfile.objects.create(user=User.objects.create_user(username=f"qc_buyer_{n}", password="Qc-Buyer-123"))

        response = self.assert_constant_queries("/api/admin/customers/", add_customers)
        by_name = {row["username"]: row["orders_count"] for row in rows(response)}
        self.assertEqual(by_name["qc_customer"], 1)
        self.assertEqual(sum(by_name.values()), 1)

    def test_console_categories(self):
        self.make_product()

        def add_categories():
            for _ in range(3):
                n = next(SERIAL)
                self.make_product(category=Category.objects.create(name=f"QC Category {n}", slug=f"qc-category-{n}"))

        response = self.assert_constant_queries("/api/admin/categories/", add_categories)
        self.assertTrue(all(row["products_count"] == 1 for row in rows(response)))

    def test_console_sellers(self):
        def add_sellers():
            for _ in range(3):
                n = next(SERIAL)
                seller = SellerProfile.objects.create(
                    user=User.objects.create_user(username=f"qc_merchant_{n}", password="Qc-Merchant-123"),
                    business_name=f"QC Merchant {n}",
                )
                Shop.objects.create(owner=seller, name=f"QC Merchant Shop {n}", slug=f"qc-merchant-shop-{n}")

        response = self.assert_constant_queries("/api/admin/sellers/", add_sellers)
        self.assertTrue(all(row["shops_count"] == 1 for row in rows(response)))
        self.assert_rows_not_loaded("/api/admin/sellers/", "shops_shop")

    def test_console_shops(self):
        self.make_product()

        def add_shops():
            for _ in range(3):
                n = next(SERIAL)
                self.make_product(shop=Shop.objects.create(owner=self.seller, name=f"QC Shop {n}", slug=f"qc-shop-{n}"))

        response = self.assert_constant_queries("/api/admin/shops/", add_shops)
        self.assertTrue(all(row["products_count"] == 1 for row in rows(response)))
        self.assert_rows_not_loaded("/api/admin/shops/", "shop_product")
        detail = self.client.get(f"/api/admin/shops/{self.shop.pk}/")
        self.assertEqual(detail.data["products_count"], 1)


    # --- TASK-043: the other list pages ---

    def test_console_products(self):
        self.make_product()
        self.assert_constant_queries("/api/admin/products/", lambda: [self.make_product() for _ in range(3)])

    def test_public_products(self):
        self.make_product()
        response = self.assert_constant_queries(
            "/api/products/", lambda: [self.make_product() for _ in range(3)], user=AnonymousUser()
        )
        self.assertTrue(all(row["shop"]["slug"] == "qc-shop" for row in rows(response)))

    def test_seller_orders(self):
        self.make_order()
        self.assert_constant_queries(
            "/api/seller/orders/", lambda: [self.make_order() for _ in range(3)], user=self.seller.user
        )

    def test_favorites(self):
        Favorite.objects.create(user=self.customer, product=self.make_product())

        def add_favorites():
            for _ in range(3):
                Favorite.objects.create(user=self.customer, product=self.make_product())

        self.assert_constant_queries("/api/favorites/", add_favorites, user=self.customer)


class CheckoutLockScopeTests(TransactionTestCase):
    """BUG-023, on MySQL: checkout holds the cart rows, not the catalog rows."""

    def setUp(self):
        self.customer = User.objects.create_user(username="lock_customer", password="Lock-Customer-123")
        self.seller = SellerProfile.objects.create(
            user=User.objects.create_user(username="lock_seller", password="Lock-Seller-123"),
            business_name="Lock Seller", status=SellerProfile.STATUS_ACTIVE,
        )
        self.shop = Shop.objects.create(owner=self.seller, name="Lock Shop", slug="lock-shop", status=Shop.STATUS_ACTIVE)
        self.category = Category.objects.create(name="Lock Category", slug="lock-category", is_active=True)
        self.product = Product.objects.create(
            name="Lock Product", slug="lock-product", category=self.category, shop=self.shop,
            price=Decimal("100.00"), stock=5, status=Product.STATUS_PUBLISHED, is_active=True,
        )
        ProductInventory.objects.create(product=self.product, available_quantity=5)
        self.item = CartItem.objects.create(cart=Cart.objects.create(user=self.customer), product=self.product)
        self.address = Address.objects.create(
            user=self.customer, recipient_name="Lock Customer", phone="01700000000",
            address_line_1="1 Lock Road", city="Dhaka", is_default=True,
        )

    def lock_states_seen_from_another_connection(self):
        """What a concurrent checkout could still share-lock: everything but the cart rows."""
        return share_lock_states({
            "product": (Product, self.product.pk),
            "category": (Category, self.category.pk),
            "shop": (Shop, self.shop.pk),
            "seller": (SellerProfile, self.seller.pk),
            "cart item": (CartItem, self.item.pk),
        })

    def test_checkout_locks_the_cart_items_but_not_the_catalog(self):
        seen = {}
        reserve = InventoryService.reserve_stock_for_cart

        def reserve_after_probing(*args, **kwargs):
            # Still inside checkout's transaction, after its cart lock.
            seen.update(self.lock_states_seen_from_another_connection())
            return reserve(*args, **kwargs)

        with mock.patch.object(InventoryService, "reserve_stock_for_cart", side_effect=reserve_after_probing):
            order = OrderService.create_order_from_cart(user=self.customer, address_id=self.address.pk)

        self.assertEqual(
            seen, {"product": "free", "category": "free", "shop": "free", "seller": "free", "cart item": "locked"}
        )
        self.assertEqual(order.items.count(), 1)

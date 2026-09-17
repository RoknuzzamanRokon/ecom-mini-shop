import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from cart.models import Cart, CartItem
from customers.models import Address
from points.models import PointTransaction, SellerWallet
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.models import Shop
from shop.inventory_service import InventoryService
from shop.models import Category, InventoryTransaction, Order, OrderItem, Product, ProductInventory
from shop.services import OrderService, ProductService

User = get_user_model()


class InventoryTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        # 1. Admin user with ROLE_ADMINISTRATOR
        cls.admin_user = User.objects.create_user(
            username="inv_admin",
            email="admin@test.com",
            password="Password123!",
        )
        assign_user_role(cls.admin_user, Role.ROLE_ADMINISTRATOR)

        # 2. Operational Seller A (Full Shop Owner)
        cls.user_seller_a = User.objects.create_user(
            username="inv_seller_a",
            email="seller_a@test.com",
            password="Password123!",
        )
        assign_user_role(cls.user_seller_a, Role.ROLE_SALES_TEAM)
        cls.seller_a = SellerProfile.objects.create(
            user=cls.user_seller_a,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Apex Electronics",
        )
        SellerWallet.objects.create(seller=cls.seller_a, balance=5000)
        cls.shop_a = Shop.objects.create(
            owner=cls.seller_a,
            name="Apex Flagship Shop",
            slug="apex-flagship-shop",
            status=Shop.STATUS_ACTIVE,
        )

        # 3. Operational Seller B (Full Shop Owner)
        cls.user_seller_b = User.objects.create_user(
            username="inv_seller_b",
            email="seller_b@test.com",
            password="Password123!",
        )
        assign_user_role(cls.user_seller_b, Role.ROLE_SALES_TEAM)
        cls.seller_b = SellerProfile.objects.create(
            user=cls.user_seller_b,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Nexus Footwear",
        )
        SellerWallet.objects.create(seller=cls.seller_b, balance=5000)
        cls.shop_b = Shop.objects.create(
            owner=cls.seller_b,
            name="Nexus Footwear Shop",
            slug="nexus-footwear-shop",
            status=Shop.STATUS_ACTIVE,
        )

        # 4. Suspended Seller C
        cls.user_seller_c = User.objects.create_user(
            username="inv_seller_c",
            email="seller_c@test.com",
            password="Password123!",
        )
        assign_user_role(cls.user_seller_c, Role.ROLE_SALES_TEAM)
        cls.seller_c = SellerProfile.objects.create(
            user=cls.user_seller_c,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_SUSPENDED,
            suspension_reason="Policy violations",
            business_name="Suspended Merchant",
        )
        cls.shop_c = Shop.objects.create(
            owner=cls.seller_c,
            name="Suspended Shop",
            slug="suspended-shop",
            status=Shop.STATUS_ACTIVE,
        )

        # 5. Customer User
        cls.customer_user = User.objects.create_user(
            username="inv_customer",
            email="customer@test.com",
            password="Password123!",
        )
        assign_user_role(cls.customer_user, Role.ROLE_CUSTOMER)
        cls.address = Address.objects.create(
            user=cls.customer_user,
            label="Home",
            recipient_name="Tariq Rahman",
            phone="01711000000",
            address_line_1="House 12, Road 5, Dhanmondi",
            city="Dhaka",
            postal_code="1205",
            country="Bangladesh",
            is_default=True,
        )

        # Category
        cls.category = Category.objects.create(
            name="Gadgets",
            slug="gadgets",
            is_active=True,
        )

    def setUp(self):
        # Create fresh products per test
        self.product_a = ProductService.create_product(
            seller=self.seller_a,
            name=f"Wireless Earbuds {self.id()}",
            category=self.category,
            shop=self.shop_a,
            description="Premium earbuds",
            price=Decimal("1500.00"),
            stock=20,
            is_active=True,
            actor=self.user_seller_a,
        )
        self.product_a.status = Product.STATUS_PUBLISHED
        self.product_a.save()

        self.product_b = ProductService.create_product(
            seller=self.seller_b,
            name=f"Running Shoes {self.id()}",
            category=self.category,
            shop=self.shop_b,
            description="Comfortable running shoes",
            price=Decimal("2500.00"),
            stock=10,
            is_active=True,
            actor=self.user_seller_b,
        )
        self.product_b.status = Product.STATUS_PUBLISHED
        self.product_b.save()

    # --- 1. Model & Constraints ---

    def test_product_inventory_creation_and_non_negative_constraints(self):
        """Verify ProductInventory model constraints and total_quantity calculation."""
        inventory = self.product_a.inventory
        self.assertIsNotNone(inventory)
        self.assertEqual(inventory.available_quantity, 20)
        self.assertEqual(inventory.reserved_quantity, 0)
        self.assertEqual(inventory.sold_quantity, 0)
        self.assertEqual(inventory.total_quantity, 20)

        # Verify initial transaction was created
        initial_tx = InventoryTransaction.objects.filter(
            product=self.product_a,
            transaction_type=InventoryTransaction.TYPE_INITIAL_STOCK,
        ).first()
        self.assertIsNotNone(initial_tx)
        self.assertEqual(initial_tx.quantity, 20)
        self.assertEqual(initial_tx.after_available, 20)

        # Validation error on negative quantity via model clean
        inventory.available_quantity = -5
        with self.assertRaises(DjangoValidationError):
            inventory.full_clean()

        # OneToOne uniqueness constraint: cannot create second inventory for same product
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductInventory.objects.create(
                    product=self.product_a,
                    available_quantity=10,
                )

    # --- 2. Stock Adjustments Service & API ---

    def test_authorized_positive_and_negative_stock_adjustment(self):
        """Verify positive and negative stock adjustments and legacy stock synchronization."""
        # Positive adjustment (+15)
        updated_inv = InventoryService.adjust_stock(
            product=self.product_a,
            quantity_delta=15,
            actor=self.user_seller_a,
            reason="Replenished inventory batch A",
        )
        self.assertEqual(updated_inv.available_quantity, 35)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, 35)

        # Verify transaction
        tx = InventoryTransaction.objects.filter(
            product=self.product_a,
            transaction_type=InventoryTransaction.TYPE_ADJUSTMENT,
        ).first()
        self.assertEqual(tx.quantity, 15)
        self.assertEqual(tx.before_available, 20)
        self.assertEqual(tx.after_available, 35)
        self.assertEqual(tx.actor, self.user_seller_a)

        # Negative adjustment (-10)
        updated_inv2 = InventoryService.adjust_stock(
            product=self.product_a,
            quantity_delta=-10,
            actor=self.user_seller_a,
            reason="Damaged items removed",
        )
        self.assertEqual(updated_inv2.available_quantity, 25)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, 25)

    def test_excessive_negative_adjustment_rejected(self):
        """Verify adjustment that would result in negative available stock is rejected."""
        # Current available is 20. Attempting -25 must fail.
        with self.assertRaises(DjangoValidationError):
            InventoryService.adjust_stock(
                product=self.product_a,
                quantity_delta=-25,
                actor=self.user_seller_a,
            )

        # Inventory must remain intact
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 20)

    def test_zero_delta_adjustment_rejected(self):
        """Verify zero quantity adjustment is rejected."""
        with self.assertRaises(DjangoValidationError):
            InventoryService.adjust_stock(
                product=self.product_a,
                quantity_delta=0,
                actor=self.user_seller_a,
            )

    # --- 3. REST API & RBAC Ownership Enforcement ---

    def test_inventory_api_permissions_and_ownership(self):
        """Verify REST API permissions, ownership isolation, and unauthorized access rejections."""
        url = f"/api/seller/inventory/{self.product_a.id}/"
        adjust_url = f"/api/seller/inventory/{self.product_a.id}/adjust/"

        # 1. Unauthenticated request -> 401
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Customer without seller profile -> 403
        self.client.force_authenticate(user=self.customer_user)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Seller B attempting to access Seller A's product -> 403
        self.client.force_authenticate(user=self.user_seller_b)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 4. Seller B attempting to adjust Seller A's product -> 403
        res = self.client.post(adjust_url, {"quantity": 5, "reason": "Unauthorized attempt"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 5. Suspended Seller C attempting to adjust -> 403
        product_c = Product.objects.create(
            name="Suspended Item",
            slug=f"suspended-item-{self.id()}",
            category=self.category,
            shop=self.shop_c,
            price=Decimal("100.00"),
            stock=5,
        )
        self.client.force_authenticate(user=self.user_seller_c)
        res = self.client.post(f"/api/seller/inventory/{product_c.id}/adjust/", {"quantity": 2}, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 6. Seller A accessing their own product -> 200 OK
        self.client.force_authenticate(user=self.user_seller_a)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["available_quantity"], 20)

        # 7. Seller A adjusting own product -> 200 OK
        res = self.client.post(adjust_url, {"quantity": 5, "reason": "Restocked"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["available_quantity"], 25)

        # 8. Staff / Admin adjusting stock -> 200 OK
        self.client.force_authenticate(user=self.admin_user)
        res = self.client.post(adjust_url, {"quantity": 10, "reason": "Admin adjustment"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["available_quantity"], 35)

    def test_seller_inventory_list_view(self):
        """Verify GET /api/seller/inventory/ lists only products owned by authenticated seller."""
        self.client.force_authenticate(user=self.user_seller_a)
        res = self.client.get("/api/seller/inventory/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        product_ids = [item["product_id"] for item in res.data.get("results", res.data)]
        self.assertIn(self.product_a.id, product_ids)
        self.assertNotIn(self.product_b.id, product_ids)

    # --- 4. Order Creation & Stock Reservation ---

    def test_order_creation_reserves_stock_atomically(self):
        """Verify order creation atomically decrements available and increments reserved stock."""
        # Setup cart with 4 units of product_a (stock is 20)
        cart, _ = Cart.objects.get_or_create(user=self.customer_user)
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=4)

        order = OrderService.create_order_from_cart(
            user=self.customer_user,
            address_id=self.address.id,
        )

        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 16)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 4)
        self.assertEqual(self.product_a.inventory.sold_quantity, 0)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, 16)

        # Verify RESERVATION transaction record
        tx = InventoryTransaction.objects.filter(
            product=self.product_a,
            order=order,
            transaction_type=InventoryTransaction.TYPE_RESERVATION,
        ).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.quantity, 4)
        self.assertEqual(tx.before_available, 20)
        self.assertEqual(tx.after_available, 16)
        self.assertEqual(tx.before_reserved, 0)
        self.assertEqual(tx.after_reserved, 4)

    def test_order_creation_insufficient_stock_fails_atomically(self):
        """Verify order creation fails if stock is insufficient; cart and inventory remain intact."""
        # Available stock is 20. Customer requests 25.
        cart, _ = Cart.objects.get_or_create(user=self.customer_user)
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=25)

        with self.assertRaises(DjangoValidationError):
            OrderService.create_order_from_cart(
                user=self.customer_user,
                address_id=self.address.id,
            )

        # Inventory must remain completely unchanged
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 20)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 0)

        # Cart item must still exist (not cleared on error)
        self.assertTrue(CartItem.objects.filter(cart=cart, product=self.product_a).exists())
        # No order should have been created
        self.assertEqual(Order.objects.filter(user=self.customer_user).count(), 0)

    def test_order_creation_exact_stock_succeeds(self):
        """Verify ordering exact available quantity leaves 0 available and full reserved."""
        cart, _ = Cart.objects.get_or_create(user=self.customer_user)
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=20)

        order = OrderService.create_order_from_cart(
            user=self.customer_user,
            address_id=self.address.id,
        )
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 0)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 20)

        # Product in_stock property must now reflect False (out of stock)
        self.product_a.refresh_from_db()
        self.assertFalse(self.product_a.in_stock)

    # --- 5. Order Cancellation & Reservation Release ---

    def test_order_cancellation_releases_inventory_reservation(self):
        """Verify cancelling an order releases reserved stock back to available stock."""
        cart, _ = Cart.objects.get_or_create(user=self.customer_user)
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=5)
        order = OrderService.create_order_from_cart(
            user=self.customer_user,
            address_id=self.address.id,
        )

        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 15)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 5)

        # Cancel the order
        OrderService.transition_order_status(
            order=order,
            new_status=Order.STATUS_CANCELLED,
            actor=self.admin_user,
            note="Customer requested cancellation",
        )

        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 20)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 0)
        self.product_a.refresh_from_db()
        self.assertEqual(self.product_a.stock, 20)

        # Verify RELEASE transaction
        tx = InventoryTransaction.objects.filter(
            product=self.product_a,
            order=order,
            transaction_type=InventoryTransaction.TYPE_RELEASE,
        ).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.quantity, 5)
        self.assertEqual(tx.after_available, 20)
        self.assertEqual(tx.after_reserved, 0)

    def test_cancellation_idempotency_does_not_double_release(self):
        """Verify duplicate release calls do not release reservation twice."""
        cart, _ = Cart.objects.get_or_create(user=self.customer_user)
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=3)
        order = OrderService.create_order_from_cart(
            user=self.customer_user,
            address_id=self.address.id,
        )

        OrderService.transition_order_status(
            order=order,
            new_status=Order.STATUS_CANCELLED,
            actor=self.admin_user,
        )
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 20)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 0)

        # Explicit second call to release_order_reservation directly
        InventoryService.release_order_reservation(order, actor=self.admin_user)

        self.product_a.inventory.refresh_from_db()
        # Must still be 20, not 23
        self.assertEqual(self.product_a.inventory.available_quantity, 20)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 0)

    # --- 6. Order Delivery & Sale Finalization ---

    def test_order_delivery_finalizes_sale(self):
        """Verify delivering an order moves reserved stock to sold stock."""
        cart, _ = Cart.objects.get_or_create(user=self.customer_user)
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=6)
        order = OrderService.create_order_from_cart(
            user=self.customer_user,
            address_id=self.address.id,
        )

        # Progress lifecycle: PENDING -> CONFIRMED -> PROCESSING -> SHIPPED -> DELIVERED
        OrderService.transition_order_status(order, Order.STATUS_CONFIRMED, actor=self.admin_user)
        OrderService.transition_order_status(order, Order.STATUS_PROCESSING, actor=self.admin_user)
        OrderService.transition_order_status(order, Order.STATUS_SHIPPED, actor=self.admin_user)

        # Before delivery: available=14, reserved=6, sold=0
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 14)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 6)
        self.assertEqual(self.product_a.inventory.sold_quantity, 0)

        # Deliver
        OrderService.transition_order_status(order, Order.STATUS_DELIVERED, actor=self.admin_user)

        # After delivery: available=14, reserved=0, sold=6
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 14)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 0)
        self.assertEqual(self.product_a.inventory.sold_quantity, 6)

        # Verify SALE transaction
        tx = InventoryTransaction.objects.filter(
            product=self.product_a,
            order=order,
            transaction_type=InventoryTransaction.TYPE_SALE,
        ).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.quantity, 6)
        self.assertEqual(tx.after_reserved, 0)
        self.assertEqual(tx.after_sold, 6)

    def test_delivery_idempotency_does_not_double_count_sales(self):
        """Verify delivery finalization is idempotent."""
        cart, _ = Cart.objects.get_or_create(user=self.customer_user)
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=2)
        order = OrderService.create_order_from_cart(
            user=self.customer_user,
            address_id=self.address.id,
        )

        OrderService.transition_order_status(order, Order.STATUS_CONFIRMED, actor=self.admin_user)
        OrderService.transition_order_status(order, Order.STATUS_PROCESSING, actor=self.admin_user)
        OrderService.transition_order_status(order, Order.STATUS_SHIPPED, actor=self.admin_user)
        OrderService.transition_order_status(order, Order.STATUS_DELIVERED, actor=self.admin_user)

        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.sold_quantity, 2)

        # Direct second finalize call
        InventoryService.finalize_order_delivery(order, actor=self.admin_user)
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.sold_quantity, 2)

    # --- 7. Multi-Seller Independent Reservation ---

    def test_multi_seller_order_independent_reservation(self):
        """Verify an order containing items from multiple sellers reserves inventory independently."""
        cart, _ = Cart.objects.get_or_create(user=self.customer_user)
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=3)  # Seller A
        CartItem.objects.create(cart=cart, product=self.product_b, quantity=4)  # Seller B

        order = OrderService.create_order_from_cart(
            user=self.customer_user,
            address_id=self.address.id,
        )

        self.product_a.inventory.refresh_from_db()
        self.product_b.inventory.refresh_from_db()

        # Product A (stock 20): reserved 3 -> avail 17, reserved 3
        self.assertEqual(self.product_a.inventory.available_quantity, 17)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 3)

        # Product B (stock 10): reserved 4 -> avail 6, reserved 4
        self.assertEqual(self.product_b.inventory.available_quantity, 6)
        self.assertEqual(self.product_b.inventory.reserved_quantity, 4)

    # --- 8. Historical OrderItem Snapshot Integrity ---

    def test_historical_order_item_snapshot_preserved_after_inventory_adjustments(self):
        """Verify stock adjustments do not modify historical OrderItem snapshot data."""
        cart, _ = Cart.objects.get_or_create(user=self.customer_user)
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=2)
        order = OrderService.create_order_from_cart(
            user=self.customer_user,
            address_id=self.address.id,
        )
        order_item = order.items.first()
        orig_price = order_item.unit_price
        orig_line_total = order_item.line_total
        orig_qty = order_item.quantity

        # Make stock adjustments and price changes on product_a
        InventoryService.adjust_stock(self.product_a, quantity_delta=-5, actor=self.admin_user)
        self.product_a.price = Decimal("2999.00")
        self.product_a.save()

        # OrderItem must remain completely unchanged
        order_item.refresh_from_db()
        self.assertEqual(order_item.unit_price, orig_price)
        self.assertEqual(order_item.line_total, orig_line_total)
        self.assertEqual(order_item.quantity, orig_qty)

    # --- 9. Product.stock / ProductInventory sync on seller product update (Known Issues #2) ---

    def test_seller_update_stock_stays_synced_with_inventory(self):
        """
        PATCH-equivalent ProductService.update_product(..., data={"stock": N}) must move
        ProductInventory.available_quantity in lockstep with Product.stock, not just the
        Product row. Regression test for Known Issues #2 in docs/MINISHOP_REVIEW_STATE.md.
        """
        self.assertEqual(self.product_a.stock, 20)
        self.assertEqual(self.product_a.inventory.available_quantity, 20)

        ProductService.update_product(
            product=self.product_a,
            seller=self.seller_a,
            data={"stock": 5},
            actor=self.user_seller_a,
        )

        self.product_a.refresh_from_db()
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.stock, 5)
        self.assertEqual(self.product_a.inventory.available_quantity, 5)

        # A matching ADJUSTMENT ledger entry must exist recording the delta.
        adj = InventoryTransaction.objects.filter(
            product=self.product_a,
            transaction_type=InventoryTransaction.TYPE_ADJUSTMENT,
        ).order_by("-created_at").first()
        self.assertIsNotNone(adj)
        self.assertEqual(adj.quantity, -15)
        self.assertEqual(adj.after_available, 5)

    def test_seller_update_stock_increase_stays_synced_with_inventory(self):
        """Increasing stock via update_product must also route through InventoryService."""
        ProductService.update_product(
            product=self.product_a,
            seller=self.seller_a,
            data={"stock": 30},
            actor=self.user_seller_a,
        )
        self.product_a.refresh_from_db()
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.stock, 30)
        self.assertEqual(self.product_a.inventory.available_quantity, 30)

    def test_seller_update_stock_noop_when_unchanged(self):
        """Setting stock to its current value must not create a spurious ledger entry."""
        tx_count_before = InventoryTransaction.objects.filter(product=self.product_a).count()
        ProductService.update_product(
            product=self.product_a,
            seller=self.seller_a,
            data={"stock": 20},
            actor=self.user_seller_a,
        )
        self.assertEqual(
            InventoryTransaction.objects.filter(product=self.product_a).count(),
            tx_count_before,
        )

    def test_seller_update_stock_respects_existing_reservation(self):
        """
        Updating stock while units are already reserved must only move the available
        pool; reserved units (already promised to a placed order) must be untouched.
        """
        cart, _ = Cart.objects.get_or_create(user=self.customer_user)
        CartItem.objects.create(cart=cart, product=self.product_a, quantity=4)
        OrderService.create_order_from_cart(user=self.customer_user, address_id=self.address.id)

        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 16)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 4)

        # Seller sets absolute stock to 10 (i.e. 10 more units on top of what is available).
        ProductService.update_product(
            product=self.product_a,
            seller=self.seller_a,
            data={"stock": 10},
            actor=self.user_seller_a,
        )

        self.product_a.refresh_from_db()
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.inventory.available_quantity, 10)
        self.assertEqual(self.product_a.inventory.reserved_quantity, 4)
        self.assertEqual(self.product_a.stock, 10)

    def test_api_seller_product_update_stock_stays_synced_with_inventory(self):
        """PATCH /api/products/mine/<id>/ with a stock field must sync ProductInventory too."""
        self.client.force_authenticate(user=self.user_seller_a)
        res = self.client.patch(f"/api/products/mine/{self.product_a.id}/", {"stock": 7})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.product_a.refresh_from_db()
        self.product_a.inventory.refresh_from_db()
        self.assertEqual(self.product_a.stock, 7)
        self.assertEqual(self.product_a.inventory.available_quantity, 7)

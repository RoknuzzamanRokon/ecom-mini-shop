"""
TASK-006 (BUG-006, BUG-021, BUG-046): Django-admin change forms cannot move
order or product lifecycles, inventory counters or seller ownership outside
the services, and every edit they do allow writes an audit row.

Same approach as audit.test_admin_action_authorization's
AdminChangeFormStatusLockdownTests (Known #22): post a complete, otherwise
valid form with crafted values, then check the stored rows. Each post also
changes one harmless field, so a rejected form cannot pass for a locked one.
The forms are posted as rendered (utils.testing.ChangeFormLockdownMixin,
TASK-043), so a field added to a form needs no change here.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission as AuthPermission
from django.test import TestCase
from django.urls import reverse

from audit.models import AuditLog
from customers.models import Address
from points.models import PointTransaction
from points.services import PointService
from sellers.models import LimitedShopOwnerProductLimit, SellerProfile
from shop.models import Category, InventoryTransaction, Order, Product, ProductInventory
from shop.inventory_service import InventoryService
from shops.fields import Point
from shops.models import Shop
from utils.testing import ChangeFormLockdownMixin

User = get_user_model()

class LockdownTestCase(ChangeFormLockdownMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="lockdown6_super", email="lockdown6@example.com", password="Lockdown-Super-1"
        )
        cls.category = Category.objects.create(name="Lockdown Goods", slug="lockdown-goods")
        LimitedShopOwnerProductLimit.objects.update_or_create(pk=1, defaults={"max_products": 2})

    def setUp(self):
        self.client.force_login(self.superuser)

    def make_seller(self, name, seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER, points=0):
        user = User.objects.create_user(username=name, password="Lockdown-Seller-1")
        seller = SellerProfile.objects.create(
            user=user, seller_type=seller_type, business_name=name.title(), status=SellerProfile.STATUS_ACTIVE
        )
        if points:
            PointService.credit(
                seller=seller, amount=points, transaction_type=PointTransaction.TYPE_BONUS, reason="Grant"
            )
        return seller

    def make_shop(self, owner, slug):
        return Shop.objects.create(
            owner=owner, name=slug.title(), slug=slug, status=Shop.STATUS_ACTIVE, location=Point(90.4125, 23.8103)
        )

    def make_product(self, shop, slug, stock=10):
        product = Product.objects.create(
            shop=shop, category=self.category, name=slug.title(), slug=slug, price=Decimal("100.00"), stock=stock,
            description="A desk lamp.",
        )
        InventoryService.get_or_create_inventory(product, default_available=stock)
        return product

    def audit_rows(self, action, obj):
        return AuditLog.objects.filter(action=action, target_id=str(obj.pk))


class OrderAdminLockdownTests(LockdownTestCase):
    def setUp(self):
        super().setUp()
        customer = User.objects.create_user(username="lockdown6_customer", password="Lockdown-Cust-1")
        self.address = Address.objects.create(
            user=customer, recipient_name="Somebody", phone="01700000000",
            address_line_1="Road 1", city="Dhaka",
        )
        self.order = Order.objects.create(
            user=customer, order_number="ORD-LOCKDOWN-1", status=Order.STATUS_PENDING,
            customer_name="Original Name",
        )
        # Ordinary staff with only the Django change permission on orders.
        self.staff = User.objects.create_user(username="lockdown6_staff", password="Lockdown-Staff-1", is_staff=True)
        self.staff.user_permissions.add(
            *AuthPermission.objects.filter(content_type__app_label="shop", codename__in=["change_order", "view_order"])
        )

    def test_crafted_status_and_address_are_ignored_and_the_edit_is_audited(self):
        self.client.force_login(self.staff)
        self.assert_change_form_keeps(
            self.order,
            reverse("admin:shop_order_change", args=[self.order.pk]),
            crafted={"status": Order.STATUS_CANCELLED, "shipping_address": str(self.address.pk)},
            harmless={"customer_name": "Corrected Name"},
        )

        self.assertEqual(self.order.status, Order.STATUS_PENDING)
        self.assertIsNone(self.order.shipping_address_id)
        self.assertFalse(InventoryTransaction.objects.filter(order=self.order).exists())

        row = self.audit_rows("ADMIN_ORDER_EDITED", self.order).get()
        self.assertEqual(row.actor, self.staff)
        self.assertEqual(row.metadata["previous_state"], {"customer_name": "Original Name"})
        self.assertEqual(row.metadata["new_state"], {"customer_name": "Corrected Name"})

    def test_orders_cannot_be_added_or_deleted_here(self):
        self.assertEqual(self.client.get(reverse("admin:shop_order_add")).status_code, 403)
        response = self.client.post(reverse("admin:shop_order_delete", args=[self.order.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())


class ProductAdminLockdownTests(LockdownTestCase):
    def setUp(self):
        super().setUp()
        self.seller = self.make_seller("lockdown6_full", points=50)
        self.shop = self.make_shop(self.seller, "lockdown6-shop")
        self.other_shop = self.make_shop(self.make_seller("lockdown6_other"), "lockdown6-other-shop")
        self.product = self.make_product(self.shop, "lockdown6-lamp", stock=10)

    def product_payload(self, **overrides):
        data = {
            "name": self.product.name, "slug": self.product.slug, "category": str(self.category.pk),
            "description": "A desk lamp.", "price": "100.00", "old_price": "", "badge": "", "is_active": "on",
            "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }
        data.update(overrides)
        return data

    def test_crafted_lifecycle_stock_and_shop_are_ignored(self):
        self.assert_change_form_keeps(
            self.product,
            reverse("admin:shop_product_change", args=[self.product.pk]),
            crafted={
                "status": Product.STATUS_PUBLISHED, "stock": "999", "shop": str(self.other_shop.pk),
                "reviewed_by": str(self.superuser.pk), "rejection_reason": "Crafted",
                "submitted_at_0": "2026-01-01", "submitted_at_1": "10:00:00",
            },
            harmless={"name": "Renamed Lamp"},
        )

        self.assertEqual(self.product.status, Product.STATUS_DRAFT)
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(self.product.shop, self.shop)
        self.assertIsNone(self.product.reviewed_by)
        self.assertIsNone(self.product.submitted_at)
        self.assertEqual(self.product.rejection_reason, "")
        self.assertEqual(ProductInventory.objects.get(product=self.product).available_quantity, 10)

        row = self.audit_rows("ADMIN_PRODUCT_EDITED", self.product).get()
        self.assertEqual(row.metadata["new_state"], {"name": "Renamed Lamp"})

    def add_payload(self, shop, **overrides):
        data = self.product_payload(name="Admin Desk", slug="admin-desk", shop=str(shop.pk), stock="7")
        data.update(overrides)
        return data

    def test_adding_charges_the_fee_and_starts_as_draft(self):
        balance = PointService.get_balance(self.seller)
        cost = PointService.get_product_creation_cost()

        response = self.client.post(
            reverse("admin:shop_product_add"), self.add_payload(self.shop, status=Product.STATUS_PUBLISHED)
        )
        self.assertEqual(response.status_code, 302)

        product = Product.objects.get(slug="admin-desk")
        self.assertEqual(product.status, Product.STATUS_DRAFT)
        self.assertEqual(PointService.get_balance(self.seller), balance - cost)
        self.assertEqual(ProductInventory.objects.get(product=product).available_quantity, 7)
        row = self.audit_rows("PRODUCT_CREATED", product).get()
        self.assertEqual(row.metadata["created_via"], "django_admin")
        self.assertEqual(row.actor, self.superuser)

    def test_adding_respects_the_limited_owner_cap(self):
        limited = self.make_seller("lockdown6_limited", SellerProfile.TYPE_LIMITED_SHOP_OWNER, points=50)
        shop = self.make_shop(limited, "lockdown6-limited-shop")
        self.make_product(shop, "lockdown6-one")
        self.make_product(shop, "lockdown6-two")
        balance = PointService.get_balance(limited)

        response = self.client.post(reverse("admin:shop_product_add"), self.add_payload(shop))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Limited Shop Owner limit")
        self.assertFalse(Product.objects.filter(slug="admin-desk").exists())
        self.assertEqual(PointService.get_balance(limited), balance)

    def test_adding_needs_enough_points(self):
        broke = self.make_seller("lockdown6_broke")
        shop = self.make_shop(broke, "lockdown6-broke-shop")
        response = self.client.post(reverse("admin:shop_product_add"), self.add_payload(shop))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Insufficient points")
        self.assertFalse(Product.objects.filter(slug="admin-desk").exists())


class ProductInventoryAdminLockdownTests(LockdownTestCase):
    def setUp(self):
        super().setUp()
        self.product = self.make_product(self.make_shop(self.make_seller("lockdown6_inv"), "lockdown6-inv"), "lockdown6-kettle", stock=10)
        self.inventory = ProductInventory.objects.get(product=self.product)
        self.changelist = reverse("admin:shop_productinventory_changelist")

    def adjust(self, **data):
        return self.client.post(self.changelist, {
            "action": "adjust_stock", "_selected_action": [str(self.inventory.pk)], **data,
        })

    def test_counters_cannot_be_posted(self):
        response = self.client.post(
            reverse("admin:shop_productinventory_change", args=[self.inventory.pk]),
            {"available_quantity": "500", "reserved_quantity": "0", "sold_quantity": "0", "_save": "Save"},
        )
        self.assertEqual(response.status_code, 302)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.available_quantity, 10)

    def test_rows_cannot_be_added_or_deleted_here(self):
        self.assertEqual(self.client.get(reverse("admin:shop_productinventory_add")).status_code, 403)
        response = self.client.post(
            reverse("admin:shop_productinventory_delete", args=[self.inventory.pk]), {"post": "yes"}
        )
        self.assertEqual(response.status_code, 403)

    def test_adjust_action_goes_through_the_inventory_service(self):
        response = self.adjust()  # first pass: the form
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="quantity"')

        response = self.adjust(apply_reason="1", quantity="5", reason="Counted the back room again")
        self.assertEqual(response.status_code, 302)

        self.inventory.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.inventory.available_quantity, 15)
        self.assertEqual(self.product.stock, 15)
        self.assertTrue(
            InventoryTransaction.objects.filter(product=self.product, quantity=5, actor=self.superuser).exists()
        )

    def test_adjust_action_validates_its_input(self):
        for quantity, reason, message in (
            ("lots", "Counted the back room again", "whole number"),
            ("0", "Counted the back room again", "cannot be zero"),
            ("5", "short", "at least 10 characters"),
        ):
            with self.subTest(quantity=quantity, reason=reason):
                response = self.adjust(apply_reason="1", quantity=quantity, reason=reason)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.available_quantity, 10)

    def test_view_only_staff_cannot_adjust(self):
        viewer = User.objects.create_user(username="lockdown6_viewer", password="Lockdown-View-1", is_staff=True)
        viewer.user_permissions.add(
            *AuthPermission.objects.filter(content_type__app_label="shop", codename="view_productinventory")
        )
        self.client.force_login(viewer)
        self.adjust(apply_reason="1", quantity="5", reason="Counted the back room again")
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.available_quantity, 10)


class ShopAndSellerAdminLockdownTests(LockdownTestCase):
    def test_moving_a_shop_respects_the_product_cap(self):
        shop = self.make_shop(self.make_seller("lockdown6_from"), "lockdown6-busy-shop")
        for n in range(3):
            self.make_product(shop, f"lockdown6-busy-{n}")
        limited = self.make_seller("lockdown6_to", SellerProfile.TYPE_LIMITED_SHOP_OWNER)

        url = reverse("admin:shops_shop_change", args=[shop.pk])
        response = self.client.post(url, self.change_form_data(url, owner=str(limited.pk)))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "over the Limited Shop Owner limit")
        shop.refresh_from_db()
        self.assertNotEqual(shop.owner, limited)

    def test_ownership_move_is_audited(self):
        old_owner = self.make_seller("lockdown6_old")
        shop = self.make_shop(old_owner, "lockdown6-moving-shop")
        new_owner = self.make_seller("lockdown6_new")

        url = reverse("admin:shops_shop_change", args=[shop.pk])
        response = self.client.post(url, self.change_form_data(url, owner=str(new_owner.pk)))
        self.assertEqual(response.status_code, 302)
        row = self.audit_rows("ADMIN_SHOP_EDITED", shop).get()
        # Only the owner changed; the re-posted location no longer reads as an
        # edit (BUG-016, TASK-019).
        self.assertEqual(row.metadata["previous_state"], {"owner": old_owner.pk})
        self.assertEqual(row.metadata["new_state"], {"owner": new_owner.pk})

    def test_seller_account_is_read_only_and_edits_are_audited(self):
        seller = self.make_seller("lockdown6_profile")
        stranger = User.objects.create_user(username="lockdown6_stranger", password="Lockdown-Str-1")

        self.assert_change_form_keeps(
            seller,
            reverse("admin:sellers_sellerprofile_change", args=[seller.pk]),
            crafted={"user": str(stranger.pk)},
            harmless={"business_name": "Renamed Business"},
        )
        self.assertNotEqual(seller.user, stranger)
        row = self.audit_rows("ADMIN_SELLER_EDITED", seller).get()
        self.assertEqual(row.metadata["new_state"], {"business_name": "Renamed Business"})

    def test_switching_to_limited_respects_the_product_cap(self):
        seller = self.make_seller("lockdown6_big")
        shop = self.make_shop(seller, "lockdown6-big-shop")
        for n in range(3):
            self.make_product(shop, f"lockdown6-big-{n}")

        url = reverse("admin:sellers_sellerprofile_change", args=[seller.pk])
        response = self.client.post(url, self.change_form_data(url, seller_type=SellerProfile.TYPE_LIMITED_SHOP_OWNER))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "may hold at most 2")
        seller.refresh_from_db()
        self.assertEqual(seller.seller_type, SellerProfile.TYPE_FULL_SHOP_OWNER)

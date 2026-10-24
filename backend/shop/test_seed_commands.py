"""
TASK-037 / BUG-068: the seed commands run only on a confirmed development
database and change only their own rows: accounts with a @minishop.demo
address, the shops those own, and the products in them. A real account,
shop or product that shares a username or slug is left exactly as it was.
"""

import shutil
import tempfile
from decimal import Decimal
from io import BytesIO, StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from PIL import Image

from sellers.models import SellerProfile
from shop.management.commands import seed_demo_data, seed_showcase
from shop.models import Category, InventoryTransaction, Product
from shops.models import Shop

User = get_user_model()

FLAG = "--i-know-this-is-a-dev-db"


def placeholder(*args, **kwargs):
    buffer = BytesIO()
    Image.new("RGB", (4, 4), (90, 90, 90)).save(buffer, "PNG")
    return ContentFile(buffer.getvalue()), "png"


class SeedCommandTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media = tempfile.mkdtemp(prefix="seed-cmd-media-")
        cls.settings_override = override_settings(DEBUG=True, MEDIA_ROOT=cls.media)
        cls.settings_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.settings_override.disable()
        shutil.rmtree(cls.media, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        # No network, and a small slice of the catalogue so a run is quick.
        for patcher in (
            mock.patch.object(seed_showcase, "fetch_photo", placeholder),
            mock.patch.object(seed_showcase, "GALLERY_VARIANTS", [{}]),
            mock.patch.object(seed_demo_data, "build_product_photo", placeholder),
            mock.patch.object(seed_demo_data, "GALLERY_SHADE_FACTORS", (0.3,)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def real_shop(self, slug="real-shop", username="real_owner"):
        seller = SellerProfile.objects.create(
            user=User.objects.create_user(username=username, email=f"{username}@example.com", password="Real-Pass-123"),
            business_name="Real Business", status=SellerProfile.STATUS_ACTIVE,
        )
        return Shop.objects.create(owner=seller, name="Real Shop Name", slug=slug, status=Shop.STATUS_ACTIVE)

    def real_product(self, name, shop):
        category = Category.objects.get_or_create(slug="real-category", defaults={"name": "Real Category"})[0]
        return Product.objects.create(
            name=name, slug=seed_showcase.slugify(name), category=category, shop=shop, price=Decimal("1.00"),
            stock=1, status=Product.STATUS_DRAFT, description="A real seller's product.",
        )

    @staticmethod
    def snapshot(model, pk, *fields):
        return model.objects.filter(pk=pk).values(*fields).get()


class SeedGuardTests(SeedCommandTestCase):
    def test_both_commands_refuse_without_debug_or_the_flag(self):
        for command in ("seed_showcase", "seed_demo_data"):
            with self.subTest(command=command):
                with override_settings(DEBUG=False), self.assertRaisesMessage(CommandError, "DEBUG is off"):
                    call_command(command, FLAG, stdout=StringIO())
                with self.assertRaisesMessage(CommandError, FLAG):
                    call_command(command, stdout=StringIO())
        self.assertFalse(Product.objects.exists())


class SeedShowcaseTests(SeedCommandTestCase):
    def run_showcase(self, shops, products, *args):
        with mock.patch.object(seed_showcase, "SHOPS", shops), mock.patch.object(seed_showcase, "PRODUCTS", products):
            call_command("seed_showcase", FLAG, *args, stdout=StringIO())

    def test_real_rows_sharing_a_username_or_slug_are_left_alone(self):
        technest, urban, bloom = seed_showcase.SHOPS[:3]
        keyboard = next(p for p in seed_showcase.PRODUCTS if p[1] == technest["slug"])
        tote = next(p for p in seed_showcase.PRODUCTS if p[1] == urban["slug"])
        mug = next(p for p in seed_showcase.PRODUCTS if p[1] == bloom["slug"])

        # A real person already uses the first seed username...
        squatter = User.objects.create_user(username=technest["username"], email="person@example.com", password="Real-Pass-123")
        # ...a real seller owns the second seed shop's slug, and a real
        # product has the third seed product's slug in a real shop.
        real_urban = self.real_shop(slug=urban["slug"])
        real_mug = self.real_product(mug[0], self.real_shop(username="real_owner_2"))
        before = (
            self.snapshot(User, squatter.pk, "password", "email", "first_name"),
            self.snapshot(Shop, real_urban.pk, "owner_id", "name", "description", "status"),
            self.snapshot(Product, real_mug.pk, "shop_id", "name", "price", "status", "stock"),
        )

        self.run_showcase([technest, urban, bloom], [keyboard, tote, mug], "--password", "Seed-Pass-123")

        after = (
            self.snapshot(User, squatter.pk, "password", "email", "first_name"),
            self.snapshot(Shop, real_urban.pk, "owner_id", "name", "description", "status"),
            self.snapshot(Product, real_mug.pk, "shop_id", "name", "price", "status", "stock"),
        )
        self.assertEqual(after, before)
        self.assertFalse(SellerProfile.objects.filter(user=squatter).exists())
        self.assertFalse(Product.objects.filter(slug=seed_showcase.slugify(keyboard[0])).exists())
        self.assertFalse(Product.objects.filter(slug=seed_showcase.slugify(tote[0])).exists())
        # The seed shop with no conflict was created, as before.
        self.assertTrue(Shop.objects.filter(slug=bloom["slug"], owner__user__username=bloom["username"]).exists())

    def test_existing_seed_accounts_keep_their_password_and_stock_goes_through_the_ledger(self):
        bloom = seed_showcase.SHOPS[2]
        mug = next(p for p in seed_showcase.PRODUCTS if p[1] == bloom["slug"])

        self.run_showcase([bloom], [mug], "--password", "First-Pass-123")
        self.run_showcase([bloom], [mug], "--password", "Second-Pass-456")

        account = User.objects.get(username=bloom["username"])
        self.assertTrue(account.check_password("First-Pass-123"))
        product = Product.objects.get(slug=seed_showcase.slugify(mug[0]))
        self.assertEqual(product.inventory.available_quantity, mug[6])
        self.assertTrue(
            InventoryTransaction.objects.filter(
                product=product, transaction_type=InventoryTransaction.TYPE_INITIAL_STOCK, quantity=mug[6]
            ).exists()
        )


class SeedDemoDataTests(SeedCommandTestCase):
    def test_products_go_into_the_seeders_own_store_and_real_rows_are_left_alone(self):
        keyboard, headphones = seed_demo_data.PRODUCTS[:2]
        real_keyboard = self.real_product(keyboard[0], self.real_shop())
        electronics = Category.objects.create(
            name="Electronics", slug="electronics", description="Ours, not the seeder's.", is_active=False
        )
        before = (
            self.snapshot(Product, real_keyboard.pk, "shop_id", "name", "price", "status", "stock"),
            self.snapshot(Category, electronics.pk, "name", "description", "is_active", "icon", "image"),
        )

        with mock.patch.object(seed_demo_data, "PRODUCTS", [keyboard, headphones]):
            call_command("seed_demo_data", FLAG, stdout=StringIO())

        after = (
            self.snapshot(Product, real_keyboard.pk, "shop_id", "name", "price", "status", "stock"),
            self.snapshot(Category, electronics.pk, "name", "description", "is_active", "icon", "image"),
        )
        self.assertEqual(after, before)
        seeded = Product.objects.get(slug=seed_demo_data.slugify(headphones[0]))
        self.assertEqual(seeded.shop.slug, seed_demo_data.DEMO_STORE_SLUG)
        self.assertTrue(seeded.shop.owner.user.email.endswith("@minishop.demo"))
        self.assertTrue(InventoryTransaction.objects.filter(product=seeded).exists())

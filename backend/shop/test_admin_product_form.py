"""
The product add / change page in the Django admin.

templates/admin/shop/product/change_form.html redraws ProductAdmin's form: a
summary header, a Photos card whose gallery inline is a custom tile template
(admin/edit_inline/mp_gallery.html), a main-photo widget, and a storefront
checklist. The markup is new but the POST contract must not be: these tests
check the page renders for editors, adders and view-only staff, and that the
gallery formset and the main photo's clear checkbox still save exactly as
Django's stock widgets did.
"""
import io
import shutil
import tempfile
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission as AuthPermission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from sellers.models import SellerProfile
from shops.models import Shop
from shop.models import Category, Product, ProductImage

User = get_user_model()

MEDIA_ROOT = tempfile.mkdtemp(prefix="minishop-admin-product-")


def png(name="photo.png", color=(186, 134, 48)):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 6), color).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class ProductAdminFormTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="product_form_admin", email="pfa@example.com", password="pw-123456"
        )
        seller_user = User.objects.create_user(username="pf_seller", password="pw-123456")
        self.seller = SellerProfile.objects.create(
            user=seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            status=SellerProfile.STATUS_ACTIVE,
            business_name="Bloom Living",
        )
        self.shop = Shop.objects.create(
            owner=self.seller, name="Bloom Shop", slug="bloom-shop", status=Shop.STATUS_ACTIVE
        )
        self.category = Category.objects.create(name="Garden", slug="garden", is_active=True)
        self.product = Product.objects.create(
            name="Plant Pot Set",
            slug="plant-pot-set",
            category=self.category,
            shop=self.shop,
            description="Three ceramic pots.",
            price=Decimal("1480.00"),
            old_price=Decimal("1800.00"),
            stock=40,
            badge="HOT",
            status=Product.STATUS_PUBLISHED,
            is_active=True,
            image=png("main.png"),
        )
        self.first = ProductImage.objects.create(product=self.product, image=png("g1.png"), order=1)
        self.second = ProductImage.objects.create(product=self.product, image=png("g2.png"), order=2)
        self.change_url = reverse("admin:shop_product_change", args=[self.product.pk])
        self.client.force_login(self.superuser)

    def post_data(self, **overrides):
        """The change form as a browser posts it, gallery rows unchanged."""
        data = {
            "name": self.product.name,
            "slug": self.product.slug,
            "category": self.category.pk,
            "shop": self.shop.pk,
            "description": self.product.description,
            "price": "1480.00",
            "old_price": "1800.00",
            "stock": "40",
            "badge": "HOT",
            "status": Product.STATUS_PUBLISHED,
            "is_active": "on",
            "submitted_at_0": "", "submitted_at_1": "",
            "reviewed_at_0": "", "reviewed_at_1": "",
            "reviewed_by": "",
            "rejection_reason": "",
            "images-TOTAL_FORMS": "2",
            "images-INITIAL_FORMS": "2",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "1000",
            "images-0-id": self.first.pk,
            "images-0-product": self.product.pk,
            "images-0-order": "1",
            "images-1-id": self.second.pk,
            "images-1-product": self.product.pk,
            "images-1-order": "2",
            "_continue": "Save and continue editing",
        }
        data.update(overrides)
        return data

    def assertSaved(self, response):
        if response.status_code != 302:
            context = response.context
            errors = [context["adminform"].form.errors] + [
                formset.formset.errors for formset in context["inline_admin_formsets"]
            ]
            self.fail(f"Form did not save: {errors}")

    # -- Rendering ---------------------------------------------------------

    def test_change_page_shows_summary_photos_and_checklist(self):
        response = self.client.get(self.change_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="mp-profile mp-product-hero"')
        self.assertContains(response, "Live on storefront")
        storefront = settings.STOREFRONT_URL.rstrip("/")
        self.assertContains(response, f'href="{storefront}/product/plant-pot-set"')
        # Price and discount in Taka, never dollars.
        self.assertContains(response, "৳1,480.00")
        self.assertContains(response, "18% off")
        # Main photo widget and one tile per gallery photo, as real images.
        self.assertContains(response, 'data-mp-cover-input')
        self.assertContains(response, 'name="image-clear"')
        self.assertContains(response, self.first.image.url)
        self.assertContains(response, self.second.image.url)
        self.assertEqual(response.content.decode().count("inline-related mp-tile has_original"), 2)
        self.assertContains(response, 'id="images-empty"')
        self.assertContains(response, "3 photos")
        # Every storefront condition passes.
        self.assertContains(response, "Visible on the storefront")
        self.assertContains(response, "5/5")
        self.assertContains(response, 'id="mp-product-data"')

    def test_hidden_product_names_what_keeps_it_off_the_storefront(self):
        self.product.status = Product.STATUS_DRAFT
        self.product.stock = 3
        self.product.save()
        response = self.client.get(self.change_url)
        self.assertContains(response, "Hidden from storefront")
        self.assertNotContains(response, "View on storefront")
        self.assertContains(response, "Hidden from the storefront")
        self.assertContains(response, "4/5")
        self.assertContains(response, "Low stock")

    def test_add_page_renders_empty_photo_state(self):
        response = self.client.get(reverse("admin:shop_product_add"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "mp-product-hero")
        self.assertContains(response, "Add the main photo")
        self.assertContains(response, 'name="images-TOTAL_FORMS" value="0"')
        self.assertContains(response, 'id="images-empty"')
        self.assertContains(response, "Hidden from the storefront")

    def test_view_only_staff_sees_photos_without_controls(self):
        viewer = User.objects.create_user(username="pf_viewer", password="pw-123456", is_staff=True)
        # The gallery inline shows only to someone who may view ProductImage too.
        viewer.user_permissions.add(*AuthPermission.objects.filter(
            content_type__app_label="shop", codename__in=("view_product", "view_productimage")
        ))
        self.client.force_login(viewer)
        response = self.client.get(self.change_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.first.image.url)
        self.assertContains(response, 'class="mp-image-preview"')
        self.assertNotContains(response, "data-mp-cover-input")
        self.assertNotContains(response, "data-mp-add")
        self.assertNotContains(response, "mp-tile-bin")
        self.assertNotContains(response, 'type="file"')

    # -- Saving ------------------------------------------------------------

    def test_gallery_rows_reorder_delete_and_add(self):
        data = self.post_data(**{
            "images-TOTAL_FORMS": "3",
            "images-0-order": "2",
            "images-1-DELETE": "on",
            "images-2-product": self.product.pk,
            "images-2-order": "1",
            "images-2-image": png("new.png"),
        })
        self.assertSaved(self.client.post(self.change_url, data))

        self.first.refresh_from_db()
        self.assertEqual(self.first.order, 2)
        self.assertFalse(ProductImage.objects.filter(pk=self.second.pk).exists())
        added = ProductImage.objects.exclude(pk=self.first.pk).get(product=self.product)
        self.assertEqual(added.order, 1)
        self.assertTrue(added.image.name.startswith("products/gallery/new"))
        # No main-photo input was sent, so the main photo is kept.
        self.product.refresh_from_db()
        self.assertTrue(self.product.image.name.startswith("products/main"))

    def test_replacing_a_gallery_photo_keeps_its_row(self):
        self.assertSaved(self.client.post(self.change_url, self.post_data(**{"images-1-image": png("swap.png")})))
        self.second.refresh_from_db()
        self.assertTrue(self.second.image.name.startswith("products/gallery/swap"))
        self.assertEqual(ProductImage.objects.filter(product=self.product).count(), 2)

    def test_failed_save_keeps_the_header_on_the_stored_product(self):
        data = self.post_data(**{
            "name": "Renamed Pot Set",
            "price": "0",
            "images-TOTAL_FORMS": "3",
            "images-2-product": self.product.pk,
            "images-2-order": "3",
            "images-2-image": png("lost.png"),
        })
        response = self.client.post(self.change_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["mp_saved"].name, "Plant Pot Set")
        self.assertContains(response, '<h1 class="mp-profile-name">Plant Pot Set</h1>', html=True)
        self.assertContains(response, "৳1,480.00")
        # The valid new photo is lost with the failed save; its tile says so.
        self.assertContains(response, "Choose this photo again")
        self.assertFalse(ProductImage.objects.filter(image__contains="lost").exists())

    def test_main_photo_remove_and_replace(self):
        self.assertSaved(self.client.post(self.change_url, self.post_data(**{"image": png("cover.png")})))
        self.product.refresh_from_db()
        self.assertTrue(self.product.image.name.startswith("products/cover"))

        self.assertSaved(self.client.post(self.change_url, self.post_data(**{"image-clear": "on"})))
        self.product.refresh_from_db()
        self.assertFalse(self.product.image)

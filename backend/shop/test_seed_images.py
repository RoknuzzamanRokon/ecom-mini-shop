"""
TASK-032 / BUG-043: media/ is runtime uploads only and gitignored, so the
category images seed_demo_data uses ship in shop/fixtures/seed_images/ and
are copied into MEDIA_ROOT when seeding.
"""

import shutil
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from shop.management.commands.seed_demo_data import CATEGORIES, SEED_IMAGE_DIR, seed_category_image


class SeedCategoryImageTests(SimpleTestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp(prefix="seed-media-")
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)

    def test_every_seeded_category_has_a_bundled_image(self):
        missing = [entry["image"] for entry in CATEGORIES if not (SEED_IMAGE_DIR / "categories" / entry["image"]).is_file()]
        self.assertEqual(missing, [])

    def test_seeding_copies_the_image_into_media(self):
        with override_settings(MEDIA_ROOT=self.media):
            self.assertEqual(seed_category_image("clothing.jpg"), "categories/clothing.jpg")
            self.assertIsNone(seed_category_image("no-such-image.jpg"))
        copied = Path(self.media) / "categories" / "clothing.jpg"
        self.assertEqual(copied.read_bytes(), (SEED_IMAGE_DIR / "categories" / "clothing.jpg").read_bytes())

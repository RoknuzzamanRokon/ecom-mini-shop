"""
TASK-019 / BUG-016: a shop opened in the Django admin can be saved again.
The location renders as WKT, reads back to the same point, and a malformed
or off-the-globe value is a form error rather than a 500.
"""

import html
import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from audit.models import AuditLog
from sellers.models import SellerProfile
from shops.fields import Point
from shops.models import Shop

User = get_user_model()

HERE = Point(90.4125, 23.8103)


class ShopAdminLocationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="loc_super", email="loc@example.com", password="Loc-Super-123"
        )
        owner = SellerProfile.objects.create(
            user=User.objects.create_user(username="loc_owner", password="Loc-Owner-123"),
            business_name="Loc Owner",
            status=SellerProfile.STATUS_ACTIVE,
        )
        cls.shop = Shop.objects.create(
            owner=owner, name="Loc Shop", slug="loc-shop", status=Shop.STATUS_ACTIVE, location=HERE
        )

    def setUp(self):
        self.client.force_login(self.superuser)
        self.url = reverse("admin:shops_shop_change", args=[self.shop.pk])

    def rendered_location(self):
        """The location exactly as the change page renders it into its input."""
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        tag = re.search(r'<input[^>]*name="location"[^>]*>', page.content.decode()).group(0)
        return html.unescape(re.search(r'value="([^"]*)"', tag).group(1))

    def post(self, **overrides):
        data = {
            "owner": str(self.shop.owner_id), "name": self.shop.name, "slug": self.shop.slug,
            "description": "", "phone": "", "address": "", "location": self.rendered_location(),
            "rejection_reason": "", "suspension_reason": "", "_save": "Save",
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_the_change_page_renders_the_location_as_wkt(self):
        self.assertEqual(self.rendered_location(), "POINT(90.4125000 23.8103000)")

    def test_reopening_and_saving_a_shop_round_trips(self):
        response = self.post(name="Loc Shop Renamed")

        self.assertEqual(response.status_code, 302)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.name, "Loc Shop Renamed")
        self.assertEqual(self.shop.location, HERE)
        # An untouched location is not recorded as an edit.
        row = AuditLog.objects.get(action="ADMIN_SHOP_EDITED", target_id=str(self.shop.pk))
        self.assertEqual(set(row.metadata["new_state"]), {"name"})

    def test_a_new_location_is_saved(self):
        response = self.post(location="POINT(91.8687 24.8949)")
        self.assertEqual(response.status_code, 302)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.location, Point(91.8687, 24.8949))

    def test_bad_locations_are_form_errors(self):
        cases = {
            "Point(longitude=90.4125, latitude=23.8103)": "Enter the location as POINT(longitude latitude)",
            "POINT(1.2.3 4)": "Enter the location as POINT(longitude latitude)",
            "POINT(200 10)": "Longitude must be between -180 and 180",
            "POINT(90 95)": "Latitude must be between -90 and 90",
        }
        for value, message in cases.items():
            with self.subTest(location=value):
                response = self.post(name="Should Not Save", location=value)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.shop.refresh_from_db()
                self.assertEqual(self.shop.name, "Loc Shop")
                self.assertEqual(self.shop.location, HERE)

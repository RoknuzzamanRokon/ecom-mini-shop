"""
TASK-009: an audit trail that can be trusted.

- BUG-015: the recorded IP is not client-controlled, always fits its column,
  and an admin action never commits a change without its audit row.
- BUG-041: deleting a user keeps their name on the rows they wrote.
- BUG-049: the /api/shops/staff/ lifecycle routes lock the row and write
  one audit row per change.
"""

import importlib
from io import StringIO
from unittest import mock

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import DataError
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from audit.services import AuditService
from audit.utils import get_client_ip
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from shops.fields import Point
from shops.models import Shop

User = get_user_model()

SPOOFED = "203.0.113.77, 198.51.100.4, 192.0.2.250, 2001:db8::dead:beef"  # 60+ characters


def request_with(remote_addr="127.0.0.1", forwarded=None):
    meta = {"REMOTE_ADDR": remote_addr}
    if forwarded is not None:
        meta["HTTP_X_FORWARDED_FOR"] = forwarded
    return RequestFactory().get("/", **meta)


class GetClientIpTests(SimpleTestCase):
    def test_forwarded_for_is_ignored_without_trusted_proxies(self):
        self.assertEqual(get_client_ip(request_with("10.1.2.3", "203.0.113.9")), "10.1.2.3")

    def test_invalid_or_missing_address_is_none(self):
        self.assertIsNone(get_client_ip(request_with("not-an-ip")))
        self.assertIsNone(get_client_ip(request_with("")))

    def test_ipv6_zone_is_dropped(self):
        self.assertEqual(get_client_ip(request_with("fe80::1%eth0")), "fe80::1")

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_one_proxy_takes_the_last_hop(self):
        # The client wrote 203.0.113.9 itself; the proxy appended 198.51.100.4.
        self.assertEqual(
            get_client_ip(request_with("10.0.0.1", "203.0.113.9, 198.51.100.4")), "198.51.100.4"
        )

    @override_settings(TRUSTED_PROXY_COUNT=2)
    def test_two_proxies_take_the_second_hop_from_the_right(self):
        self.assertEqual(
            get_client_ip(request_with("10.0.0.1", "1.1.1.1, 203.0.113.9, 198.51.100.4")), "203.0.113.9"
        )

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_a_garbage_hop_is_none_not_an_error(self):
        self.assertIsNone(get_client_ip(request_with("10.0.0.1", "x" * 60)))

    @override_settings(TRUSTED_PROXY_COUNT=1)
    def test_no_forwarded_header_behind_a_proxy_uses_remote_addr(self):
        self.assertEqual(get_client_ip(request_with("10.0.0.1")), "10.0.0.1")


class ShopFixtureMixin:
    def make_shop(self, status=Shop.STATUS_PENDING, **extra):
        n = Shop.objects.count()
        owner_user = User.objects.create_user(username=f"trail_owner_{n}", password="Trail-Owner-123")
        owner = SellerProfile.objects.create(
            user=owner_user, business_name=f"Trail Seller {n}", status=SellerProfile.STATUS_ACTIVE
        )
        return Shop.objects.create(
            owner=owner, name=f"Trail Shop {n}", slug=f"trail-shop-{n}", status=status,
            location=Point(90.4125, 23.8103), **extra,
        )


class AdminActionAuditTests(ShopFixtureMixin, TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="trail_super", email="trail@example.com", password="Trail-Super-123"
        )
        self.client.force_login(self.superuser)

    def approve(self, shop, **extra):
        return self.client.post(
            reverse("admin:shops_shop_changelist"),
            {"action": "approve_and_activate", "_selected_action": [str(shop.pk)]},
            **extra,
        )

    def test_spoofed_forwarded_for_is_not_recorded(self):
        shop = self.make_shop()
        response = self.approve(shop, HTTP_X_FORWARDED_FOR=SPOOFED)
        self.assertEqual(response.status_code, 302)

        shop.refresh_from_db()
        self.assertEqual(shop.status, Shop.STATUS_ACTIVE)
        row = AuditLog.objects.get(action="ADMIN_SHOP_APPROVE", target_id=str(shop.pk))
        self.assertEqual(row.ip_address, "127.0.0.1")

    def test_a_failed_audit_write_undoes_the_change(self):
        shop = self.make_shop()
        with mock.patch("audit.admin_mixins.AuditService.log", side_effect=DataError("too long")):
            with self.assertRaises(DataError):
                self.approve(shop)
        shop.refresh_from_db()
        self.assertEqual(shop.status, Shop.STATUS_PENDING)


class ActorSnapshotTests(TestCase):
    def test_deleting_the_actor_keeps_the_attribution(self):
        actor = User.objects.create_user(username="trail_leaver", password="Trail-Leaver-123")
        actor_pk = actor.pk
        row = AuditService.log(action="TRAIL_TEST", target=actor, actor=actor)
        self.assertEqual((row.actor_username, row.actor_user_id), ("trail_leaver", actor_pk))

        actor.delete()
        row.refresh_from_db()
        self.assertIsNone(row.actor)
        self.assertEqual(row.actor_username, "trail_leaver")
        self.assertEqual(row.actor_user_id, actor_pk)
        self.assertEqual(row.actor_name, "trail_leaver (deleted)")
        self.assertIn("trail_leaver (deleted)", str(row))

    def test_system_rows_stay_system(self):
        row = AuditService.log(action="TRAIL_SYSTEM", target=Role(code="X", pk=1))
        self.assertEqual(row.actor_name, "System")

    def test_migration_backfills_existing_rows(self):
        actor = User.objects.create_user(username="trail_old_row", password="Trail-Old-123")
        row = AuditService.log(action="TRAIL_OLD", target=actor, actor=actor)
        AuditLog.objects.filter(pk=row.pk).update(actor_username="", actor_user_id=None)

        migration = importlib.import_module("audit.migrations.0002_auditlog_actor_snapshot")
        migration.snapshot_existing_actors(apps, None)

        row.refresh_from_db()
        self.assertEqual((row.actor_username, row.actor_user_id), ("trail_old_row", actor.pk))


class ConsoleAuditApiSnapshotTests(APITestCase):
    def test_console_rows_name_a_deleted_actor(self):
        call_command("seed_rbac", stdout=StringIO())
        viewer = User.objects.create_user(username="trail_viewer", password="Trail-Viewer-123")
        assign_user_role(viewer, Role.ROLE_SUPER_ADMINISTRATOR)
        leaver = User.objects.create_user(username="trail_gone", password="Trail-Gone-123")
        AuditService.log(action="TRAIL_API", target=viewer, actor=leaver)
        leaver.delete()

        self.client.force_authenticate(user=viewer)
        response = self.client.get("/api/admin/audit-logs/", {"actor": "trail_gone"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        rows = response.data["results"]
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["actor"])
        self.assertEqual(rows[0]["actor_username"], "trail_gone")


class StaffShopRouteAuditTests(ShopFixtureMixin, APITestCase):
    REASON = {"reason": "Documents could not be verified."}

    def setUp(self):
        call_command("seed_rbac", stdout=StringIO())
        self.staff = User.objects.create_user(username="trail_ops", password="Trail-Ops-123")
        assign_user_role(self.staff, Role.ROLE_OPERATION_MANAGER)
        self.client.force_authenticate(user=self.staff)

    def post(self, shop, action, data=None):
        return self.client.post(f"/api/shops/staff/{shop.pk}/{action}/", data or {}, format="json")

    def rows(self, shop):
        return AuditLog.objects.filter(target_type="Shop", target_id=str(shop.pk), action__startswith="ADMIN_SHOP_")

    def test_each_transition_writes_exactly_one_audit_row(self):
        cases = (
            ("approve", Shop.STATUS_PENDING, {}, Shop.STATUS_ACTIVE),
            ("reject", Shop.STATUS_PENDING, self.REASON, Shop.STATUS_REJECTED),
            ("suspend", Shop.STATUS_ACTIVE, self.REASON, Shop.STATUS_SUSPENDED),
            ("reactivate", Shop.STATUS_SUSPENDED, {}, Shop.STATUS_ACTIVE),
        )
        for action, start, data, end in cases:
            with self.subTest(action=action):
                extra = {"suspension_reason": "Under review."} if start == Shop.STATUS_SUSPENDED else {}
                shop = self.make_shop(start, **extra)
                response = self.post(shop, action, data)
                self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
                row = self.rows(shop).get()
                self.assertEqual(row.action, f"ADMIN_SHOP_{action.upper()}")
                self.assertEqual(row.actor, self.staff)
                self.assertEqual(row.metadata["previous_state"], {"status": start})
                self.assertEqual(row.metadata["new_state"], {"status": end})

    def test_refused_transition_writes_no_row(self):
        shop = self.make_shop(Shop.STATUS_ACTIVE)
        response = self.post(shop, "approve")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self.rows(shop).exists())

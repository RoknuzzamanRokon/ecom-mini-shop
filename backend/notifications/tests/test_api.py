"""
The inbox and preferences API (docs/NOTIFICATION_SYSTEM.md §8, Task 11): own
rows only (IDOR), audience permissions, keyset paging, read-all scoping, the
unread-count throttle, and preferences with their locks and audit trail.
"""
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from audit.models import AuditLog
from notifications import categories as c
from notifications.models import Audience, Channel, Notification, NotificationPreference
from rbac.models import Permission, Role, UserPermission
from rbac.services import assign_user_role
from sellers.models import SellerProfile

User = get_user_model()

INBOX = "/api/notifications/"
UNREAD = "/api/notifications/unread-count/"
READ_ALL = "/api/notifications/read-all/"
PREFERENCES = "/api/notifications/preferences/"


def mark_read_url(pk):
    return f"/api/notifications/{pk}/read/"


class ApiFixtures:
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.customer = User.objects.create_user(username="api_customer", password="pw")
        assign_user_role(cls.customer, Role.ROLE_CUSTOMER)
        cls.other = User.objects.create_user(username="api_other", password="pw")
        cls.seller = User.objects.create_user(username="api_seller", password="pw")
        SellerProfile.objects.create(
            user=cls.seller, seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="API Co", status=SellerProfile.STATUS_SUSPENDED, suspension_reason="Review",
        )
        cls.staff = User.objects.create_user(username="api_staff", password="pw")
        assign_user_role(cls.staff, Role.ROLE_SUPPORT_TEAM)

    def setUp(self):
        cache.clear()  # the unread-count throttle keeps its history in the cache
        self.base_time = timezone.now()

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def notify(self, user, audience=Audience.CUSTOMER, minutes_ago=0, read=False, category=c.ORDERS, title="Hello"):
        return Notification.objects.create(
            recipient=user, event=None, event_type="order.placed", category=category, audience=audience,
            title=title, body="Body", action_url="/profile/orders/X",
            occurred_at=self.base_time - timedelta(minutes=minutes_ago),
            read_at=self.base_time if read else None,
        )


class InboxTests(ApiFixtures, TestCase):
    def test_lists_your_own_notifications_newest_first(self):
        older = self.notify(self.customer, minutes_ago=5, title="Older")
        newer = self.notify(self.customer, minutes_ago=1, title="Newer")
        self.notify(self.other, title="Someone else's")
        self.notify(self.customer, audience=Audience.STAFF, title="Wrong surface")

        response = self.client_for(self.customer).get(INBOX, {"audience": "CUSTOMER"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["results"]], [newer.pk, older.pk])
        self.assertIsNone(response.data["next_cursor"])
        self.assertEqual(
            set(response.data["results"][0]),
            {"id", "event_type", "category", "title", "body", "action_url", "priority", "occurred_at", "read_at"},
        )

    def test_unread_filter(self):
        self.notify(self.customer, read=True)
        unread = self.notify(self.customer)
        response = self.client_for(self.customer).get(INBOX, {"audience": "CUSTOMER", "unread": "1"})
        self.assertEqual([row["id"] for row in response.data["results"]], [unread.pk])

    def test_keyset_pages_of_twenty(self):
        rows = [self.notify(self.customer, minutes_ago=i) for i in range(25)]
        # Two rows at the same instant still page in a stable order (by id).
        tie = self.notify(self.customer, minutes_ago=24)
        client = self.client_for(self.customer)

        first = client.get(INBOX, {"audience": "CUSTOMER"}).data
        self.assertEqual(len(first["results"]), 20)
        self.assertIsNotNone(first["next_cursor"])
        second = client.get(INBOX, {"audience": "CUSTOMER", "cursor": first["next_cursor"]}).data
        self.assertIsNone(second["next_cursor"])

        seen = [row["id"] for row in first["results"] + second["results"]]
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(set(seen), {row.pk for row in rows} | {tie.pk})

    def test_bad_parameters_are_400(self):
        client = self.client_for(self.customer)
        for params in ({}, {"audience": "PARTNER"}, {"audience": "CUSTOMER", "cursor": "not-a-cursor"}):
            with self.subTest(params=params):
                self.assertEqual(client.get(INBOX, params).status_code, 400)

    def test_signed_out_is_401_everywhere(self):
        client = APIClient()
        for method, url in (("get", INBOX), ("get", UNREAD), ("post", READ_ALL), ("get", PREFERENCES),
                            ("post", mark_read_url(1))):
            with self.subTest(url=url):
                self.assertEqual(getattr(client, method)(url, {"audience": "CUSTOMER"}).status_code, 401)


class AudiencePermissionTests(ApiFixtures, TestCase):
    def status_for(self, user, audience):
        return self.client_for(user).get(UNREAD, {"audience": audience}).status_code

    def test_customer_inbox_is_open_to_everyone_signed_in(self):
        for user in (self.customer, self.other, self.seller, self.staff):
            with self.subTest(user=user.username):
                self.assertEqual(self.status_for(user, "CUSTOMER"), 200)

    def test_seller_inbox_needs_a_seller_profile_in_any_status(self):
        self.assertEqual(self.status_for(self.seller, "SELLER"), 200)  # suspended, still allowed
        for user in (self.customer, self.staff):
            with self.subTest(user=user.username):
                self.assertEqual(self.status_for(user, "SELLER"), 403)

    def test_staff_inbox_needs_a_staff_role_or_grant(self):
        self.assertEqual(self.status_for(self.staff, "STAFF"), 200)
        for user in (self.customer, self.other, self.seller):
            with self.subTest(user=user.username):
                self.assertEqual(self.status_for(user, "STAFF"), 403)
        django_staff = User.objects.create_user(username="api_django_staff", password="pw", is_staff=True)
        granted = User.objects.create_user(username="api_granted", password="pw")
        UserPermission.objects.create(user=granted, permission=Permission.objects.get(code="support.staff.view"))
        for user in (django_staff, granted):
            with self.subTest(user=user.username):
                self.assertEqual(self.status_for(user, "STAFF"), 200)

    def test_read_all_checks_the_audience_too(self):
        self.assertEqual(self.client_for(self.customer).post(f"{READ_ALL}?audience=STAFF").status_code, 403)


class ReadStateTests(ApiFixtures, TestCase):
    def test_unread_count_is_per_audience(self):
        self.notify(self.seller)
        self.notify(self.seller, audience=Audience.SELLER)
        self.notify(self.seller, audience=Audience.SELLER)
        self.notify(self.seller, audience=Audience.SELLER, read=True)
        client = self.client_for(self.seller)
        self.assertEqual(client.get(UNREAD, {"audience": "SELLER"}).data, {"unread": 2})
        self.assertEqual(client.get(UNREAD, {"audience": "CUSTOMER"}).data, {"unread": 1})

    def test_marking_your_own_notification_read(self):
        row = self.notify(self.customer)
        client = self.client_for(self.customer)
        self.assertEqual(client.post(mark_read_url(row.pk)).status_code, 204)
        row.refresh_from_db()
        first_read = row.read_at
        self.assertIsNotNone(first_read)
        self.assertEqual(client.post(mark_read_url(row.pk)).status_code, 204)  # idempotent
        row.refresh_from_db()
        self.assertEqual(row.read_at, first_read)

    def test_someone_elses_notification_is_a_404(self):
        theirs = self.notify(self.other)
        for user in (self.customer, self.staff):
            with self.subTest(user=user.username):
                self.assertEqual(self.client_for(user).post(mark_read_url(theirs.pk)).status_code, 404)
        theirs.refresh_from_db()
        self.assertIsNone(theirs.read_at)
        self.assertEqual(self.client_for(self.customer).post(mark_read_url(999999999)).status_code, 404)

    def test_read_all_is_scoped_to_you_and_the_audience(self):
        mine = [self.notify(self.seller), self.notify(self.seller)]
        seller_side = self.notify(self.seller, audience=Audience.SELLER)
        someone_else = self.notify(self.other)

        response = self.client_for(self.seller).post(f"{READ_ALL}?audience=CUSTOMER")

        self.assertEqual(response.data, {"updated": 2})
        self.assertTrue(all(Notification.objects.get(pk=row.pk).read_at for row in mine))
        self.assertIsNone(Notification.objects.get(pk=seller_side.pk).read_at)
        self.assertIsNone(Notification.objects.get(pk=someone_else.pk).read_at)

    @override_settings(NOTIFICATIONS={"UNREAD_COUNT_RATE": "3/min"})
    def test_unread_count_is_throttled_per_user(self):
        client = self.client_for(self.customer)
        for _ in range(3):
            self.assertEqual(client.get(UNREAD, {"audience": "CUSTOMER"}).status_code, 200)
        self.assertEqual(client.get(UNREAD, {"audience": "CUSTOMER"}).status_code, 429)
        # Another person has their own allowance; the inbox itself isn't throttled.
        self.assertEqual(self.client_for(self.other).get(UNREAD, {"audience": "CUSTOMER"}).status_code, 200)
        self.assertEqual(client.get(INBOX, {"audience": "CUSTOMER"}).status_code, 200)


class PreferenceApiTests(ApiFixtures, TestCase):
    def categories(self, user, **params):
        response = self.client_for(user).get(PREFERENCES, params)
        self.assertEqual(response.status_code, 200)
        return {row["category"]: row for row in response.data}

    def put(self, user, body):
        return self.client_for(user).put(PREFERENCES, body, format="json")

    def test_you_see_the_categories_that_reach_you(self):
        self.assertEqual(list(self.categories(self.customer)), [c.ORDERS, c.PAYMENTS, c.SUPPORT])
        self.assertIn(c.STAFF_QUEUE, self.categories(self.staff))
        seller = self.categories(self.seller)
        self.assertLessEqual({c.SELLER_ORDERS, c.ACCOUNT, c.SHOPS, c.CATALOG, c.INVENTORY, c.REVIEWS, c.WALLET}, set(seller))
        self.assertNotIn(c.STAFF_QUEUE, seller)
        self.assertEqual(list(self.categories(self.seller, audience="CUSTOMER")), [c.ORDERS, c.PAYMENTS, c.SUPPORT])

    def test_row_shape_and_locks(self):
        rows = self.categories(self.seller)
        self.assertEqual(rows[c.ORDERS], {
            "category": c.ORDERS, "label": "Your orders",
            "channels": {"in_app": {"enabled": True, "locked": True}, "email": {"enabled": True, "locked": False}},
        })
        self.assertEqual(rows[c.ACCOUNT]["channels"]["email"], {"enabled": True, "locked": True})
        self.assertEqual(rows[c.INVENTORY]["channels"], {"in_app": {"enabled": True, "locked": True}})

    def test_switching_email_off_and_back_on(self):
        body = [{"category": c.ORDERS, "channels": {"email": {"enabled": False}}}]
        response = self.put(self.customer, body)
        self.assertEqual(response.status_code, 200)
        self.assertFalse({row["category"]: row for row in response.data}[c.ORDERS]["channels"]["email"]["enabled"])
        self.assertTrue(NotificationPreference.objects.filter(
            user=self.customer, category=c.ORDERS, channel=Channel.EMAIL, enabled=False).exists())
        entry = AuditLog.objects.get(action="NOTIFICATION_PREFERENCES_UPDATED")
        self.assertEqual((entry.actor, entry.metadata["previous_state"], entry.metadata["new_state"]),
                         (self.customer, {"ORDERS.email": True}, {"ORDERS.email": False}))

        body[0]["channels"]["email"]["enabled"] = True
        self.put(self.customer, body)
        self.assertFalse(NotificationPreference.objects.filter(user=self.customer).exists())  # sparse again
        self.assertEqual(AuditLog.objects.filter(action="NOTIFICATION_PREFERENCES_UPDATED").count(), 2)

    def test_an_unchanged_put_writes_no_audit_row(self):
        response = self.put(self.customer, [{"category": c.ORDERS, "channels": {"email": {"enabled": True}}}])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AuditLog.objects.filter(action="NOTIFICATION_PREFERENCES_UPDATED").exists())

    def test_locked_channels_refuse_to_switch_off(self):
        for body in (
            [{"category": c.PAYMENTS, "channels": {"email": {"enabled": False}}}],
            [{"category": c.ORDERS, "channels": {"in_app": {"enabled": False}}}],
        ):
            with self.subTest(body=body):
                response = self.put(self.customer, body)
                self.assertEqual(response.status_code, 400)
                self.assertIn("can't be switched off", response.data["detail"])
        # Confirming a locked channel is on is harmless.
        ok = self.put(self.customer, [{"category": c.PAYMENTS, "channels": {"email": {"enabled": True}}}])
        self.assertEqual(ok.status_code, 200)
        self.assertFalse(NotificationPreference.objects.exists())

    def test_a_refused_body_changes_nothing(self):
        cases = (
            {"category": c.ORDERS},  # not a list
            [{"category": c.SHOPS, "channels": {"email": {"enabled": False}}}],  # not a customer category
            [{"category": c.INVENTORY, "channels": {"email": {"enabled": False}}}],  # seller-only, and no email
            [{"category": c.ORDERS, "channels": {"sms": {"enabled": False}}}],
            [{"category": c.ORDERS, "channels": {"email": {"enabled": "no"}}}],
            # One bad entry refuses the whole body, including the valid one.
            [{"category": c.SUPPORT, "channels": {"email": {"enabled": False}}},
             {"category": c.PAYMENTS, "channels": {"email": {"enabled": False}}}],
        )
        for body in cases:
            with self.subTest(body=body):
                self.assertEqual(self.put(self.customer, body).status_code, 400)
        self.assertFalse(NotificationPreference.objects.exists())

    def test_audience_parameter_is_checked_on_preferences_too(self):
        self.assertEqual(self.client_for(self.customer).get(PREFERENCES, {"audience": "STAFF"}).status_code, 403)

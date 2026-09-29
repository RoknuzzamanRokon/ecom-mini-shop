"""
Wave 2 producers and handlers (docs/NOTIFICATION_SYSTEM.md Task 9): seller
and shop lifecycle, and shops submitted for review, from every entry point
that calls the services, including the Django admin actions.
"""
from io import StringIO

from django.contrib.admin import helpers
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from notifications import categories as c
from notifications import events
from notifications.models import (
    Audience,
    Channel,
    Notification,
    NotificationEvent,
    NotificationPreference,
)
from notifications.routing import route_event
from rbac.models import Role
from rbac.services import assign_user_role
from sellers.models import SellerProfile
from sellers.services import approve_seller, reactivate_seller, reject_seller, suspend_seller
from shops.models import Shop
from shops.services import InvalidShopTransitionError, ShopService

User = get_user_model()


def events_of(event_type):
    return NotificationEvent.objects.filter(event_type=event_type)


def route_all(event_type):
    for event in events_of(event_type):
        route_event(event.pk)
    return Notification.objects.filter(event_type=event_type)


class LifecycleFixtures:
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())

        def staff(name, role=None, **flags):
            user = User.objects.create_user(username=f"ls_{name}", email=f"{name}@minishop.test",
                                            password="pw", is_staff=True, **flags)
            if role:
                assign_user_role(user, role)
            return user

        cls.admin = staff("admin", Role.ROLE_ADMINISTRATOR)
        cls.operations = staff("operations", Role.ROLE_OPERATION_MANAGER)
        cls.finance = staff("finance", Role.ROLE_FINANCE)
        cls.root = staff("root", is_superuser=True)
        cls.seller_user = User.objects.create_user(username="ls_seller", email="owner@example.com", password="pw")

    def make_seller(self, status=SellerProfile.STATUS_PENDING):
        return SellerProfile.objects.create(
            user=self.seller_user, seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Lifecycle Co", status=status,
        )

    def post_admin_action(self, url_name, action, obj, reason=None):
        self.client.force_login(self.root)
        payload = {"action": action, "index": "0", helpers.ACTION_CHECKBOX_NAME: [str(obj.pk)]}
        if reason:
            payload.update({"apply_reason": "1", "reason": reason})
        return self.client.post(reverse(url_name), payload, follow=True)


class SellerLifecycleTests(LifecycleFixtures, TestCase):
    def test_approval_publishes_once_and_tells_the_seller(self):
        seller = self.make_seller()
        approve_seller(seller, self.admin)

        event = events_of(events.SELLER_STATUS_CHANGED).get()
        self.assertEqual(event.payload, {
            "seller_id": seller.pk, "from_status": "PENDING", "to_status": "ACTIVE", "reason": "",
        })
        self.assertEqual(event.actor, self.admin)
        row = route_all(events.SELLER_STATUS_CHANGED).get()
        self.assertEqual((row.recipient, row.audience, row.category), (self.seller_user, Audience.SELLER, c.ACCOUNT))
        self.assertEqual(row.title, "Your seller account is approved")
        self.assertEqual(row.action_url, "/seller")

    def test_account_decisions_are_always_emailed(self):
        NotificationPreference.objects.create(
            user=self.seller_user, category=c.ACCOUNT, channel=Channel.EMAIL, enabled=False
        )
        approve_seller(self.make_seller(), self.admin)
        row = route_all(events.SELLER_STATUS_CHANGED).get()
        self.assertEqual(row.deliveries.get().destination, "owner@example.com")

    def test_rejection_and_suspension_carry_the_reason(self):
        seller = self.make_seller()
        reject_seller(seller, self.admin, "  Missing trade licence  ")
        row = route_all(events.SELLER_STATUS_CHANGED).get()
        self.assertEqual(row.title, "Your seller application wasn't approved")
        self.assertTrue(row.body.endswith("Reason: Missing trade licence"))

        # Inbox rows outlive their events (SET_NULL), so clear both.
        Notification.objects.all().delete()
        NotificationEvent.objects.all().delete()
        seller = SellerProfile.objects.get(pk=seller.pk)
        approve_seller(seller, self.admin)
        suspend_seller(seller, self.admin, "Repeated late shipping")
        reactivate_seller(seller, self.admin)
        titles = list(
            route_all(events.SELLER_STATUS_CHANGED).order_by("occurred_at", "id").values_list("title", flat=True)
        )
        self.assertEqual(titles, [
            "Your seller account is approved",
            "Your seller account is suspended",
            "Your seller account is active again",
        ])

    def test_a_refused_transition_publishes_nothing(self):
        seller = self.make_seller()
        with self.assertRaises(ValidationError):
            reactivate_seller(seller, self.admin)  # only approved or suspended sellers
        with self.assertRaises(ValidationError):
            suspend_seller(seller, self.admin, "   ")
        self.assertFalse(events_of(events.SELLER_STATUS_CHANGED).exists())

    def test_the_django_admin_actions_notify(self):
        seller = self.make_seller()
        self.post_admin_action("admin:sellers_sellerprofile_changelist", "approve_and_activate", seller)
        self.post_admin_action(
            "admin:sellers_sellerprofile_changelist", "suspend_sellers", seller, reason="Policy review"
        )
        payloads = [e.payload for e in events_of(events.SELLER_STATUS_CHANGED).order_by("occurred_at")]
        self.assertEqual(
            [(p["from_status"], p["to_status"], p["reason"]) for p in payloads],
            [("PENDING", "ACTIVE", ""), ("ACTIVE", "SUSPENDED", "Policy review")],
        )


class ShopLifecycleTests(LifecycleFixtures, TestCase):
    def setUp(self):
        self.seller = self.make_seller(SellerProfile.STATUS_ACTIVE)

    def make_shop(self, status=Shop.STATUS_PENDING):
        return Shop.objects.create(owner=self.seller, name="Alpha Mart", status=status)

    def test_submission_tells_the_reviewers_only(self):
        shop = self.make_shop(Shop.STATUS_DRAFT)
        ShopService.submit_for_review(shop, self.seller)

        event = events_of(events.SHOP_SUBMITTED).get()
        self.assertEqual(event.payload, {"shop_id": shop.pk, "shop_name": "Alpha Mart", "seller_name": "Lifecycle Co"})
        self.assertEqual(event.actor, self.seller_user)
        rows = route_all(events.SHOP_SUBMITTED)
        # ADMINISTRATOR and OPERATION_MANAGER hold shops.approve; FINANCE doesn't,
        # and a superuser without a role isn't counted (D5).
        self.assertEqual(set(rows.values_list("recipient_id", flat=True)), {self.admin.pk, self.operations.pk})
        row = rows.get(recipient=self.operations)
        self.assertEqual((row.audience, row.category), (Audience.STAFF, c.STAFF_QUEUE))
        self.assertEqual(row.title, "Alpha Mart is waiting for review")
        self.assertEqual(row.action_url, f"/admin/shops/{shop.pk}")
        self.assertFalse(any(r.deliveries.exists() for r in rows))

    def test_creating_a_shop_straight_into_review_counts_as_a_submission(self):
        ShopService.create_shop(self.seller, name="Direct Submit", submit_for_review=True)
        self.assertEqual(events_of(events.SHOP_SUBMITTED).get().payload["shop_name"], "Direct Submit")

    def test_a_draft_or_refused_submission_publishes_nothing(self):
        ShopService.create_shop(self.seller, name="Just A Draft")
        with self.assertRaises(InvalidShopTransitionError):
            ShopService.submit_for_review(self.make_shop(Shop.STATUS_ACTIVE), self.seller)
        self.assertFalse(events_of(events.SHOP_SUBMITTED).exists())

    def test_approval_tells_the_owner(self):
        shop = self.make_shop()
        ShopService.approve_shop(shop, self.operations)
        event = events_of(events.SHOP_STATUS_CHANGED).get()
        self.assertEqual(event.payload, {
            "shop_id": shop.pk, "shop_name": "Alpha Mart", "from_status": "PENDING", "to_status": "ACTIVE", "reason": "",
        })
        row = route_all(events.SHOP_STATUS_CHANGED).get()
        self.assertEqual((row.recipient, row.category, row.title), (self.seller_user, c.SHOPS, "Alpha Mart is approved"))
        self.assertEqual(row.deliveries.count(), 1)

    def test_rejection_suspension_and_reactivation(self):
        shop = self.make_shop()
        ShopService.reject_shop(shop, self.operations, "Blurry logo")
        ShopService.approve_shop(shop, self.operations)
        ShopService.suspend_shop(shop, self.admin, "Counterfeit goods")
        ShopService.reactivate_shop(shop, self.admin)
        rows = route_all(events.SHOP_STATUS_CHANGED).order_by("occurred_at", "id")
        self.assertEqual(list(rows.values_list("title", flat=True)), [
            "Alpha Mart wasn't approved",
            "Alpha Mart is approved",
            "Alpha Mart is suspended",
            "Alpha Mart is active again",
        ])
        self.assertTrue(rows[0].body.endswith("Reason: Blurry logo"))
        self.assertTrue(rows[2].body.endswith("Reason: Counterfeit goods"))

    def test_email_can_be_switched_off_for_shops(self):
        NotificationPreference.objects.create(
            user=self.seller_user, category=c.SHOPS, channel=Channel.EMAIL, enabled=False
        )
        ShopService.approve_shop(self.make_shop(), self.operations)
        self.assertFalse(route_all(events.SHOP_STATUS_CHANGED).get().deliveries.exists())

    def test_a_refused_transition_publishes_nothing(self):
        with self.assertRaises(InvalidShopTransitionError):
            ShopService.reject_shop(self.make_shop(Shop.STATUS_DRAFT), self.operations, "No")
        self.assertFalse(events_of(events.SHOP_STATUS_CHANGED).exists())

    def test_the_console_and_the_django_admin_notify(self):
        shop = self.make_shop()
        api = APIClient()
        api.force_authenticate(user=self.operations)
        response = api.post(f"/api/admin/shops/{shop.pk}/status/", {"action": "approve"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.post_admin_action("admin:shops_shop_changelist", "suspend_shops", shop, reason="Policy review")
        payloads = [e.payload for e in events_of(events.SHOP_STATUS_CHANGED).order_by("occurred_at")]
        self.assertEqual(
            [(p["from_status"], p["to_status"]) for p in payloads],
            [("PENDING", "ACTIVE"), ("ACTIVE", "SUSPENDED")],
        )

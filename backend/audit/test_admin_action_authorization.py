"""
Django-admin action authorization for the seller and shop lifecycle.

Both `SellerProfileAdmin` and `ShopAdmin` drive their lifecycle actions through
`ReasonRequiredActionMixin` in this app, so the boundary they share is tested
here in one place rather than split across `sellers/` and `shops/`.

The boundary: a custom ModelAdmin action carries no permission requirement
unless it declares `allowed_permissions`, and the changelist opens on
`has_view_or_change_permission`. Without that declaration, `is_staff` plus the
model's `view` permission was enough to approve, reject, suspend or reactivate
any seller or shop -- and to write an AuditLog entry naming the read-only
account as the actor. This mirrors the OrderAdmin gap fixed in `ca95013`.

Each case posts the action exactly as the changelist does, including the
`apply_reason` confirmation payload for the two reason-required actions, so the
tests exercise the real admin dispatch path rather than calling the action
functions directly. Posting the confirmed payload straight away is also the
realistic attack: it skips the intermediate page the UI would have shown.
"""
from django.contrib import admin
from django.contrib.admin import helpers
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from audit.models import AuditLog
from sellers.models import SellerProfile
from shops.models import Shop

User = get_user_model()

#: Long enough to clear `ReasonRequiredActionMixin.reason_min_length`.
REASON = "Policy violation reported by the operations team."

#: (action name, starting status, extra fixture fields, status once authorized,
#:  whether the action requires the reason confirmation payload)
SELLER_ACTIONS = (
    ("approve_and_activate", SellerProfile.STATUS_PENDING, {},
     SellerProfile.STATUS_ACTIVE, False),
    ("reject_sellers", SellerProfile.STATUS_PENDING, {},
     SellerProfile.STATUS_REJECTED, True),
    ("suspend_sellers", SellerProfile.STATUS_ACTIVE, {},
     SellerProfile.STATUS_SUSPENDED, True),
    ("reactivate_sellers", SellerProfile.STATUS_SUSPENDED,
     {"suspension_reason": "Suspended while under review."},
     SellerProfile.STATUS_ACTIVE, False),
)

SHOP_ACTIONS = (
    ("approve_and_activate", Shop.STATUS_PENDING, {}, Shop.STATUS_ACTIVE, False),
    ("reject_shops", Shop.STATUS_PENDING, {}, Shop.STATUS_REJECTED, True),
    ("suspend_shops", Shop.STATUS_ACTIVE, {}, Shop.STATUS_SUSPENDED, True),
    ("reactivate_shops", Shop.STATUS_SUSPENDED,
     {"suspension_reason": "Suspended while under review."},
     Shop.STATUS_ACTIVE, False),
)


class AdminLifecycleActionAuthorizationTests(TestCase):
    """A `view`-only admin account must not be able to run a lifecycle action."""

    @classmethod
    def setUpTestData(cls):
        seller_ct = ContentType.objects.get_for_model(SellerProfile)
        shop_ct = ContentType.objects.get_for_model(Shop)
        view_seller = Permission.objects.get(content_type=seller_ct, codename="view_sellerprofile")
        change_seller = Permission.objects.get(content_type=seller_ct, codename="change_sellerprofile")
        view_shop = Permission.objects.get(content_type=shop_ct, codename="view_shop")
        change_shop = Permission.objects.get(content_type=shop_ct, codename="change_shop")

        # May read sellers and shops, and nothing else. The account the actions
        # must refuse.
        cls.readonly_staff = User.objects.create_user(
            username="lifecycle_readonly",
            email="lifecycle_readonly@minishop.com",
            password="Password123!",
            is_staff=True,
        )
        cls.readonly_staff.user_permissions.add(view_seller, view_shop)

        # May edit both -- its existing capability must survive the fix.
        cls.editor_staff = User.objects.create_user(
            username="lifecycle_editor",
            email="lifecycle_editor@minishop.com",
            password="Password123!",
            is_staff=True,
        )
        cls.editor_staff.user_permissions.add(
            view_seller, change_seller, view_shop, change_shop
        )

        cls.superuser = User.objects.create_superuser(
            username="lifecycle_superuser",
            email="lifecycle_super@minishop.com",
            password="Password123!",
        )

    # -- fixtures ------------------------------------------------------------

    def _make_seller(self, status, **extra):
        user = User.objects.create_user(
            username=f"lifecycle_seller_{User.objects.count()}",
            email=f"lifecycle_seller_{User.objects.count()}@minishop.com",
            password="Password123!",
        )
        return SellerProfile.objects.create(
            user=user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Lifecycle Test Seller",
            status=status,
            **extra,
        )

    def _make_shop(self, status, **extra):
        owner = self._make_seller(SellerProfile.STATUS_ACTIVE)
        return Shop.objects.create(
            owner=owner,
            name=f"Lifecycle Test Shop {Shop.objects.count()}",
            status=status,
            **extra,
        )

    # -- admin dispatch ------------------------------------------------------

    def _post_action(self, user, url_name, action, obj, needs_reason):
        """POSTs `action` against `obj` exactly as the admin changelist would."""
        client = Client()
        client.force_login(user)
        payload = {
            "action": action,
            "index": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(obj.pk)],
        }
        if needs_reason:
            # Skip straight to the confirmed step -- the UI page is not a gate.
            payload["apply_reason"] = "1"
            payload["reason"] = REASON
        return client.post(reverse(url_name), payload, follow=True)

    def _assert_refused(self, user, url_name, cases, make):
        for action, start, extra, _authorized_status, needs_reason in cases:
            with self.subTest(action=action):
                obj = make(start, **extra)
                audit_before = AuditLog.objects.filter(actor=user).count()

                self._post_action(user, url_name, action, obj, needs_reason)

                obj.refresh_from_db()
                self.assertEqual(obj.status, start)
                self.assertEqual(AuditLog.objects.filter(actor=user).count(), audit_before)

    def _assert_allowed(self, user, url_name, cases, make):
        for action, start, extra, authorized_status, needs_reason in cases:
            with self.subTest(action=action):
                obj = make(start, **extra)

                self._post_action(user, url_name, action, obj, needs_reason)

                obj.refresh_from_db()
                self.assertEqual(obj.status, authorized_status)

    # -----------------------------------------------------------------------
    # Precondition
    # -----------------------------------------------------------------------

    def test_readonly_staff_reaches_both_changelists(self):
        """
        Pins why the actions need their own permission: view access alone opens
        the changelist that dispatches them.
        """
        client = Client()
        client.force_login(self.readonly_staff)
        for url_name in ("admin:sellers_sellerprofile_changelist", "admin:shops_shop_changelist"):
            with self.subTest(url_name=url_name):
                self.assertEqual(client.get(reverse(url_name)).status_code, 200)

    # -----------------------------------------------------------------------
    # Seller
    # -----------------------------------------------------------------------

    def test_readonly_staff_cannot_run_any_seller_action(self):
        self._assert_refused(
            self.readonly_staff,
            "admin:sellers_sellerprofile_changelist",
            SELLER_ACTIONS,
            self._make_seller,
        )

    def test_change_authorized_staff_can_run_every_seller_action(self):
        self._assert_allowed(
            self.editor_staff,
            "admin:sellers_sellerprofile_changelist",
            SELLER_ACTIONS,
            self._make_seller,
        )

    def test_superuser_can_run_every_seller_action(self):
        self._assert_allowed(
            self.superuser,
            "admin:sellers_sellerprofile_changelist",
            SELLER_ACTIONS,
            self._make_seller,
        )

    # -----------------------------------------------------------------------
    # Shop
    # -----------------------------------------------------------------------

    def test_readonly_staff_cannot_run_any_shop_action(self):
        self._assert_refused(
            self.readonly_staff,
            "admin:shops_shop_changelist",
            SHOP_ACTIONS,
            self._make_shop,
        )

    def test_change_authorized_staff_can_run_every_shop_action(self):
        self._assert_allowed(
            self.editor_staff,
            "admin:shops_shop_changelist",
            SHOP_ACTIONS,
            self._make_shop,
        )

    def test_superuser_can_run_every_shop_action(self):
        self._assert_allowed(
            self.superuser,
            "admin:shops_shop_changelist",
            SHOP_ACTIONS,
            self._make_shop,
        )

    # -----------------------------------------------------------------------
    # The dropdown reflects the same boundary the server enforces
    # -----------------------------------------------------------------------

    def test_lifecycle_actions_are_offered_by_permission(self):
        cases = (
            (SellerProfile, [action for action, *_ in SELLER_ACTIONS]),
            (Shop, [action for action, *_ in SHOP_ACTIONS]),
        )
        for model, action_names in cases:
            model_admin = admin.site._registry[model]
            for user, expected in ((self.readonly_staff, False), (self.editor_staff, True)):
                with self.subTest(model=model.__name__, user=user.username):
                    request = RequestFactory().get("/admin/")
                    request.user = user
                    offered = model_admin.get_actions(request)
                    for name in action_names:
                        self.assertEqual(name in offered, expected)

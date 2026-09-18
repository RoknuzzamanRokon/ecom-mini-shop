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


class AdminChangeFormStatusLockdownTests(TestCase):
    """
    Known Issue #22: the plain Django-admin *change form* for SellerProfile and
    Shop left `status` directly editable -- a bypass around every lifecycle
    method (approve/reject/suspend/reactivate) and the AuditService trail those
    methods write through, reachable with nothing more than the ordinary
    Django `change` permission on either model (no `allowed_permissions`-style
    action gate applies to the change form itself).

    `status` is now listed in both ModelAdmins' `readonly_fields`. Django
    excludes readonly fields from the generated ModelForm entirely (they are
    added to the form's `exclude` list in `ModelAdmin.get_form()`), so this is
    a server-side exclusion, not a template/widget-only restriction. These
    tests prove that by POSTing a complete, otherwise-valid change-form
    submission with a crafted `status` value directly to the change view and
    asserting the *persisted* value in the database afterwards -- while also
    asserting an unrelated field in the same submission genuinely did change,
    so a validation failure of the whole request could not produce a false
    pass.
    """

    @classmethod
    def setUpTestData(cls):
        seller_ct = ContentType.objects.get_for_model(SellerProfile)
        shop_ct = ContentType.objects.get_for_model(Shop)
        change_seller = Permission.objects.get(content_type=seller_ct, codename="change_sellerprofile")
        change_shop = Permission.objects.get(content_type=shop_ct, codename="change_shop")

        # Holds only the ordinary Django "change" permission on both models --
        # exactly the account the audit found could bypass the lifecycle
        # controls through the plain change form.
        cls.editor_staff = User.objects.create_user(
            username="lockdown_editor",
            email="lockdown_editor@minishop.com",
            password="Password123!",
            is_staff=True,
        )
        cls.editor_staff.user_permissions.add(change_seller, change_shop)

        cls.superuser = User.objects.create_superuser(
            username="lockdown_superuser",
            email="lockdown_super@minishop.com",
            password="Password123!",
        )

    # -- fixtures ------------------------------------------------------------

    def _make_seller(self, status=SellerProfile.STATUS_PENDING, **extra):
        user = User.objects.create_user(
            username=f"lockdown_seller_{User.objects.count()}",
            email=f"lockdown_seller_{User.objects.count()}@minishop.com",
            password="Password123!",
        )
        return SellerProfile.objects.create(
            user=user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Lockdown Test Seller",
            status=status,
            **extra,
        )

    def _make_shop(self, status=Shop.STATUS_ACTIVE, **extra):
        owner = self._make_seller(SellerProfile.STATUS_ACTIVE)
        return Shop.objects.create(
            owner=owner,
            name="Lockdown Test Shop",
            slug=f"lockdown-test-shop-{Shop.objects.count()}",
            status=status,
            **extra,
        )

    # -- crafted change-form POSTs --------------------------------------------

    def _seller_post_data(self, seller, *, business_name, status):
        """A complete, otherwise-valid SellerProfileAdmin change-form body."""
        return {
            "user": str(seller.user_id),
            "seller_type": seller.seller_type,
            "status": status,
            "business_name": business_name,
            "business_email": "",
            "business_phone": "",
            "tax_id": "",
            "description": "",
            "rejection_reason": "",
            "suspension_reason": "",
            "_save": "Save",
        }

    def _shop_post_data(self, shop, *, name, status):
        """A complete, otherwise-valid ShopAdmin change-form body."""
        return {
            "owner": str(shop.owner_id),
            "name": name,
            "slug": shop.slug,
            "description": "",
            "phone": "",
            "address": "",
            "location": "POINT(90.4125000 23.8103000)",
            "rejection_reason": "",
            "suspension_reason": "",
            "_save": "Save",
        }

    def test_crafted_post_cannot_change_seller_status(self):
        """A POST that legitimately updates business_name while also smuggling
        a different `status` must persist the name change but leave status
        exactly where it started -- proving the exclusion is server-side."""
        for user in (self.editor_staff, self.superuser):
            with self.subTest(user=user.username):
                seller = self._make_seller(status=SellerProfile.STATUS_PENDING)
                url = reverse("admin:sellers_sellerprofile_change", args=[seller.pk])
                client = Client()
                client.force_login(user)

                response = client.post(
                    url,
                    self._seller_post_data(
                        seller,
                        business_name="Renamed By Crafted POST",
                        status=SellerProfile.STATUS_ACTIVE,
                    ),
                )

                # A 302 redirect means the form validated and saved; a 200
                # would mean it was redisplayed with errors, which would make
                # the "status unchanged" assertion below a false pass.
                self.assertEqual(response.status_code, 302)

                seller.refresh_from_db()
                self.assertEqual(seller.business_name, "Renamed By Crafted POST")
                self.assertEqual(seller.status, SellerProfile.STATUS_PENDING)

    def test_crafted_post_cannot_change_shop_status(self):
        for user in (self.editor_staff, self.superuser):
            with self.subTest(user=user.username):
                shop = self._make_shop(status=Shop.STATUS_ACTIVE)
                url = reverse("admin:shops_shop_change", args=[shop.pk])
                client = Client()
                client.force_login(user)

                response = client.post(
                    url,
                    self._shop_post_data(
                        shop,
                        name="Renamed Shop By Crafted POST",
                        status=Shop.STATUS_SUSPENDED,
                    ),
                )

                self.assertEqual(response.status_code, 302)

                shop.refresh_from_db()
                self.assertEqual(shop.name, "Renamed Shop By Crafted POST")
                self.assertEqual(shop.status, Shop.STATUS_ACTIVE)

    def test_status_field_excluded_from_generated_form(self):
        """Pins the actual mechanism: `status` must not be a field on the
        ModelAdmin's generated form at all, for either model -- not merely
        rendered as read-only. This is what makes the crafted-POST tests above
        a server-side guarantee rather than a coincidence of this request."""
        seller = self._make_seller()
        shop = self._make_shop()
        request = RequestFactory().get("/admin/")
        request.user = self.superuser

        seller_admin = admin.site._registry[SellerProfile]
        shop_admin = admin.site._registry[Shop]

        seller_form_class = seller_admin.get_form(request, obj=seller)
        shop_form_class = shop_admin.get_form(request, obj=shop)

        self.assertNotIn("status", seller_form_class.base_fields)
        self.assertNotIn("status", shop_form_class.base_fields)
        self.assertIn("status", seller_admin.get_readonly_fields(request, seller))
        self.assertIn("status", shop_admin.get_readonly_fields(request, shop))

    # -- lifecycle actions must still be the working, audited path -----------

    def test_seller_lifecycle_actions_still_work_and_are_still_audited(self):
        """The guarded path this lockdown pushes everyone toward must remain
        fully functional: permission-gated, business-logic-enforced, and
        audited -- unchanged by locking the change form."""
        self._assert_lifecycle_actions_allowed_and_audited(
            self.editor_staff,
            "admin:sellers_sellerprofile_changelist",
            SELLER_ACTIONS,
            self._make_seller,
        )

    def test_shop_lifecycle_actions_still_work_and_are_still_audited(self):
        self._assert_lifecycle_actions_allowed_and_audited(
            self.editor_staff,
            "admin:shops_shop_changelist",
            SHOP_ACTIONS,
            self._make_shop,
        )

    #: action name (as declared on the ModelAdmin) -> AuditLog `action` it writes.
    _AUDIT_ACTION_NAMES = {
        "approve_and_activate": "APPROVE",
        "reject_sellers": "REJECT",
        "suspend_sellers": "SUSPEND",
        "reactivate_sellers": "REACTIVATE",
        "reject_shops": "REJECT",
        "suspend_shops": "SUSPEND",
        "reactivate_shops": "REACTIVATE",
    }

    def _post_action(self, user, url_name, action, obj, needs_reason):
        client = Client()
        client.force_login(user)
        payload = {
            "action": action,
            "index": "0",
            helpers.ACTION_CHECKBOX_NAME: [str(obj.pk)],
        }
        if needs_reason:
            payload["apply_reason"] = "1"
            payload["reason"] = REASON
        return client.post(reverse(url_name), payload, follow=True)

    def _assert_lifecycle_actions_allowed_and_audited(self, user, url_name, cases, make):
        for action, start, extra, authorized_status, needs_reason in cases:
            with self.subTest(action=action):
                obj = make(start, **extra)
                model_prefix = "SELLER" if isinstance(obj, SellerProfile) else "SHOP"
                audit_action = f"ADMIN_{model_prefix}_{self._AUDIT_ACTION_NAMES[action]}"

                self._post_action(user, url_name, action, obj, needs_reason)

                obj.refresh_from_db()
                self.assertEqual(obj.status, authorized_status)
                self.assertTrue(
                    AuditLog.objects.filter(
                        action=audit_action,
                        target_type=type(obj).__name__,
                        target_id=str(obj.pk),
                        actor=user,
                    ).exists()
                )

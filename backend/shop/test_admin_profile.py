"""
Tests for /admin/profile/ (config/admin_profile.py, templates/admin/profile.html).

Kept beside test_admin_site.py so `manage.py test shop` covers the admin chrome.
"""
import shutil
import tempfile
from datetime import timedelta
from io import BytesIO, StringIO
from unittest import mock

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from audit.models import AuditLog
from config import admin_profile, validators
from config.admin_profile import action_style, humanize_action
from customers.models import CustomerProfile
from points.models import StaffPointTransaction, StaffWallet
from rbac.models import Permission, Role, UserPermission
from rbac.services import assign_user_role, get_user_permissions
from support.models import SupportTicket

User = get_user_model()

PROFILE_URL = "/admin/profile/"


def image_upload(name="me.png", image_format="PNG", size=(8, 8)):
    buffer = BytesIO()
    Image.new("RGB", size, (200, 120, 40)).save(buffer, image_format)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{image_format.lower()}")


class AdminProfileAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.staff = User.objects.create_user(
            username="pf_ops", password="pw", email="ops@example.com", is_staff=True,
            first_name="Nadia", last_name="Rahman",
        )
        assign_user_role(cls.staff, Role.ROLE_OPERATION_MANAGER)
        cls.superuser = User.objects.create_superuser(username="pf_root", email="root@example.com", password="pw")
        cls.customer = User.objects.create_user(username="pf_shopper", password="pw")

    def test_url_is_registered_on_the_admin_site(self):
        self.assertEqual(reverse("admin:profile"), PROFILE_URL)

    def test_anonymous_visitor_is_sent_to_the_admin_login(self):
        response = self.client.get(PROFILE_URL)
        self.assertRedirects(response, f"/admin/login/?next={PROFILE_URL}", fetch_redirect_response=False)

    def test_non_staff_account_is_sent_to_the_admin_login(self):
        self.client.force_login(self.customer)
        response = self.client.get(PROFILE_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_missing_trailing_slash_redirects(self):
        self.client.force_login(self.staff)
        response = self.client.get("/admin/profile")
        self.assertRedirects(response, PROFILE_URL, status_code=301, fetch_redirect_response=False)

    def test_staff_member_sees_their_own_profile(self):
        self.client.force_login(self.staff)
        response = self.client.get(PROFILE_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/profile.html")
        self.assertContains(response, "Nadia Rahman")
        self.assertContains(response, "ops@example.com")
        self.assertContains(response, "Operation Manager")
        self.assertEqual(response.context["access"]["key"], "staff")
        self.assertNotContains(response, "pf_root")

    def test_console_permission_count_comes_from_the_shared_resolver(self):
        self.client.force_login(self.staff)
        rbac = self.client.get(PROFILE_URL).context["rbac"]
        effective = get_user_permissions(self.staff)
        self.assertFalse(rbac["full_access"])
        self.assertGreater(rbac["granted"], 0)
        self.assertEqual(rbac["granted"], len(effective))

    def test_superuser_is_shown_full_access_not_zero(self):
        self.client.force_login(self.superuser)
        response = self.client.get(PROFILE_URL)
        rbac = response.context["rbac"]
        self.assertTrue(rbac["full_access"])
        self.assertEqual(rbac["granted"], rbac["total"])
        self.assertEqual(response.context["panel"]["reachable"], response.context["panel"]["total"])
        self.assertContains(response, "Full platform access.")

    def test_partial_access_lists_held_and_missing_permissions(self):
        self.client.force_login(self.staff)
        rbac = self.client.get(PROFILE_URL).context["rbac"]
        for section in rbac["sections"]:
            with self.subTest(area=section["key"]):
                self.assertEqual(len(section["permissions"]) + len(section["missing"]), section["total"])
        self.assertTrue(any(section["missing"] for section in rbac["sections"]))

    def test_revoked_grants_are_split_from_active_ones(self):
        live, gone = Permission.objects.order_by("code")[:2]
        UserPermission.objects.create(user=self.staff, permission=live, granted_by=self.superuser, note="Cover")
        UserPermission.objects.create(user=self.staff, permission=gone, granted_by=self.superuser, is_active=False)
        self.client.force_login(self.staff)
        response = self.client.get(PROFILE_URL)
        grants = response.context["grants"]
        self.assertEqual([g["code"] for g in grants["active"]], [live.code])
        self.assertEqual([g["code"] for g in grants["revoked"]], [gone.code])
        self.assertContains(response, "1 revoked grant")

    def test_superuser_permission_stat_reads_all(self):
        self.client.force_login(self.superuser)
        kpis = self.client.get(PROFILE_URL).context["kpis"]
        self.assertEqual(str(kpis[-1]["value"]), "All")

    def test_account_menu_links_to_the_profile(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, f'href="{PROFILE_URL}"')

    def test_profile_is_marked_current_in_the_account_menu(self):
        self.client.force_login(self.staff)
        response = self.client.get(PROFILE_URL)
        self.assertContains(response, f'href="{PROFILE_URL}" aria-current="page"')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="pf-media-"))
class AdminProfileEditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="pf_editor", password="pw", email="editor@example.com", is_staff=True
        )

    @classmethod
    def tearDownClass(cls):
        from django.conf import settings

        shutil.rmtree(settings.MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.client.force_login(self.staff)

    def post(self, **fields):
        data = {
            "first_name": "", "last_name": "", "display_name": "", "phone": "",
            "date_of_birth": "", "gender": "",
        }
        data.update(fields)
        return self.client.post(PROFILE_URL, data)

    def test_edit_query_shows_the_form(self):
        response = self.client.get(PROFILE_URL + "?edit=1")
        self.assertTrue(response.context["editing"])
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'name="phone"')

    def test_saving_updates_user_and_profile_and_is_audited(self):
        response = self.post(
            first_name="Tanvir", last_name="Ahmed", display_name="Tanvir",
            phone="+880 1711-000000", date_of_birth="1990-04-12", gender=CustomerProfile.GENDER_MALE,
        )
        self.assertRedirects(response, PROFILE_URL + "#personal", fetch_redirect_response=False)

        self.staff.refresh_from_db()
        profile = CustomerProfile.objects.get(user=self.staff)
        self.assertEqual((self.staff.first_name, self.staff.last_name), ("Tanvir", "Ahmed"))
        self.assertEqual(profile.phone, "+880 1711-000000")
        self.assertEqual(str(profile.date_of_birth), "1990-04-12")
        self.assertEqual(profile.gender, CustomerProfile.GENDER_MALE)

        entry = AuditLog.objects.get(action="PROFILE_UPDATED")
        self.assertEqual(entry.actor, self.staff)
        self.assertIn("phone", entry.metadata["changed_fields"])

    def test_access_and_identity_fields_cannot_be_posted(self):
        self.post(
            first_name="Mallory", is_superuser="on", is_staff="on", is_active="on",
            username="someone_else", email="attacker@example.com",
        )
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.first_name, "Mallory")
        self.assertFalse(self.staff.is_superuser)
        self.assertEqual(self.staff.username, "pf_editor")
        self.assertEqual(self.staff.email, "editor@example.com")

    def test_unchanged_form_saves_nothing(self):
        response = self.post()
        self.assertRedirects(response, PROFILE_URL + "#personal", fetch_redirect_response=False)
        self.assertFalse(AuditLog.objects.filter(action="PROFILE_UPDATED").exists())
        self.assertFalse(CustomerProfile.objects.filter(user=self.staff).exists())

    def test_junk_phone_is_rejected(self):
        response = self.post(phone="call me maybe")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["editing"])
        self.assertIn("phone", response.context["form"].errors)
        self.assertContains(response, 'aria-invalid="true"')
        self.assertFalse(CustomerProfile.objects.filter(user=self.staff).exists())

    def test_future_date_of_birth_is_rejected(self):
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        response = self.post(date_of_birth=tomorrow)
        self.assertIn("date_of_birth", response.context["form"].errors)

    def test_photo_upload_is_saved_and_shown_in_the_header(self):
        response = self.client.post(PROFILE_URL, {"avatar": image_upload()})
        self.assertEqual(response.status_code, 302)
        profile = CustomerProfile.objects.get(user=self.staff)
        self.assertTrue(profile.avatar.name.startswith("customers/avatars/"))

        index = self.client.get(reverse("admin:index"))
        self.assertEqual(index.context["admin_avatar_url"], profile.avatar.url)
        self.assertContains(index, f'<img src="{profile.avatar.url}" alt="">')

    def test_photo_can_be_removed(self):
        self.client.post(PROFILE_URL, {"avatar": image_upload()})
        self.client.post(PROFILE_URL, {"remove_avatar": "on"})
        self.assertFalse(CustomerProfile.objects.get(user=self.staff).avatar)

    def test_oversized_photo_is_rejected(self):
        with mock.patch.object(validators, "AVATAR_MAX_BYTES", 10):
            response = self.client.post(PROFILE_URL, {"avatar": image_upload()})
        self.assertIn("avatar", response.context["form"].errors)
        self.assertFalse(CustomerProfile.objects.filter(user=self.staff).exists())

    def test_unsupported_image_format_is_rejected(self):
        response = self.client.post(PROFILE_URL, {"avatar": image_upload("me.gif", "GIF")})
        self.assertIn("avatar", response.context["form"].errors)


class AdminProfileActivityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.me = User.objects.create_superuser(username="pf_me", email="me@example.com", password="pw")
        cls.other = User.objects.create_superuser(username="pf_other", email="o@example.com", password="pw")
        cls.shopper = User.objects.create_user(username="pf_customer", password="pw")

    def setUp(self):
        self.client.force_login(self.me)

    def audit(self, actor, action="ADMIN_SELLER_APPROVE", repr_="Acme Traders"):
        return AuditLog.objects.create(
            actor=actor, action=action, target_type="SellerProfile", target_id="1", target_repr=repr_
        )

    def test_timeline_lists_only_my_actions(self):
        self.audit(self.me)
        self.audit(self.other, repr_="Someone Else Ltd")
        response = self.client.get(PROFILE_URL)
        self.assertContains(response, "Seller approved")
        self.assertContains(response, "Acme Traders")
        self.assertNotContains(response, "Someone Else Ltd")

    def test_heatmap_counts_audit_and_admin_history_inside_the_window(self):
        self.audit(self.me)
        LogEntry.objects.create(
            user=self.me,
            content_type=ContentType.objects.get_for_model(User),
            object_id=str(self.shopper.pk),
            object_repr="pf_customer",
            action_flag=CHANGE,
            change_message="[]",
        )
        old = self.audit(self.me, repr_="Long ago")
        AuditLog.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=200))

        activity = self.client.get(PROFILE_URL).context["activity"]
        self.assertEqual(activity["total"], 2)
        self.assertEqual(activity["last_30_days"], 2)
        self.assertEqual(activity["active_days"], 1)
        self.assertEqual(len(activity["weeks"]), admin_profile.ACTIVITY_WEEKS)
        self.assertEqual(sum(len(group["items"]) for group in activity["timeline"]), 3)

    def test_back_to_back_changes_to_one_record_merge_into_one_row(self):
        now = timezone.now()
        for offset, state in enumerate(["WAITING_ON_CUSTOMER", "IN_PROGRESS", "RESOLVED"]):
            entry = self.audit(self.me, action="SUPPORT_TICKET_STATUS_CHANGED", repr_=f"TKT0001 ({state})")
            AuditLog.objects.filter(pk=entry.pk).update(created_at=now - timedelta(minutes=10 - offset))

        timeline = self.client.get(PROFILE_URL).context["activity"]["timeline"]
        items = [item for group in timeline for item in group["items"]]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["count"], 3)
        self.assertEqual(items[0]["target"], "TKT0001")
        self.assertEqual(items[0]["states"], ["Waiting on customer", "In progress", "Resolved"])

    def test_assigned_tickets_show_under_your_work(self):
        SupportTicket.objects.create(
            ticket_number="TKT20260930PF0001", customer=self.shopper, category=SupportTicket.CATEGORY_ORDER,
            subject="Parcel never arrived", assigned_to=self.me,
        )
        SupportTicket.objects.create(
            ticket_number="TKT20260930PF0002", customer=self.shopper, category=SupportTicket.CATEGORY_ORDER,
            subject="Somebody else's ticket", assigned_to=self.other,
        )
        response = self.client.get(PROFILE_URL)
        work = response.context["work"]
        self.assertEqual(work["unresolved"], 1)
        self.assertContains(response, "Parcel never arrived")
        self.assertNotContains(response, "Somebody else")
        self.assertEqual(
            work["tickets_url"],
            reverse("admin:support_supportticket_changelist") + f"?assigned_to__id__exact={self.me.pk}",
        )

    def test_audit_changelist_accepts_the_actor_filter(self):
        self.audit(self.me)
        self.audit(self.other, repr_="Someone Else Ltd")
        response = self.client.get(
            reverse("admin:audit_auditlog_changelist") + f"?actor__id__exact={self.me.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acme Traders")
        self.assertNotContains(response, "Someone Else Ltd")

    def test_support_changelist_accepts_the_assignee_filter(self):
        response = self.client.get(
            reverse("admin:support_supportticket_changelist") + f"?assigned_to__id__exact={self.me.pk}"
        )
        self.assertEqual(response.status_code, 200)


class AdminProfilePointsTests(TestCase):
    """Every profile shows the signed-in user's available points (their StaffWallet balance)."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(username="pf_points", password="pw", is_staff=True)
        cls.boss = User.objects.create_superuser(username="pf_boss", email="boss@example.com", password="pw")

    def movement(self, wallet, kind, amount, before, after, reason):
        return StaffPointTransaction.objects.create(
            wallet=wallet, transaction_type=kind, amount=amount,
            balance_before=before, balance_after=after, reason=reason, actor=wallet.user,
        )

    def test_account_without_a_wallet_shows_zero_and_creates_none(self):
        self.client.force_login(self.staff)
        points = self.client.get(PROFILE_URL).context["points"]
        self.assertEqual(points["balance"], 0)
        self.assertFalse(points["has_wallet"])
        self.assertEqual(points["recent"], [])
        self.assertFalse(StaffWallet.objects.filter(user=self.staff).exists())

    def test_balance_totals_and_recent_movements(self):
        wallet = StaffWallet.objects.create(user=self.boss, balance=700)
        self.movement(wallet, StaffPointTransaction.TYPE_MINT, 1000, 0, 1000, "Seed points")
        self.movement(wallet, StaffPointTransaction.TYPE_SELLER_CREDIT, 300, 1000, 700, "Launch bonus")

        self.client.force_login(self.boss)
        points = self.client.get(PROFILE_URL).context["points"]
        self.assertEqual(points["balance"], 700)
        self.assertTrue(points["has_wallet"])
        self.assertEqual(points["received"], 1000)
        self.assertEqual(points["given_to_sellers"], 300)
        self.assertEqual([row["label"] for row in points["recent"]], ["Given to Seller", "Created by Superuser"])
        self.assertFalse(points["recent"][0]["incoming"])
        self.assertTrue(points["recent"][1]["incoming"])

    def test_available_points_are_the_hero_headline(self):
        StaffWallet.objects.create(user=self.boss, balance=1234)
        self.client.force_login(self.boss)
        response = self.client.get(PROFILE_URL)
        self.assertEqual(response.context["points"]["balance_display"], "1,234")
        self.assertContains(response, 'class="pf-wallet"')
        self.assertContains(response, "<b>1,234</b>", html=False)

    def test_zero_points_still_show_on_the_profile(self):
        self.client.force_login(self.staff)
        response = self.client.get(PROFILE_URL)
        self.assertContains(response, 'class="pf-wallet is-empty"')
        self.assertContains(response, "<b>0</b>", html=False)

    def test_ledger_link_is_filtered_to_my_wallet(self):
        mine = StaffWallet.objects.create(user=self.boss, balance=50)
        self.movement(mine, StaffPointTransaction.TYPE_MINT, 50, 0, 50, "Mine to give")
        theirs = StaffWallet.objects.create(user=self.staff, balance=20)
        self.movement(theirs, StaffPointTransaction.TYPE_TRANSFER_IN, 20, 0, 20, "Somebody else's")

        self.client.force_login(self.boss)
        ledger_url = self.client.get(PROFILE_URL).context["points"]["ledger_url"]
        self.assertIn(f"wallet__id__exact={mine.pk}", ledger_url)
        ledger = self.client.get(ledger_url)
        self.assertEqual(ledger.status_code, 200)
        self.assertContains(ledger, "Mine to give")
        self.assertNotContains(ledger, "Somebody else")


class ActionWordingTests(SimpleTestCase):
    def test_humanize_action(self):
        self.assertEqual(humanize_action("ADMIN_SELLER_APPROVE"), "Seller approved")
        self.assertEqual(humanize_action("PRODUCT_UPDATED"), "Product updated")
        self.assertEqual(humanize_action("SUPERUSER_POINTS_MINT"), "Points minted")
        self.assertEqual(humanize_action("ADMIN"), "Admin")

    def test_action_style_matches_whole_words(self):
        self.assertEqual(action_style("PRODUCT_DELETED"), ("delete", "rose"))
        self.assertEqual(action_style("SHOP_REVIEW_UNHIDDEN"), ("check_circle", "green"))
        self.assertEqual(action_style("SHOP_REVIEW_HIDDEN"), ("pause_circle", "amber"))
        self.assertEqual(action_style("SOMETHING_ODD"), ("bolt", "indigo"))

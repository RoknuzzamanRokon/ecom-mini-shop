"""
The business rules registry, RuleService, /api/admin/rules/, the read-only
Django admin pages and the generated docs/BUSINESS_RULES.md
(docs/BUSINESS_RULES_PLAN.md).
"""
from importlib import import_module
from io import StringIO

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.validators import MaxValueValidator, MinValueValidator
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from onboarding.models import OnboardingSettings
from points.models import PointExpiryPolicy, ProductCreationCost, SellerPointPolicy
from rbac.models import Permission, Role, RolePermission, UserRole
from rbac.services import assign_user_role, get_user_permissions
from sellers.models import LimitedShopOwnerProductLimit, SellerProfile
from shop.listing_service import ListingService
from shop.models import InventoryPolicy, ProductListingPolicy, low_stock_threshold
from support.models import SupportPolicy
from .registry import CHECKS, GROUPS, RULES
from .services import AUDIT_ACTION, RuleError, RuleService, StaleRuleError

User = get_user_model()
URL = "/api/admin/rules/"
RULE_MODELS = (
    ProductCreationCost, PointExpiryPolicy, SellerPointPolicy, ProductListingPolicy,
    InventoryPolicy, OnboardingSettings, LimitedShopOwnerProductLimit, SupportPolicy,
)


def change(key, to, seen=None):
    return {key: {"from": RULES[key].default if seen is None else seen, "to": to}}


class RegistryTests(TestCase):
    def test_every_rule_names_a_real_field_with_a_default_in_range(self):
        for rule in RULES.values():
            with self.subTest(rule=rule.key):
                field = rule.model._meta.get_field(rule.field)
                self.assertIsInstance(rule.default, int)
                self.assertLessEqual(rule.minimum, rule.default)
                self.assertLessEqual(rule.default, rule.maximum)
                # The registry range sits inside the model's own validators,
                # so a value the page accepts never fails model validation.
                for validator in field.validators:
                    if isinstance(validator, MinValueValidator):
                        self.assertGreaterEqual(rule.minimum, validator.limit_value)
                    if isinstance(validator, MaxValueValidator):
                        self.assertLessEqual(rule.maximum, validator.limit_value)

    def test_keys_are_unique_and_every_rule_model_is_covered(self):
        self.assertEqual(len(RULES), sum(len(group.rules) for group in GROUPS))
        self.assertEqual({rule.model for rule in RULES.values()}, set(RULE_MODELS))

    def test_the_checks_accept_the_defaults(self):
        defaults = {key: rule.default for key, rule in RULES.items()}
        for check in CHECKS:
            self.assertEqual(check.find(defaults), {})

    def test_the_written_copy_is_up_to_date(self):
        call_command("rules_doc", check=True, stdout=StringIO())


class RuleServiceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="rules_admin", password="Rules-Admin-1", is_staff=True)

    def update(self, changes, reason="Price review"):
        return RuleService.update(changes, reason, actor=self.admin, ip_address="127.0.0.1")

    def test_without_saved_rows_every_value_is_its_default(self):
        self.assertFalse(any(model.objects.exists() for model in RULE_MODELS))
        self.assertEqual(RuleService.values(), {key: rule.default for key, rule in RULES.items()})

    def test_a_change_saves_the_row_and_writes_one_audit_row(self):
        changed = self.update(change("product.creation_cost", 8))

        self.assertEqual(changed, [{"key": "product.creation_cost", "from": 5, "to": 8}])
        self.assertEqual(ProductCreationCost.objects.get(pk=1).required_points, 8)
        entry = AuditLog.objects.get(action=AUDIT_ACTION)
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.target_type, "ProductCreationCost")
        self.assertEqual(entry.ip_address, "127.0.0.1")
        self.assertEqual(entry.metadata["rule"], "product.creation_cost")
        self.assertEqual(entry.metadata["previous_state"], 5)
        self.assertEqual(entry.metadata["new_state"], 8)
        self.assertEqual(entry.metadata["reason"], "Price review")

    def test_one_save_changes_rules_on_several_rows(self):
        self.update({
            **change("product.first_period_months", 6),
            **change("product.renewal_points", 7),
            **change("onboarding.tokens_per_seller", 60),
        })

        policy = ProductListingPolicy.objects.get(pk=1)
        self.assertEqual((policy.first_period_months, policy.renewal_points, policy.renewal_period_months), (6, 7, 2))
        self.assertEqual(OnboardingSettings.objects.get(pk=1).tokens_per_seller, 60)
        self.assertEqual(AuditLog.objects.filter(action=AUDIT_ACTION).count(), 3)

    def test_the_services_follow_a_saved_value(self):
        self.update({
            **change("product.creation_cost", 9),
            **change("product.limited_max_products", 4),
            **change("points.staff_expiry_months", 3),
            **change("stock.low_stock_threshold", 25),
            **change("product.ending_soon_days", 14),
            **change("support.auto_close_after_days", 10),
        })

        self.assertEqual(ProductCreationCost.get_cost(), 9)
        self.assertEqual(LimitedShopOwnerProductLimit.get_limit(), 4)
        self.assertEqual(PointExpiryPolicy.get_months(), 3)
        self.assertEqual(low_stock_threshold(), 25)
        owner = User.objects.create_user(username="rules_owner", password="Rules-Owner-1")
        seller = SellerProfile.objects.create(
            user=owner, seller_type=SellerProfile.TYPE_LIMITED_SHOP_OWNER, business_name="Rules Tea",
            status=SellerProfile.STATUS_ACTIVE,
        )
        self.assertEqual(ListingService.seller_summary(seller)["ending_soon_days"], 14)
        self.assertEqual(SupportPolicy.current().auto_close_after_days, 10)

    def test_out_of_range_and_malformed_values_are_refused_and_nothing_is_saved(self):
        cases = {
            "out of range": change("points.seller_validity_days", 366),
            "below range": change("product.creation_cost", 0),
            "unknown rule": {"product.free_delivery": {"from": 0, "to": 1}},
            "a boolean": {"product.creation_cost": {"from": 5, "to": True}},
            "a string": {"product.creation_cost": {"from": 5, "to": "8"}},
            "no from": {"product.creation_cost": {"to": 8}},
        }
        for name, changes in cases.items():
            with self.subTest(name), self.assertRaises(RuleError) as caught:
                self.update(changes)
            self.assertEqual(list(caught.exception.errors), list(changes))
        self.assertFalse(any(model.objects.exists() for model in RULE_MODELS))
        self.assertFalse(AuditLog.objects.filter(action=AUDIT_ACTION).exists())

    def test_the_reason_is_required_and_bounded(self):
        for reason in ("", "   ", None, "x" * 501):
            with self.subTest(reason=reason), self.assertRaises(RuleError) as caught:
                self.update(change("product.creation_cost", 8), reason=reason)
            self.assertIn("reason", caught.exception.errors)

    def test_an_empty_or_unchanged_request_is_refused(self):
        for changes in ({}, None, [], change("product.creation_cost", 5)):
            with self.subTest(changes=changes), self.assertRaises(RuleError) as caught:
                self.update(changes)
            self.assertIn("changes", caught.exception.errors)

    def test_a_stale_value_is_refused_with_the_stored_one(self):
        self.update(change("product.creation_cost", 8))

        with self.assertRaises(StaleRuleError) as caught:
            self.update({**change("product.creation_cost", 10), **change("product.renewal_points", 6)})

        self.assertEqual(caught.exception.current, {"product.creation_cost": 8})
        self.assertEqual(ProductCreationCost.get_cost(), 8)
        self.assertEqual(ProductListingPolicy.current().renewal_points, 5)

    def test_the_minimum_sale_cannot_pass_the_starting_points_alone(self):
        with self.assertRaises(RuleError) as caught:
            self.update(change("points.minimum_purchase", 300))

        self.assertEqual(list(caught.exception.errors), ["onboarding.starting_points"])
        self.assertIn("raise both in one save", caught.exception.errors["onboarding.starting_points"])
        self.assertFalse(SellerPointPolicy.objects.exists())

    def test_raising_both_in_one_save_or_giving_no_starting_points_works(self):
        self.update({**change("points.minimum_purchase", 300), **change("onboarding.starting_points", 300)})
        self.assertEqual(SellerPointPolicy.current().minimum_purchase, 300)

        self.update(change("onboarding.starting_points", 0, seen=300))
        self.update(change("points.minimum_purchase", 500, seen=300))
        self.assertEqual(RuleService.values()["onboarding.starting_points"], 0)

    def test_starting_points_below_the_minimum_are_refused(self):
        with self.assertRaises(RuleError) as caught:
            self.update(change("onboarding.starting_points", 50))
        self.assertIn("onboarding.starting_points", caught.exception.errors)

    def test_the_snapshot_shows_values_defaults_and_the_last_change(self):
        self.update(change("product.creation_cost", 8), reason="First")
        self.update(change("product.creation_cost", 6, seen=8), reason="Second")

        snapshot = RuleService.snapshot()
        self.assertEqual([group["key"] for group in snapshot["groups"]], [group.key for group in GROUPS])
        rule = snapshot["groups"][0]["rules"][0]
        self.assertEqual(rule["key"], "product.creation_cost")
        self.assertEqual((rule["value"], rule["default"], rule["unit"]), (6, 5, "points"))
        self.assertEqual(rule["last_change"]["by"], "rules_admin")
        self.assertEqual(rule["last_change"]["reason"], "Second")
        self.assertIsNone(snapshot["groups"][0]["rules"][1]["last_change"])
        self.assertTrue(snapshot["groups"][0]["fixed"])
        self.assertEqual(snapshot["checks"], [check.description for check in CHECKS])


class RulesAPITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())

    def staff(self, username, role_code=None, *codes):
        user = User.objects.create_user(username=username, password="Rules-Staff-1", is_staff=True)
        if role_code:
            assign_user_role(user, role_code)
        if codes:
            role = Role.objects.create(code=f"RULES_TEST_{username.upper()}", name=f"Rules test {username}")
            for code in codes:
                RolePermission.objects.create(role=role, permission=Permission.objects.get(code=code))
            UserRole.objects.create(user=user, role=role, is_active=True)
        self.client.force_authenticate(user=user)
        return user

    def patch(self, changes, reason="Quarterly review"):
        return self.client.patch(URL, {"changes": changes, "reason": reason}, format="json")

    def test_signed_out_and_unpermitted_users_are_refused(self):
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_401_UNAUTHORIZED)
        self.staff("rules_nobody", Role.ROLE_SUPPORT_TEAM)
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_403_FORBIDDEN)

    def test_the_seeded_roles(self):
        expected = {
            Role.ROLE_ADMINISTRATOR: {"rules.view", "rules.manage"},
            Role.ROLE_OPERATION_MANAGER: {"rules.view"},
            Role.ROLE_FINANCE: {"rules.view"},
            Role.ROLE_SALES_MANAGER: set(),
            Role.ROLE_SALES_TEAM: set(),
            Role.ROLE_SUPPORT_TEAM: set(),
            Role.ROLE_CUSTOMER: set(),
        }
        for role_code, codes in expected.items():
            with self.subTest(role=role_code):
                user = User.objects.create_user(username=f"seeded_{role_code.lower()}", password="Rules-Staff-1")
                assign_user_role(user, role_code)
                self.assertEqual(get_user_permissions(user) & {"rules.view", "rules.manage"}, codes)

    def test_viewers_read_but_cannot_change(self):
        self.staff("rules_finance", Role.ROLE_FINANCE)

        response = self.client.get(URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["can_manage"])
        self.assertEqual(len(response.data["groups"]), len(GROUPS))
        refused = self.patch(change("product.creation_cost", 8))
        self.assertEqual(refused.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("rules.manage", refused.data["detail"])
        self.assertFalse(ProductCreationCost.objects.exists())

    def test_an_administrator_changes_a_rule(self):
        self.staff("rules_boss", Role.ROLE_ADMINISTRATOR)
        self.assertTrue(self.client.get(URL).data["can_manage"])

        response = self.patch(change("points.seller_validity_days", 45))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["changed"], [{"key": "points.seller_validity_days", "from": 30, "to": 45}])
        rule = next(r for g in response.data["groups"] for r in g["rules"] if r["key"] == "points.seller_validity_days")
        self.assertEqual(rule["value"], 45)
        self.assertEqual(rule["last_change"]["by"], "rules_boss")
        self.assertEqual(SellerPointPolicy.current().validity_days, 45)

    def test_manage_alone_also_reads(self):
        self.staff("rules_manager_only", None, "rules.manage")
        self.assertEqual(self.client.get(URL).status_code, status.HTTP_200_OK)

    def test_refusals_say_why(self):
        self.staff("rules_boss2", Role.ROLE_ADMINISTRATOR)

        invalid = self.patch(change("points.minimum_purchase", 300))
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("onboarding.starting_points", invalid.data["errors"])
        self.assertEqual(invalid.data["detail"], invalid.data["errors"]["onboarding.starting_points"])

        no_reason = self.patch(change("product.creation_cost", 8), reason="")
        self.assertEqual(no_reason.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", no_reason.data["errors"])

        self.assertEqual(self.client.patch(URL, [1, 2], format="json").status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_stale_save_answers_409(self):
        self.staff("rules_boss3", Role.ROLE_ADMINISTRATOR)
        self.patch(change("product.creation_cost", 8))

        response = self.patch(change("product.creation_cost", 10))

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["current"], {"product.creation_cost": 8})

    def test_the_migration_grants_existing_roles(self):
        RolePermission.objects.filter(permission__code__startswith="rules.").delete()

        import_module("rbac.migrations.0006_rules_permissions").add_rules_permissions(apps, None)

        granted = set(
            RolePermission.objects.filter(permission__code__startswith="rules.")
            .values_list("role__code", "permission__code")
        )
        self.assertEqual(granted, {
            (Role.ROLE_ADMINISTRATOR, "rules.view"),
            (Role.ROLE_ADMINISTRATOR, "rules.manage"),
            (Role.ROLE_OPERATION_MANAGER, "rules.view"),
            (Role.ROLE_FINANCE, "rules.view"),
        })


class ReadOnlyDjangoAdminTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="rules_super", email="rules@example.com", password="Rules-Super-123"
        )
        self.client.force_login(self.superuser)

    @staticmethod
    def url(model, view, *args):
        return reverse(f"admin:{model._meta.app_label}_{model._meta.model_name}_{view}", args=args)

    def test_every_rule_page_is_read_only_and_points_to_the_console(self):
        for model in RULE_MODELS:
            with self.subTest(model=model.__name__):
                listing = self.client.get(self.url(model, "changelist"))
                self.assertEqual(listing.status_code, 200)
                self.assertContains(listing, "Console Rules page")
                self.assertContains(listing, "/admin/rules")
                self.assertEqual(self.client.get(self.url(model, "add")).status_code, 403)

                row = model.objects.create()
                view = self.client.get(self.url(model, "change", row.pk))
                self.assertEqual(view.status_code, 200)
                self.assertNotContains(view, 'name="_save"')
                field = next(rule.field for rule in RULES.values() if rule.model is model)
                posted = self.client.post(self.url(model, "change", row.pk), {field: 99})
                self.assertEqual(posted.status_code, 403)
                self.assertEqual(self.client.post(self.url(model, "delete", row.pk), {"post": "yes"}).status_code, 403)

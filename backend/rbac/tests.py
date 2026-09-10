from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import Permission, Role, RolePermission, UserRole
from .permissions import HasObjectPermission, HasPermission, require_permission
from .services import (
    assign_user_role,
    get_user_permissions,
    get_user_role_codes,
    has_user_permission,
    remove_user_role,
)

User = get_user_model()


class DummyObject:
    """Mock object for object-level permission tests."""
    def __init__(self, owner=None):
        self.owner = owner


class RBACSeedTest(TestCase):
    """Verifies that the seed command creates all 7 roles, permissions and mappings idempotently."""

    def test_seed_creates_all_seven_roles_and_permissions(self):
        out = StringIO()
        call_command("seed_rbac", stdout=out)

        expected_roles = [
            "SUPER_ADMINISTRATOR",
            "ADMINISTRATOR",
            "OPERATION_MANAGER",
            "SALES_MANAGER",
            "SALES_TEAM",
            "FINANCE",
            "SUPPORT_TEAM",
        ]
        for role_code in expected_roles:
            self.assertTrue(Role.objects.filter(code=role_code).exists(), f"Role {role_code} missing")

        # Verify key permissions exist
        expected_perms = [
            "users.view", "users.create", "users.update", "users.delete",
            "roles.view", "roles.assign",
            "products.view", "products.create", "products.approve", "products.reject",
            "shops.view", "shops.approve",
            "sellers.view", "sellers.approve", "sellers.suspend",
            "orders.view", "orders.refund",
            "payments.view", "payments.verify",
            "points.view", "points.add", "points.deduct",
            "reports.view",
        ]
        for perm_code in expected_perms:
            self.assertTrue(Permission.objects.filter(code=perm_code).exists(), f"Permission {perm_code} missing")

        # Verify super administrator has role permissions assigned
        super_role = Role.objects.get(code="SUPER_ADMINISTRATOR")
        self.assertGreater(super_role.permissions.count(), 30)

    def test_seed_idempotency_no_duplicates(self):
        call_command("seed_rbac", stdout=StringIO())
        perms_count_1 = Permission.objects.count()
        roles_count_1 = Role.objects.count()
        role_perms_count_1 = RolePermission.objects.count()

        # Run second time
        call_command("seed_rbac", stdout=StringIO())
        self.assertEqual(Permission.objects.count(), perms_count_1)
        self.assertEqual(Role.objects.count(), roles_count_1)
        self.assertEqual(RolePermission.objects.count(), role_perms_count_1)


class JWTAuthenticationTest(TestCase):
    """Verifies JWT token obtain, refresh, and authenticated user endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="securepassword123",
        )

    def test_token_obtain_success(self):
        response = self.client.post(
            "/api/auth/token/",
            {"username": "testuser", "password": "securepassword123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_token_obtain_invalid_credentials_fails(self):
        response = self.client.post(
            "/api/auth/token/",
            {"username": "testuser", "password": "wrongpassword"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_refresh_success(self):
        token_res = self.client.post(
            "/api/auth/token/",
            {"username": "testuser", "password": "securepassword123"},
            format="json",
        )
        refresh_token = token_res.data["refresh"]

        refresh_res = self.client.post(
            "/api/auth/token/refresh/",
            {"refresh": refresh_token},
            format="json",
        )
        self.assertEqual(refresh_res.status_code, status.HTTP_200_OK)
        self.assertIn("access", refresh_res.data)

    def test_unauthenticated_request_rejected(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_me_endpoint_returns_user_and_permissions(self):
        call_command("seed_rbac", stdout=StringIO())
        assign_user_role(self.user, "OPERATION_MANAGER")

        token_res = self.client.post(
            "/api/auth/token/",
            {"username": "testuser", "password": "securepassword123"},
            format="json",
        )
        access_token = token_res.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

        res = self.client.get("/api/auth/me/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["username"], "testuser")
        self.assertIn("OPERATION_MANAGER", res.data["roles"])
        self.assertIn("products.approve", res.data["permissions"])


class RBACAuthorizationTest(TestCase):
    """Verifies permission resolution, role combinations, superadmin privileges, and object permissions."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())

        cls.op_user = User.objects.create_user(
            username="op_user", password="password123"
        )
        assign_user_role(cls.op_user, "OPERATION_MANAGER")

        cls.sales_user = User.objects.create_user(
            username="sales_user", password="password123"
        )
        assign_user_role(cls.sales_user, "SALES_TEAM")

        cls.superadmin_user = User.objects.create_user(
            username="superadmin_user", password="password123"
        )
        assign_user_role(cls.superadmin_user, "SUPER_ADMINISTRATOR")

        cls.regular_user = User.objects.create_user(
            username="regular_user", password="password123"
        )

    def setUp(self):
        self.client = APIClient()

    def test_user_with_permission_allowed(self):
        # op_user has 'products.approve'
        self.assertTrue(has_user_permission(self.op_user, "products.approve"))

        self.client.force_authenticate(user=self.op_user)
        res = self.client.get("/api/auth/test-permission/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_user_without_permission_denied(self):
        # sales_user does NOT have 'products.approve'
        self.assertFalse(has_user_permission(self.sales_user, "products.approve"))

        self.client.force_authenticate(user=self.sales_user)
        res = self.client.get("/api/auth/test-permission/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_multiple_roles_combine_permissions(self):
        # Initially sales_user cannot refund orders or approve products
        self.assertFalse(has_user_permission(self.sales_user, "orders.refund"))
        self.assertFalse(has_user_permission(self.sales_user, "products.approve"))

        # Assign FINANCE role as well
        assign_user_role(self.sales_user, "FINANCE")

        # Now has union of SALES_TEAM + FINANCE permissions
        self.assertTrue(has_user_permission(self.sales_user, "orders.refund"))
        self.assertTrue(has_user_permission(self.sales_user, "points.add"))
        self.assertTrue(has_user_permission(self.sales_user, "products.create"))

    def test_super_administrator_has_full_permissions(self):
        self.assertTrue(has_user_permission(self.superadmin_user, "anything.custom"))
        self.assertTrue(has_user_permission(self.superadmin_user, "products.approve"))

        self.client.force_authenticate(user=self.superadmin_user)
        res = self.client.get("/api/auth/test-permission/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_django_superuser_has_full_permissions(self):
        su = User.objects.create_superuser("django_su", "su@example.com", "pass123")
        self.assertTrue(has_user_permission(su, "random.permission"))

    def test_deactivated_role_revokes_permission(self):
        user = User.objects.create_user("temp_user", password="pass")
        assign_user_role(user, "FINANCE")
        self.assertTrue(has_user_permission(user, "payments.refund"))

        remove_user_role(user, "FINANCE")
        self.assertFalse(has_user_permission(user, "payments.refund"))

    def test_object_level_permission(self):
        perm_class = HasObjectPermission()

        class MockView:
            staff_permission = "products.update"

        view = MockView()

        # 1. Owner of object
        obj1 = DummyObject(owner=self.regular_user)
        class MockRequest:
            user = self.regular_user

        self.assertTrue(perm_class.has_object_permission(MockRequest(), view, obj1))

        # 2. Non-owner without staff permission is denied
        other_user = User.objects.create_user("non_owner_user", password="password123")
        class NonOwnerRequest:
            user = other_user

        self.assertFalse(perm_class.has_object_permission(NonOwnerRequest(), view, obj1))

        # 3. Super Administrator can access any object
        class SuperAdminRequest:
            user = self.superadmin_user

        self.assertTrue(perm_class.has_object_permission(SuperAdminRequest(), view, obj1))

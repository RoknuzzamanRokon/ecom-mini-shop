import datetime
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from audit.services import AuditService
from rbac.models import Permission, Role, RolePermission, UserRole
from sellers.models import SellerProfile
from shops.models import Shop

User = get_user_model()


class AdminPhase1APITests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # 1. Superuser
        cls.superadmin = User.objects.create_superuser(
            username="phase1_superadmin",
            email="superadmin@example.com",
            password="adminpassword123",
        )

        # 2. Platform Admin (ROLE_ADMINISTRATOR with users.admin.view, shops.admin.manage, etc.)
        cls.admin_user = User.objects.create_user(
            username="phase1_admin",
            email="admin@example.com",
            password="adminpassword123",
            is_staff=True,
        )
        admin_role, _ = Role.objects.get_or_create(
            code=Role.ROLE_ADMINISTRATOR,
            defaults={"name": "Administrator"},
        )
        users_admin_view_perm, _ = Permission.objects.get_or_create(
            code="users.admin.view",
            defaults={"name": "View Admin Users", "resource": "users", "action": "admin_view"},
        )
        shops_admin_manage_perm, _ = Permission.objects.get_or_create(
            code="shops.admin.manage",
            defaults={"name": "Manage Shops", "resource": "shops", "action": "admin_manage"},
        )
        RolePermission.objects.get_or_create(role=admin_role, permission=users_admin_view_perm)
        RolePermission.objects.get_or_create(role=admin_role, permission=shops_admin_manage_perm)
        UserRole.objects.create(user=cls.admin_user, role=admin_role)

        # 3. Operation Manager (ROLE_OPERATION_MANAGER with shops.view, shops.approve)
        cls.op_manager = User.objects.create_user(
            username="phase1_op_manager",
            email="op@example.com",
            password="staffpassword123",
            is_staff=True,
        )
        op_role, _ = Role.objects.get_or_create(
            code=Role.ROLE_OPERATION_MANAGER,
            defaults={"name": "Operation Manager"},
        )
        shops_view_perm, _ = Permission.objects.get_or_create(
            code="shops.view",
            defaults={"name": "View Shops", "resource": "shops", "action": "view"},
        )
        shops_approve_perm, _ = Permission.objects.get_or_create(
            code="shops.approve",
            defaults={"name": "Approve Shops", "resource": "shops", "action": "approve"},
        )
        RolePermission.objects.get_or_create(role=op_role, permission=shops_view_perm)
        RolePermission.objects.get_or_create(role=op_role, permission=shops_approve_perm)
        UserRole.objects.create(user=cls.op_manager, role=op_role)

        # 4. Standard Customer (ROLE_CUSTOMER)
        cls.customer = User.objects.create_user(
            username="phase1_customer",
            email="customer@example.com",
            password="customerpassword123",
        )
        cust_role, _ = Role.objects.get_or_create(
            code=Role.ROLE_CUSTOMER,
            defaults={"name": "Customer"},
        )
        UserRole.objects.create(user=cls.customer, role=cust_role)

        # 5. Unauthorized Staff User (No governance / shop permissions)
        cls.unauthorized_staff = User.objects.create_user(
            username="phase1_no_perms_staff",
            email="noperms@example.com",
            password="staffpassword123",
            is_staff=True,
        )

        # 6. Sample Seller Profile and Shop for testing
        cls.seller_user = User.objects.create_user(
            username="phase1_seller_user",
            email="seller@example.com",
            password="sellerpassword123",
        )
        cls.seller_profile = SellerProfile.objects.create(
            user=cls.seller_user,
            business_name="Phase1 Test Business",
            status=SellerProfile.STATUS_APPROVED,
        )
        cls.test_shop = Shop.objects.create(
            name="Phase1 Test Shop",
            slug="phase1-test-shop",
            owner=cls.seller_profile,
            status=Shop.STATUS_PENDING,
        )

        # 7. Seed Audit Logs
        cls.audit_entry1 = AuditLog.objects.create(
            actor=cls.admin_user,
            action="TEST_ACTION_A",
            target_type="Shop",
            target_id=str(cls.test_shop.id),
            target_repr="Phase1 Test Shop",
            metadata={"reason": "Initial test setup", "token": "super_secret_jwt_token", "safe_note": "Normal log note"},
            created_at=timezone.now() - datetime.timedelta(days=2),
        )
        cls.audit_entry2 = AuditLog.objects.create(
            actor=cls.op_manager,
            action="TEST_ACTION_B",
            target_type="Product",
            target_id="999",
            target_repr="Sample Product 999",
            metadata={"reason": "Product inspected", "password": "sensitive_raw_password"},
            created_at=timezone.now() - datetime.timedelta(days=1),
        )
        cls.audit_entry3 = AuditLog.objects.create(
            actor=cls.admin_user,
            action="TEST_ACTION_C",
            target_type="Shop",
            target_id=str(cls.test_shop.id),
            target_repr="Phase1 Test Shop",
            metadata={"reason": "Follow up verification"},
            created_at=timezone.now(),
        )

    def setUp(self):
        self.audit_list_url = reverse("shop:admin_audit_logs_list")
        self.shops_list_url = reverse("shop:admin_shops_list")
        self.shop_detail_url = reverse("shop:admin_shops_detail", kwargs={"pk": self.test_shop.id})
        self.shop_status_url = reverse("shop:admin_shops_status", kwargs={"pk": self.test_shop.id})

    # =========================================================================
    # AUDIT LOGS ENDPOINT TESTS
    # =========================================================================

    def test_audit_logs_unauthenticated_rejected(self):
        """Unauthenticated requests must be rejected with 401."""
        response = self.client.get(self.audit_list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_audit_logs_customer_rejected(self):
        """Customer requests must be denied with 403."""
        self.client.force_authenticate(user=self.customer)
        response = self.client.get(self.audit_list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_audit_logs_unauthorized_staff_rejected(self):
        """Staff without governance/audit permissions must be denied with 403."""
        self.client.force_authenticate(user=self.unauthorized_staff)
        response = self.client.get(self.audit_list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_audit_logs_superadmin_allowed(self):
        """Super Administrator is granted access."""
        self.client.force_authenticate(user=self.superadmin)
        response = self.client.get(self.audit_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertGreaterEqual(response.data["count"], 3)

    def test_audit_logs_platform_admin_allowed(self):
        """Platform Administrator with users.admin.view is granted access."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.audit_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)

    def test_audit_logs_newest_first_ordering(self):
        """Audit logs must be returned descending by created_at (newest first)."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.audit_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertGreaterEqual(len(results), 2)
        # Verify first element is newer than or equal to second
        self.assertGreaterEqual(results[0]["created_at"], results[1]["created_at"])

    def test_audit_logs_pagination(self):
        """Audit logs response adheres to standard AdminPagination."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f"{self.audit_list_url}?page=1&page_size=2")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 2)

    def test_audit_logs_filtering_by_action(self):
        """Filter by action code."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f"{self.audit_list_url}?action=TEST_ACTION_B")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertIn("TEST_ACTION_B", item["action"])

    def test_audit_logs_filtering_by_resource_type(self):
        """Filter by resource/target type."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f"{self.audit_list_url}?resource_type=Product")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertEqual(item["target_type"].lower(), "product")

    def test_audit_logs_filtering_by_resource_id(self):
        """Filter by target/resource ID."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f"{self.audit_list_url}?resource_id={self.test_shop.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertEqual(str(item["target_id"]), str(self.test_shop.id))

    def test_audit_logs_filtering_by_actor(self):
        """Filter by actor ID or username."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f"{self.audit_list_url}?actor={self.op_manager.id}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for item in response.data["results"]:
            self.assertEqual(item["actor"]["id"], self.op_manager.id)

    def test_audit_logs_read_only_methods(self):
        """Audit Log API is strictly read-only; mutations are forbidden with 405."""
        self.client.force_authenticate(user=self.superadmin)
        post_res = self.client.post(self.audit_list_url, {"action": "NEW_LOG"})
        self.assertEqual(post_res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        put_res = self.client.put(self.audit_list_url, {"action": "NEW_LOG"})
        self.assertEqual(put_res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        patch_res = self.client.patch(self.audit_list_url, {"action": "NEW_LOG"})
        self.assertEqual(patch_res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        del_res = self.client.delete(self.audit_list_url)
        self.assertEqual(del_res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_audit_logs_sensitive_data_redaction(self):
        """Sensitive credential keys in metadata/changes are redacted to [REDACTED]."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(f"{self.audit_list_url}?action=TEST_ACTION_A")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertTrue(len(results) > 0)
        target_item = results[0]
        self.assertEqual(target_item["metadata"].get("token"), "[REDACTED]")
        self.assertEqual(target_item["metadata"].get("safe_note"), "Normal log note")

    # =========================================================================
    # OPERATION MANAGER SHOP ACCESS TESTS
    # =========================================================================

    def test_operation_manager_can_view_shop_list(self):
        """Operation Manager with 'shops.view' can GET /api/admin/shops/."""
        self.client.force_authenticate(user=self.op_manager)
        response = self.client.get(self.shops_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)

    def test_operation_manager_can_view_shop_detail(self):
        """Operation Manager with 'shops.view' can GET /api/admin/shops/<id>/."""
        self.client.force_authenticate(user=self.op_manager)
        response = self.client.get(self.shop_detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.test_shop.id)

    def test_operation_manager_can_approve_shop(self):
        """Operation Manager with 'shops.approve' can approve a pending shop."""
        self.client.force_authenticate(user=self.op_manager)
        response = self.client.post(self.shop_status_url, {"action": "approve"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.test_shop.refresh_from_db()
        self.assertEqual(self.test_shop.status, Shop.STATUS_ACTIVE)

    def test_operation_manager_cannot_suspend_shop(self):
        """Operation Manager without 'shops.admin.manage' CANNOT suspend a shop (403)."""
        self.client.force_authenticate(user=self.op_manager)
        response = self.client.post(
            self.shop_status_url,
            {"action": "suspend", "reason": "Suspension attempt without broader permission"},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Broader shop management permission", str(response.data))

    def test_admin_with_manage_permission_can_suspend_shop(self):
        """Administrator with 'shops.admin.manage' can suspend a shop."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.post(
            self.shop_status_url,
            {"action": "suspend", "reason": "Policy violation flagged by admin"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.test_shop.refresh_from_db()
        self.assertEqual(self.test_shop.status, Shop.STATUS_SUSPENDED)

    def test_unauthorized_staff_denied_shop_access(self):
        """Staff without shop view permission is denied (403)."""
        self.client.force_authenticate(user=self.unauthorized_staff)
        list_res = self.client.get(self.shops_list_url)
        self.assertEqual(list_res.status_code, status.HTTP_403_FORBIDDEN)
        detail_res = self.client.get(self.shop_detail_url)
        self.assertEqual(detail_res.status_code, status.HTTP_403_FORBIDDEN)
        status_res = self.client.post(self.shop_status_url, {"action": "approve"})
        self.assertEqual(status_res.status_code, status.HTTP_403_FORBIDDEN)

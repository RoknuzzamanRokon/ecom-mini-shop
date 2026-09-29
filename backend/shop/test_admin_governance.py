import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from audit.models import AuditLog
from customers.models import Address, CustomerProfile
from rbac.models import Permission, Role, RolePermission, UserRole
from rbac.services import assign_user_role, get_user_permissions, get_user_role_codes
from sellers.models import SellerProfile
from shop.models import Category, Product
from shops.models import Shop

User = get_user_model()


class AdminGovernanceTests(APITestCase):
    """
    Comprehensive test suite for Task 17: Admin & Platform Governance Management.
    Audits authorization, RBAC anti-escalation, sensitive data protection,
    seller/shop/product/category/customer administration, category deletion safeguard,
    financial data protection, audit logging, and concurrency.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        # 1. Super Administrator
        cls.superadmin = User.objects.create_superuser(
            username="super_gov_admin",
            email="superadmin@minishop.com",
            password="SuperPassword123!",
        )
        assign_user_role(cls.superadmin, Role.ROLE_SUPER_ADMINISTRATOR)

        # 2. Administrator
        cls.admin = User.objects.create_user(
            username="gov_admin",
            email="admin@minishop.com",
            password="AdminPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.admin, Role.ROLE_ADMINISTRATOR)

        # 3. Operation Manager
        cls.op_manager = User.objects.create_user(
            username="gov_op_manager",
            email="op@minishop.com",
            password="OpPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.op_manager, Role.ROLE_OPERATION_MANAGER)

        # 4. Support User
        cls.support_user = User.objects.create_user(
            username="gov_support",
            email="support@minishop.com",
            password="SupportPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.support_user, Role.ROLE_SUPPORT_TEAM)

        # 4b. Sales Team User (products.view/create/update only — no approve/reject/publish/admin.manage)
        cls.sales_team_user = User.objects.create_user(
            username="gov_sales_team",
            email="sales_team@minishop.com",
            password="SalesTeamPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.sales_team_user, Role.ROLE_SALES_TEAM)

        # 5. Seller User
        cls.seller_user = User.objects.create_user(
            username="gov_seller_user",
            email="seller@minishop.com",
            password="SellerPassword123!",
        )
        cls.seller_profile = SellerProfile.objects.create(
            user=cls.seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Gov Seller Shop",
            business_email="seller@minishop.com",
            business_phone="01711111111",
            status=SellerProfile.STATUS_APPROVED,
        )

        # 6. Customer User
        cls.customer_user = User.objects.create_user(
            username="gov_customer",
            email="customer@minishop.com",
            password="CustomerPassword123!",
        )
        assign_user_role(cls.customer_user, Role.ROLE_CUSTOMER)
        cls.customer_profile = CustomerProfile.objects.create(
            user=cls.customer_user,
            display_name="Gov Customer",
            phone="01822222222",
            gender=CustomerProfile.GENDER_MALE,
        )
        cls.customer_address = Address.objects.create(
            user=cls.customer_user,
            label=Address.LABEL_HOME,
            recipient_name="Gov Customer",
            phone="01822222222",
            address_line_1="123 Dhaka Road",
            city="Dhaka",
            is_default=True,
        )

        # 7. Category & Shop & Product
        cls.category = Category.objects.create(
            name="Governance Electronics",
            slug="gov-electronics",
            is_active=True,
        )
        cls.shop = Shop.objects.create(
            owner=cls.seller_profile,
            name="Gov Tech Shop",
            slug="gov-tech-shop",
            status=Shop.STATUS_ACTIVE,
        )
        cls.product = Product.objects.create(
            category=cls.category,
            shop=cls.shop,
            name="Gov Smart Watch",
            slug="gov-smart-watch",
            price=Decimal("4500.00"),
            stock=15,
            status=Product.STATUS_APPROVED,
            is_active=True,
        )

    # ==========================================================================
    # 1. AUTHORIZATION MATRIX TESTS
    # ==========================================================================

    def test_anonymous_user_blocked_401(self):
        """Anonymous user must receive 401 Unauthorized across admin endpoints."""
        endpoints = [
            "/api/admin/users/",
            "/api/admin/roles/",
            "/api/admin/sellers/",
            "/api/admin/shops/",
            "/api/admin/products/",
            "/api/admin/categories/",
            "/api/admin/customers/",
        ]
        for url in endpoints:
            res = self.client.get(url)
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED, f"Failed at {url}")

    def test_customer_blocked_403(self):
        """Retail customer must receive 403 Forbidden across admin endpoints."""
        self.client.force_authenticate(user=self.customer_user)
        endpoints = [
            "/api/admin/users/",
            "/api/admin/roles/",
            "/api/admin/sellers/",
            "/api/admin/shops/",
            "/api/admin/products/",
            "/api/admin/categories/",
            "/api/admin/customers/",
        ]
        for url in endpoints:
            res = self.client.get(url)
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, f"Failed at {url}")

    def test_seller_blocked_403(self):
        """Seller must receive 403 Forbidden across admin endpoints."""
        self.client.force_authenticate(user=self.seller_user)
        res = self.client.get("/api/admin/users/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_support_user_blocked_on_unauthorized_endpoints(self):
        """Support team without user management permissions receives 403 on admin user/role APIs."""
        self.client.force_authenticate(user=self.support_user)
        res = self.client.get("/api/admin/users/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        res = self.client.get("/api/admin/roles/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_administrator_allowed_on_governance_endpoints(self):
        """Administrator holding admin permissions is allowed on admin endpoints."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/admin/users/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        res = self.client.get("/api/admin/roles/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        res = self.client.get("/api/admin/sellers/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        res = self.client.get("/api/admin/shops/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        res = self.client.get("/api/admin/products/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        res = self.client.get("/api/admin/categories/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        res = self.client.get("/api/admin/customers/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    # ==========================================================================
    # 2. CRITICAL RBAC ANTI-ESCALATION SECURITY AUDIT
    # ==========================================================================

    def test_admin_cannot_assign_super_administrator_role(self):
        """An Administrator cannot assign SUPER_ADMINISTRATOR to any user."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(
            f"/api/admin/users/{self.customer_user.id}/",
            data={"roles": [Role.ROLE_SUPER_ADMINISTRATOR], "reason": "Attempting privilege escalation"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertNotIn(Role.ROLE_SUPER_ADMINISTRATOR, get_user_role_codes(self.customer_user))

    def test_admin_cannot_self_modify_roles(self):
        """An Administrator cannot modify their own roles to prevent self-escalation."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(
            f"/api/admin/users/{self.admin.id}/",
            data={"roles": [Role.ROLE_SUPER_ADMINISTRATOR], "reason": "Self escalation"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_modify_super_admin_account(self):
        """An Administrator cannot modify a Super Administrator account."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(
            f"/api/admin/users/{self.superadmin.id}/",
            data={"is_active": False, "reason": "Disabling superadmin"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_deactivate_last_active_super_admin(self):
        """System prevents deactivating the last active Super Administrator."""
        self.client.force_authenticate(user=self.superadmin)
        res = self.client.patch(
            f"/api/admin/users/{self.superadmin.id}/",
            data={"is_active": False, "reason": "Testing deactivating last superadmin"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.superadmin.refresh_from_db()
        self.assertTrue(self.superadmin.is_active)

    def test_cannot_create_protected_role(self):
        """Cannot create role with protected code SUPER_ADMINISTRATOR or ADMINISTRATOR."""
        self.client.force_authenticate(user=self.superadmin)
        res = self.client.post(
            "/api/admin/roles/",
            data={
                "code": Role.ROLE_SUPER_ADMINISTRATOR,
                "name": "Fake Super Admin",
                "reason": "Tamper test",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_modify_or_delete_protected_role(self):
        """Protected system roles (SUPER_ADMINISTRATOR, ADMINISTRATOR) cannot be updated or deleted."""
        self.client.force_authenticate(user=self.admin)
        super_role = Role.objects.get(code=Role.ROLE_SUPER_ADMINISTRATOR)

        # Attempt modify
        res = self.client.patch(
            f"/api/admin/roles/{super_role.id}/",
            data={"name": "Compromised Name", "reason": "Unauthorized rename"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Attempt delete
        res = self.client.delete(f"/api/admin/roles/{super_role.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_cannot_delete_role_with_active_users(self):
        """Cannot delete a custom role if users are currently assigned to it."""
        self.client.force_authenticate(user=self.superadmin)
        custom_role = Role.objects.create(code="CUSTOM_ANALYST", name="Custom Analyst")
        assign_user_role(self.customer_user, "CUSTOM_ANALYST")

        res = self.client.delete(f"/api/admin/roles/{custom_role.id}/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(Role.objects.filter(code="CUSTOM_ANALYST").exists())

    # ==========================================================================
    # 3. SENSITIVE CREDENTIALS & PRIVACY TESTS
    # ==========================================================================

    def test_user_and_customer_apis_exclude_passwords_and_tokens(self):
        """User and customer admin endpoints must never serialize password or security tokens."""
        self.client.force_authenticate(user=self.admin)

        # User List & Detail
        res_list = self.client.get("/api/admin/users/")
        res_detail = self.client.get(f"/api/admin/users/{self.admin.id}/")
        for res in [res_list, res_detail]:
            payload_str = json.dumps(res.data)
            self.assertNotIn("password", payload_str)
            self.assertNotIn("token", payload_str)
            self.assertNotIn("secret", payload_str)

        # Customer List & Detail
        res_c_list = self.client.get("/api/admin/customers/")
        res_c_detail = self.client.get(f"/api/admin/customers/{self.customer_profile.id}/")
        for res in [res_c_list, res_c_detail]:
            payload_str = json.dumps(res.data)
            self.assertNotIn("password", payload_str)
            self.assertNotIn("token", payload_str)

    # ==========================================================================
    # 4. SELLER ADMINISTRATION TESTS
    # ==========================================================================

    def test_seller_lifecycle_transitions_and_audit(self):
        """Admin can suspend and reactivate sellers with audit logging."""
        self.client.force_authenticate(user=self.admin)

        # Suspend
        res_suspend = self.client.post(
            f"/api/admin/sellers/{self.seller_profile.id}/status/",
            data={"action": "suspend", "reason": "Policy violation investigation"},
            format="json",
        )
        self.assertEqual(res_suspend.status_code, status.HTTP_200_OK)
        self.seller_profile.refresh_from_db()
        self.assertEqual(self.seller_profile.status, SellerProfile.STATUS_SUSPENDED)
        self.assertEqual(self.seller_profile.suspension_reason, "Policy violation investigation")

        # Verify audit log
        audit = AuditLog.objects.filter(action="ADMIN_SELLER_SUSPEND", target_id=str(self.seller_profile.id)).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor, self.admin)
        self.assertEqual(audit.metadata.get("reason"), "Policy violation investigation")

        # Reactivate
        res_reactivate = self.client.post(
            f"/api/admin/sellers/{self.seller_profile.id}/status/",
            data={"action": "reactivate", "reason": "Investigation cleared"},
            format="json",
        )
        self.assertEqual(res_reactivate.status_code, status.HTTP_200_OK)
        self.seller_profile.refresh_from_db()
        self.assertEqual(self.seller_profile.status, SellerProfile.STATUS_ACTIVE)

    # ==========================================================================
    # 5. SHOP ADMINISTRATION TESTS
    # ==========================================================================

    def test_shop_lifecycle_transitions_and_audit(self):
        """Admin can suspend and reactivate shops."""
        self.client.force_authenticate(user=self.admin)

        res = self.client.post(
            f"/api/admin/shops/{self.shop.id}/status/",
            data={"action": "suspend", "reason": "Copyright dispute"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.status, Shop.STATUS_SUSPENDED)
        self.assertEqual(self.shop.suspension_reason, "Copyright dispute")

        # Reactivate
        res_re = self.client.post(
            f"/api/admin/shops/{self.shop.id}/status/",
            data={"action": "reactivate", "reason": "Dispute resolved"},
            format="json",
        )
        self.assertEqual(res_re.status_code, status.HTTP_200_OK)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.status, Shop.STATUS_ACTIVE)

    # ==========================================================================
    # 6. PRODUCT ADMINISTRATION & PUBLISHING RULES
    # ==========================================================================

    def test_product_approval_publishing_and_safeguards(self):
        """Product approval and publishing enforces shop/seller operational state."""
        self.client.force_authenticate(user=self.admin)

        # 1. Unpublish
        res_unpub = self.client.post(
            f"/api/admin/products/{self.product.id}/status/",
            data={"action": "unpublish", "reason": "Temporary review"},
            format="json",
        )
        self.assertEqual(res_unpub.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_UNPUBLISHED)

        # 2. Publish when shop is operational -> Succeeds
        res_pub = self.client.post(
            f"/api/admin/products/{self.product.id}/status/",
            data={"action": "publish", "reason": "Review completed"},
            format="json",
        )
        self.assertEqual(res_pub.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_PUBLISHED)

        # 3. Publish when shop is SUSPENDED -> Blocked by business rule
        self.shop.status = Shop.STATUS_SUSPENDED
        self.shop.suspension_reason = "Test suspension"
        self.shop.save()

        res_blocked = self.client.post(
            f"/api/admin/products/{self.product.id}/status/",
            data={"action": "publish", "reason": "Attempting publish on suspended shop"},
            format="json",
        )
        self.assertEqual(res_blocked.status_code, status.HTTP_400_BAD_REQUEST)

        # Restore shop
        self.shop.status = Shop.STATUS_ACTIVE
        self.shop.suspension_reason = ""
        self.shop.save()

    # ==========================================================================
    # 6b. PRODUCT RBAC PERMISSION SEPARATION (Phase 1A.1)
    #
    # Prior to this fix, /api/admin/products/ (list & detail) and the status
    # transition endpoint were both gated by the single blanket permission
    # 'products.admin.manage'. OPERATION_MANAGER holds 'products.view',
    # 'products.approve', 'products.reject' and 'products.publish' but NOT
    # 'products.admin.manage', so it could not even list products despite
    # being the role responsible for reviewing them. These tests prove:
    #   - viewing is unlocked by 'products.view' alone,
    #   - each status action is unlocked by its own matching permission,
    #   - holding one narrow permission does NOT grant the others,
    #   - 'products.admin.manage' remains required for 'unpublish' (which has
    #     no narrower permission of its own),
    #   - SALES_TEAM (view/create/update only) can view but not transition.
    # ==========================================================================

    def test_operation_manager_can_view_product_list(self):
        """Operation Manager with 'products.view' can GET /api/admin/products/."""
        self.client.force_authenticate(user=self.op_manager)
        res = self.client.get("/api/admin/products/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("results", res.data)

    def test_operation_manager_can_view_product_detail(self):
        """Operation Manager with 'products.view' can GET /api/admin/products/<id>/."""
        self.client.force_authenticate(user=self.op_manager)
        res = self.client.get(f"/api/admin/products/{self.product.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], self.product.id)

    def test_operation_manager_can_approve_product(self):
        """Operation Manager with 'products.approve' can approve a product."""
        self.client.force_authenticate(user=self.op_manager)
        res = self.client.post(
            f"/api/admin/products/{self.product.id}/status/",
            data={"action": "approve", "reason": "Meets catalog standards"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_APPROVED)

    def test_operation_manager_can_reject_product(self):
        """Operation Manager with 'products.reject' can reject a product."""
        self.client.force_authenticate(user=self.op_manager)
        res = self.client.post(
            f"/api/admin/products/{self.product.id}/status/",
            data={"action": "reject", "reason": "Listing violates policy"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_REJECTED)
        self.assertEqual(self.product.rejection_reason, "Listing violates policy")

    def test_operation_manager_can_publish_product(self):
        """Operation Manager with 'products.publish' can publish a product."""
        self.client.force_authenticate(user=self.op_manager)
        res = self.client.post(
            f"/api/admin/products/{self.product.id}/status/",
            data={"action": "publish", "reason": "Approved for storefront"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.product.refresh_from_db()
        self.assertEqual(self.product.status, Product.STATUS_PUBLISHED)

    def test_operation_manager_cannot_unpublish_product(self):
        """
        Operation Manager without 'products.admin.manage' CANNOT unpublish (403).
        'unpublish' has no narrower permission of its own, unlike approve/reject/publish.
        """
        self.client.force_authenticate(user=self.op_manager)
        res = self.client.post(
            f"/api/admin/products/{self.product.id}/status/",
            data={"action": "unpublish", "reason": "Attempted unpublish without broader permission"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("Broader product management permission", str(res.data))

    def test_sales_team_can_view_but_not_transition_product_status(self):
        """
        Sales Team holds 'products.view' (list/detail allowed) but none of
        'products.approve' / 'products.reject' / 'products.publish' /
        'products.admin.manage', so every status transition is 403.
        """
        self.client.force_authenticate(user=self.sales_team_user)

        res_list = self.client.get("/api/admin/products/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)

        res_detail = self.client.get(f"/api/admin/products/{self.product.id}/")
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)

        for action in ("approve", "reject", "publish", "unpublish"):
            res = self.client.post(
                f"/api/admin/products/{self.product.id}/status/",
                data={"action": action, "reason": "Sales team escalation attempt"},
                format="json",
            )
            self.assertEqual(
                res.status_code, status.HTTP_403_FORBIDDEN, f"Sales Team unexpectedly allowed to {action}"
            )

    def test_support_team_without_product_permissions_blocked_403(self):
        """Support Team holds no products.* permission and is blocked from admin product views."""
        self.client.force_authenticate(user=self.support_user)
        res = self.client.get("/api/admin/products/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_administrator_retains_full_product_management(self):
        """Administrator with 'products.admin.manage' can perform every status action, including unpublish."""
        self.client.force_authenticate(user=self.admin)
        for action in ("approve", "reject", "publish", "unpublish"):
            res = self.client.post(
                f"/api/admin/products/{self.product.id}/status/",
                data={"action": action, "reason": "Administrator full-access check"},
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_200_OK, f"Administrator unexpectedly blocked on {action}")

    def test_super_administrator_retains_full_product_management(self):
        """Super Administrator (implicit full access) can view and transition products freely."""
        self.client.force_authenticate(user=self.superadmin)
        res = self.client.get("/api/admin/products/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        res = self.client.post(
            f"/api/admin/products/{self.product.id}/status/",
            data={"action": "approve", "reason": "Super admin check"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    # ==========================================================================
    # 7. CATEGORY ADMINISTRATION & DELETION SAFEGUARD
    # ==========================================================================

    def test_cannot_delete_category_with_products(self):
        """CRITICAL SAFEGUARD: Cannot delete a category that has products attached."""
        self.client.force_authenticate(user=self.admin)

        res = self.client.delete(f"/api/admin/categories/{self.category.id}/")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("referenced by", str(res.data))
        self.assertTrue(Category.objects.filter(id=self.category.id).exists())

    def test_can_delete_unused_category(self):
        """Unused category without products can be deleted safely."""
        self.client.force_authenticate(user=self.admin)
        empty_cat = Category.objects.create(name="Empty Category", slug="empty-cat")

        res = self.client.delete(f"/api/admin/categories/{empty_cat.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(Category.objects.filter(id=empty_cat.id).exists())

    # ==========================================================================
    # 8. CUSTOMER ADMINISTRATION READ-ONLY TESTS
    # ==========================================================================

    def test_customer_admin_is_strictly_read_only(self):
        """Customer admin endpoints allow GET but reject POST/PATCH/DELETE (405)."""
        self.client.force_authenticate(user=self.admin)

        # GET detail works
        res_get = self.client.get(f"/api/admin/customers/{self.customer_profile.id}/")
        self.assertEqual(res_get.status_code, status.HTTP_200_OK)
        self.assertEqual(res_get.data["display_name"], "Gov Customer")
        self.assertEqual(len(res_get.data["addresses"]), 1)

        # POST / PUT / PATCH / DELETE rejected
        res_post = self.client.post("/api/admin/customers/", data={"name": "test"}, format="json")
        self.assertEqual(res_post.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        res_patch = self.client.patch(f"/api/admin/customers/{self.customer_profile.id}/", data={"phone": "123"}, format="json")
        self.assertEqual(res_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        res_del = self.client.delete(f"/api/admin/customers/{self.customer_profile.id}/")
        self.assertEqual(res_del.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # ==========================================================================
    # 9. PAGINATION & FILTERING TESTS
    # ==========================================================================

    def test_admin_pagination_structure(self):
        """Admin list endpoints return paginated responses with count, next, previous, results."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/admin/users/?page_size=5")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("count", res.data)
        self.assertIn("results", res.data)
        self.assertIsInstance(res.data["results"], list)


class AdminPermissionDelegationTests(APITestCase):
    """
    Phase 1G-A: the permission-delegation boundary and the catalogue endpoint
    that lets the Management Console preview it.

    The governance rule under test is "you may only give away what you already
    hold": a non-wildcard user creating or editing a role may attach a
    permission only if it is in their own effective permission set.

    NOTE ON FIXTURES: none of these tests alters a seeded role's permissions.
    The delegator below is an isolated, test-only role built from a controlled
    subset of the real catalogue, so the suite never has to grant
    OPERATION_MANAGER (or any other shipped role) an extra permission just to
    make a scenario reachable.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        cls.superadmin = User.objects.create_superuser(
            username="deleg_superadmin",
            email="deleg_super@minishop.com",
            password="SuperPassword123!",
        )
        assign_user_role(cls.superadmin, Role.ROLE_SUPER_ADMINISTRATOR)

        # Isolated test-only role: may administer roles, and holds exactly two
        # business permissions it is therefore allowed to delegate.
        cls.DELEGATABLE_BUSINESS_PERMS = ["sellers.view", "sellers.create"]
        cls.delegator_role = Role.objects.create(
            code="TEST_DELEGATOR",
            name="Test Delegator",
            description="Isolated Phase 1G-A fixture. Not a shipped role.",
        )
        for code in ["roles.admin.view", "roles.admin.manage"] + cls.DELEGATABLE_BUSINESS_PERMS:
            RolePermission.objects.create(
                role=cls.delegator_role,
                permission=Permission.objects.get(code=code),
            )

        cls.delegator = User.objects.create_user(
            username="deleg_actor",
            email="deleg_actor@minishop.com",
            password="DelegatorPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.delegator, "TEST_DELEGATOR")

        # Holds no RBAC governance permission at all.
        cls.outsider = User.objects.create_user(
            username="deleg_outsider",
            email="deleg_outsider@minishop.com",
            password="OutsiderPassword123!",
        )
        assign_user_role(cls.outsider, Role.ROLE_CUSTOMER)

    # ==========================================================================
    # PERMISSION CATALOGUE ENDPOINT
    # ==========================================================================

    def test_permission_catalogue_requires_authentication(self):
        res = self.client.get("/api/admin/permissions/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_permission_catalogue_requires_roles_admin_view(self):
        """A user without 'roles.admin.view' cannot read the catalogue."""
        self.client.force_authenticate(user=self.outsider)
        res = self.client.get("/api/admin/permissions/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_permission_catalogue_returns_full_seeded_catalogue(self):
        """The catalogue is the database's, never a hardcoded client-side list."""
        self.client.force_authenticate(user=self.superadmin)
        res = self.client.get("/api/admin/permissions/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        expected = set(Permission.objects.values_list("code", flat=True))
        returned = {row["code"] for row in res.data["results"]}
        self.assertEqual(returned, expected)
        self.assertEqual(res.data["count"], len(expected))

        # Every row carries what the selector groups and labels by.
        for row in res.data["results"]:
            self.assertIn("resource", row)
            self.assertIn("action", row)
            self.assertIn("name", row)
            self.assertIn("is_delegatable", row)

    def test_super_administrator_may_delegate_everything(self):
        """Wildcard access is reported as such, not expanded into N grants."""
        self.client.force_authenticate(user=self.superadmin)
        res = self.client.get("/api/admin/permissions/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["has_full_platform_access"])
        self.assertEqual(res.data["delegatable_count"], res.data["count"])
        self.assertTrue(all(row["is_delegatable"] for row in res.data["results"]))

    def test_catalogue_delegatable_flags_match_actor_effective_permissions(self):
        """
        For a non-wildcard actor, the delegatable set is exactly their own
        effective permission set — no more, and nothing silently hidden.
        """
        self.client.force_authenticate(user=self.delegator)
        res = self.client.get("/api/admin/permissions/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["has_full_platform_access"])

        delegatable = {row["code"] for row in res.data["results"] if row["is_delegatable"]}
        self.assertEqual(delegatable, get_user_permissions(self.delegator))

        for code in self.DELEGATABLE_BUSINESS_PERMS:
            self.assertIn(code, delegatable)
        self.assertNotIn("users.admin.manage", delegatable)

    # ==========================================================================
    # DELEGATION ENFORCEMENT ON ROLE CREATION
    # ==========================================================================

    def test_delegator_can_create_role_with_permissions_it_holds(self):
        self.client.force_authenticate(user=self.delegator)
        res = self.client.post(
            "/api/admin/roles/",
            data={
                "code": "MANAGER",
                "name": "Manager",
                "permissions": self.DELEGATABLE_BUSINESS_PERMS,
                "reason": "Phase 1G-A delegation scenario",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        created = Role.objects.get(code="MANAGER")
        self.assertEqual(
            set(created.permissions.values_list("code", flat=True)),
            set(self.DELEGATABLE_BUSINESS_PERMS),
        )

    def test_delegator_cannot_create_role_with_permission_it_lacks(self):
        """The §31 escalation attempt: granting away users.admin.manage."""
        self.client.force_authenticate(user=self.delegator)
        res = self.client.post(
            "/api/admin/roles/",
            data={
                "code": "ESCALATED_MANAGER",
                "name": "Escalated Manager",
                "permissions": ["sellers.view", "users.admin.manage"],
                "reason": "Attempting to delegate beyond own authority",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Role.objects.filter(code="ESCALATED_MANAGER").exists())

    def test_every_locked_catalogue_row_is_actually_rejected(self):
        """
        The console's lock icon must be a faithful preview of a backend refusal.
        Asserts the two sides agree for a sample of non-delegatable codes rather
        than trusting that they were derived from the same helper.
        """
        self.client.force_authenticate(user=self.delegator)
        catalogue = self.client.get("/api/admin/permissions/")
        locked = sorted(
            row["code"] for row in catalogue.data["results"] if not row["is_delegatable"]
        )
        self.assertTrue(locked, "fixture must leave some permissions undelegatable")

        for index, code in enumerate(locked[:5]):
            res = self.client.post(
                "/api/admin/roles/",
                data={
                    "code": f"LOCKED_PROBE_{index}",
                    "name": f"Locked Probe {index}",
                    "permissions": [code],
                    "reason": "Verifying the locked preview matches enforcement",
                },
                format="json",
            )
            self.assertEqual(
                res.status_code,
                status.HTTP_403_FORBIDDEN,
                msg=f"catalogue locked '{code}' but the role endpoint accepted it",
            )

    # ==========================================================================
    # DELEGATION ENFORCEMENT ON ROLE UPDATE
    # ==========================================================================

    def test_delegator_cannot_add_undelegatable_permission_to_existing_role(self):
        self.client.force_authenticate(user=self.delegator)
        role = Role.objects.create(code="EDIT_TARGET", name="Edit Target")
        RolePermission.objects.create(
            role=role, permission=Permission.objects.get(code="sellers.view")
        )

        res = self.client.patch(
            f"/api/admin/roles/{role.id}/",
            data={
                "permissions": ["sellers.view", "users.admin.manage"],
                "reason": "Attempting to widen a role beyond own authority",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            set(role.permissions.values_list("code", flat=True)), {"sellers.view"}
        )

    def test_delegator_can_update_role_within_its_authority(self):
        self.client.force_authenticate(user=self.delegator)
        role = Role.objects.create(code="WIDEN_TARGET", name="Widen Target")
        RolePermission.objects.create(
            role=role, permission=Permission.objects.get(code="sellers.view")
        )

        res = self.client.patch(
            f"/api/admin/roles/{role.id}/",
            data={
                "permissions": self.DELEGATABLE_BUSINESS_PERMS,
                "reason": "Granting a permission the actor holds",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(role.permissions.values_list("code", flat=True)),
            set(self.DELEGATABLE_BUSINESS_PERMS),
        )

    def test_delegator_cannot_reach_super_administrator_through_role_editing(self):
        """Protected roles stay protected regardless of delegation authority."""
        self.client.force_authenticate(user=self.delegator)
        super_role = Role.objects.get(code=Role.ROLE_SUPER_ADMINISTRATOR)
        res = self.client.patch(
            f"/api/admin/roles/{super_role.id}/",
            data={"permissions": ["sellers.view"], "reason": "Tamper attempt"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(super_role.permissions.count(), Permission.objects.count())

    # ==========================================================================
    # EFFECTIVE PERMISSIONS ON THE USER DETAIL PAYLOAD
    # ==========================================================================

    def test_user_detail_exposes_effective_permissions_without_credentials(self):
        self.client.force_authenticate(user=self.superadmin)
        res = self.client.get(f"/api/admin/users/{self.delegator.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.assertEqual(set(res.data["permissions"]), get_user_permissions(self.delegator))
        self.assertFalse(res.data["has_full_platform_access"])
        self.assertNotIn("*", res.data["permissions"])

        body = json.dumps(res.data)
        for leaked in ("password", "token", "secret"):
            self.assertNotIn(leaked, body.lower())

    def test_user_detail_reports_wildcard_for_super_administrator(self):
        """
        Full platform access is flagged, and "*" never appears as an assignable
        code in the permission list.
        """
        self.client.force_authenticate(user=self.superadmin)
        res = self.client.get(f"/api/admin/users/{self.superadmin.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["has_full_platform_access"])
        self.assertNotIn("*", res.data["permissions"])
        self.assertEqual(
            set(res.data["permissions"]),
            set(Permission.objects.values_list("code", flat=True)),
        )

    def test_user_detail_effective_permissions_require_view_permission(self):
        self.client.force_authenticate(user=self.outsider)
        res = self.client.get(f"/api/admin/users/{self.delegator.id}/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class AdminUserCreationTests(APITestCase):
    """
    Phase 1G-B: POST /api/admin/users/.

    The governance question under test is that creation cannot become a way
    around a restriction that already applies to editing — an actor who may not
    grant a role via PATCH must not be able to grant it by creating a user.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        cls.superadmin = User.objects.create_superuser(
            username="uc_superadmin",
            email="uc_super@minishop.com",
            password="SuperPassword123!",
        )
        assign_user_role(cls.superadmin, Role.ROLE_SUPER_ADMINISTRATOR)

        cls.admin = User.objects.create_user(
            username="uc_admin",
            email="uc_admin@minishop.com",
            password="AdminPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.admin, Role.ROLE_ADMINISTRATOR)

        # Holds users.admin.view but NOT users.admin.manage.
        cls.viewer_role = Role.objects.create(code="UC_VIEWER", name="User Viewer")
        RolePermission.objects.create(
            role=cls.viewer_role, permission=Permission.objects.get(code="users.admin.view")
        )
        cls.viewer = User.objects.create_user(
            username="uc_viewer", email="uc_viewer@minishop.com", password="ViewerPassword123!"
        )
        assign_user_role(cls.viewer, "UC_VIEWER")

        cls.outsider = User.objects.create_user(
            username="uc_outsider", email="uc_outsider@minishop.com", password="OutsiderPassword123!"
        )
        assign_user_role(cls.outsider, Role.ROLE_CUSTOMER)

    def _payload(self, **overrides):
        payload = {
            "username": "created_user",
            "email": "created_user@minishop.com",
            "password": "BrandNewPassword123!",
            "password_confirm": "BrandNewPassword123!",
            "first_name": "Created",
            "last_name": "User",
            "reason": "Phase 1G-B creation test",
        }
        payload.update(overrides)
        return payload

    # -- authorization -------------------------------------------------------

    def test_anonymous_cannot_create_user(self):
        res = self.client.post("/api/admin/users/", data=self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(User.objects.filter(username="created_user").exists())

    def test_user_without_manage_permission_gets_403(self):
        """users.admin.view is not enough to create — only to read."""
        self.client.force_authenticate(user=self.viewer)
        res = self.client.post("/api/admin/users/", data=self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(username="created_user").exists())

    def test_unrelated_user_gets_403(self):
        self.client.force_authenticate(user=self.outsider)
        res = self.client.post("/api/admin/users/", data=self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # -- happy path ----------------------------------------------------------

    def test_authorized_actor_creates_user_with_roles(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/users/",
            data=self._payload(roles=[Role.ROLE_SUPPORT_TEAM]),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        created = User.objects.get(username="created_user")
        self.assertTrue(created.is_active)
        self.assertEqual(created.email, "created_user@minishop.com")
        self.assertEqual(get_user_role_codes(created), {Role.ROLE_SUPPORT_TEAM})

        # The password must be usable and stored hashed, never echoed back.
        self.assertTrue(created.check_password("BrandNewPassword123!"))
        self.assertNotIn("password", json.dumps(res.data).lower())

        # Response follows the existing admin user representation.
        self.assertEqual(res.data["id"], created.id)
        self.assertIn("permissions", res.data)
        self.assertIn("has_full_platform_access", res.data)

    def test_creation_is_audited(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/users/", data=self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        entry = AuditLog.objects.filter(action="ADMIN_USER_CREATED").order_by("-id").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.metadata.get("reason"), "Phase 1G-B creation test")
        self.assertEqual(entry.metadata["new_state"]["username"], "created_user")

    def test_can_create_inactive_user(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/users/", data=self._payload(is_active=False), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertFalse(User.objects.get(username="created_user").is_active)

    # -- input validation ----------------------------------------------------

    def test_duplicate_username_rejected_case_insensitively(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/users/", data=self._payload(username="UC_ADMIN"), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", res.data)

    def test_duplicate_email_rejected_case_insensitively(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/users/", data=self._payload(email="UC_ADMIN@minishop.com"), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", res.data)

    def test_password_mismatch_rejected(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/users/", data=self._payload(password_confirm="Different123!"), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_weak_password_rejected_by_django_validators(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/users/",
            data=self._payload(password="123", password_confirm="123"),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", res.data)

    def test_reason_is_required(self):
        payload = self._payload()
        del payload["reason"]
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/users/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", res.data)

    def test_unknown_role_code_rejected(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/users/", data=self._payload(roles=["NO_SUCH_ROLE"]), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="created_user").exists())

    def test_inactive_role_cannot_be_assigned(self):
        inactive = Role.objects.create(code="UC_RETIRED", name="Retired", is_active=False)
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/users/", data=self._payload(roles=[inactive.code]), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="created_user").exists())

    # -- anti-escalation -----------------------------------------------------

    def test_administrator_cannot_create_super_administrator(self):
        """The escalation attempt this endpoint most needs to refuse."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/users/",
            data=self._payload(roles=[Role.ROLE_SUPER_ADMINISTRATOR]),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(username="created_user").exists())

    def test_administrator_cannot_create_another_protected_role_holder(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/users/",
            data=self._payload(roles=[Role.ROLE_ADMINISTRATOR]),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(username="created_user").exists())

    def test_super_administrator_may_create_protected_role_holder(self):
        """The restriction is the actor's authority, not a blanket ban."""
        self.client.force_authenticate(user=self.superadmin)
        res = self.client.post(
            "/api/admin/users/",
            data=self._payload(roles=[Role.ROLE_ADMINISTRATOR]),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            get_user_role_codes(User.objects.get(username="created_user")),
            {Role.ROLE_ADMINISTRATOR},
        )

    def test_failed_role_assignment_creates_no_user(self):
        """Creation and role assignment share one transaction."""
        self.client.force_authenticate(user=self.admin)
        before = User.objects.count()
        res = self.client.post(
            "/api/admin/users/",
            data=self._payload(roles=[Role.ROLE_SUPPORT_TEAM, Role.ROLE_SUPER_ADMINISTRATOR]),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(User.objects.count(), before)

    def test_patch_protections_still_hold_after_adding_post(self):
        """Regression guard: the new POST must not have relaxed the PATCH path."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(
            f"/api/admin/users/{self.outsider.id}/",
            data={"roles": [Role.ROLE_SUPER_ADMINISTRATOR], "reason": "escalation attempt"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res = self.client.patch(
            f"/api/admin/users/{self.admin.id}/",
            data={"roles": [Role.ROLE_SUPER_ADMINISTRATOR], "reason": "self escalation"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class AdminSellerCreationTests(APITestCase):
    """Phase 1G-B: POST /api/admin/sellers/ for an existing user."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        cls.superadmin = User.objects.create_superuser(
            username="sc_superadmin",
            email="sc_super@minishop.com",
            password="SuperPassword123!",
        )
        assign_user_role(cls.superadmin, Role.ROLE_SUPER_ADMINISTRATOR)

        cls.admin = User.objects.create_user(
            username="sc_admin",
            email="sc_admin@minishop.com",
            password="AdminPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.admin, Role.ROLE_ADMINISTRATOR)

        # OPERATION_MANAGER holds sellers.view but NOT sellers.admin.manage.
        cls.op_manager = User.objects.create_user(
            username="sc_op_manager",
            email="sc_op@minishop.com",
            password="OpPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.op_manager, Role.ROLE_OPERATION_MANAGER)

        cls.target_user = User.objects.create_user(
            username="sc_target", email="sc_target@minishop.com", password="TargetPassword123!"
        )
        cls.already_seller = User.objects.create_user(
            username="sc_existing", email="sc_existing@minishop.com", password="ExistingPassword123!"
        )
        SellerProfile.objects.create(
            user=cls.already_seller,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Existing Business",
            status=SellerProfile.STATUS_ACTIVE,
        )

    def _payload(self, **overrides):
        payload = {
            "user_id": self.target_user.id,
            "business_name": "Admin Created Shop",
            "seller_type": SellerProfile.TYPE_PRODUCT_OWNER,
            "business_email": "created@minishop.com",
            "business_phone": "01799999999",
            "reason": "Phase 1G-B seller creation test",
        }
        payload.update(overrides)
        return payload

    def test_anonymous_cannot_create_seller(self):
        res = self.client.post("/api/admin/sellers/", data=self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_seller_view_permission_is_not_enough(self):
        """OPERATION_MANAGER can read the directory but not create in it."""
        self.client.force_authenticate(user=self.op_manager)
        res = self.client.post("/api/admin/sellers/", data=self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(SellerProfile.objects.filter(user=self.target_user).exists())

        # ...and the GET path it does hold still works.
        self.assertEqual(self.client.get("/api/admin/sellers/").status_code, status.HTTP_200_OK)

    def test_authorized_actor_creates_seller_for_specified_user(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/sellers/", data=self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        seller = SellerProfile.objects.get(user=self.target_user)
        # Attached to the named user, NOT to the acting administrator.
        self.assertEqual(seller.user, self.target_user)
        self.assertFalse(SellerProfile.objects.filter(user=self.admin).exists())

        self.assertEqual(seller.status, SellerProfile.STATUS_PENDING)
        self.assertFalse(seller.is_operational)
        self.assertEqual(seller.seller_type, SellerProfile.TYPE_PRODUCT_OWNER)
        self.assertEqual(seller.business_name, "Admin Created Shop")
        self.assertEqual(res.data["id"], seller.id)

    def test_creation_has_no_side_effects(self):
        """No wallet, no points, no roles, no shop."""
        from points.models import PointTransaction as PT, SellerWallet

        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/sellers/", data=self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        seller = SellerProfile.objects.get(user=self.target_user)
        self.assertFalse(SellerWallet.objects.filter(seller=seller).exists())
        self.assertFalse(PT.objects.filter(seller=seller).exists())
        self.assertEqual(get_user_role_codes(self.target_user), set())
        self.assertEqual(seller.shops.count(), 0)

    def test_creation_is_audited(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post("/api/admin/sellers/", data=self._payload(), format="json")

        entry = AuditLog.objects.filter(action="ADMIN_SELLER_CREATED").order_by("-id").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.metadata["new_state"]["user_id"], self.target_user.id)

    def test_nonexistent_user_rejected(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/sellers/", data=self._payload(user_id=999999), format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("user_id", res.data)

    def test_user_with_existing_profile_rejected(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/sellers/", data=self._payload(user_id=self.already_seller.id), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SellerProfile.objects.filter(user=self.already_seller).count(), 1)

    def test_invalid_seller_type_rejected(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/sellers/", data=self._payload(seller_type="GALACTIC_OVERLORD"), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(SellerProfile.objects.filter(user=self.target_user).exists())

    def test_blank_business_name_rejected(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/sellers/", data=self._payload(business_name="   "), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reason_is_required(self):
        payload = self._payload()
        del payload["reason"]
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/sellers/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", res.data)


class AdminSellerGranularPermissionTests(APITestCase):
    """
    The narrow seller codes work in the admin console without
    'sellers.admin.manage': sellers.create -> POST /api/admin/sellers/,
    sellers.update -> PATCH /api/admin/sellers/<pk>/, sellers.approve ->
    approve/reject, sellers.suspend -> suspend/reactivate.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        def staff_with(username, codes):
            role = Role.objects.create(code=f"PROBE_{username.upper()}", name=f"Probe {username}")
            for code in ["sellers.view", *codes]:
                RolePermission.objects.create(role=role, permission=Permission.objects.get(code=code))
            user = User.objects.create_user(
                username=username,
                email=f"{username}@minishop.com",
                password="ProbePassword123!",
                is_staff=True,
            )
            assign_user_role(user, role.code)
            return user

        cls.viewer = staff_with("gp_viewer", [])
        cls.approver = staff_with("gp_approver", ["sellers.approve"])
        cls.suspender = staff_with("gp_suspender", ["sellers.suspend"])
        cls.creator = staff_with("gp_creator", ["sellers.create"])
        cls.updater = staff_with("gp_updater", ["sellers.update"])

        cls.target_user = User.objects.create_user(
            username="gp_target", email="gp_target@minishop.com", password="TargetPassword123!"
        )

    def setUp(self):
        seller_user = User.objects.create_user(
            username=f"gp_seller_{SellerProfile.objects.count()}",
            email="gp_seller@minishop.com",
            password="SellerPassword123!",
        )
        self.pending = SellerProfile.objects.create(
            user=seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Granular Pending",
            business_email="pending@minishop.com",
            status=SellerProfile.STATUS_PENDING,
        )

    def _status(self, user, action, reason="Granular permission test"):
        self.client.force_authenticate(user=user)
        return self.client.post(
            f"/api/admin/sellers/{self.pending.id}/status/",
            data={"action": action, "reason": reason},
            format="json",
        )

    # --- status ---------------------------------------------------------------

    def test_approve_permission_allows_approve_and_reject_only(self):
        res = self._status(self.approver, "suspend")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, SellerProfile.STATUS_PENDING)
        self.assertFalse(AuditLog.objects.filter(action="ADMIN_SELLER_SUSPEND").exists())

        res = self._status(self.approver, "reject")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], SellerProfile.STATUS_REJECTED)

        res = self._status(self.approver, "approve")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], SellerProfile.STATUS_ACTIVE)
        self.assertTrue(
            AuditLog.objects.filter(action="ADMIN_SELLER_APPROVE", actor=self.approver).exists()
        )

    def test_suspend_permission_allows_suspend_and_reactivate_only(self):
        res = self._status(self.suspender, "approve")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, SellerProfile.STATUS_PENDING)

        self.pending.status = SellerProfile.STATUS_ACTIVE
        self.pending.save()

        res = self._status(self.suspender, "suspend", reason="Policy review")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], SellerProfile.STATUS_SUSPENDED)

        res = self._status(self.suspender, "reject")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res = self._status(self.suspender, "reactivate")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], SellerProfile.STATUS_ACTIVE)

    def test_view_only_cannot_change_status(self):
        for action in ("approve", "reject", "suspend", "reactivate"):
            res = self._status(self.viewer, action)
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, msg=action)

    def test_create_and_update_permissions_do_not_grant_status_changes(self):
        for user in (self.creator, self.updater):
            res = self._status(user, "approve")
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, msg=user.username)

    # --- create ---------------------------------------------------------------

    def _create_payload(self):
        return {
            "user_id": self.target_user.id,
            "business_name": "Granular Created",
            "reason": "Granular create test",
        }

    def test_create_permission_allows_seller_creation(self):
        self.client.force_authenticate(user=self.creator)
        res = self.client.post("/api/admin/sellers/", data=self._create_payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], SellerProfile.STATUS_PENDING)
        self.assertTrue(
            AuditLog.objects.filter(action="ADMIN_SELLER_CREATED", actor=self.creator).exists()
        )

    def test_other_seller_permissions_do_not_grant_creation(self):
        for user in (self.viewer, self.approver, self.suspender, self.updater):
            self.client.force_authenticate(user=user)
            res = self.client.post("/api/admin/sellers/", data=self._create_payload(), format="json")
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, msg=user.username)
        self.assertFalse(SellerProfile.objects.filter(user=self.target_user).exists())

    # --- update ---------------------------------------------------------------

    def _patch(self, user, payload):
        self.client.force_authenticate(user=user)
        return self.client.patch(
            f"/api/admin/sellers/{self.pending.id}/", data=payload, format="json"
        )

    def test_update_permission_edits_business_details_with_audit(self):
        res = self._patch(
            self.updater,
            {
                "business_name": "  Renamed Business  ",
                "business_phone": "01700000000",
                "business_email": "pending@minishop.com",
                "reason": "Seller asked for a rename",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["business_name"], "Renamed Business")
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.business_phone, "01700000000")

        entry = AuditLog.objects.get(action="ADMIN_SELLER_UPDATED")
        self.assertEqual(entry.actor, self.updater)
        self.assertEqual(entry.metadata["reason"], "Seller asked for a rename")
        # Unchanged business_email is not recorded as a change.
        self.assertEqual(
            entry.metadata["previous_state"],
            {"business_name": "Granular Pending", "business_phone": ""},
        )
        self.assertEqual(
            entry.metadata["new_state"],
            {"business_name": "Renamed Business", "business_phone": "01700000000"},
        )

    def test_update_cannot_change_status_or_seller_type(self):
        res = self._patch(
            self.updater,
            {
                "description": "Updated description",
                "status": SellerProfile.STATUS_ACTIVE,
                "seller_type": SellerProfile.TYPE_PRODUCT_OWNER,
                "reason": "Tamper attempt",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.description, "Updated description")
        self.assertEqual(self.pending.status, SellerProfile.STATUS_PENDING)
        self.assertEqual(self.pending.seller_type, SellerProfile.TYPE_FULL_SHOP_OWNER)

    def test_unchanged_update_writes_no_audit(self):
        res = self._patch(
            self.updater, {"business_name": "Granular Pending", "reason": "No-op edit"}
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(AuditLog.objects.filter(action="ADMIN_SELLER_UPDATED").exists())

    def test_update_validation(self):
        cases = [
            {"business_name": "New Name"},  # no reason
            {"business_name": "   ", "reason": "Blank name"},
            {"business_email": "not-an-email", "reason": "Bad email"},
            {"reason": "Nothing to change"},
        ]
        for payload in cases:
            res = self._patch(self.updater, payload)
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg=payload)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.business_name, "Granular Pending")

    def test_other_seller_permissions_do_not_grant_update(self):
        for user in (self.viewer, self.approver, self.suspender, self.creator):
            res = self._patch(user, {"business_name": "Hijacked", "reason": "Not allowed"})
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, msg=user.username)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.business_name, "Granular Pending")

    def test_update_missing_seller_returns_404(self):
        self.client.force_authenticate(user=self.updater)
        res = self.client.patch(
            "/api/admin/sellers/999999/",
            data={"business_name": "Ghost", "reason": "Missing"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class AdminSellerNewAccountCreationTests(APITestCase):
    """POST /api/admin/sellers/ with `account`: new login account + seller profile in one call."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        role = Role.objects.create(code="PROBE_NA_CREATOR", name="Probe new-account creator")
        for code in ("sellers.view", "sellers.create"):
            RolePermission.objects.create(role=role, permission=Permission.objects.get(code=code))
        cls.creator = User.objects.create_user(
            username="na_creator",
            email="na_creator@minishop.com",
            password="CreatorPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.creator, role.code)

        # Seeded OPERATION_MANAGER: sellers.view only.
        cls.viewer = User.objects.create_user(
            username="na_viewer",
            email="na_viewer@minishop.com",
            password="ViewerPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.viewer, Role.ROLE_OPERATION_MANAGER)

        cls.existing_user = User.objects.create_user(
            username="na_existing", email="na_existing@minishop.com", password="ExistingPassword123!"
        )

    def _payload(self, **account_overrides):
        account = {
            "username": "na_new_seller",
            "email": "NA_New_Seller@MiniShop.com",
            "password": "NewSellerPass123!",
            "password_confirm": "NewSellerPass123!",
            "first_name": "Nadia",
            "last_name": "Rahman",
        }
        account.update(account_overrides)
        return {
            "account": account,
            "business_name": "Nadia Crafts",
            "seller_type": SellerProfile.TYPE_LIMITED_SHOP_OWNER,
            "reason": "Onboarding a seller without an account",
        }

    def _post(self, payload, user=None):
        self.client.force_authenticate(user=user or self.creator)
        return self.client.post("/api/admin/sellers/", data=payload, format="json")

    def test_creates_account_and_seller_together(self):
        res = self._post(self._payload())
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)

        new_user = User.objects.get(username="na_new_seller")
        self.assertEqual(new_user.email, "na_new_seller@minishop.com")
        self.assertEqual((new_user.first_name, new_user.last_name), ("Nadia", "Rahman"))
        self.assertTrue(new_user.check_password("NewSellerPass123!"))
        self.assertTrue(new_user.is_active)
        self.assertFalse(new_user.is_staff)
        self.assertFalse(new_user.is_superuser)
        self.assertEqual(get_user_role_codes(new_user), set())

        seller = SellerProfile.objects.get(user=new_user)
        self.assertEqual(res.data["id"], seller.id)
        self.assertEqual(res.data["username"], "na_new_seller")
        self.assertEqual(seller.status, SellerProfile.STATUS_PENDING)
        self.assertEqual(seller.seller_type, SellerProfile.TYPE_LIMITED_SHOP_OWNER)

    def test_both_creations_are_audited_without_the_password(self):
        self._post(self._payload())
        new_user = User.objects.get(username="na_new_seller")

        user_entry = AuditLog.objects.get(action="ADMIN_USER_CREATED", target_id=str(new_user.id))
        self.assertEqual(user_entry.actor, self.creator)
        self.assertEqual(user_entry.metadata["reason"], "Onboarding a seller without an account")
        self.assertEqual(user_entry.metadata["new_state"]["roles"], [])
        self.assertEqual(user_entry.metadata["new_state"]["source"], "seller_creation")

        seller_entry = AuditLog.objects.get(action="ADMIN_SELLER_CREATED")
        self.assertEqual(seller_entry.metadata["new_state"]["user_id"], new_user.id)
        self.assertTrue(seller_entry.metadata["new_state"]["new_account"])

        for entry in (user_entry, seller_entry):
            self.assertNotIn("NewSellerPass123!", json.dumps(entry.metadata))

    def test_privileged_account_fields_are_ignored(self):
        res = self._post(
            self._payload(is_staff=True, is_superuser=True, roles=[Role.ROLE_ADMINISTRATOR])
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        new_user = User.objects.get(username="na_new_seller")
        self.assertFalse(new_user.is_staff)
        self.assertFalse(new_user.is_superuser)
        self.assertEqual(get_user_role_codes(new_user), set())

    def test_view_only_cannot_create_account(self):
        res = self._post(self._payload(), user=self.viewer)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(username="na_new_seller").exists())

    def test_user_id_and_account_are_mutually_exclusive(self):
        both = self._payload()
        both["user_id"] = self.existing_user.id
        neither = self._payload()
        del neither["account"]
        for payload in (both, neither):
            res = self._post(payload)
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="na_new_seller").exists())
        self.assertFalse(SellerProfile.objects.filter(user=self.existing_user).exists())

    def test_account_validation(self):
        cases = [
            {"username": "NA_EXISTING"},  # case-insensitive duplicate
            {"email": "na_existing@minishop.com"},
            {"password_confirm": "SomethingElse123!"},
            {"password": "abc", "password_confirm": "abc"},  # MinimumLengthValidator
            {"username": "   "},
        ]
        for overrides in cases:
            res = self._post(self._payload(**overrides))
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg=overrides)
            self.assertIn("account", res.data, msg=overrides)
        self.assertEqual(SellerProfile.objects.count(), 0)

    def test_failed_profile_rolls_back_the_account(self):
        from unittest import mock
        from django.core.exceptions import ValidationError as DjangoValidationError

        with mock.patch(
            "shop.admin_views.create_seller_profile",
            side_effect=DjangoValidationError({"user": "Simulated profile failure."}),
        ):
            res = self._post(self._payload())
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(username="na_new_seller").exists())
        self.assertFalse(AuditLog.objects.filter(action="ADMIN_USER_CREATED").exists())

    def test_new_account_can_log_in(self):
        self._post(self._payload())
        self.client.force_authenticate(user=None)
        res = self.client.post(
            "/api/auth/token/",
            data={"username": "na_new_seller", "password": "NewSellerPass123!"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)


class AdminShopCreationTests(APITestCase):
    """Phase 1H: POST /api/admin/shops/ creates a Shop and assigns an existing seller as owner."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        cls.superadmin = User.objects.create_superuser(
            username="shc_superadmin",
            email="shc_super@minishop.com",
            password="SuperPassword123!",
        )
        assign_user_role(cls.superadmin, Role.ROLE_SUPER_ADMINISTRATOR)

        cls.admin = User.objects.create_user(
            username="shc_admin",
            email="shc_admin@minishop.com",
            password="AdminPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.admin, Role.ROLE_ADMINISTRATOR)

        # OPERATION_MANAGER holds shops.view + shops.approve but NOT shops.admin.manage.
        cls.op_manager = User.objects.create_user(
            username="shc_op_manager",
            email="shc_op@minishop.com",
            password="OpPassword123!",
            is_staff=True,
        )
        assign_user_role(cls.op_manager, Role.ROLE_OPERATION_MANAGER)

        cls.seller_user = User.objects.create_user(
            username="shc_seller", email="shc_seller@minishop.com", password="SellerPassword123!"
        )
        cls.eligible_seller = SellerProfile.objects.create(
            user=cls.seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Eligible Seller Co",
            status=SellerProfile.STATUS_ACTIVE,
        )

        cls.product_owner_user = User.objects.create_user(
            username="shc_product_owner",
            email="shc_product_owner@minishop.com",
            password="ProductPassword123!",
        )
        cls.product_owner_seller = SellerProfile.objects.create(
            user=cls.product_owner_user,
            seller_type=SellerProfile.TYPE_PRODUCT_OWNER,
            business_name="Product Owner Co",
            status=SellerProfile.STATUS_ACTIVE,
        )

        cls.limited_user = User.objects.create_user(
            username="shc_limited", email="shc_limited@minishop.com", password="LimitedPassword123!"
        )
        cls.limited_seller_at_cap = SellerProfile.objects.create(
            user=cls.limited_user,
            seller_type=SellerProfile.TYPE_LIMITED_SHOP_OWNER,
            business_name="Limited Owner Co",
            status=SellerProfile.STATUS_ACTIVE,
        )
        Shop.objects.create(owner=cls.limited_seller_at_cap, name="Existing Limited Shop")

    def _payload(self, **overrides):
        payload = {
            "seller_id": self.eligible_seller.id,
            "name": "Admin Assigned Shop",
            "description": "Created and assigned by an administrator.",
            "phone": "01799999999",
            "address": "House 1, Road 1, Dhaka",
            "reason": "Phase 1H admin shop creation test",
        }
        payload.update(overrides)
        return payload

    def test_anonymous_cannot_create_shop(self):
        res = self.client.post("/api/admin/shops/", data=self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_shop_view_permission_is_not_enough(self):
        """OPERATION_MANAGER can read the directory but not create in it."""
        self.client.force_authenticate(user=self.op_manager)
        res = self.client.post("/api/admin/shops/", data=self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Shop.objects.filter(name="Admin Assigned Shop").exists())

        # ...and the GET path it does hold still works.
        self.assertEqual(self.client.get("/api/admin/shops/").status_code, status.HTTP_200_OK)

    def test_authorized_actor_creates_shop_and_assigns_owner(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/shops/", data=self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        shop = Shop.objects.get(name="Admin Assigned Shop")
        self.assertEqual(shop.owner, self.eligible_seller)
        self.assertEqual(shop.status, Shop.STATUS_DRAFT)
        self.assertEqual(res.data["owner_id"], self.eligible_seller.id)
        self.assertEqual(res.data["id"], shop.id)

    def test_creation_is_audited(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post("/api/admin/shops/", data=self._payload(), format="json")

        entry = AuditLog.objects.filter(action="ADMIN_SHOP_CREATED").order_by("-id").first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.metadata["new_state"]["owner_id"], self.eligible_seller.id)

    def test_nonexistent_seller_rejected(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/shops/", data=self._payload(seller_id=999999), format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("seller_id", res.data)

    def test_product_owner_seller_rejected(self):
        """ShopService's PRODUCT_OWNER restriction applies to admin-assigned shops too."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/shops/",
            data=self._payload(seller_id=self.product_owner_seller.id, name="Product Owner Shop"),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("seller_id", res.data)
        self.assertFalse(Shop.objects.filter(name="Product Owner Shop").exists())

    def test_limited_shop_owner_cap_applies_to_admin_creation(self):
        """A LIMITED_SHOP_OWNER already at their 1-shop cap cannot be assigned a second shop."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/shops/",
            data=self._payload(seller_id=self.limited_seller_at_cap.id, name="Second Limited Shop"),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("seller_id", res.data)
        self.assertFalse(Shop.objects.filter(name="Second Limited Shop").exists())

    def test_full_shop_owner_single_shop_cap_applies_to_admin_creation(self):
        """Confirmed business rule: a FULL_SHOP_OWNER already owning one Shop cannot be assigned a second."""
        self.client.force_authenticate(user=self.admin)
        first_res = self.client.post("/api/admin/shops/", data=self._payload(), format="json")
        self.assertEqual(first_res.status_code, status.HTTP_201_CREATED)

        second_res = self.client.post(
            "/api/admin/shops/",
            data=self._payload(name="Second Admin Assigned Shop"),
            format="json",
        )
        self.assertEqual(second_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("seller_id", second_res.data)
        self.assertFalse(Shop.objects.filter(name="Second Admin Assigned Shop").exists())
        self.assertEqual(Shop.objects.filter(owner=self.eligible_seller).count(), 1)

    def test_blank_name_rejected(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/shops/", data=self._payload(name="   "), format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_coordinates_are_stored_and_returned(self):
        """Coordinates sent at creation (typed, or filled by the browser) are saved and echoed back."""
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/admin/shops/",
            data=self._payload(latitude=23.8103457, longitude=90.4125123),
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertAlmostEqual(res.data["latitude"], 23.8103457, places=6)
        self.assertAlmostEqual(res.data["longitude"], 90.4125123, places=6)

        shop = Shop.objects.get(pk=res.data["id"])
        self.assertAlmostEqual(shop.latitude, 23.8103457, places=6)
        self.assertAlmostEqual(shop.longitude, 90.4125123, places=6)

        detail = self.client.get(f"/api/admin/shops/{shop.id}/")
        self.assertAlmostEqual(detail.data["latitude"], 23.8103457, places=6)

    def test_shop_without_coordinates_reports_null(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/shops/", data=self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(res.data["latitude"])
        self.assertIsNone(res.data["longitude"])

    def test_out_of_range_coordinates_rejected(self):
        """The backend, not the browser, decides what a valid coordinate is."""
        self.client.force_authenticate(user=self.admin)
        for name, coords in (
            ("Bad Latitude Shop", {"latitude": 95.0, "longitude": 90.4}),
            ("Bad Longitude Shop", {"latitude": 23.8, "longitude": -180.5}),
            ("Half Coordinate Shop", {"latitude": 23.8}),
        ):
            with self.subTest(name=name):
                res = self.client.post(
                    "/api/admin/shops/", data=self._payload(name=name, **coords), format="json"
                )
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertFalse(Shop.objects.filter(name=name).exists())

    def test_reason_is_required(self):
        payload = self._payload()
        del payload["reason"]
        self.client.force_authenticate(user=self.admin)
        res = self.client.post("/api/admin/shops/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("reason", res.data)

    def test_seller_cannot_create_shop_via_admin_endpoint(self):
        """A plain seller account (no RBAC role) is blocked from the admin endpoint too."""
        self.client.force_authenticate(user=self.seller_user)
        res = self.client.post("/api/admin/shops/", data=self._payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class AdminShopGranularPermissionTests(APITestCase):
    """
    The narrow shop codes work in the admin console without
    'shops.admin.manage': shops.create -> POST /api/admin/shops/,
    shops.update -> PATCH /api/admin/shops/<pk>/, shops.approve ->
    approve/reject. Suspend/reactivate still need 'shops.admin.manage'.
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")

        def staff_with(username, codes):
            role = Role.objects.create(code=f"PROBE_{username.upper()}", name=f"Probe {username}")
            for code in ["shops.view", *codes]:
                RolePermission.objects.create(role=role, permission=Permission.objects.get(code=code))
            user = User.objects.create_user(
                username=username,
                email=f"{username}@minishop.com",
                password="ProbePassword123!",
                is_staff=True,
            )
            assign_user_role(user, role.code)
            return user

        cls.viewer = staff_with("sg_viewer", [])
        cls.approver = staff_with("sg_approver", ["shops.approve"])
        cls.creator = staff_with("sg_creator", ["shops.create"])
        cls.updater = staff_with("sg_updater", ["shops.update"])

        seller_user = User.objects.create_user(
            username="sg_seller", email="sg_seller@minishop.com", password="SellerPassword123!"
        )
        cls.seller = SellerProfile.objects.create(
            user=seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Granular Shop Owner",
            status=SellerProfile.STATUS_ACTIVE,
        )

    def setUp(self):
        self.shop = Shop.objects.create(
            owner=self.seller,
            name="Granular Shop",
            phone="01711111111",
            status=Shop.STATUS_PENDING,
        )

    def _status(self, user, action, reason="Granular permission test"):
        self.client.force_authenticate(user=user)
        return self.client.post(
            f"/api/admin/shops/{self.shop.id}/status/",
            data={"action": action, "reason": reason},
            format="json",
        )

    def _patch(self, user, payload):
        self.client.force_authenticate(user=user)
        return self.client.patch(f"/api/admin/shops/{self.shop.id}/", data=payload, format="json")

    # --- status ---------------------------------------------------------------

    def test_approve_permission_allows_approve_and_reject(self):
        res = self._status(self.approver, "reject")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], Shop.STATUS_REJECTED)

        res = self._status(self.approver, "approve")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], Shop.STATUS_ACTIVE)

    def test_approve_permission_does_not_allow_suspend_or_reactivate(self):
        self.shop.status = Shop.STATUS_ACTIVE
        self.shop.save()
        for action in ("suspend", "reactivate"):
            res = self._status(self.approver, action)
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, msg=action)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.status, Shop.STATUS_ACTIVE)

    def test_create_update_and_view_do_not_grant_status_changes(self):
        for user in (self.viewer, self.creator, self.updater):
            res = self._status(user, "approve")
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, msg=user.username)

    # --- create ---------------------------------------------------------------

    def _create_payload(self):
        return {"seller_id": self.seller.id, "name": "Created By Probe", "reason": "Granular create"}

    def test_create_permission_allows_shop_creation(self):
        self.shop.delete()  # Shop Owners are capped at one shop.
        self.client.force_authenticate(user=self.creator)
        res = self.client.post("/api/admin/shops/", data=self._create_payload(), format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(res.data["owner_id"], self.seller.id)

    def test_other_shop_permissions_do_not_grant_creation(self):
        for user in (self.viewer, self.approver, self.updater):
            self.client.force_authenticate(user=user)
            res = self.client.post("/api/admin/shops/", data=self._create_payload(), format="json")
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, msg=user.username)
        self.assertFalse(Shop.objects.filter(name="Created By Probe").exists())

    # --- update ---------------------------------------------------------------

    def test_update_permission_edits_details_and_location_with_audit(self):
        res = self._patch(
            self.updater,
            {
                "name": "  Renamed Shop ",
                "phone": "01711111111",
                "address": "House 5, Banani",
                "latitude": 23.7936,
                "longitude": 90.4043,
                "reason": "Owner moved the shop",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data["name"], "Renamed Shop")
        self.assertAlmostEqual(res.data["latitude"], 23.7936)
        self.assertAlmostEqual(res.data["longitude"], 90.4043)

        self.shop.refresh_from_db()
        self.assertEqual(self.shop.slug, "granular-shop")  # public URL is stable
        self.assertEqual(self.shop.status, Shop.STATUS_PENDING)

        entry = AuditLog.objects.get(action="ADMIN_SHOP_UPDATED")
        self.assertEqual(entry.actor, self.updater)
        self.assertEqual(entry.metadata["reason"], "Owner moved the shop")
        # Unchanged phone is not recorded.
        self.assertEqual(
            entry.metadata["previous_state"],
            {"name": "Granular Shop", "address": "", "latitude": None, "longitude": None},
        )
        self.assertEqual(entry.metadata["new_state"]["name"], "Renamed Shop")

    def test_update_can_clear_location(self):
        self._patch(self.updater, {"latitude": 23.79, "longitude": 90.40, "reason": "Set"})
        res = self._patch(self.updater, {"latitude": None, "longitude": None, "reason": "Clear"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIsNone(res.data["latitude"])
        self.shop.refresh_from_db()
        self.assertFalse(self.shop.has_coordinates)

    def test_update_cannot_change_owner_status_or_slug(self):
        other_user = User.objects.create_user(
            username="sg_other", email="sg_other@minishop.com", password="OtherPassword123!"
        )
        other_seller = SellerProfile.objects.create(
            user=other_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Other Owner",
            status=SellerProfile.STATUS_ACTIVE,
        )
        res = self._patch(
            self.updater,
            {
                "description": "New description",
                "owner": other_seller.id,
                "owner_id": other_seller.id,
                "status": Shop.STATUS_ACTIVE,
                "slug": "hijacked",
                "reason": "Tamper attempt",
            },
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.description, "New description")
        self.assertEqual(self.shop.owner, self.seller)
        self.assertEqual(self.shop.status, Shop.STATUS_PENDING)
        self.assertEqual(self.shop.slug, "granular-shop")

    def test_unchanged_update_writes_no_audit(self):
        res = self._patch(self.updater, {"name": "Granular Shop", "reason": "No-op"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(AuditLog.objects.filter(action="ADMIN_SHOP_UPDATED").exists())

    def test_update_validation(self):
        cases = [
            {"name": "New"},  # no reason
            {"name": "   ", "reason": "Blank"},
            {"latitude": 23.79, "reason": "Half a coordinate"},
            {"latitude": 23.79, "longitude": None, "reason": "One null"},
            {"latitude": 123.0, "longitude": 90.4, "reason": "Out of range"},
            {"reason": "Nothing to change"},
        ]
        for payload in cases:
            res = self._patch(self.updater, payload)
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg=payload)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.name, "Granular Shop")
        self.assertFalse(self.shop.has_coordinates)

    def test_other_shop_permissions_do_not_grant_update(self):
        for user in (self.viewer, self.approver, self.creator):
            res = self._patch(user, {"name": "Hijacked", "reason": "Not allowed"})
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN, msg=user.username)
        self.shop.refresh_from_db()
        self.assertEqual(self.shop.name, "Granular Shop")


class AdminShopPhoneNumberTests(APITestCase):
    """Shop.additional_phones through POST /api/admin/shops/ and PATCH /api/admin/shops/<pk>/."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.admin = User.objects.create_user(
            username="ph_admin", email="ph_admin@minishop.com", password="AdminPassword123!", is_staff=True
        )
        assign_user_role(cls.admin, Role.ROLE_ADMINISTRATOR)
        seller_user = User.objects.create_user(
            username="ph_seller", email="ph_seller@minishop.com", password="SellerPassword123!"
        )
        cls.seller = SellerProfile.objects.create(
            user=seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Phone Seller",
            business_phone="01700000001",
            status=SellerProfile.STATUS_ACTIVE,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.admin)

    def _create(self, **overrides):
        payload = {"seller_id": self.seller.id, "name": "Phone Shop", "reason": "Phone test"}
        payload.update(overrides)
        return self.client.post("/api/admin/shops/", data=payload, format="json")

    def test_create_with_additional_phones_normalizes_them(self):
        res = self._create(
            phone="01700000001",
            additional_phones=[" 01800000002 ", "", "01700000001", "01800000002", "01900000003"],
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        # Trimmed; blanks, repeats and the primary number dropped; order kept.
        self.assertEqual(res.data["additional_phones"], ["01800000002", "01900000003"])
        shop = Shop.objects.get(pk=res.data["id"])
        self.assertEqual(shop.phone, "01700000001")
        self.assertEqual(shop.additional_phones, ["01800000002", "01900000003"])

    def test_create_without_additional_phones_defaults_to_empty(self):
        res = self._create(phone="01700000001")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["additional_phones"], [])

    def test_create_rejects_too_many_or_too_long_numbers(self):
        too_many = [f"0180000000{i}" for i in range(Shop.MAX_ADDITIONAL_PHONES + 1)]
        for extras in (too_many, ["0" * (Shop.PHONE_MAX_LENGTH + 1)]):
            res = self._create(additional_phones=extras)
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, msg=extras)
            self.assertIn("additional_phones", res.data)
        self.assertFalse(Shop.objects.filter(name="Phone Shop").exists())

    def test_update_edits_additional_phones_with_audit(self):
        shop_id = self._create(phone="01700000001", additional_phones=["01800000002"]).data["id"]
        res = self.client.patch(
            f"/api/admin/shops/{shop_id}/",
            data={"additional_phones": ["01800000002", "01900000003"], "reason": "Added a number"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data["additional_phones"], ["01800000002", "01900000003"])
        entry = AuditLog.objects.get(action="ADMIN_SHOP_UPDATED")
        self.assertEqual(entry.metadata["previous_state"], {"additional_phones": ["01800000002"]})
        self.assertEqual(
            entry.metadata["new_state"], {"additional_phones": ["01800000002", "01900000003"]}
        )

    def test_promoting_an_extra_to_primary_removes_it_from_the_extras(self):
        shop_id = self._create(phone="01700000001", additional_phones=["01800000002"]).data["id"]
        res = self.client.patch(
            f"/api/admin/shops/{shop_id}/",
            data={"phone": "01800000002", "reason": "New main number"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["phone"], "01800000002")
        self.assertEqual(res.data["additional_phones"], [])


class AdminShopStatusTransitionRuleTests(APITestCase):
    """
    POST /api/admin/shops/<pk>/status/ delegates to ShopService, so the Console
    accepts exactly the source statuses the service and the Django admin do.
    """

    ALLOWED = (
        (Shop.STATUS_DRAFT, "approve", Shop.STATUS_ACTIVE),
        (Shop.STATUS_PENDING, "approve", Shop.STATUS_ACTIVE),
        (Shop.STATUS_REJECTED, "approve", Shop.STATUS_ACTIVE),
        (Shop.STATUS_PENDING, "reject", Shop.STATUS_REJECTED),
        (Shop.STATUS_ACTIVE, "suspend", Shop.STATUS_SUSPENDED),
        (Shop.STATUS_APPROVED, "suspend", Shop.STATUS_SUSPENDED),
        (Shop.STATUS_SUSPENDED, "reactivate", Shop.STATUS_ACTIVE),
    )
    REFUSED = (
        (Shop.STATUS_ACTIVE, "approve"),
        (Shop.STATUS_SUSPENDED, "approve"),
        (Shop.STATUS_DRAFT, "reject"),
        (Shop.STATUS_ACTIVE, "reject"),
        (Shop.STATUS_SUSPENDED, "reject"),
        (Shop.STATUS_PENDING, "suspend"),
        (Shop.STATUS_REJECTED, "suspend"),
        (Shop.STATUS_SUSPENDED, "suspend"),
        (Shop.STATUS_PENDING, "reactivate"),
        (Shop.STATUS_ACTIVE, "reactivate"),
    )

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac")
        cls.admin = User.objects.create_user(
            username="tr_admin", email="tr_admin@minishop.com", password="AdminPassword123!", is_staff=True
        )
        assign_user_role(cls.admin, Role.ROLE_ADMINISTRATOR)
        seller_user = User.objects.create_user(
            username="tr_seller", email="tr_seller@minishop.com", password="SellerPassword123!"
        )
        cls.seller = SellerProfile.objects.create(
            user=seller_user,
            seller_type=SellerProfile.TYPE_FULL_SHOP_OWNER,
            business_name="Transition Seller",
            status=SellerProfile.STATUS_ACTIVE,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.admin)

    def _shop(self, shop_status):
        return Shop.objects.create(
            owner=self.seller,
            name=f"Transition {shop_status} Shop",
            status=shop_status,
            rejection_reason="Earlier rejection" if shop_status == Shop.STATUS_REJECTED else "",
            suspension_reason="Earlier suspension" if shop_status == Shop.STATUS_SUSPENDED else "",
        )

    def _status(self, shop, action):
        return self.client.post(
            f"/api/admin/shops/{shop.id}/status/",
            data={"action": action, "reason": "Transition rule test"},
            format="json",
        )

    def _audit_rows(self, shop):
        return AuditLog.objects.filter(action__startswith="ADMIN_SHOP_", target_id=str(shop.id))

    def test_allowed_transitions_apply_with_one_audit_row(self):
        for source, action, target in self.ALLOWED:
            with self.subTest(source=source, action=action):
                shop = self._shop(source)
                res = self._status(shop, action)
                self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
                self.assertEqual(res.data["status"], target)
                entry = self._audit_rows(shop).get()
                self.assertEqual(entry.action, f"ADMIN_SHOP_{action.upper()}")
                self.assertEqual(entry.metadata["previous_state"], {"status": source})
                self.assertEqual(entry.metadata["new_state"], {"status": target})

    def test_refused_transitions_are_400_and_change_nothing(self):
        for source, action in self.REFUSED:
            with self.subTest(source=source, action=action):
                shop = self._shop(source)
                res = self._status(shop, action)
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
                # A bare list of messages, which the Console shows as-is.
                self.assertIsInstance(res.data, list)
                self.assertIn(f"Cannot {action} shop with status '{source}'", str(res.data[0]))
                shop.refresh_from_db()
                self.assertEqual(shop.status, source)
                self.assertFalse(self._audit_rows(shop).exists())

    def test_approving_a_rejected_shop_clears_the_rejection_reason(self):
        shop = self._shop(Shop.STATUS_REJECTED)
        res = self._status(shop, "approve")
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        shop.refresh_from_db()
        self.assertEqual(shop.status, Shop.STATUS_ACTIVE)
        self.assertEqual(shop.rejection_reason, "")
        self.assertEqual(shop.reviewed_by, self.admin)
        self.assertIsNotNone(shop.approved_at)

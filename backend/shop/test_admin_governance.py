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
from rbac.services import assign_user_role, get_user_role_codes
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

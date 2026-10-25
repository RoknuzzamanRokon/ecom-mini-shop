"""
TASK-048 decision 9: the CUSTOMER role's definition is locked like the
protected roles. The Console can neither change nor delete it, and in the
Django admin only a Super Administrator can change it; nobody deletes it.
Holding or assigning CUSTOMER needs nothing extra.
"""

from io import StringIO

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .admin import RoleAdmin
from .models import Permission, Role, RolePermission
from .services import LOCKED_ROLE_CODES, PROTECTED_ROLE_CODES, assign_user_role


class CustomerRoleLockedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())
        cls.customer_role = Role.objects.get(code=Role.ROLE_CUSTOMER)
        cls.role_admin = User.objects.create_user(username="lock_role_admin", password="Lock-Role-1", is_staff=True)
        assign_user_role(cls.role_admin, Role.ROLE_ADMINISTRATOR)
        cls.superuser = User.objects.create_superuser(username="lock_root", email="lock@example.com", password="Lock-Role-1")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.role_admin)
        self.url = f"/api/admin/roles/{self.customer_role.pk}/"

    def test_the_console_cannot_switch_it_off_or_narrow_it(self):
        for payload in ({"is_active": False}, {"permissions": ["cart.view"]}, {"name": "Shoppers"}):
            with self.subTest(payload=payload):
                res = self.client.patch(self.url, {**payload, "reason": "Trying"}, format="json")
                self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.customer_role.refresh_from_db()
        self.assertTrue(self.customer_role.is_active)
        self.assertGreater(RolePermission.objects.filter(role=self.customer_role).count(), 1)

    def test_the_console_cannot_delete_it_and_marks_it_protected(self):
        self.assertEqual(self.client.delete(self.url, {"reason": "Trying"}, format="json").status_code, 403)
        self.assertTrue(self.client.get(self.url).data["is_protected"])

    def test_only_a_super_administrator_changes_it_in_the_django_admin(self):
        role_admin = RoleAdmin(Role, admin.site)
        request = RequestFactory().get("/")
        request.user = self.role_admin
        self.assertFalse(role_admin.has_change_permission(request, self.customer_role))
        request.user = self.superuser
        self.assertTrue(role_admin.has_change_permission(request, self.customer_role))
        self.assertFalse(role_admin.has_delete_permission(request, self.customer_role))

    def test_assigning_customer_stays_open(self):
        self.assertNotIn(Role.ROLE_CUSTOMER, PROTECTED_ROLE_CODES)
        self.assertIn(Role.ROLE_CUSTOMER, LOCKED_ROLE_CODES)
        res = self.client.post(
            "/api/admin/users/",
            {"username": "lock_new_customer", "email": "lnc@example.com", "password": "Lock-New-Cust-1", "password_confirm": "Lock-New-Cust-1",
             "roles": [Role.ROLE_CUSTOMER], "reason": "New shopper"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)

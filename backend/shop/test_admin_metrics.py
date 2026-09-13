from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from rbac.models import Role, UserRole
from shop.models import Category, Order, Payment, Product
from shops.models import Shop
from sellers.models import SellerProfile

User = get_user_model()


class AdminMetricsAPITests(APITestCase):
    def setUp(self):
        # 1. Superuser / Admin
        self.admin_user = User.objects.create_superuser(
            username="admin_user",
            email="admin@example.com",
            password="adminpassword123",
        )

        # 2. Staff user with Role
        self.staff_user = User.objects.create_user(
            username="staff_user",
            email="staff@example.com",
            password="staffpassword123",
            is_staff=True,
        )
        op_role, _ = Role.objects.get_or_create(
            code=Role.ROLE_OPERATION_MANAGER,
            defaults={"name": "Operation Manager"},
        )
        UserRole.objects.create(user=self.staff_user, role=op_role)

        # 3. Regular Customer
        self.customer = User.objects.create_user(
            username="customer_user",
            email="customer@example.com",
            password="customerpassword123",
        )
        cust_role, _ = Role.objects.get_or_create(
            code=Role.ROLE_CUSTOMER,
            defaults={"name": "Customer"},
        )
        UserRole.objects.create(user=self.customer, role=cust_role)

        self.url = reverse("shop:admin_metrics")

    def test_unauthenticated_request_rejected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_customer_access_denied(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("detail", response.data)

    def test_admin_access_granted(self):
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total_orders", response.data)
        self.assertIn("total_revenue", response.data)
        self.assertIn("pending_shops", response.data)
        self.assertIn("pending_sellers", response.data)
        self.assertIn("total_shops", response.data)
        self.assertIn("total_sellers", response.data)
        self.assertIn("total_products", response.data)

    def test_staff_role_access_granted(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

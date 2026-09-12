from io import StringIO
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from .models import Role
from .services import get_user_role_codes, get_user_permissions

User = get_user_model()


class CustomerRegistrationTests(TestCase):
    """
    Unit and integration tests for public customer self-registration:
    - Successful customer account creation
    - Anti-escalation security
    - Mandatory fields and validation rules
    - Unique username and email (case-insensitive)
    - Password hashing and password confirmation
    - Default CUSTOMER RBAC role assignment
    - Seamless immediate login via /api/auth/token/
    """

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())

    def setUp(self):
        self.client = APIClient()

    def test_successful_customer_registration(self):
        payload = {
            "username": "johndoe",
            "email": "john.doe@example.com",
            "password": "SecurePassword123!",
            "password_confirm": "SecurePassword123!",
            "first_name": "John",
            "last_name": "Doe",
        }
        response = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify response shape does NOT leak password
        self.assertNotIn("password", response.data)
        self.assertNotIn("password_confirm", response.data)
        self.assertEqual(response.data["username"], "johndoe")
        self.assertEqual(response.data["email"], "john.doe@example.com")
        self.assertEqual(response.data["first_name"], "John")
        self.assertEqual(response.data["last_name"], "Doe")
        self.assertIn("message", response.data)

        # Verify user in database
        user = User.objects.get(username="johndoe")
        self.assertTrue(user.check_password("SecurePassword123!"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        # Verify role assignment is CUSTOMER
        roles = get_user_role_codes(user)
        self.assertIn(Role.ROLE_CUSTOMER, roles)
        self.assertEqual(len(roles), 1)

        # Verify customer profile creation
        self.assertTrue(hasattr(user, "customer_profile"))
        self.assertEqual(user.customer_profile.display_name, "John Doe")

    def test_registration_mandatory_fields(self):
        # Empty payload
        response = self.client.post("/api/auth/register/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)
        self.assertIn("email", response.data)
        self.assertIn("password", response.data)
        self.assertIn("password_confirm", response.data)

    def test_duplicate_username_rejected(self):
        User.objects.create_user(
            username="existinguser",
            email="existing@example.com",
            password="Password123!",
        )

        payload = {
            "username": "ExistingUser",  # case-insensitive check
            "email": "unique@example.com",
            "password": "Password123!",
            "password_confirm": "Password123!",
        }
        response = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

    def test_duplicate_email_rejected(self):
        User.objects.create_user(
            username="someuser",
            email="existing@example.com",
            password="Password123!",
        )

        payload = {
            "username": "newuser",
            "email": "Existing@Example.COM",  # case-insensitive check
            "password": "Password123!",
            "password_confirm": "Password123!",
        }
        response = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_password_confirmation_mismatch_rejected(self):
        payload = {
            "username": "mismatchuser",
            "email": "mismatch@example.com",
            "password": "Password123!",
            "password_confirm": "DifferentPassword123!",
        }
        response = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password_confirm", response.data)

    def test_weak_password_rejected(self):
        payload = {
            "username": "weakuser",
            "email": "weak@example.com",
            "password": "123",
            "password_confirm": "123",
        }
        response = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_anti_escalation_role_injection_rejected(self):
        privileged_attempts = [
            {"role": "SUPER_ADMINISTRATOR"},
            {"roles": ["ADMINISTRATOR", "SUPER_ADMINISTRATOR"]},
            {"permissions": ["*"]},
            {"is_staff": True},
            {"is_superuser": True},
        ]
        for attempt in privileged_attempts:
            payload = {
                "username": f"hacker_{list(attempt.keys())[0]}",
                "email": f"hacker_{list(attempt.keys())[0]}@example.com",
                "password": "Password123!",
                "password_confirm": "Password123!",
                **attempt,
            }
            response = self.client.post("/api/auth/register/", payload, format="json")
            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Attempt with {attempt} was not rejected!",
            )
            # Ensure user was not created
            self.assertFalse(
                User.objects.filter(username=payload["username"]).exists()
            )

    def test_login_works_immediately_after_registration(self):
        payload = {
            "username": "newcustomer",
            "email": "newcustomer@example.com",
            "password": "CustomerPassword123!",
            "password_confirm": "CustomerPassword123!",
            "first_name": "Rahim",
            "last_name": "Karim",
        }
        reg_res = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(reg_res.status_code, status.HTTP_201_CREATED)

        # 1. Obtain JWT token
        token_res = self.client.post(
            "/api/auth/token/",
            {"username": "newcustomer", "password": "CustomerPassword123!"},
            format="json",
        )
        self.assertEqual(token_res.status_code, status.HTTP_200_OK)
        access_token = token_res.data["access"]
        self.assertTrue(access_token)

        # 2. Query /api/auth/me/
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
        me_res = self.client.get("/api/auth/me/")
        self.assertEqual(me_res.status_code, status.HTTP_200_OK)
        self.assertEqual(me_res.data["username"], "newcustomer")
        self.assertEqual(me_res.data["roles"], ["CUSTOMER"])
        self.assertFalse(me_res.data["is_staff"])
        self.assertFalse(me_res.data["is_superuser"])

        # Customer permissions check
        expected_perms = {"cart.view", "cart.update", "orders.view", "orders.create", "profile.view"}
        user_perms = set(me_res.data["permissions"])
        for perm in expected_perms:
            self.assertIn(perm, user_perms)

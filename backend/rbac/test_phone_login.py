from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework import serializers, status
from rest_framework.test import APIClient

from .models import LoginPhone, Role
from .phone import normalize_phone
from .serializers import create_login_phone
from .services import get_user_role_codes

User = get_user_model()

REGISTER_URL = "/api/auth/register/"
TOKEN_URL = "/api/auth/token/"
ME_URL = "/api/auth/me/"
PASSWORD = "Shapla-Pass-123"


class NormalizePhoneTests(SimpleTestCase):
    def test_usual_spellings_give_one_number(self):
        for spelling in (
            "01712345678",
            "8801712345678",
            "+8801712345678",
            "+880 1712 345678",
            "01712-345678",
            " (017) 1234.5678 ",
            "০১৭১২৩৪৫৬৭৮",
        ):
            with self.subTest(spelling=spelling):
                self.assertEqual(normalize_phone(spelling), "+8801712345678")

    def test_every_operator_prefix_is_accepted(self):
        for prefix in "3456789":
            with self.subTest(prefix=prefix):
                self.assertEqual(normalize_phone(f"01{prefix}12345678"), f"+8801{prefix}12345678")

    def test_other_values_are_not_numbers(self):
        for value in (
            "",
            "johndoe",
            "01212345678",  # no such operator
            "0171234567",  # one digit short
            "017123456789",  # one digit long
            "+4401712345678",
            "0171234567a",
            "+88+01712345678",
            None,
            1712345678,
        ):
            with self.subTest(value=value):
                self.assertIsNone(normalize_phone(value))


class PhoneRegistrationTests(TestCase):
    """POST /api/auth/register/ with a mobile number instead of, or beside, an email."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())

    def setUp(self):
        self.client = APIClient()

    def register(self, **fields):
        payload = {"username": "rahim", "password": PASSWORD, "password_confirm": PASSWORD, **fields}
        return self.client.post(REGISTER_URL, payload, format="json")

    def test_phone_only_registration(self):
        response = self.register(phone="01712-345678", first_name="Rahim")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["phone"], "+8801712345678")
        self.assertEqual(response.data["email"], "")

        user = User.objects.get(username="rahim")
        self.assertEqual(user.email, "")
        self.assertEqual(user.login_phone.number, "+8801712345678")
        # No SMS provider yet, so nothing has verified the number.
        self.assertIsNone(user.login_phone.verified_at)
        self.assertEqual(get_user_role_codes(user), {Role.ROLE_CUSTOMER})
        self.assertEqual(user.customer_profile.phone, "01712345678")

    def test_email_only_registration_has_no_login_phone(self):
        response = self.register(email="rahim@example.com")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIsNone(response.data["phone"])
        self.assertFalse(LoginPhone.objects.exists())
        self.assertEqual(User.objects.get(username="rahim").customer_profile.phone, "")

    def test_email_and_phone_together(self):
        response = self.register(email="rahim@example.com", phone="01812345678")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        user = User.objects.get(username="rahim")
        self.assertEqual(user.email, "rahim@example.com")
        self.assertEqual(user.login_phone.number, "+8801812345678")

    def test_neither_email_nor_phone_is_refused(self):
        response = self.register(email="", phone="  ")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.data)
        self.assertFalse(User.objects.filter(username="rahim").exists())

    def test_invalid_phone_is_refused(self):
        response = self.register(phone="01212345678")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)

    def test_number_taken_in_another_spelling_is_refused(self):
        self.assertEqual(self.register(phone="01712345678").status_code, status.HTTP_201_CREATED)
        response = self.register(username="karim", phone="+880 1712 345678")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone", response.data)
        self.assertFalse(User.objects.filter(username="karim").exists())

    def test_two_phone_only_accounts_share_the_blank_email(self):
        self.assertEqual(self.register(phone="01712345678").status_code, status.HTTP_201_CREATED)
        response = self.register(username="karim", phone="01912345678")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_username_that_reads_as_a_number_is_refused(self):
        response = self.register(username="01712345678", email="rahim@example.com")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("username", response.data)

    def test_number_taken_after_the_check_is_a_400(self):
        # A concurrent registration can claim the number between the
        # serializer's check and the insert.
        owner = User.objects.create_user(username="owner", password=PASSWORD)
        LoginPhone.objects.create(user=owner, number="+8801712345678")
        racer = User.objects.create_user(username="racer", password=PASSWORD)
        with self.assertRaises(serializers.ValidationError) as caught:
            create_login_phone(racer, "+8801712345678")
        self.assertIn("phone", caught.exception.detail)


class PhoneSignInTests(TestCase):
    """POST /api/auth/token/ with a login phone number in the username field."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="rahim", password=PASSWORD)
        LoginPhone.objects.create(user=cls.user, number="+8801712345678")

    def setUp(self):
        self.client = APIClient()

    def sign_in(self, username, password=PASSWORD):
        return self.client.post(TOKEN_URL, {"username": username, "password": password}, format="json")

    def test_any_spelling_of_the_number_signs_in(self):
        for spelling in ("01712345678", "+8801712345678", "01712-345678", "০১৭১২৩৪৫৬৭৮"):
            with self.subTest(spelling=spelling):
                response = self.sign_in(spelling)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
                me = self.client.get(ME_URL)
                self.client.credentials()
                self.assertEqual(me.data["username"], "rahim")
                self.assertEqual(me.data["phone"], "+8801712345678")

    def test_the_username_still_signs_in(self):
        self.assertEqual(self.sign_in("rahim").status_code, status.HTTP_200_OK)

    def test_wrong_password_is_refused(self):
        self.assertEqual(self.sign_in("01712345678", "Wrong-Pass-123").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unknown_number_is_refused(self):
        self.assertEqual(self.sign_in("01912345678").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_account_is_refused(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(self.sign_in("01712345678").status_code, status.HTTP_401_UNAUTHORIZED)

    def test_account_without_a_phone_reports_none(self):
        User.objects.create_user(username="karim", password=PASSWORD)
        token = self.sign_in("karim").data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertIsNone(self.client.get(ME_URL).data["phone"])

    def test_username_that_reads_as_the_number_does_not_block_its_owner(self):
        # Usernames like this predate the registration check. Each account
        # still signs in with its own password.
        User.objects.create_user(username="01712345678", password="Other-Pass-456")
        self.assertEqual(self.sign_in("01712345678", "Other-Pass-456").status_code, status.HTTP_200_OK)
        response = self.sign_in("01712345678")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        self.assertEqual(self.client.get(ME_URL).data["username"], "rahim")


class LoginPhoneAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(username="root", password=PASSWORD)
        user = User.objects.create_user(username="rahim", password=PASSWORD)
        cls.login_phone = LoginPhone.objects.create(user=user, number="+8801712345678")

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_user_list_finds_an_account_by_its_number(self):
        response = self.client.get("/admin/auth/user/", {"q": "01712345678"})
        self.assertContains(response, "rahim")

    def test_numbers_cannot_be_added_or_edited_in_the_admin(self):
        self.assertEqual(self.client.get("/admin/rbac/loginphone/add/").status_code, 403)
        response = self.client.post(
            f"/admin/rbac/loginphone/{self.login_phone.pk}/change/",
            {"number": "+8801912345678"},
        )
        self.assertEqual(response.status_code, 403)
        self.login_phone.refresh_from_db()
        self.assertEqual(self.login_phone.number, "+8801712345678")

"""Token revocation, rate limits and password policy (BUG-013, BUG-014)."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()

PASSWORD = "Kolapata-Leaf-2026"
NEW_PASSWORD = "Shapla-Pond-7781"

TOKEN_URL = "/api/auth/token/"
REFRESH_URL = "/api/auth/token/refresh/"
LOGOUT_URL = "/api/auth/logout/"
ME_URL = "/api/auth/me/"
CHANGE_PASSWORD_URL = "/api/auth/change-password/"
REGISTER_URL = "/api/auth/register/"
ADMIN_LOGIN_URL = "/admin/login/"


def low_rates(**rates):
    """AUTH_THROTTLE_RATES with every scope effectively unlimited except ``rates``."""
    values = {
        "auth_token": "1000/min",
        "auth_refresh": "1000/min",
        "auth_register": "1000/min",
        "auth_password": "1000/min",
    }
    values.update(rates)
    return override_settings(AUTH_THROTTLE_RATES=values)


class TokenTestCase(TestCase):
    def setUp(self):
        cache.clear()  # throttle counts live in the cache
        self.addCleanup(cache.clear)
        self.client = APIClient()
        self.user = User.objects.create_user(username="token_user", email="token_user@example.com", password=PASSWORD)

    def obtain(self, password=PASSWORD):
        response = self.client.post(TOKEN_URL, {"username": "token_user", "password": password}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        return response.data["access"], response.data["refresh"]

    def me(self, access):
        return self.client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {access}")

    def refresh(self, refresh):
        return self.client.post(REFRESH_URL, {"refresh": refresh}, format="json")


class RefreshRotationTests(TokenTestCase):
    def test_rotated_refresh_token_is_rejected_on_reuse(self):
        _, refresh = self.obtain()

        first = self.refresh(refresh)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertNotEqual(first.data["refresh"], refresh)

        reuse = self.refresh(refresh)
        self.assertEqual(reuse.status_code, status.HTTP_401_UNAUTHORIZED)

        # The token it was rotated into still works.
        self.assertEqual(self.refresh(first.data["refresh"]).status_code, status.HTTP_200_OK)

    def test_refresh_token_of_deleted_user_is_rejected(self):
        _, refresh = self.obtain()
        self.user.delete()
        self.assertEqual(self.refresh(refresh).status_code, status.HTTP_401_UNAUTHORIZED)


class LogoutTests(TokenTestCase):
    def test_logout_blacklists_the_refresh_token(self):
        _, refresh = self.obtain()

        response = self.client.post(LOGOUT_URL, {"refresh": refresh}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(self.refresh(refresh).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_needs_no_access_token(self):
        _, refresh = self.obtain()
        self.client.credentials()  # nothing in Authorization
        response = self.client.post(LOGOUT_URL, {"refresh": refresh}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_logout_rejects_a_bad_token(self):
        response = self.client.post(LOGOUT_URL, {"refresh": "not-a-token"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordChangeRevocationTests(TokenTestCase):
    def change_password(self, access):
        return self.client.post(
            CHANGE_PASSWORD_URL,
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )

    def test_password_change_revokes_old_tokens_and_returns_a_new_pair(self):
        other_access, other_refresh = self.obtain()  # another device
        access, refresh = self.obtain()

        response = self.change_password(access)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)

        for old_access in (access, other_access):
            self.assertEqual(self.me(old_access).status_code, status.HTTP_401_UNAUTHORIZED)
        for old_refresh in (refresh, other_refresh):
            self.assertEqual(self.refresh(old_refresh).status_code, status.HTTP_401_UNAUTHORIZED)

        # The device that made the change stays signed in with the new pair.
        self.assertEqual(self.me(response.data["access"]).status_code, status.HTTP_200_OK)
        self.assertEqual(self.refresh(response.data["refresh"]).status_code, status.HTTP_200_OK)

    def test_password_set_anywhere_else_revokes_tokens_too(self):
        """The Django admin and management commands save through set_password."""
        access, refresh = self.obtain()
        self.user.set_password(NEW_PASSWORD)
        self.user.save()

        self.assertEqual(self.me(access).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.refresh(refresh).status_code, status.HTTP_401_UNAUTHORIZED)
        self.obtain(password=NEW_PASSWORD)


class SeededTokenTestCase(TokenTestCase):
    """Registration assigns the CUSTOMER role, which seed_rbac creates."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_rbac", stdout=StringIO())


class PasswordPolicyTests(SeededTokenTestCase):
    def register(self, password, username="policy_user"):
        return self.client.post(
            REGISTER_URL,
            {
                "username": username,
                "email": f"{username}@example.com",
                "password": password,
                "password_confirm": password,
            },
            format="json",
        )

    def test_weak_passwords_are_rejected(self):
        for password in ("Ab1!xyz", "password123", "12345678901", "policy_user99"):
            with self.subTest(password=password):
                response = self.register(password)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn("password", response.data)

    def test_reasonable_password_is_accepted(self):
        self.assertEqual(self.register(NEW_PASSWORD).status_code, status.HTTP_201_CREATED)

    def test_password_change_applies_the_policy(self):
        access, _ = self.obtain()
        response = self.client.post(
            CHANGE_PASSWORD_URL,
            {"current_password": PASSWORD, "new_password": "short", "new_password_confirm": "short"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password", response.data)


class AuthThrottleTests(SeededTokenTestCase):
    def test_failed_logins_are_throttled(self):
        with low_rates(auth_token="3/min"):
            for _ in range(3):
                response = self.client.post(TOKEN_URL, {"username": "token_user", "password": "wrong"}, format="json")
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

            response = self.client.post(TOKEN_URL, {"username": "token_user", "password": PASSWORD}, format="json")
            self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
            self.assertIn("Retry-After", response)

    def test_spoofed_forwarded_for_does_not_reset_the_count(self):
        with low_rates(auth_token="2/min"):
            for n in range(2):
                self.client.post(
                    TOKEN_URL, {"username": "token_user", "password": "wrong"}, format="json",
                    HTTP_X_FORWARDED_FOR=f"10.0.0.{n}",
                )
            response = self.client.post(
                TOKEN_URL, {"username": "token_user", "password": "wrong"}, format="json",
                HTTP_X_FORWARDED_FOR="10.0.0.99",
            )
            self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_refresh_is_throttled(self):
        _, refresh = self.obtain()
        with low_rates(auth_refresh="1/min"):
            first = self.refresh(refresh)
            self.assertEqual(first.status_code, status.HTTP_200_OK)
            self.assertEqual(self.refresh(first.data["refresh"]).status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_registration_is_throttled(self):
        with low_rates(auth_register="1/min"):
            payload = {"username": "throttle_new", "email": "throttle_new@example.com",
                       "password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD}
            self.assertEqual(self.client.post(REGISTER_URL, payload, format="json").status_code, status.HTTP_201_CREATED)
            payload.update(username="throttle_new2", email="throttle_new2@example.com")
            self.assertEqual(
                self.client.post(REGISTER_URL, payload, format="json").status_code,
                status.HTTP_429_TOO_MANY_REQUESTS,
            )

    def test_password_change_is_throttled_per_user(self):
        access, _ = self.obtain()
        bad = {"current_password": "wrong", "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD}
        with low_rates(auth_password="2/min"):
            for _ in range(2):
                response = self.client.post(CHANGE_PASSWORD_URL, bad, format="json", HTTP_AUTHORIZATION=f"Bearer {access}")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            response = self.client.post(CHANGE_PASSWORD_URL, bad, format="json", HTTP_AUTHORIZATION=f"Bearer {access}")
            self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


@override_settings(ADMIN_LOGIN_FAILURE_LIMIT=3, ADMIN_LOGIN_FAILURE_WINDOW_SECONDS=600)
class AdminLoginLockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        User.objects.create_user(username="staff_member", password=PASSWORD, is_staff=True)

    def post(self, password):
        return self.client.post(ADMIN_LOGIN_URL, {"username": "staff_member", "password": password, "next": "/admin/"})

    def test_lockout_after_repeated_failures(self):
        for _ in range(3):
            self.assertEqual(self.post("wrong").status_code, 200)

        # Locked: even the right password is not checked.
        response = self.post(PASSWORD)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "600")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_successful_login_below_the_limit(self):
        self.assertEqual(self.post("wrong").status_code, 200)
        response = self.post(PASSWORD)
        self.assertEqual(response.status_code, 302)

    def test_viewing_the_form_is_never_locked(self):
        for _ in range(3):
            self.post("wrong")
        self.assertEqual(self.client.get(ADMIN_LOGIN_URL).status_code, 200)

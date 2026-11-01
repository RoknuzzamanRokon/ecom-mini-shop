"""
An account still on the password someone else set (rbac.StartingPassword)
reaches nothing but the password change (docs/SALES_TEAM_EDITS_PAYOUTS_PLAN.md §4).
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from .authentication import STARTING_PASSWORD_CLAIM
from .models import StartingPassword

User = get_user_model()

PASSWORD = "Set-By-Onboarder-11"
OWN_PASSWORD = "Chosen-By-Owner-2026"


class StartingPasswordTests(TestCase):
    def setUp(self):
        cache.clear()  # throttle counts live in the cache
        self.addCleanup(cache.clear)
        self.client = APIClient()
        self.onboarder = User.objects.create_user(username="sp_onboarder", password="Onboarder-Pass-1")
        self.owner = User.objects.create_user(username="sp_owner", password=PASSWORD)
        StartingPassword.objects.create(user=self.owner, set_by=self.onboarder)

    def sign_in(self, password=PASSWORD):
        response = self.client.post("/api/auth/token/", {"username": "sp_owner", "password": password}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def get(self, url, access):
        return self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {access}")

    def change(self, access, new=OWN_PASSWORD, current=PASSWORD):
        return self.client.post(
            "/api/auth/change-password/",
            {"current_password": current, "new_password": new, "new_password_confirm": new},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {access}",
        )

    def test_the_api_answers_only_the_password_change(self):
        tokens = self.sign_in()
        self.assertTrue(AccessToken(tokens["access"]).payload[STARTING_PASSWORD_CLAIM])
        me = self.get("/api/auth/me/", tokens["access"])
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertTrue(me.data["must_change_password"])

        for url in ("/api/notifications/", "/api/notifications/unread-count/?audience=CUSTOMER", "/api/onboarding/me/"):
            with self.subTest(url=url):
                response = self.get(url, tokens["access"])
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(response.data["code"], "password_change_required")

        # A refreshed token carries the mark on.
        refreshed = self.client.post("/api/auth/token/refresh/", {"refresh": tokens["refresh"]}, format="json").data
        self.assertEqual(self.get("/api/notifications/unread-count/?audience=CUSTOMER", refreshed["access"]).status_code, status.HTTP_403_FORBIDDEN)

    def test_choosing_a_password_frees_the_account(self):
        tokens = self.sign_in()
        response = self.change(tokens["access"])
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIsNotNone(StartingPassword.objects.get(user=self.owner).replaced_at)

        self.assertEqual(self.get("/api/notifications/unread-count/?audience=CUSTOMER", response.data["access"]).status_code, status.HTTP_200_OK)
        self.assertFalse(self.get("/api/auth/me/", response.data["access"]).data["must_change_password"])
        # The marked tokens died with the old password.
        self.assertEqual(self.get("/api/auth/me/", tokens["access"]).status_code, status.HTTP_401_UNAUTHORIZED)
        # A new sign-in is unmarked.
        fresh = self.sign_in(OWN_PASSWORD)
        self.assertEqual(self.get("/api/notifications/unread-count/?audience=CUSTOMER", fresh["access"]).status_code, status.HTTP_200_OK)

    def test_the_same_password_again_is_refused(self):
        tokens = self.sign_in()
        response = self.change(tokens["access"], new=PASSWORD)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("different from your current one", str(response.data["new_password"]))
        self.assertIsNone(StartingPassword.objects.get(user=self.owner).replaced_at)

    def test_other_accounts_are_untouched(self):
        response = self.client.post(
            "/api/auth/token/", {"username": "sp_onboarder", "password": "Onboarder-Pass-1"}, format="json"
        )
        self.assertNotIn(STARTING_PASSWORD_CLAIM, AccessToken(response.data["access"]).payload)
        self.assertEqual(self.get("/api/notifications/unread-count/?audience=CUSTOMER", response.data["access"]).status_code, status.HTTP_200_OK)
        self.assertFalse(self.get("/api/auth/me/", response.data["access"]).data["must_change_password"])

    def test_logout_works_with_a_marked_token(self):
        tokens = self.sign_in()
        response = self.client.post("/api/auth/logout/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

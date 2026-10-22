"""The settings modules themselves: secrets, production posture, WSGI entry point.

A settings module can only be loaded once per process, so every module other
than the one running this suite is exercised in a child interpreter.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.utils import get_random_secret_key
from django.test import SimpleTestCase
from rest_framework_simplejwt.settings import api_settings as jwt_settings

BACKEND_DIR = Path(__file__).resolve().parent.parent

PRINT_SETTINGS = """
import json
import django
from django.conf import settings
django.setup()
print(json.dumps({
    "DEBUG": settings.DEBUG,
    "ALLOWED_HOSTS": settings.ALLOWED_HOSTS,
    "CORS_ALLOWED_ORIGINS": settings.CORS_ALLOWED_ORIGINS,
    "SESSION_COOKIE_SECURE": settings.SESSION_COOKIE_SECURE,
    "CSRF_COOKIE_SECURE": settings.CSRF_COOKIE_SECURE,
    "SECURE_SSL_REDIRECT": settings.SECURE_SSL_REDIRECT,
    "SECURE_HSTS_SECONDS": settings.SECURE_HSTS_SECONDS,
    "SECURE_PROXY_SSL_HEADER": settings.SECURE_PROXY_SSL_HEADER,
    "SECRET_KEY": settings.SECRET_KEY,
    "SIGNING_KEY": settings.SIMPLE_JWT["SIGNING_KEY"],
    "PASSWORD_VALIDATORS": [v["NAME"].rsplit(".", 1)[1] for v in settings.AUTH_PASSWORD_VALIDATORS],
}))
"""


def child_env(**overrides):
    """The current environment with a settings module of the caller's choosing.

    An empty string blocks the matching backend/.env line: base.py only fills
    variables that are not already set.
    """
    env = {key: value for key, value in os.environ.items() if key != "DJANGO_SETTINGS_MODULE"}
    env.update(
        DATABASE_URL="mysql://user:pass@127.0.0.1:3306/settings_test",  # never connected to
        DJANGO_SECRET_KEY="",
        DJANGO_JWT_SIGNING_KEY="",
    )
    env.update(overrides)
    return env


def prod_env(**overrides):
    values = dict(
        DJANGO_SETTINGS_MODULE="config.settings.prod",
        DJANGO_SECRET_KEY=get_random_secret_key(),
        DJANGO_JWT_SIGNING_KEY=get_random_secret_key(),
        DJANGO_ALLOWED_HOSTS="api.example.com, admin.example.com",
        DJANGO_CORS_ALLOWED_ORIGINS="https://shop.example.com",
    )
    values.update(overrides)
    return child_env(**values)


def run_python(args, env):
    return subprocess.run(
        [sys.executable, *args], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120
    )


class ProdSettingsTests(SimpleTestCase):
    def load(self, env):
        result = run_python(["-c", PRINT_SETTINGS], env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def assertRefusesToStart(self, env, message):
        result = run_python(["-c", PRINT_SETTINGS], env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ImproperlyConfigured", result.stderr)
        self.assertIn(message, result.stderr)

    def test_production_posture(self):
        env = prod_env()
        values = self.load(env)

        self.assertIs(values["DEBUG"], False)
        self.assertIs(values["SESSION_COOKIE_SECURE"], True)
        self.assertIs(values["CSRF_COOKIE_SECURE"], True)
        self.assertIs(values["SECURE_SSL_REDIRECT"], True)
        self.assertGreater(values["SECURE_HSTS_SECONDS"], 0)
        self.assertIsNone(values["SECURE_PROXY_SSL_HEADER"])
        self.assertEqual(values["ALLOWED_HOSTS"], ["api.example.com", "admin.example.com"])
        self.assertEqual(values["CORS_ALLOWED_ORIGINS"], ["https://shop.example.com"])
        self.assertEqual(values["SECRET_KEY"], env["DJANGO_SECRET_KEY"])
        self.assertEqual(values["SIGNING_KEY"], env["DJANGO_JWT_SIGNING_KEY"])
        self.assertEqual(
            values["PASSWORD_VALIDATORS"],
            [
                "UserAttributeSimilarityValidator",
                "MinimumLengthValidator",
                "CommonPasswordValidator",
                "NumericPasswordValidator",
            ],
        )

    def test_proxy_header_is_opt_in(self):
        values = self.load(prod_env(DJANGO_BEHIND_TLS_PROXY="true"))
        self.assertEqual(values["SECURE_PROXY_SSL_HEADER"], ["HTTP_X_FORWARDED_PROTO", "https"])

    def test_deploy_check_reports_nothing(self):
        result = run_python(["manage.py", "check", "--deploy", "--fail-level", "WARNING"], prod_env())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no issues", result.stdout)

    def test_refuses_missing_secret_key(self):
        self.assertRefusesToStart(prod_env(DJANGO_SECRET_KEY=""), "DJANGO_SECRET_KEY")

    def test_refuses_missing_jwt_signing_key(self):
        self.assertRefusesToStart(prod_env(DJANGO_JWT_SIGNING_KEY=""), "DJANGO_JWT_SIGNING_KEY")

    def test_refuses_one_key_for_both_jobs(self):
        key = get_random_secret_key()
        self.assertRefusesToStart(
            prod_env(DJANGO_SECRET_KEY=key, DJANGO_JWT_SIGNING_KEY=key), "must differ"
        )

    def test_refuses_weak_keys(self):
        self.assertRefusesToStart(prod_env(DJANGO_JWT_SIGNING_KEY="short"), "at least 50 characters")
        self.assertRefusesToStart(
            prod_env(DJANGO_SECRET_KEY="django-insecure-" + get_random_secret_key()),
            "at least 50 characters",
        )

    def test_refuses_missing_hosts_and_origins(self):
        self.assertRefusesToStart(prod_env(DJANGO_ALLOWED_HOSTS=" , "), "DJANGO_ALLOWED_HOSTS")
        self.assertRefusesToStart(prod_env(DJANGO_CORS_ALLOWED_ORIGINS=""), "DJANGO_CORS_ALLOWED_ORIGINS")


class DevSettingsTests(SimpleTestCase):
    def test_dev_refuses_to_start_without_keys(self):
        result = run_python(["-c", PRINT_SETTINGS], child_env(DJANGO_SETTINGS_MODULE="config.settings.dev"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY and DJANGO_JWT_SIGNING_KEY", result.stderr)


class EntryPointTests(SimpleTestCase):
    def test_wsgi_and_asgi_require_a_settings_module(self):
        for module in ("config.wsgi", "config.asgi"):
            with self.subTest(module=module):
                result = run_python(["-c", f"import {module}"], child_env())
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Set DJANGO_SETTINGS_MODULE", result.stderr)


class RunningSuiteKeyTests(SimpleTestCase):
    def test_jwt_tokens_are_not_signed_with_the_secret_key(self):
        self.assertTrue(settings.SECRET_KEY)
        self.assertTrue(jwt_settings.SIGNING_KEY)
        self.assertEqual(jwt_settings.SIGNING_KEY, settings.SIMPLE_JWT["SIGNING_KEY"])
        self.assertNotEqual(jwt_settings.SIGNING_KEY, settings.SECRET_KEY)

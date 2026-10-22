"""Production settings: any instance reachable by someone other than its developer.

Serve ``config.wsgi:application`` (or ``config.asgi``) with
``DJANGO_SETTINGS_MODULE=config.settings.prod``.

Everything environment-specific comes from the environment (``backend/.env``
is still read, but real environment variables win):

* ``DATABASE_URL`` — MySQL 8, as everywhere else.
* ``DJANGO_SECRET_KEY`` and ``DJANGO_JWT_SIGNING_KEY`` — two different values,
  at least 50 characters each.
* ``DJANGO_ALLOWED_HOSTS`` — comma-separated host names.
* ``DJANGO_CORS_ALLOWED_ORIGINS`` — comma-separated origins of the storefront,
  for example ``https://shop.example.com``.
* ``DJANGO_CSRF_TRUSTED_ORIGINS`` — optional, comma-separated origins.
* ``DJANGO_BEHIND_TLS_PROXY`` — ``true`` when a proxy terminates HTTPS and sets
  ``X-Forwarded-Proto``. Only set it when the proxy overwrites that header;
  otherwise a client could claim HTTPS on a plain connection.
* ``DJANGO_SECURE_HSTS_SECONDS`` — optional, defaults to one year.

Missing values stop the process at startup rather than falling back to a
development default. ``manage.py check --deploy --settings=config.settings.prod``
must report no issues.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import JWT_SIGNING_KEY_ENV, require_secret_keys


def _env_list(name, *, required):
    """Split a comma-separated variable, dropping blanks."""
    values = [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]
    if required and not values:
        raise ImproperlyConfigured(f"{__name__} needs {name} (comma-separated).")
    return values


def _env_bool(name, default):
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


DEBUG = False

# --- Secrets ----------------------------------------------------------------
# Django's deploy check wants 50+ characters for SECRET_KEY; the JWT key signs
# every API token, so it is held to the same bar.
require_secret_keys(SECRET_KEY, SIMPLE_JWT["SIGNING_KEY"], __name__)  # noqa: F405
for _name, _value in (("DJANGO_SECRET_KEY", SECRET_KEY), (JWT_SIGNING_KEY_ENV, SIMPLE_JWT["SIGNING_KEY"])):  # noqa: F405
    if len(_value) < 50 or _value.startswith("django-insecure-"):
        raise ImproperlyConfigured(
            f"{_name} must be at least 50 characters and must not be a generated "
            "'django-insecure-' development key."
        )

# --- Hosts and origins -------------------------------------------------------
ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", required=True)
CORS_ALLOWED_ORIGINS = _env_list("DJANGO_CORS_ALLOWED_ORIGINS", required=True)
CSRF_TRUSTED_ORIGINS = _env_list("DJANGO_CSRF_TRUSTED_ORIGINS", required=False)

# --- HTTPS -------------------------------------------------------------------
SECURE_SSL_REDIRECT = True
if _env_bool("DJANGO_BEHIND_TLS_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS") or 60 * 60 * 24 * 365)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

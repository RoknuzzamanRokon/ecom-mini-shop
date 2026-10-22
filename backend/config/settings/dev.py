"""Local development settings.

These are the values ``config/settings.py`` carried before the split, so
``manage.py runserver`` behaves exactly as it did, except that the secret keys
now come from ``backend/.env`` (see "Secrets" in :mod:`config.settings.base`).
"""

import os

from .base import *  # noqa: F401,F403
from .base import require_secret_keys

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# No fallback key: a made-up one would change on every autoreload and log
# everyone out, and a fixed one would be a committed secret again.
require_secret_keys(SECRET_KEY, SIMPLE_JWT["SIGNING_KEY"], __name__)  # noqa: F405

ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

# Print emails instead of sending them, until real SMTP settings are given
# (set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend and the
# EMAIL_* variables in backend/.env).
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

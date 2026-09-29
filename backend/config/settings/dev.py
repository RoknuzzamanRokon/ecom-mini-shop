"""Local development settings.

These are the values ``config/settings.py`` carried before the split, so
``manage.py runserver`` behaves exactly as it did.
"""

import os

from .base import *  # noqa: F401,F403

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

# Print emails instead of sending them, until real SMTP settings are given
# (set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend and the
# EMAIL_* variables in backend/.env).
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

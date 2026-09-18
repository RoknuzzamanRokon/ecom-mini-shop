"""Local development settings.

These are the values ``config/settings.py`` carried before the split, so
``manage.py runserver`` behaves exactly as it did.
"""

from .base import *  # noqa: F401,F403

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

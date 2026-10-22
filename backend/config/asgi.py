"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.exceptions import ImproperlyConfigured
from django.core.asgi import get_asgi_application

# No default: a server started without a settings module must not quietly come
# up as dev, with DEBUG on. manage.py still defaults to config.settings.dev.
if not os.environ.get('DJANGO_SETTINGS_MODULE'):
    raise ImproperlyConfigured(
        "Set DJANGO_SETTINGS_MODULE: config.settings.prod for a deployment, "
        "config.settings.dev on a developer machine."
    )

application = get_asgi_application()

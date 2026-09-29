"""
Notification settings: settings.NOTIFICATIONS over the defaults below, so a
test can override one key without restating the rest.

A leaf module: it imports only Django.
"""
from django.conf import settings

DEFAULTS = {
    "ROUTE_ON_COMMIT": True,
    "BATCH_SIZE": 50,
    "LEASE_SECONDS": 60,
    "BACKOFF_BASE_SECONDS": 30,
    "BACKOFF_CAP_SECONDS": 3600,
    "EVENT_MAX_ATTEMPTS": 5,
    "DELIVERY_MAX_ATTEMPTS": 8,
    "EMAIL_RATE_PER_SECOND": 10,
    "FROM_EMAIL": "MiniShop <no-reply@minishop.local>",
    "FANOUT_CAP": 500,
    "UNREAD_COUNT_RATE": "120/min",
}


def notification_setting(name):
    if name not in DEFAULTS:
        raise KeyError(f"Unknown NOTIFICATIONS setting '{name}'.")
    return getattr(settings, "NOTIFICATIONS", {}).get(name, DEFAULTS[name])

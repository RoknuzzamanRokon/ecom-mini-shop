"""Request limits on the authentication endpoints (BUG-014)."""

from django.conf import settings
from rest_framework.throttling import ScopedRateThrottle


class AuthRateThrottle(ScopedRateThrottle):
    """ScopedRateThrottle with its rates in ``settings.AUTH_THROTTLE_RATES``.

    The rate is looked up on every request rather than copied when DRF is
    imported, so ``override_settings`` reaches it (the same reason
    notifications' UnreadCountThrottle overrides ``get_rate``). Anonymous
    clients are counted per address, signed-in users per account.
    """

    def get_rate(self):
        return settings.AUTH_THROTTLE_RATES[self.scope]

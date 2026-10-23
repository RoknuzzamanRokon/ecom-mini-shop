"""Request helpers shared by audit-logging call sites."""

import ipaddress

from django.conf import settings


def get_client_ip(request):
    """
    The client's IP address, or None when there is no valid one.

    X-Forwarded-For is only read behind trusted proxies
    (settings.TRUSTED_PROXY_COUNT, the DJANGO_NUM_PROXIES variable). Each
    proxy appends the address it received from, so with N proxies the client
    is the Nth entry from the right; anything further left was written by
    the client and proves nothing. Without proxies, REMOTE_ADDR is the only
    honest source (BUG-015).

    The value is checked with `ipaddress`, so it always fits the audit
    column: a malformed or oversized value never reaches the database.
    """
    candidate = request.META.get("REMOTE_ADDR")
    proxies = getattr(settings, "TRUSTED_PROXY_COUNT", 0)
    if proxies > 0:
        hops = [hop.strip() for hop in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if hop.strip()]
        if hops:
            candidate = hops[-min(proxies, len(hops))]
    if not candidate:
        return None
    try:
        # An IPv6 zone ("fe80::1%eth0") is local detail, not part of the address.
        return str(ipaddress.ip_address(candidate.split("%", 1)[0]))
    except ValueError:
        return None

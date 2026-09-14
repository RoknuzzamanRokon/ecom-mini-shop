"""Request helpers shared by audit-logging call sites."""


def get_client_ip(request):
    """Best-effort client IP, honouring X-Forwarded-For's first hop."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')

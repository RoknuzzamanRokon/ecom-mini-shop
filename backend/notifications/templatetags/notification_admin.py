"""
The notification bell in the Django admin header (templates/admin/base_site.html).

It shows the signed-in person's STAFF inbox, the same one as the Console's
bell, and talks to the /api/notifications/ endpoints through the admin's own
session login (static/js/admin_notifications.js). Links open in the Console,
because every action_url is a path in the Next.js app.
"""
from django import template
from django.conf import settings
from django.urls import reverse

from notifications.models import Audience, Notification
from notifications.permissions import can_read_audience

register = template.Library()


@register.inclusion_tag("notifications/admin/bell.html", takes_context=True)
def admin_notification_bell(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    if user is None or not can_read_audience(user, Audience.STAFF):
        return {"show": False}

    unread = Notification.objects.filter(recipient=user, audience=Audience.STAFF, read_at__isnull=True).count()
    app_url = getattr(settings, "STOREFRONT_URL", "http://localhost:3000").rstrip("/")
    query = f"?audience={Audience.STAFF}"
    return {
        "show": True,
        "unread": unread,
        "badge": "99+" if unread > 99 else str(unread),
        "app_url": app_url,
        "inbox_url": f"{app_url}/admin/notifications",
        "list_url": reverse("notifications:inbox") + query,
        "count_url": reverse("notifications:unread-count") + query,
        "read_all_url": reverse("notifications:read-all") + query,
        # The script swaps the 0 for a notification's id.
        "read_url": reverse("notifications:mark-read", args=[0]),
    }

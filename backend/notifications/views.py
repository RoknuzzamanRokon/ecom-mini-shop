"""
The inbox and preferences API, under /api/notifications/ (docs/NOTIFICATION_SYSTEM.md §8).

Every query is filtered by recipient = request.user, so another person's
notification id is simply a 404 (§4.7). `audience` picks which surface's
notifications to show; asking for one you can't read is a 403.
"""
import base64
import binascii
from datetime import datetime

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from audit.services import AuditService
from audit.utils import get_client_ip

from .conf import notification_setting
from .models import Audience, Notification
from .permissions import can_read_audience, readable_audiences
from .preferences import (
    PreferenceError,
    apply_preference_changes,
    describe_preferences,
    parse_preference_changes,
)
from .serializers import NotificationSerializer

PAGE_SIZE = 20


def requested_audience(request, *, required=True):
    """The ?audience= value, checked against what the caller may read."""
    raw = (request.query_params.get("audience") or "").strip().upper()
    if not raw and not required:
        return None
    if raw not in Audience.values:
        raise ValidationError({"audience": f"Choose one of {', '.join(Audience.values)}."})
    if not can_read_audience(request.user, raw):
        raise PermissionDenied("You can't read that inbox.")
    return raw


def encode_cursor(notification):
    raw = f"{notification.occurred_at.isoformat()}|{notification.pk}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor):
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        occurred_at, pk = raw.rsplit("|", 1)
        return datetime.fromisoformat(occurred_at), int(pk)
    except (ValueError, UnicodeDecodeError, binascii.Error):
        raise ValidationError({"cursor": "That page link is invalid."}) from None


class UnreadCountThrottle(UserRateThrottle):
    """The bell polls this endpoint, so it's the one that gets a per-user limit."""

    scope = "notifications_unread"

    def get_rate(self):
        return notification_setting("UNREAD_COUNT_RATE")


class InboxView(APIView):
    """GET /api/notifications/?audience=…&unread=1&cursor=… — newest first, 20 a page."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        audience = requested_audience(request)
        rows = Notification.objects.filter(recipient=request.user, audience=audience)
        if request.query_params.get("unread") in ("1", "true"):
            rows = rows.filter(read_at__isnull=True)
        cursor = request.query_params.get("cursor")
        if cursor:
            occurred_at, pk = decode_cursor(cursor)
            # Keyset pagination on (occurred_at, id), never OFFSET (§10).
            rows = rows.filter(Q(occurred_at__lt=occurred_at) | Q(occurred_at=occurred_at, pk__lt=pk))
        page = list(rows.order_by("-occurred_at", "-id")[: PAGE_SIZE + 1])
        more = len(page) > PAGE_SIZE
        page = page[:PAGE_SIZE]
        return Response({
            "results": NotificationSerializer(page, many=True).data,
            "next_cursor": encode_cursor(page[-1]) if more else None,
        })


class UnreadCountView(APIView):
    """GET /api/notifications/unread-count/?audience=… — the bell's badge."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [UnreadCountThrottle]

    def get(self, request):
        audience = requested_audience(request)
        unread = Notification.objects.filter(
            recipient=request.user, audience=audience, read_at__isnull=True
        ).count()
        return Response({"unread": unread})


class MarkReadView(APIView):
    """POST /api/notifications/<id>/read/ — 204, or 404 if it isn't yours."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        if notification.read_at is None:
            Notification.objects.filter(pk=notification.pk, read_at__isnull=True).update(read_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReadAllView(APIView):
    """POST /api/notifications/read-all/?audience=… — marks that inbox read."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        audience = requested_audience(request)
        updated = Notification.objects.filter(
            recipient=request.user, audience=audience, read_at__isnull=True
        ).update(read_at=timezone.now())
        return Response({"updated": updated})


class PreferencesView(APIView):
    """
    GET /api/notifications/preferences/[?audience=…] — the category × channel
    toggles for every category that reaches you (or one audience's).
    PUT — change some of them; the body has the same shape. Switching off a
    locked channel is a 400. Changes are audited.
    """

    permission_classes = [IsAuthenticated]

    def audiences(self, request):
        audience = requested_audience(request, required=False)
        return [audience] if audience else readable_audiences(request.user)

    def get(self, request):
        return Response(describe_preferences(request.user, self.audiences(request)))

    def put(self, request):
        audiences = self.audiences(request)
        try:
            changes = parse_preference_changes(request.data, audiences)
        except PreferenceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            changed = apply_preference_changes(request.user, changes)
            if changed:
                AuditService.log(
                    action="NOTIFICATION_PREFERENCES_UPDATED",
                    target=request.user,
                    actor=request.user,
                    previous_state={f"{code}.{channel.lower()}": before for (code, channel), (before, _) in changed.items()},
                    new_state={f"{code}.{channel.lower()}": after for (code, channel), (_, after) in changed.items()},
                    ip_address=get_client_ip(request),
                )
        return Response(describe_preferences(request.user, audiences))

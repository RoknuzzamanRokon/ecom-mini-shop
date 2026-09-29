"""
Notification storage (docs/NOTIFICATION_SYSTEM.md §6).

A leaf module, like `audit`: it imports nothing from another project app, so
every domain app can import `notifications.publisher` (which imports only this
module and the registries) without an import cycle. Users are referenced
through settings.AUTH_USER_MODEL. `notifications/tests/test_leaf_imports.py`
enforces the rule.

Event types and categories are plain strings validated against the registries
in `events.py` and `categories.py`, not model choices, so adding one never
needs a migration.
"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Audience(models.TextChoices):
    """Which surface shows a notification (§4.7)."""

    CUSTOMER = "CUSTOMER", "Customer"
    SELLER = "SELLER", "Seller"
    STAFF = "STAFF", "Staff"


class Channel(models.TextChoices):
    """
    Where a notification reaches someone. IN_APP is the inbox row itself; every
    other channel is an external send with one NotificationDelivery row. SMS and
    PUSH are reserved (§3 D1) and get a value here once they have an adapter.
    """

    IN_APP = "IN_APP", "In-app"
    EMAIL = "EMAIL", "Email"


class Priority(models.TextChoices):
    NORMAL = "NORMAL", "Normal"
    HIGH = "HIGH", "High"


class NotificationEvent(models.Model):
    """
    The outbox. One row per business fact, inserted in the producer's own
    transaction so it commits or rolls back with the change it describes.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        ROUTED = "ROUTED", "Routed"
        FAILED = "FAILED", "Failed"
        DEAD = "DEAD", "Dead"

    # Generated in Python, so the id is known before the insert.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=64, db_index=True, help_text="A name from notifications/events.py.")
    schema_version = models.PositiveSmallIntegerField()
    aggregate_type = models.CharField(max_length=64, help_text="For tracing only, e.g. 'Order'.")
    aggregate_id = models.CharField(max_length=64, help_text="For tracing only, e.g. '42'.")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Who caused the event.",
    )
    payload = models.JSONField(default=dict, help_text="The fact snapshot the wording is built from.")
    idempotency_key = models.CharField(max_length=191, unique=True)
    occurred_at = models.DateTimeField(default=timezone.now, help_text="Business time. The inbox sorts by it.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now, help_text="Earliest time a worker may claim it.")
    locked_until = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=64, blank=True)
    last_error = models.TextField(blank=True)
    routed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["status", "available_at"], name="notif_event_claim_idx")]

    def __str__(self):
        return f"{self.event_type} {self.aggregate_type}:{self.aggregate_id} ({self.status})"


class Notification(models.Model):
    """The in-app inbox: one row per recipient per event."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    # SET_NULL because events are purged sooner than inbox rows (§3 D9).
    event = models.ForeignKey(
        NotificationEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )
    # Copied from the event, so the inbox never needs it.
    event_type = models.CharField(max_length=64)
    category = models.CharField(max_length=32, help_text="A code from notifications/categories.py.")
    audience = models.CharField(max_length=16, choices=Audience.choices)
    title = models.CharField(max_length=200)
    body = models.TextField(help_text="Rendered plain text.")
    action_url = models.CharField(
        max_length=500,
        blank=True,
        help_text="An app path, never an absolute URL to another site.",
    )
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.NORMAL)
    occurred_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        constraints = [
            # Re-routing an event never duplicates an inbox row. A purged event
            # leaves NULLs, which a unique constraint doesn't compare.
            models.UniqueConstraint(fields=["recipient", "event"], name="notif_unique_recipient_event"),
        ]
        indexes = [
            models.Index(fields=["recipient", "audience", "read_at"], name="notif_unread_idx"),
            models.Index(fields=["recipient", "audience", "-occurred_at", "-id"], name="notif_inbox_idx"),
        ]

    def __str__(self):
        return f"{self.title} -> {self.recipient_id} ({self.audience})"


class NotificationDelivery(models.Model):
    """One external send (e.g. an email) for one inbox notification."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"
        DEAD = "DEAD", "Dead"
        SKIPPED = "SKIPPED", "Skipped"  # no address, or a permanent refusal

    # Also the email Message-ID, so a retried send is recognisably the same message.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="deliveries")
    channel = models.CharField(max_length=16, choices=Channel.choices)
    destination = models.CharField(max_length=254, blank=True, help_text="The address at routing time.")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    locked_until = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=64, blank=True)
    last_error = models.TextField(blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "notification deliveries"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["notification", "channel"], name="notif_unique_delivery_channel"),
            # The inbox row is the in-app channel; a delivery is always external.
            models.CheckConstraint(condition=~Q(channel=Channel.IN_APP), name="notif_delivery_is_external"),
        ]
        indexes = [models.Index(fields=["status", "available_at"], name="notif_delivery_claim_idx")]

    def __str__(self):
        return f"{self.channel} to {self.destination or '(no address)'} ({self.status})"


class NotificationPreference(models.Model):
    """
    A sparse override: a row exists only where someone changed a category's
    default for a channel. Locked channels ignore it (§3 D8).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    category = models.CharField(max_length=32, help_text="A code from notifications/categories.py.")
    channel = models.CharField(max_length=16, choices=Channel.choices)
    enabled = models.BooleanField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "category", "channel"], name="notif_unique_preference"),
        ]

    def __str__(self):
        return f"{self.user_id} {self.category}/{self.channel}: {'on' if self.enabled else 'off'}"

"""
Customer support tickets.

A ticket is a conversation between one customer and the support staff. Status,
assignment and the activity timestamps are changed only by the support service
(SupportTicketService), under a row lock and with an audit entry. They are
never changed by saving the model from a view, and never from Django admin,
where tickets are read-only.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .storage import private_storage, support_attachment_path


class SupportTicket(models.Model):
    STATUS_OPEN = "OPEN"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_WAITING_ON_CUSTOMER = "WAITING_ON_CUSTOMER"
    STATUS_RESOLVED = "RESOLVED"
    STATUS_CLOSED = "CLOSED"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_IN_PROGRESS, "In progress"),
        (STATUS_WAITING_ON_CUSTOMER, "Waiting on customer"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_CLOSED, "Closed"),
    ]

    # Staff-driven transitions. CLOSED is terminal. Two customer-driven moves
    # are applied by the service on top of this table: a customer reply sends
    # CUSTOMER_REOPEN_STATUSES back to OPEN, and a customer may close the ticket
    # from any status except CLOSED (every non-terminal row here includes it).
    VALID_TRANSITIONS = {
        STATUS_OPEN: [STATUS_IN_PROGRESS, STATUS_WAITING_ON_CUSTOMER, STATUS_RESOLVED, STATUS_CLOSED],
        STATUS_IN_PROGRESS: [STATUS_WAITING_ON_CUSTOMER, STATUS_RESOLVED, STATUS_CLOSED],
        STATUS_WAITING_ON_CUSTOMER: [STATUS_IN_PROGRESS, STATUS_RESOLVED, STATUS_CLOSED],
        STATUS_RESOLVED: [STATUS_IN_PROGRESS, STATUS_CLOSED],
        STATUS_CLOSED: [],
    }

    CUSTOMER_REOPEN_STATUSES = (STATUS_WAITING_ON_CUSTOMER, STATUS_RESOLVED)

    # Counted against the per-customer cap on tickets still being worked on.
    UNRESOLVED_STATUSES = (STATUS_OPEN, STATUS_IN_PROGRESS, STATUS_WAITING_ON_CUSTOMER)

    CATEGORY_ORDER = "ORDER"
    CATEGORY_PAYMENT = "PAYMENT"
    CATEGORY_PRODUCT = "PRODUCT"
    CATEGORY_RETURN = "RETURN"
    CATEGORY_ACCOUNT = "ACCOUNT"
    CATEGORY_SHOP = "SHOP"
    CATEGORY_OTHER = "OTHER"

    CATEGORY_CHOICES = [
        (CATEGORY_ORDER, "Order & delivery"),
        (CATEGORY_PAYMENT, "Payment & refund"),
        (CATEGORY_PRODUCT, "Wrong or damaged item"),
        (CATEGORY_RETURN, "Return & exchange"),
        (CATEGORY_ACCOUNT, "Account & login"),
        (CATEGORY_SHOP, "Shop or seller complaint"),
        (CATEGORY_OTHER, "Other"),
    ]

    PRIORITY_LOW = "LOW"
    PRIORITY_NORMAL = "NORMAL"
    PRIORITY_HIGH = "HIGH"
    PRIORITY_URGENT = "URGENT"

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    ticket_number = models.CharField(
        max_length=20,
        unique=True,
        help_text="Server-generated reference the customer quotes (TKT<YYYYMMDD><6-HEX>).",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
        help_text="The customer who opened the ticket. The ticket is kept if the user is deleted.",
    )
    order = models.ForeignKey(
        "shop.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
        help_text="Optional order the ticket is about; always one of the customer's own orders.",
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    subject = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_NORMAL,
        help_text="Set by staff only; never shown to the customer.",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_support_tickets",
        help_text="Staff member handling the ticket; must hold support.staff.reply.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
        help_text="Latest public message or status change; the list sort key.",
    )
    last_customer_message_at = models.DateTimeField(null=True, blank=True)
    last_staff_reply_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Latest public staff reply. Internal notes do not count.",
    )
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    customer_last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_activity_at", "-id"]
        verbose_name = "Support Ticket"
        verbose_name_plural = "Support Tickets"
        indexes = [
            models.Index(fields=["customer", "-last_activity_at"], name="support_tkt_cust_act_idx"),
            models.Index(fields=["status", "-last_activity_at"], name="support_tkt_status_act_idx"),
            models.Index(fields=["assigned_to", "status"], name="support_tkt_assignee_idx"),
        ]

    def __str__(self):
        return f"{self.ticket_number} ({self.status})"

    @property
    def is_closed(self) -> bool:
        return self.status == self.STATUS_CLOSED

    @property
    def has_unread_for_customer(self) -> bool:
        """A public staff reply the customer hasn't opened the ticket to see yet."""
        if self.last_staff_reply_at is None:
            return False
        read_at = self.customer_last_read_at
        return read_at is None or self.last_staff_reply_at > read_at

    def can_transition_to(self, new_status: str) -> bool:
        """Whether staff may move the ticket from its current status to new_status."""
        return new_status in self.VALID_TRANSITIONS.get(self.status, [])


class TicketMessage(models.Model):
    AUTHOR_CUSTOMER = "CUSTOMER"
    AUTHOR_STAFF = "STAFF"
    AUTHOR_SYSTEM = "SYSTEM"

    AUTHOR_TYPE_CHOICES = [
        (AUTHOR_CUSTOMER, "Customer"),
        (AUTHOR_STAFF, "Staff"),
        (AUTHOR_SYSTEM, "System"),
    ]

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_messages",
    )
    author_type = models.CharField(max_length=10, choices=AUTHOR_TYPE_CHOICES)
    body = models.TextField()
    is_internal = models.BooleanField(
        default=False,
        help_text="Staff-only note or event. Never returned by the customer API.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "Ticket Message"
        verbose_name_plural = "Ticket Messages"
        indexes = [
            models.Index(fields=["ticket", "created_at"], name="support_msg_tkt_created_idx"),
        ]
        constraints = [
            # A customer's own words are always visible to them.
            models.CheckConstraint(
                condition=~Q(author_type="CUSTOMER", is_internal=True),
                name="support_msg_customer_not_internal",
            ),
        ]

    def __str__(self):
        return f"{self.ticket_id} · {self.author_type} · {self.created_at:%Y-%m-%d %H:%M}"


class TicketAttachment(models.Model):
    message = models.ForeignKey(TicketMessage, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=support_attachment_path, storage=private_storage, max_length=255)
    original_name = models.CharField(max_length=255, help_text="Client file name, for display only.")
    content_type = models.CharField(max_length=100, help_text="Detected from the file content.")
    size = models.PositiveIntegerField(help_text="Bytes.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Ticket Attachment"
        verbose_name_plural = "Ticket Attachments"

    def __str__(self):
        return self.original_name

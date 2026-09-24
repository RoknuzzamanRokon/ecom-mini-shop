from django.urls import reverse
from rest_framework import serializers

from .models import SupportTicket, TicketMessage
from .services import (
    DESCRIPTION_MIN_LENGTH,
    MESSAGE_MAX_LENGTH,
    SUBJECT_MAX_LENGTH,
    SUBJECT_MIN_LENGTH,
)

SUPPORT_TEAM_NAME = "MiniShop Support"

# Status names as the customer reads them; staff see STATUS_CHOICES.
CUSTOMER_STATUS_LABELS = {
    SupportTicket.STATUS_OPEN: "Open",
    SupportTicket.STATUS_IN_PROGRESS: "In progress",
    SupportTicket.STATUS_WAITING_ON_CUSTOMER: "Waiting on you",
    SupportTicket.STATUS_RESOLVED: "Resolved",
    SupportTicket.STATUS_CLOSED: "Closed",
}


def _text_errors(label, min_length=None, max_length=None):
    messages = {
        "required": f"{label} is required.",
        "blank": f"{label} is required.",
    }
    if min_length:
        messages["min_length"] = f"{label} must be at least {min_length} characters."
    if max_length:
        messages["max_length"] = f"{label} can be at most {max_length} characters."
    return messages


def _attachments_field():
    # Count, size and type are checked by support.validators (through the
    # service), which reads the file's content; this only collects the files.
    return serializers.ListField(
        child=serializers.FileField(allow_empty_file=True),
        required=False,
        allow_empty=True,
    )


# ---------------------------------------------------------------------- input


class TicketCreateSerializer(serializers.Serializer):
    category = serializers.ChoiceField(
        choices=SupportTicket.CATEGORY_CHOICES,
        error_messages={"invalid_choice": "Choose a valid category.", "required": "Choose a category."},
    )
    subject = serializers.CharField(
        min_length=SUBJECT_MIN_LENGTH,
        max_length=SUBJECT_MAX_LENGTH,
        error_messages=_text_errors("Subject", SUBJECT_MIN_LENGTH, SUBJECT_MAX_LENGTH),
    )
    description = serializers.CharField(
        min_length=DESCRIPTION_MIN_LENGTH,
        max_length=MESSAGE_MAX_LENGTH,
        error_messages=_text_errors("Description", DESCRIPTION_MIN_LENGTH, MESSAGE_MAX_LENGTH),
    )
    order_number = serializers.CharField(required=False, allow_blank=True, max_length=64)
    attachments = _attachments_field()


class TicketReplySerializer(serializers.Serializer):
    body = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=MESSAGE_MAX_LENGTH,
        error_messages=_text_errors("Message", max_length=MESSAGE_MAX_LENGTH),
    )
    attachments = _attachments_field()


# --------------------------------------------------------------------- output


class CustomerAttachmentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField(source="original_name")
    content_type = serializers.CharField()
    size = serializers.IntegerField()
    url = serializers.SerializerMethodField()

    def get_url(self, attachment):
        return reverse("support:attachment-download", args=[attachment.pk])


class CustomerMessageSerializer(serializers.ModelSerializer):
    """A public message as the ticket's customer sees it. Staff are shown by first name only."""

    author_name = serializers.SerializerMethodField()
    attachments = CustomerAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = TicketMessage
        fields = ["id", "author_type", "author_name", "body", "created_at", "attachments"]

    def get_author_name(self, message):
        if message.author_type == TicketMessage.AUTHOR_CUSTOMER:
            return "You"
        if message.author_type == TicketMessage.AUTHOR_STAFF and message.author:
            first_name = message.author.first_name.strip()
            if first_name:
                return f"{first_name} · {SUPPORT_TEAM_NAME}"
        return SUPPORT_TEAM_NAME


class CustomerTicketListSerializer(serializers.ModelSerializer):
    """
    A ticket as its customer sees it. Deliberately has no priority, assignee or
    staff timestamps: those are staff-only (docs/SUPPORT_SYSTEM.md D6, D14).
    """

    category_label = serializers.CharField(source="get_category_display", read_only=True)
    status_label = serializers.SerializerMethodField()
    order_number = serializers.SerializerMethodField()
    has_unread = serializers.BooleanField(source="has_unread_for_customer", read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            "ticket_number", "subject", "category", "category_label", "status",
            "status_label", "order_number", "created_at", "last_activity_at",
            "resolved_at", "closed_at", "has_unread",
        ]

    def get_status_label(self, ticket):
        return CUSTOMER_STATUS_LABELS.get(ticket.status, ticket.get_status_display())

    def get_order_number(self, ticket):
        return ticket.order.order_number if ticket.order_id else None


class CustomerTicketDetailSerializer(CustomerTicketListSerializer):
    can_reply = serializers.SerializerMethodField()
    can_close = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()

    class Meta(CustomerTicketListSerializer.Meta):
        fields = CustomerTicketListSerializer.Meta.fields + ["can_reply", "can_close", "messages"]

    def get_can_reply(self, ticket):
        return not ticket.is_closed

    def get_can_close(self, ticket):
        return not ticket.is_closed

    def get_messages(self, ticket):
        # Internal notes must never reach a customer, so this never falls back to
        # ticket.messages.all().
        messages = getattr(ticket, "public_messages", None)
        if messages is None:
            messages = (
                ticket.messages.filter(is_internal=False)
                .select_related("author")
                .prefetch_related("attachments")
            )
        return CustomerMessageSerializer(messages, many=True, context=self.context).data

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


# ---------------------------------------------------------------------- staff


def customer_display_name(user) -> str:
    """Display name, else full name, else username — the name staff know the customer by."""
    if user is None:
        return "Deleted user"
    profile = getattr(user, "customer_profile", None)
    return (
        (profile.display_name.strip() if profile and profile.display_name else "")
        or user.get_full_name().strip()
        or user.username
    )


def staff_display_name(user) -> str:
    if user is None:
        return "Deleted user"
    return user.get_full_name().strip() or user.username


def _person(user, name):
    return {"id": user.pk, "name": name} if user is not None else None


class StaffMessageInputSerializer(serializers.Serializer):
    body = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=MESSAGE_MAX_LENGTH,
        error_messages=_text_errors("Message", max_length=MESSAGE_MAX_LENGTH),
    )
    is_internal = serializers.BooleanField(required=False, default=False)
    set_status = serializers.ChoiceField(
        choices=SupportTicket.STATUS_CHOICES,
        required=False,
        allow_blank=True,
        error_messages={"invalid_choice": "Choose a valid status."},
    )
    attachments = _attachments_field()


class StaffTicketUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=SupportTicket.STATUS_CHOICES,
        required=False,
        error_messages={"invalid_choice": "Choose a valid status."},
    )
    priority = serializers.ChoiceField(
        choices=SupportTicket.PRIORITY_CHOICES,
        required=False,
        error_messages={"invalid_choice": "Choose a valid priority."},
    )
    category = serializers.ChoiceField(
        choices=SupportTicket.CATEGORY_CHOICES,
        required=False,
        error_messages={"invalid_choice": "Choose a valid category."},
    )
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class StaffAssignSerializer(serializers.Serializer):
    assignee_id = serializers.IntegerField(allow_null=True)


class StaffAttachmentSerializer(CustomerAttachmentSerializer):
    def get_url(self, attachment):
        return reverse("support:staff-attachment-download", args=[attachment.pk])


class StaffMessageSerializer(serializers.ModelSerializer):
    """Any message, internal ones included, with the author's real name."""

    author = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()
    attachments = StaffAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = TicketMessage
        fields = [
            "id", "author_type", "author", "author_name", "body", "is_internal",
            "created_at", "attachments",
        ]

    def _name(self, message):
        if message.author_type == TicketMessage.AUTHOR_CUSTOMER:
            return customer_display_name(message.author)
        if message.author_type == TicketMessage.AUTHOR_STAFF:
            return staff_display_name(message.author)
        return "System"

    def get_author(self, message):
        return _person(message.author, self._name(message))

    def get_author_name(self, message):
        return self._name(message)


class StaffTicketListSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)
    customer = serializers.SerializerMethodField()
    assigned_to = serializers.SerializerMethodField()
    order_number = serializers.SerializerMethodField()
    needs_reply = serializers.BooleanField(read_only=True)

    class Meta:
        model = SupportTicket
        fields = [
            "ticket_number", "subject", "category", "category_label", "status",
            "status_label", "priority", "priority_label", "customer", "assigned_to",
            "order_number", "needs_reply", "created_at", "last_activity_at",
        ]

    def get_customer(self, ticket):
        user = ticket.customer
        if user is None:
            return None
        return {"id": user.pk, "name": customer_display_name(user), "email": user.email}

    def get_assigned_to(self, ticket):
        return _person(ticket.assigned_to, staff_display_name(ticket.assigned_to))

    def get_order_number(self, ticket):
        return ticket.order.order_number if ticket.order_id else None


class StaffTicketDetailSerializer(StaffTicketListSerializer):
    order = serializers.SerializerMethodField()
    allowed_transitions = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()

    class Meta(StaffTicketListSerializer.Meta):
        fields = StaffTicketListSerializer.Meta.fields + [
            "order", "allowed_transitions", "updated_at", "last_customer_message_at",
            "last_staff_reply_at", "first_response_at", "resolved_at", "closed_at",
            "messages",
        ]

    def get_customer(self, ticket):
        user = ticket.customer
        if user is None:
            return None
        profile = getattr(user, "customer_profile", None)
        return {
            "id": user.pk,
            "name": customer_display_name(user),
            "username": user.username,
            "email": user.email,
            "phone": profile.phone if profile else "",
            "customer_profile_id": profile.pk if profile else None,
        }

    def get_order(self, ticket):
        order = ticket.order
        if order is None:
            return None
        return {
            "id": order.pk,
            "order_number": order.order_number,
            "status": order.status,
            "total_amount": str(order.total_amount),
            "created_at": serializers.DateTimeField().to_representation(order.created_at),
        }

    def get_allowed_transitions(self, ticket):
        return list(SupportTicket.VALID_TRANSITIONS.get(ticket.status, []))

    def get_messages(self, ticket):
        messages = getattr(ticket, "all_messages", None)
        if messages is None:
            messages = ticket.messages.select_related("author").prefetch_related("attachments")
        return StaffMessageSerializer(messages, many=True, context=self.context).data

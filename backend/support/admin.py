from django.contrib import admin
from django.template.defaultfilters import filesizeformat

from .models import SupportTicket, TicketMessage


class TicketMessageInline(admin.TabularInline):
    """The conversation, read-only. Attachments are listed by name: they live in
    private storage and have no URL to link to."""

    model = TicketMessage
    extra = 0
    can_delete = False
    fields = ("created_at", "author_type", "author", "is_internal", "body", "attachment_summary")
    readonly_fields = fields

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("author").prefetch_related("attachments")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Attachments")
    def attachment_summary(self, obj):
        return ", ".join(
            f"{a.original_name} ({filesizeformat(a.size)})" for a in obj.attachments.all()
        ) or "—"


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    """
    Read-only. Every ticket change (status, assignee, priority, replies) goes
    through SupportTicketService, which locks the row and writes the audit
    log; an editable change form here would bypass both (see Known Issue #22
    for the same problem on seller/shop status).
    """

    list_display = (
        "ticket_number", "subject", "customer", "category", "status",
        "priority", "assigned_to", "last_activity_at",
    )
    list_filter = ("status", "priority", "category", "created_at")
    search_fields = (
        "ticket_number", "subject", "customer__username", "customer__email",
        "order__order_number",
    )
    list_select_related = ("customer", "assigned_to")
    inlines = [TicketMessageInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

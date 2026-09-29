from django.contrib import admin

from rbac.services import has_user_permission

from .models import Notification, NotificationDelivery, NotificationEvent, NotificationPreference


class NotificationReadOnlyAdmin(admin.ModelAdmin):
    """
    Inspect only. Access is the MiniShop code 'notifications.admin.view'
    (§7), not Django's model permissions: inbox rows are personal data, so
    they stay with the roles that are granted the code. Rows are written only
    by the notification pipeline; requeue actions come with Task 15.
    """

    def has_module_permission(self, request):
        return has_user_permission(request.user, "notifications.admin.view")

    def has_view_permission(self, request, obj=None):
        return has_user_permission(request.user, "notifications.admin.view")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NotificationEvent)
class NotificationEventAdmin(NotificationReadOnlyAdmin):
    list_display = (
        "event_type", "aggregate_type", "aggregate_id", "status", "attempts",
        "occurred_at", "available_at", "routed_at",
    )
    list_filter = ("status", "event_type", "occurred_at")
    search_fields = ("idempotency_key", "aggregate_id", "event_type", "last_error")
    list_select_related = ("actor",)
    date_hierarchy = "occurred_at"


@admin.register(Notification)
class NotificationAdmin(NotificationReadOnlyAdmin):
    list_display = ("title", "recipient", "audience", "category", "event_type", "priority", "occurred_at", "read_at")
    list_filter = ("audience", "category", "event_type", "priority", ("read_at", admin.EmptyFieldListFilter))
    search_fields = ("title", "recipient__username", "recipient__email", "event_type")
    list_select_related = ("recipient",)
    date_hierarchy = "occurred_at"


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(NotificationReadOnlyAdmin):
    list_display = (
        "notification", "channel", "destination", "status", "attempts",
        "available_at", "sent_at",
    )
    list_filter = ("channel", "status", "created_at")
    search_fields = ("destination", "provider_message_id", "notification__recipient__username", "last_error")
    list_select_related = ("notification",)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(NotificationReadOnlyAdmin):
    list_display = ("user", "category", "channel", "enabled", "updated_at")
    list_filter = ("category", "channel", "enabled")
    search_fields = ("user__username", "user__email")
    list_select_related = ("user",)

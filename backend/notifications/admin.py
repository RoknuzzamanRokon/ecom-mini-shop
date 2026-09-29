from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied

from audit.services import AuditService
from audit.utils import get_client_ip
from rbac.services import has_user_permission

from .models import Notification, NotificationDelivery, NotificationEvent, NotificationPreference
from .operations import requeue, retry_now

VIEW_CODE = "notifications.admin.view"
MANAGE_CODE = "notifications.admin.manage"


class NotificationReadOnlyAdmin(admin.ModelAdmin):
    """
    Inspect only. Access is the MiniShop code 'notifications.admin.view'
    (§7), not Django's model permissions: inbox rows are personal data, so
    they stay with the roles that are granted the code. Rows are written only
    by the notification pipeline; the queues add Requeue and Retry now
    (QueueActionsMixin).
    """

    def has_module_permission(self, request):
        return has_user_permission(request.user, VIEW_CODE)

    def has_view_permission(self, request, obj=None):
        return has_user_permission(request.user, VIEW_CODE)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class QueueActionsMixin:
    """
    Requeue and Retry now for the outbox and the delivery queue (§4.8, §17).
    Both need 'notifications.admin.manage' and write one audit row per row
    they change. They only change queue state: a running worker does the
    work on its next pass. Selected rows in any other status are left alone.
    """

    actions = ["requeue_rows", "retry_rows_now"]

    # Django shows an action with permissions=["manage"] only when this is true.
    def has_manage_permission(self, request):
        return has_user_permission(request.user, MANAGE_CODE)

    @admin.action(description="Requeue selected DEAD or FAILED rows (attempts reset)", permissions=["manage"])
    def requeue_rows(self, request, queryset):
        self._apply(
            request, queryset, requeue,
            audit_action="NOTIFICATION_REQUEUED",
            done="Requeued {n} {name} with a fresh set of attempts.",
            eligible="DEAD or FAILED",
        )

    @admin.action(description="Retry selected FAILED rows now (attempts kept)", permissions=["manage"])
    def retry_rows_now(self, request, queryset):
        self._apply(
            request, queryset, retry_now,
            audit_action="NOTIFICATION_RETRY_NOW",
            done="Made {n} {name} due now; each keeps its attempt count.",
            eligible="FAILED",
        )

    def _apply(self, request, queryset, operation, *, audit_action, done, eligible):
        # Django already hides the action without the code; this stops a
        # hand-made POST too.
        if not self.has_manage_permission(request):
            raise PermissionDenied
        pks = list(queryset.values_list("pk", flat=True))
        changed = operation(self.model, pks)
        ip_address = get_client_ip(request)
        for row, previous_state in changed:
            AuditService.log(
                action=audit_action,
                target=row,
                actor=request.user,
                previous_state=previous_state,
                new_state={"status": row.status, "attempts": row.attempts},
                ip_address=ip_address,
            )
        name = self.model._meta.verbose_name_plural if len(changed) != 1 else self.model._meta.verbose_name
        if changed:
            self.message_user(
                request,
                done.format(n=len(changed), name=name)
                + f" A running worker picks {'it' if len(changed) == 1 else 'them'} up on its next pass.",
                messages.SUCCESS,
            )
        left = len(pks) - len(changed)
        if left:
            self.message_user(
                request,
                f"{left} selected row(s) weren't {eligible} and were left alone.",
                messages.WARNING,
            )


@admin.register(NotificationEvent)
class NotificationEventAdmin(QueueActionsMixin, NotificationReadOnlyAdmin):
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
class NotificationDeliveryAdmin(QueueActionsMixin, NotificationReadOnlyAdmin):
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

from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "action",
        "target_type",
        "target_id",
        "target_repr",
        "actor",
        "shop",
        "seller",
        "created_at",
    )
    list_filter = ("action", "target_type", "created_at")
    search_fields = (
        "action",
        "target_id",
        "target_repr",
        "actor__username",
        "actor__email",
        "shop__name",
        "seller__business_name",
    )
    date_hierarchy = "created_at"
    readonly_fields = [field.name for field in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

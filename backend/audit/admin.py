from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'actor', 'target_type', 'target_repr', 'shop', 'seller', 'ip_address', 'created_at')
    search_fields = ('actor__username', 'action', 'target_repr', 'ip_address')
    list_filter = ('action', 'target_type', 'created_at')
    readonly_fields = (
        'actor', 'action', 'target_type', 'target_id', 'target_repr',
        'shop', 'seller', 'metadata', 'ip_address', 'created_at'
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('actor', 'shop', 'seller')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

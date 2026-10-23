from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'actor_display', 'target_type', 'target_repr', 'shop', 'seller', 'ip_address', 'created_at')
    search_fields = ('actor__username', 'actor_username', 'action', 'target_repr', 'ip_address')
    # `actor` backs /admin/profile/'s "My audit trail" link (?actor__id__exact=<pk>).
    list_filter = ('action', 'target_type', ('actor', admin.RelatedOnlyFieldListFilter), 'created_at')
    readonly_fields = (
        'actor', 'actor_username', 'actor_user_id', 'action', 'target_type', 'target_id', 'target_repr',
        'shop', 'seller', 'metadata', 'ip_address', 'created_at'
    )

    @admin.display(description='Actor', ordering='actor_username')
    def actor_display(self, obj):
        return obj.actor_name

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('actor', 'shop', 'seller')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count

from audit.admin_mixins import ReasonRequiredActionMixin, StatusBadgeMixin
from .models import Shop
from .services import ShopService, ShopError

@admin.register(Shop)
class ShopAdmin(ReasonRequiredActionMixin, StatusBadgeMixin, admin.ModelAdmin):
    list_display = (
        'name', 'owner', 'status_badge', 'product_count', 
        'phone', 'created_at'
    )
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'slug', 'owner__user__username', 'phone')
    readonly_fields = (
        'status', 'reviewed_by', 'reviewed_at', 'approved_at',
        'suspended_at', 'created_at', 'updated_at', 'location_display'
    )
    actions = ['approve_and_activate', 'suspend_shops', 'reject_shops', 'reactivate_shops']

    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'name', 'slug', 'description', 'status')
        }),
        ('Media', {
            'fields': ('logo', 'cover_image')
        }),
        ('Contact & Location', {
            'fields': ('phone', 'address', 'location', 'location_display')
        }),
        ('Status & Reviews', {
            'fields': ('rejection_reason', 'suspension_reason', 'reviewed_by', 
                       'reviewed_at', 'approved_at', 'suspended_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related('owner', 'owner__user', 'reviewed_by')
        qs = qs.annotate(product_count=Count('products', distinct=True))
        return qs

    def product_count(self, obj):
        return obj.product_count
    product_count.short_description = 'Products'
    product_count.admin_order_field = 'product_count'

    def location_display(self, obj):
        if obj.location:
            return f"Lat: {obj.location.y}, Lng: {obj.location.x}"
        return "N/A"
    location_display.short_description = 'Location (Lat, Lng)'


    def audit_context(self, obj):
        return {'shop': obj, 'seller': obj.owner}

    def approve_and_activate(self, request, queryset):
        self.run_simple_action(
            request, queryset,
            verb='Approved and activated',
            perform=lambda shop, user: ShopService.approve_shop(shop, user),
            audit_action='ADMIN_SHOP_APPROVE',
            catch=(ValidationError, ShopError),
        )
    approve_and_activate.short_description = "Approve and activate selected shops"
    approve_and_activate.allowed_permissions = ('change',)

    def suspend_shops(self, request, queryset):
        return self.run_reason_action(
            request, queryset,
            action_name='suspend_shops',
            title='Suspend shops',
            verb='Suspended',
            reason_label='Suspension reason',
            help_text='Suspending a shop removes it and its products from the storefront.',
            perform=lambda shop, user, reason: ShopService.suspend_shop(shop, user, reason),
            audit_action='ADMIN_SHOP_SUSPEND',
            catch=(ValidationError, ShopError),
        )
    suspend_shops.short_description = "Suspend selected shops (reason required)"
    suspend_shops.allowed_permissions = ('change',)

    def reject_shops(self, request, queryset):
        return self.run_reason_action(
            request, queryset,
            action_name='reject_shops',
            title='Reject shops',
            verb='Rejected',
            reason_label='Rejection reason',
            help_text='Rejecting a shop application is visible to its owner.',
            perform=lambda shop, user, reason: ShopService.reject_shop(shop, user, reason),
            audit_action='ADMIN_SHOP_REJECT',
            catch=(ValidationError, ShopError),
        )
    reject_shops.short_description = "Reject selected shops (reason required)"
    reject_shops.allowed_permissions = ('change',)

    def reactivate_shops(self, request, queryset):
        self.run_simple_action(
            request, queryset,
            verb='Reactivated',
            perform=lambda shop, user: ShopService.reactivate_shop(shop, user),
            audit_action='ADMIN_SHOP_REACTIVATE',
            catch=(ValidationError, ShopError),
        )
    reactivate_shops.short_description = "Reactivate selected shops"
    reactivate_shops.allowed_permissions = ('change',)

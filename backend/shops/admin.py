from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.contrib import messages

from audit.admin_mixins import StatusBadgeMixin
from .models import Shop
from .services import ShopService, ShopError, InvalidShopTransitionError, IneligibleSellerError, ShopLimitExceededError

@admin.register(Shop)
class ShopAdmin(StatusBadgeMixin, admin.ModelAdmin):
    list_display = (
        'name', 'owner', 'status_badge', 'product_count', 
        'phone', 'created_at'
    )
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'slug', 'owner__user__username', 'phone')
    readonly_fields = (
        'reviewed_by', 'reviewed_at', 'approved_at', 
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


    def approve_and_activate(self, request, queryset):
        success = 0
        error = 0
        for shop in queryset:
            try:
                ShopService.approve_shop(shop, request.user)
                success += 1
            except (ValidationError, ShopError) as e:
                self.message_user(request, f"Error approving {shop}: {e}", level=messages.ERROR)
                error += 1
        if success:
            self.message_user(request, f"Successfully approved {success} shops.", level=messages.SUCCESS)
    approve_and_activate.short_description = "Approve and activate selected shops"

    def suspend_shops(self, request, queryset):
        success = 0
        error = 0
        for shop in queryset:
            try:
                ShopService.suspend_shop(shop, request.user, 'Suspended via admin action')
                success += 1
            except (ValidationError, ShopError) as e:
                self.message_user(request, f"Error suspending {shop}: {e}", level=messages.ERROR)
                error += 1
        if success:
            self.message_user(request, f"Successfully suspended {success} shops.", level=messages.SUCCESS)
    suspend_shops.short_description = "Suspend selected shops"

    def reject_shops(self, request, queryset):
        success = 0
        error = 0
        for shop in queryset:
            try:
                ShopService.reject_shop(shop, request.user, 'Rejected via admin action')
                success += 1
            except (ValidationError, ShopError) as e:
                self.message_user(request, f"Error rejecting {shop}: {e}", level=messages.ERROR)
                error += 1
        if success:
            self.message_user(request, f"Successfully rejected {success} shops.", level=messages.SUCCESS)
    reject_shops.short_description = "Reject selected shops"

    def reactivate_shops(self, request, queryset):
        success = 0
        error = 0
        for shop in queryset:
            try:
                ShopService.reactivate_shop(shop, request.user)
                success += 1
            except (ValidationError, ShopError) as e:
                self.message_user(request, f"Error reactivating {shop}: {e}", level=messages.ERROR)
                error += 1
        if success:
            self.message_user(request, f"Successfully reactivated {success} shops.", level=messages.SUCCESS)
    reactivate_shops.short_description = "Reactivate selected shops"

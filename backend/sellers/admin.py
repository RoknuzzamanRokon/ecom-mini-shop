from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils.html import format_html
from django.contrib import messages
from .models import SellerProfile
from .services import approve_seller, suspend_seller, reject_seller, reactivate_seller

@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'business_name', 'seller_type', 'status_badge', 
        'shop_count', 'product_count', 'created_at'
    )
    list_filter = ('status', 'seller_type', 'created_at')
    search_fields = ('user__username', 'user__email', 'business_name', 'business_email', 'tax_id')
    readonly_fields = (
        'reviewed_by', 'reviewed_at', 'approved_at', 
        'suspended_at', 'created_at', 'updated_at'
    )
    actions = ['approve_and_activate', 'suspend_sellers', 'reject_sellers', 'reactivate_sellers']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('user', 'seller_type', 'status', 'description')
        }),
        ('Business Details', {
            'fields': ('business_name', 'business_email', 'business_phone', 'tax_id')
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
        qs = qs.select_related('user', 'reviewed_by')
        qs = qs.annotate(
            shop_count=Count('shops', distinct=True),
            product_count=Count('shops__products', distinct=True)
        )
        return qs

    def shop_count(self, obj):
        return obj.shop_count
    shop_count.short_description = 'Shops'
    shop_count.admin_order_field = 'shop_count'

    def product_count(self, obj):
        return obj.product_count
    product_count.short_description = 'Products'
    product_count.admin_order_field = 'product_count'

    def status_badge(self, obj):
        colors = {
            'ACTIVE': ('#10B981', '#ECFDF5'), 'APPROVED': ('#10B981', '#ECFDF5'),
            'PENDING': ('#3B82F6', '#EFF6FF'), 'UNDER_REVIEW': ('#3B82F6', '#EFF6FF'),
            'DRAFT': ('#F59E0B', '#FFFBEB'), 'SUBMITTED': ('#F59E0B', '#FFFBEB'),
            'SUSPENDED': ('#EF4444', '#FEF2F2'), 'REJECTED': ('#EF4444', '#FEF2F2'),
            'CANCELLED': ('#EF4444', '#FEF2F2'),
        }
        status = obj.status.upper() if obj.status else ''
        color, bg = colors.get(status, ('#6B7280', '#F3F4F6'))
        return format_html(
            '<span style="display:inline-block;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:700;color:{};background:{};">{}</span>',
            color, bg, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def approve_and_activate(self, request, queryset):
        success = 0
        error = 0
        for seller in queryset:
            try:
                approve_seller(seller, request.user)
                success += 1
            except ValidationError as e:
                self.message_user(request, f"Error approving {seller}: {e}", level=messages.ERROR)
                error += 1
        if success:
            self.message_user(request, f"Successfully approved {success} sellers.", level=messages.SUCCESS)
    approve_and_activate.short_description = "Approve and activate selected sellers"

    def suspend_sellers(self, request, queryset):
        success = 0
        error = 0
        for seller in queryset:
            try:
                suspend_seller(seller, request.user, 'Suspended via admin action')
                success += 1
            except ValidationError as e:
                self.message_user(request, f"Error suspending {seller}: {e}", level=messages.ERROR)
                error += 1
        if success:
            self.message_user(request, f"Successfully suspended {success} sellers.", level=messages.SUCCESS)
    suspend_sellers.short_description = "Suspend selected sellers"

    def reject_sellers(self, request, queryset):
        success = 0
        error = 0
        for seller in queryset:
            try:
                reject_seller(seller, request.user, 'Rejected via admin action')
                success += 1
            except ValidationError as e:
                self.message_user(request, f"Error rejecting {seller}: {e}", level=messages.ERROR)
                error += 1
        if success:
            self.message_user(request, f"Successfully rejected {success} sellers.", level=messages.SUCCESS)
    reject_sellers.short_description = "Reject selected sellers"

    def reactivate_sellers(self, request, queryset):
        success = 0
        error = 0
        for seller in queryset:
            try:
                reactivate_seller(seller, request.user)
                success += 1
            except ValidationError as e:
                self.message_user(request, f"Error reactivating {seller}: {e}", level=messages.ERROR)
                error += 1
        if success:
            self.message_user(request, f"Successfully reactivated {success} sellers.", level=messages.SUCCESS)
    reactivate_sellers.short_description = "Reactivate selected sellers"

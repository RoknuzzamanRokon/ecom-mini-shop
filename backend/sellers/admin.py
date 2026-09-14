from django.contrib import admin
from django.db.models import Count

from audit.admin_mixins import ReasonRequiredActionMixin, StatusBadgeMixin
from .models import SellerProfile
from .services import approve_seller, suspend_seller, reject_seller, reactivate_seller

@admin.register(SellerProfile)
class SellerProfileAdmin(ReasonRequiredActionMixin, StatusBadgeMixin, admin.ModelAdmin):
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


    def audit_context(self, obj):
        return {'seller': obj}

    def approve_and_activate(self, request, queryset):
        self.run_simple_action(
            request, queryset,
            verb='Approved and activated',
            perform=approve_seller,
            audit_action='ADMIN_SELLER_APPROVE',
        )
    approve_and_activate.short_description = "Approve and activate selected sellers"

    def suspend_sellers(self, request, queryset):
        return self.run_reason_action(
            request, queryset,
            action_name='suspend_sellers',
            title='Suspend sellers',
            verb='Suspended',
            reason_label='Suspension reason',
            help_text='Suspending a seller blocks their shops and products from the storefront.',
            perform=suspend_seller,
            audit_action='ADMIN_SELLER_SUSPEND',
        )
    suspend_sellers.short_description = "Suspend selected sellers (reason required)"

    def reject_sellers(self, request, queryset):
        return self.run_reason_action(
            request, queryset,
            action_name='reject_sellers',
            title='Reject sellers',
            verb='Rejected',
            reason_label='Rejection reason',
            help_text='Rejecting a seller application is visible to the applicant.',
            perform=reject_seller,
            audit_action='ADMIN_SELLER_REJECT',
        )
    reject_sellers.short_description = "Reject selected sellers (reason required)"

    def reactivate_sellers(self, request, queryset):
        self.run_simple_action(
            request, queryset,
            verb='Reactivated',
            perform=reactivate_seller,
            audit_action='ADMIN_SELLER_REACTIVATE',
        )
    reactivate_sellers.short_description = "Reactivate selected sellers"

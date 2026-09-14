from django.contrib import admin
from django.utils.html import format_html
from .models import SellerWallet, PointTransaction, ProductCreationCost

@admin.register(SellerWallet)
class SellerWalletAdmin(admin.ModelAdmin):
    list_display = ('seller', 'balance_display', 'created_at', 'updated_at')
    search_fields = ('seller__user__username', 'seller__business_name')
    list_filter = ('created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('seller', 'seller__user')

    def balance_display(self, obj):
        return f"{obj.balance} pts"
    balance_display.short_description = 'Balance'

@admin.register(PointTransaction)
class PointTransactionAdmin(admin.ModelAdmin):
    list_display = ('wallet', 'transaction_type', 'amount_display', 'balance_after_display', 'reason', 'created_at')
    search_fields = ('wallet__seller__user__username', 'reason', 'reference_id')
    list_filter = ('transaction_type', 'created_at')
    readonly_fields = (
        'wallet', 'seller', 'transaction_type', 'amount',
        'balance_before', 'balance_after', 'reason',
        'reference_type', 'reference_id', 'actor', 'created_at'
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('wallet', 'seller', 'seller__user', 'actor')

    def amount_display(self, obj):
        # `amount` is a PositiveIntegerField, so direction lives in the balance
        # delta -- authoritative even for ADJUSTMENT, which goes either way.
        credited = obj.balance_after >= obj.balance_before
        color = '#10B981' if credited else '#EF4444'
        sign = '+' if credited else '-'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}{} pts</span>',
            color, sign, obj.amount
        )
    amount_display.short_description = 'Amount'
    amount_display.admin_order_field = 'amount'

    def balance_after_display(self, obj):
        return f"{obj.balance_after} pts"
    balance_after_display.short_description = 'Balance After'
    balance_after_display.admin_order_field = 'balance_after'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(ProductCreationCost)
class ProductCreationCostAdmin(admin.ModelAdmin):
    list_display = ('required_points', 'updated_at')
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        # Singleton (pk=1) enforced in ProductCreationCost.save().
        return not ProductCreationCost.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

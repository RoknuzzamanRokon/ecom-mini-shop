from django.contrib import admin
from .models import Cart, CartItem

class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ('created_at', 'updated_at', 'line_total')
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at', 'updated_at', 'total_items', 'total_amount_display')
    search_fields = ('user__username', 'user__email')
    list_filter = ('created_at', 'updated_at')
    inlines = [CartItemInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

    def total_items(self, obj):
        return obj.total_items_count
    total_items.short_description = 'Items'

    def total_amount_display(self, obj):
        return f"৳{obj.total_amount}"
    total_amount_display.short_description = 'Total Amount'

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ('cart', 'product', 'quantity', 'unit_price_display', 'line_total_display')
    search_fields = ('cart__user__username', 'product__name')
    list_filter = ('created_at', 'updated_at')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'cart', 'cart__user', 'product', 'product__shop'
        )

    def unit_price_display(self, obj):
        return f"৳{obj.unit_price}"
    unit_price_display.short_description = 'Unit Price'

    def line_total_display(self, obj):
        return f"৳{obj.line_total}"
    line_total_display.short_description = 'Line Total'

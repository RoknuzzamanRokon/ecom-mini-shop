from django.contrib import admin

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    raw_id_fields = ["product"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "total_items_count", "total_amount", "created_at", "updated_at"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ["id", "cart", "product", "quantity", "unit_price", "line_total", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["cart__user__username", "product__name"]
    raw_id_fields = ["cart", "product"]
    readonly_fields = ["created_at", "updated_at"]

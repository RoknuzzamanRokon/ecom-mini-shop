from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Order, OrderItem, Product, ProductImage


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("image_preview", "name", "slug", "icon", "is_active")
    list_editable = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "description")
    fields = ("name", "slug", "icon", "image", "image_preview", "description", "is_active")
    readonly_fields = ("image_preview",)

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:44px;width:64px;object-fit:cover;border-radius:4px;border:1px solid #ddd;" />',
                obj.image.url,
            )
        return format_html('<span style="color:#999;font-size:12px;">No image</span>')

    image_preview.short_description = "Image Preview"


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "order")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "shop",
        "seller_display",
        "status",
        "price",
        "old_price",
        "stock",
        "badge",
        "is_active",
        "image_preview",
    )
    list_editable = ("status", "price", "old_price", "stock", "badge", "is_active")
    list_filter = ("status", "category", "shop", "is_active", "badge")
    search_fields = ("name", "description", "shop__name", "shop__owner__business_name")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline]

    def seller_display(self, obj):
        seller = obj.seller
        return seller.business_name if seller else "-"
    seller_display.short_description = "Seller"

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:40px;border-radius:4px;" />', obj.image.url)
        return "-"

    image_preview.short_description = "Image"



class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "product",
        "product_name",
        "shop_name",
        "seller_name",
        "unit_price",
        "quantity",
        "line_total",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "order_number",
        "user",
        "customer_name",
        "shipping_city",
        "subtotal",
        "total_amount",
        "status",
        "created_at",
    )
    list_editable = ("status",)
    list_filter = ("status", "created_at")
    search_fields = ("order_number", "customer_name", "shipping_phone", "user__username")
    readonly_fields = (
        "order_number",
        "user",
        "subtotal",
        "discount_total",
        "shipping_fee",
        "total_amount",
        "created_at",
        "updated_at",
    )
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product_name", "shop_name", "unit_price", "quantity", "line_total")
    search_fields = ("product_name", "shop_name", "order__order_number")
    readonly_fields = (
        "order",
        "product",
        "product_name",
        "product_slug",
        "shop",
        "shop_name",
        "seller",
        "seller_name",
        "unit_price",
        "price",
        "quantity",
        "line_total",
        "subtotal",
        "created_at",
        "updated_at",
    )

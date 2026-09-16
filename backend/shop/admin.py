from decimal import Decimal

from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from django.utils.html import format_html
from django.db.models import Count
from django.core.exceptions import PermissionDenied, ValidationError

from .models import (
    Category, Order, OrderItem, Product, ProductImage,
    ProductInventory, InventoryTransaction, Payment, Refund
)
from shop.services import OrderService
from shop.invoice import build_order_invoice_pdf, invoice_filename
from audit.admin_mixins import StatusBadgeMixin


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("image_preview", "name", "slug", "icon", "is_active", "product_count")
    list_editable = ("is_active",)
    prepopulated_fields = {"slug": ("name",)}
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    fields = ("name", "slug", "icon", "image", "image_preview", "description", "is_active")
    readonly_fields = ("image_preview",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_product_count=Count('products'))

    def product_count(self, obj):
        return obj._product_count
    product_count.admin_order_field = '_product_count'
    product_count.short_description = 'Products'

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
class ProductAdmin(StatusBadgeMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "shop",
        "seller_display",
        "status_badge",
        "price",
        "old_price",
        "stock",
        "badge",
        "is_active",
        "image_preview",
    )
    list_editable = ("price", "old_price", "stock", "badge", "is_active")
    list_filter = ("status", "category", "shop", "is_active", "badge")
    search_fields = ("name", "description", "shop__name", "shop__owner__business_name")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category', 'shop', 'shop__owner')

    def seller_display(self, obj):
        seller = getattr(obj, 'seller', None)
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
    verbose_name_plural = "Order Items"
    fields = (
        "product_name",
        "shop_name",
        "seller_name",
        "unit_price_display",
        "quantity",
        "line_total_display",
    )
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Unit price")
    def unit_price_display(self, obj):
        return self._money(obj.unit_price or obj.price)

    @admin.display(description="Line total")
    def line_total_display(self, obj):
        return self._money(obj.line_total or obj.subtotal)

    @staticmethod
    def _money(amount):
        # Taka, grouped to thousands -- the raw DecimalField rendered as a bare
        # "3250.00", which reads as neither a price nor a quantity.
        return format_html("৳ {}", f"{Decimal(amount or 0):,.2f}")

    def get_queryset(self, request):
        # The inline renders the shop and seller snapshots; without this every
        # row costs two extra queries.
        return super().get_queryset(request).select_related("product", "shop", "seller")


@admin.register(Order)
class OrderAdmin(StatusBadgeMixin, admin.ModelAdmin):
    list_display = (
        "order_number",
        "user",
        "customer_name",
        "shipping_city",
        "subtotal",
        "total_amount",
        "status_badge",
        "created_at",
    )
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
    actions = [
        "confirm_orders",
        "mark_orders_processing",
        "mark_orders_shipped",
        "mark_orders_delivered",
        "cancel_orders",
    ]

    change_form_template = "admin/shop/order/change_form.html"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user').prefetch_related('items')

    def get_urls(self):
        # Registered ahead of super() so "<pk>/invoice/" is matched before
        # ModelAdmin's catch-all "<path:object_id>/" change route.
        custom = [
            path(
                "<path:object_id>/invoice/",
                self.admin_site.admin_view(self.invoice_pdf_view),
                name="shop_order_invoice",
            ),
        ]
        return custom + super().get_urls()

    def invoice_pdf_view(self, request, object_id):
        """Streams the order invoice as a PDF named after the order number."""
        order = get_object_or_404(
            Order.objects.select_related("user").prefetch_related(
                "items", "payments", "refunds__payment"
            ),
            pk=object_id,
        )
        if not self.has_view_permission(request, order):
            raise PermissionDenied

        pdf = build_order_invoice_pdf(order, generated_by=request.user)
        response = HttpResponse(pdf, content_type="application/pdf")
        # `attachment` so the browser saves it under the order-derived name
        # instead of showing it in the built-in viewer as "invoice".
        response["Content-Disposition"] = (
            f'attachment; filename="{invoice_filename(order)}"'
        )
        response["Content-Length"] = str(len(pdf))
        return response

    def confirm_orders(self, request, queryset):
        self._transition_orders(request, queryset, 'CONFIRMED')
    confirm_orders.short_description = "Mark selected orders as Confirmed"

    def mark_orders_processing(self, request, queryset):
        self._transition_orders(request, queryset, 'PROCESSING')
    mark_orders_processing.short_description = "Mark selected orders as Processing"

    def mark_orders_shipped(self, request, queryset):
        self._transition_orders(request, queryset, 'SHIPPED')
    mark_orders_shipped.short_description = "Mark selected orders as Shipped"

    def mark_orders_delivered(self, request, queryset):
        self._transition_orders(request, queryset, 'DELIVERED')
    mark_orders_delivered.short_description = "Mark selected orders as Delivered"

    def cancel_orders(self, request, queryset):
        self._transition_orders(request, queryset, 'CANCELLED')
    cancel_orders.short_description = "Mark selected orders as Cancelled"

    def _transition_orders(self, request, queryset, new_status):
        success_count = 0
        for order in queryset:
            try:
                OrderService.transition_order_status(order, new_status, actor=request.user)
                success_count += 1
            except ValidationError as e:
                self.message_user(request, f"Error transitioning {order.order_number}: {getattr(e, 'message', str(e))}", level=messages.ERROR)
            except Exception as e:
                self.message_user(request, f"Error transitioning {order.order_number}: {str(e)}", level=messages.ERROR)
        
        if success_count > 0:
            self.message_user(request, f"Successfully transitioned {success_count} order(s) to {new_status}.", level=messages.SUCCESS)


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
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('order', 'product', 'shop', 'seller')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


LOW_STOCK_THRESHOLD = 10


class StockLevelFilter(admin.SimpleListFilter):
    """Filter inventory rows by how much sellable stock is left."""
    title = "stock level"
    parameter_name = "stock_level"

    def lookups(self, request, model_admin):
        return (
            ("out", "Out of stock (0)"),
            ("low", f"Low stock (1-{LOW_STOCK_THRESHOLD})"),
            ("ok", f"In stock (>{LOW_STOCK_THRESHOLD})"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "out":
            return queryset.filter(available_quantity=0)
        if value == "low":
            return queryset.filter(
                available_quantity__gt=0, available_quantity__lte=LOW_STOCK_THRESHOLD
            )
        if value == "ok":
            return queryset.filter(available_quantity__gt=LOW_STOCK_THRESHOLD)
        return queryset


@admin.register(ProductInventory)
class ProductInventoryAdmin(admin.ModelAdmin):
    list_display = ("product", "available_display", "reserved_quantity", "sold_quantity", "total_display", "updated_at")
    list_filter = (StockLevelFilter, "updated_at")
    search_fields = ("product__name", "product__slug")
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')

    def available_display(self, obj):
        val = obj.available_quantity
        if val == 0:
            return format_html('<span style="color:#EF4444;font-weight:bold;">{}</span>', val)
        elif val <= LOW_STOCK_THRESHOLD:
            return format_html('<span style="color:#F59E0B;font-weight:bold;">{}</span>', val)
        return val
    available_display.short_description = "Available Quantity"
    available_display.admin_order_field = "available_quantity"

    def total_display(self, obj):
        return obj.available_quantity + obj.reserved_quantity + obj.sold_quantity
    total_display.short_description = "Total Quantity"


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = ("product", "transaction_type", "quantity_display", "before_available", "after_available", "actor", "order", "created_at")
    list_filter = ("transaction_type", "created_at")
    search_fields = ("product__name", "order__order_number", "actor__username")
    date_hierarchy = "created_at"

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product', 'inventory', 'order', 'actor')

    # Stock-increasing vs stock-decreasing transaction types, per
    # InventoryTransaction.TRANSACTION_TYPE_CHOICES.
    _INBOUND = (
        InventoryTransaction.TYPE_INITIAL_STOCK,
        InventoryTransaction.TYPE_STOCK_IN,
        InventoryTransaction.TYPE_RELEASE,
    )
    _OUTBOUND = (
        InventoryTransaction.TYPE_STOCK_OUT,
        InventoryTransaction.TYPE_RESERVATION,
        InventoryTransaction.TYPE_SALE,
    )

    def quantity_display(self, obj):
        val = getattr(obj, 'quantity', 0)
        t_type = getattr(obj, 'transaction_type', '')
        if t_type in self._INBOUND:
            sign, color = '+', '#10B981'
        elif t_type in self._OUTBOUND:
            sign, color = '-', '#EF4444'
        else:
            # ADJUSTMENT can go either way -- let the stored sign speak.
            if not val:
                return val
            sign = '+' if val > 0 else '-'
            color = '#10B981' if val > 0 else '#EF4444'
            val = abs(val)
        return format_html(
            '<span style="color:{};font-weight:bold;">{}{}</span>', color, sign, val
        )
    quantity_display.short_description = "Quantity"


@admin.register(Payment)
class PaymentAdmin(StatusBadgeMixin, admin.ModelAdmin):
    list_display = ("payment_number", "order", "user", "payment_method_badge", "amount_display", "status_badge", "paid_at", "created_at")
    list_filter = ("status", "payment_method", "created_at")
    search_fields = ("payment_number", "order__order_number", "user__username", "transaction_id")
    
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('order', 'user')

    def payment_method_badge(self, obj):
        return format_html('<span style="padding:2px 8px;border-radius:4px;background:#E5E7EB;color:#374151;font-size:11px;font-weight:bold;">{}</span>', obj.get_payment_method_display() if hasattr(obj, 'get_payment_method_display') else getattr(obj, 'payment_method', ''))
    payment_method_badge.short_description = "Method"

    def amount_display(self, obj):
        return f"৳ {obj.amount}"
    amount_display.short_description = "Amount"
    amount_display.admin_order_field = "amount"


@admin.register(Refund)
class RefundAdmin(StatusBadgeMixin, admin.ModelAdmin):
    list_display = ("refund_number", "order", "payment", "amount_display", "status_badge", "processed_by", "created_at")
    search_fields = ("refund_number", "order__order_number", "payment__payment_number", "transaction_id")
    list_filter = ('status', 'created_at')
    
    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]
    
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('order', 'payment', 'processed_by')

    def amount_display(self, obj):
        return f"৳ {obj.amount}"
    amount_display.short_description = "Amount"
    amount_display.admin_order_field = "amount"

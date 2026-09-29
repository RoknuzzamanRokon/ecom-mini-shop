from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import path
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Count
from django.core.exceptions import PermissionDenied, ValidationError

from .models import (
    LOW_STOCK_THRESHOLD, Category, Order, OrderItem, Product, ProductImage,
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


# Shop and seller statuses the storefront shows, as in Product.is_publicly_visible
# and ProductQuerySet.public(). The product form's storefront checklist and
# preview (admin_product_form.js) are built from these.
LIVE_PARTNER_STATUSES = ("APPROVED", "ACTIVE")


class ProductPhotoInput(forms.ClearableFileInput):
    """The main photo as a preview panel with Upload / Replace / Remove / Open
    (templates/admin/widgets/mp_product_photo.html).

    Still a ClearableFileInput, so the file input and its "-clear" checkbox
    post exactly as before. Rendered through the project template engine for
    the reason rbac/widgets.py gives: the form renderer never sees
    TEMPLATES["DIRS"], where every other admin override lives.
    """

    template_name = "admin/widgets/mp_product_photo.html"

    def render(self, name, value, attrs=None, renderer=None):
        context = self.get_context(name, value, attrs)
        return mark_safe(render_to_string(self.template_name, context))


class ProductImageInlineForm(forms.ModelForm):
    class Meta:
        # A bare file input: a tile shows the saved photo itself, so the
        # "Currently: <path>" line of the admin's file widget has no place.
        # An empty input on a saved row keeps its file.
        widgets = {"image": forms.FileInput}
        labels = {"order": "Position"}


class ProductImageInline(admin.StackedInline):
    """Gallery photos as image tiles inside the product form's Photos card
    (templates/admin/edit_inline/mp_gallery.html).

    extra=0: rows are added by the card's "Add photos" tile, one per picked or
    dropped file (static/js/admin_product_form.js), so no blank row sits in
    the grid waiting to fail validation.
    """

    model = ProductImage
    form = ProductImageInlineForm
    extra = 0
    fields = ("image", "order")
    template = "admin/edit_inline/mp_gallery.html"


class ProductAdminForm(forms.ModelForm):
    """The card layout (see ProductAdmin.get_fieldsets) puts labels above fields, where
    Django's trailing ":" reads oddly; money inputs get the ৳ prefix hook."""

    LABELS = {
        "image": "Main photo",
        "is_active": "Active",
    }

    HELP_TEXTS = {
        "slug": "The product's web address. Filled in from the name.",
        "badge": "Optional label on the product card: NEW, HOT, SALE or TOP.",
        "status": "Only Published products can appear on the storefront.",
        "is_active": "Switch off to hide the product without changing its status.",
    }

    class Meta:
        widgets = {"image": ProductPhotoInput}

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        for name, label in self.LABELS.items():
            if name in self.fields:
                self.fields[name].label = label
        for name, text in self.HELP_TEXTS.items():
            if name in self.fields:
                self.fields[name].help_text = text
        for name in ("price", "old_price"):
            if name in self.fields:
                widget = self.fields[name].widget
                widget.attrs["class"] = f"{widget.attrs.get('class', '')} mp-money".strip()


def storefront_checks(product):
    """What decides whether `product` shows on the storefront, one check per
    condition of Product.is_publicly_visible. Works on an unsaved product too
    (the add form), where every relation may still be empty."""
    category = product.category if product.category_id else None
    shop = product.shop if product.shop_id else None
    seller = shop.owner if shop else None
    return [
        {"key": "active", "ok": bool(product.is_active),
         "label": "Active switch is on", "detail": ""},
        {"key": "published", "ok": product.status == Product.STATUS_PUBLISHED,
         "label": "Status is Published", "detail": product.get_status_display()},
        {"key": "category", "ok": bool(category and category.is_active),
         "label": "Category is active", "detail": category.name if category else "None chosen"},
        {"key": "shop", "ok": bool(shop and shop.status in LIVE_PARTNER_STATUSES),
         "label": "Shop is approved", "detail": shop.name if shop else "None chosen"},
        {"key": "seller", "ok": bool(seller and seller.status in LIVE_PARTNER_STATUSES),
         "label": "Seller is approved", "detail": seller.business_name if seller else "No shop"},
    ]


@admin.register(Product)
class ProductAdmin(StatusBadgeMixin, admin.ModelAdmin):
    form = ProductAdminForm
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
    readonly_fields = ("current_image", "storefront_checklist")
    # The only inline: change_form.html draws it inside the Photos card.
    inlines = [ProductImageInline]

    def get_fieldsets(self, request, obj=None):
        # Cards in the order a product is written: what it is, how it looks,
        # what it costs. "mp-form" is the stacked two-column card layout in
        # japanese_admin.css. templates/admin/shop/product/change_form.html
        # puts "mp-side" cards in the right-hand column and draws the
        # "mp-media" card as the Photos card, with the gallery inline inside.
        # Moderation is admin-only bookkeeping, so it starts folded away when
        # adding and open when editing.
        moderation_classes = ("mp-form",) if obj else ("mp-form", "collapse")
        # A view-only account gets the photo itself; the read-only form of
        # the file field is only a link to its path.
        can_edit = obj is None or self.has_change_permission(request, obj)
        return (
            ("Product details", {
                "classes": ("mp-form",),
                "fields": ("name", "slug", "category", "shop", "description"),
            }),
            ("Photos", {
                "classes": ("mp-form", "mp-media"),
                "description": "The main photo leads the product card and the product page; gallery photos follow it in position order.",
                "fields": ("image",) if can_edit else ("current_image",),
            }),
            ("Pricing & inventory", {
                "classes": ("mp-form",),
                "description": "Prices in Taka (৳). Old price is the struck-through “was” price; leave it empty when there is no discount.",
                "fields": ("price", "old_price", "stock", "badge"),
            }),
            ("Moderation", {
                "classes": moderation_classes,
                "fields": ("submitted_at", "reviewed_at", "reviewed_by", "rejection_reason"),
            }),
            ("Visibility", {
                "classes": ("mp-form", "mp-side"),
                "fields": ("status", "is_active", "storefront_checklist"),
            }),
        )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category', 'shop', 'shop__owner')

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        saved = obj
        if obj is not None and obj.pk and request.method == "POST":
            # A failed save re-renders with the posted values already copied
            # onto `obj` by the form; the header describes the stored product.
            saved = self.get_queryset(request).get(pk=obj.pk)
        context.update(self._product_page_context(saved))
        return super().render_change_form(request, context, add, change, form_url, obj)

    def _product_page_context(self, obj):
        """The summary header's figures (`mp_saved`, `mp_product`) and the data
        the live checklist and storefront preview read (json_script
        "mp-product-data")."""
        Shop = Product._meta.get_field("shop").related_model
        page_data = {
            "categories": {
                str(row["pk"]): {"name": row["name"], "live": row["is_active"]}
                for row in Category.objects.values("pk", "name", "is_active")
            },
            "shops": {
                str(row["pk"]): {
                    "name": row["name"],
                    "live": row["status"] in LIVE_PARTNER_STATUSES,
                    "seller": row["owner__business_name"],
                    "sellerLive": row["owner__status"] in LIVE_PARTNER_STATUSES,
                }
                for row in Shop.objects.values(
                    "pk", "name", "status", "owner__business_name", "owner__status"
                )
            },
        }
        context = {"mp_product_data": page_data}
        if obj is None or obj.pk is None:
            return context

        context["mp_saved"] = obj

        inventory = ProductInventory.objects.filter(product=obj).first()
        gallery = list(obj.images.all())
        available = inventory.available_quantity if inventory else obj.stock
        if available == 0:
            stock_state = "out"
        elif available <= LOW_STOCK_THRESHOLD:
            stock_state = "low"
        else:
            stock_state = "ok"
        is_live = obj.is_publicly_visible
        storefront_url = getattr(settings, "STOREFRONT_URL", "http://localhost:3000").rstrip("/")
        context["mp_product"] = {
            "inventory": inventory,
            "available": available,
            "stock_state": stock_state,
            "photo_count": len(gallery) + (1 if obj.image else 0),
            # The storefront card shows the main photo or a placeholder, never a
            # gallery photo; the header thumbnail may fall back to one.
            "cover_url": obj.image.url if obj.image else "",
            "thumb_url": obj.image.url if obj.image else (gallery[0].image.url if gallery else ""),
            "is_live": is_live,
            # The Next.js product page 404s for anything not public, so the
            # link is offered only when it will open.
            "storefront_url": f"{storefront_url}/product/{obj.slug}" if is_live else "",
            "seller": obj.seller,
        }
        return context

    def seller_display(self, obj):
        seller = getattr(obj, 'seller', None)
        return seller.business_name if seller else "-"
    seller_display.short_description = "Seller"

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:40px;border-radius:4px;" />', obj.image.url)
        return "-"
    image_preview.short_description = "Image"

    @admin.display(description="Main photo")
    def current_image(self, obj):
        if not obj or not obj.image:
            return "-"
        return format_html('<img class="mp-image-preview" src="{}" alt="" />', obj.image.url)

    @admin.display(description="Storefront checklist")
    def storefront_checklist(self, obj):
        checks = storefront_checks(obj)
        return render_to_string("admin/shop/product/storefront_checklist.html", {
            "checks": checks,
            "passed": sum(check["ok"] for check in checks),
            "total": len(checks),
        })


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

    # `allowed_permissions` is what keeps these actions off a read-only account.
    # The changelist opens with view permission alone, and a custom action that
    # declares nothing runs for anyone who can reach it -- so without this the
    # five actions below handed every order-viewer the full OrderService
    # lifecycle: inventory release, sale finalization and automatic refunds.
    def confirm_orders(self, request, queryset):
        self._transition_orders(request, queryset, 'CONFIRMED')
    confirm_orders.short_description = "Mark selected orders as Confirmed"
    confirm_orders.allowed_permissions = ("change",)

    def mark_orders_processing(self, request, queryset):
        self._transition_orders(request, queryset, 'PROCESSING')
    mark_orders_processing.short_description = "Mark selected orders as Processing"
    mark_orders_processing.allowed_permissions = ("change",)

    def mark_orders_shipped(self, request, queryset):
        self._transition_orders(request, queryset, 'SHIPPED')
    mark_orders_shipped.short_description = "Mark selected orders as Shipped"
    mark_orders_shipped.allowed_permissions = ("change",)

    def mark_orders_delivered(self, request, queryset):
        self._transition_orders(request, queryset, 'DELIVERED')
    mark_orders_delivered.short_description = "Mark selected orders as Delivered"
    mark_orders_delivered.allowed_permissions = ("change",)

    def cancel_orders(self, request, queryset):
        self._transition_orders(request, queryset, 'CANCELLED')
    cancel_orders.short_description = "Mark selected orders as Cancelled"
    cancel_orders.allowed_permissions = ("change",)

    def _transition_orders(self, request, queryset, new_status):
        # Belt and braces: `allowed_permissions` gates the action, and this gates
        # the service call, so a future action wired to this helper cannot quietly
        # reintroduce the bypass.
        if not self.has_change_permission(request):
            raise PermissionDenied

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

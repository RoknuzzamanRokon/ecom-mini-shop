from decimal import Decimal
from rest_framework import serializers
from customers.services import rating_breakdown
from shops.models import Shop
from .models import Category, Product, ProductImage, Order, OrderItem, ProductInventory, InventoryTransaction, Payment, Refund


class ShopSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = ["id", "name", "slug", "status"]


class CategorySerializer(serializers.ModelSerializer):
    products_count = serializers.IntegerField(read_only=True, default=0)
    image_url = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "icon",
            "is_active",
            "products_count",
            "image_url",
            "description",
            "created_at",
            "updated_at",
        ]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and hasattr(obj.image, "url"):
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url

        first_product = obj.products.filter(is_active=True).exclude(image="").first()
        if first_product and first_product.image and hasattr(first_product.image, "url"):
            if request:
                return request.build_absolute_uri(first_product.image.url)
            return first_product.image.url
        return None

    def get_description(self, obj):
        if obj.description:
            return obj.description
        CATEGORY_DESCRIPTIONS = {
            "clothing": "Curated essentials designed for everyday comfort, timeless modern silhouettes, and architectural elegance.",
            "electronics": "Cutting-edge audio, custom mechanical keyboards, smart wearable tech, and innovative everyday workspace accessories.",
            "shoes": "Step into comfort and style with everyday canvas sneakers, trail runners, athletic footwear, and lightweight soles.",
            "watches": "Precision timepieces featuring genuine leather straps, scratch-resistant dials, and timeless chronograph detailing.",
            "jewellery": "Handcrafted sterling silver necklaces, delicate pendants, and natural stone beaded bracelet sets.",
            "health-and-beauty": "Formulated with clean botanical extracts, refreshing natural serums, and daily restorative wellness essentials.",
            "kids-and-babies": "Ultra-soft gentle cotton essentials, playful educational puzzle sets, and durable wear for the little ones.",
            "sports": "High-performance workout equipment, premium yoga mats, and rugged essentials designed to keep you moving.",
            "home-and-garden": "Elevate your living spaces with functional home decor, modern planters, cozy textures, and indoor botanicals.",
        }
        return CATEGORY_DESCRIPTIONS.get(obj.slug, "Explore our curated collection of quality products.")


class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "image", "image_url", "order"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and hasattr(obj.image, "url"):
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class ProductListSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    shop = ShopSummarySerializer(read_only=True)
    image_url = serializers.SerializerMethodField()
    discount_percent = serializers.ReadOnlyField()
    savings_amount = serializers.ReadOnlyField()
    in_stock = serializers.ReadOnlyField()
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "category",
            "shop",
            "description",
            "price",
            "old_price",
            "image",
            "image_url",
            "stock",
            "badge",
            "is_active",
            "status",
            "discount_percent",
            "savings_amount",
            "in_stock",
            "average_rating",
            "review_count",
            "created_at",
        ]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and hasattr(obj.image, "url"):
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_average_rating(self, obj):
        value = getattr(obj, "average_rating", None)
        return round(float(value), 1) if value is not None else 0.0


class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    all_image_urls = serializers.SerializerMethodField()
    # Detail only: one extra GROUP BY query, which the list endpoints don't pay.
    rating_breakdown = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "images",
            "all_image_urls",
            "rating_breakdown",
        ]

    def get_rating_breakdown(self, obj):
        return rating_breakdown(obj.customer_reviews.all())

    def get_all_image_urls(self, obj):
        request = self.context.get("request")
        urls = []
        for img in obj.all_images:
            if hasattr(img, "url"):
                urls.append(
                    request.build_absolute_uri(img.url) if request else img.url
                )
        return urls


class SellerProductSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for seller self-service product operations.
    Exposes shop details, lifecycle status, review data, and pricing analytics.
    """
    category = CategorySerializer(read_only=True)
    shop = ShopSummarySerializer(read_only=True)
    image_url = serializers.SerializerMethodField()
    discount_percent = serializers.ReadOnlyField()
    savings_amount = serializers.ReadOnlyField()
    in_stock = serializers.ReadOnlyField()
    owner_business_name = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "category",
            "shop",
            "owner_business_name",
            "description",
            "price",
            "old_price",
            "stock",
            "badge",
            "is_active",
            "status",
            "rejection_reason",
            "image",
            "image_url",
            "discount_percent",
            "savings_amount",
            "in_stock",
            "created_at",
            "updated_at",
        ]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and hasattr(obj.image, "url"):
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None

    def get_owner_business_name(self, obj):
        return obj.shop.owner.business_name if obj.shop and obj.shop.owner else None


class SellerProductCreateSerializer(serializers.Serializer):
    """
    Input validation serializer for seller product creation.
    Validates category, seller-owned shop, pricing, and product attributes.
    """
    name = serializers.CharField(max_length=200)
    category_id = serializers.IntegerField()
    # Optional: a Shop Owner has exactly one assigned Shop, so the backend
    # auto-resolves it (see SellerProductListCreateAPIView.post). If a client
    # still sends shop_id, it is validated exactly as before and must match
    # the seller's own Shop — it can never be used to target another seller's Shop.
    shop_id = serializers.IntegerField(required=False)
    description = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    old_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    stock = serializers.IntegerField(min_value=0, default=0, required=False)
    badge = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    image = serializers.ImageField(required=False, allow_null=True)
    is_active = serializers.BooleanField(default=True, required=False)

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Product name cannot be empty.")
        return name

    def validate_price(self, value):
        if value <= Decimal("0.00"):
            raise serializers.ValidationError("Price must be strictly greater than 0.")
        return value

    def validate_old_price(self, value):
        if value is not None and value <= Decimal("0.00"):
            raise serializers.ValidationError("Old price must be strictly greater than 0.")
        return value

    def validate_category_id(self, value):
        try:
            return Category.objects.get(id=value, is_active=True)
        except Category.DoesNotExist:
            raise serializers.ValidationError(f"Active category with ID {value} does not exist.")

    def validate_shop_id(self, value):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "seller_profile"):
            raise serializers.ValidationError("Authenticated seller profile is required.")

        seller = request.user.seller_profile
        try:
            shop = Shop.objects.get(id=value)
        except Shop.DoesNotExist:
            raise serializers.ValidationError(f"Shop with ID {value} does not exist.")

        if shop.owner != seller:
            raise serializers.ValidationError("You can only create products for shops that you own.")

        if shop.status not in (Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE):
            raise serializers.ValidationError(
                f"Shop '{shop.name}' is currently '{shop.status}'. Products can only be created for active/approved shops."
            )

        return shop


class SellerProductUpdateSerializer(serializers.Serializer):
    """
    Input validation serializer for seller product updates.
    Enforces shop ownership constraints and validates updated values.
    """
    name = serializers.CharField(max_length=200, required=False)
    category_id = serializers.IntegerField(required=False)
    shop_id = serializers.IntegerField(required=False)
    description = serializers.CharField(required=False)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    old_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    stock = serializers.IntegerField(min_value=0, required=False)
    badge = serializers.CharField(max_length=20, required=False, allow_blank=True)
    image = serializers.ImageField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False)

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Product name cannot be empty.")
        return name

    def validate_price(self, value):
        if value <= Decimal("0.00"):
            raise serializers.ValidationError("Price must be strictly greater than 0.")
        return value

    def validate_old_price(self, value):
        if value is not None and value <= Decimal("0.00"):
            raise serializers.ValidationError("Old price must be strictly greater than 0.")
        return value

    def validate_category_id(self, value):
        try:
            return Category.objects.get(id=value, is_active=True)
        except Category.DoesNotExist:
            raise serializers.ValidationError(f"Active category with ID {value} does not exist.")

    def validate_shop_id(self, value):
        request = self.context.get("request")
        if not request or not hasattr(request.user, "seller_profile"):
            raise serializers.ValidationError("Authenticated seller profile is required.")

        seller = request.user.seller_profile
        try:
            shop = Shop.objects.get(id=value)
        except Shop.DoesNotExist:
            raise serializers.ValidationError(f"Shop with ID {value} does not exist.")

        if shop.owner != seller:
            raise serializers.ValidationError("You can only assign products to shops that you own.")

        if shop.status not in (Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE):
            raise serializers.ValidationError(
                f"Shop '{shop.name}' is currently '{shop.status}'. Products can only belong to active/approved shops."
            )

        return shop



class OrderItemInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class OrderItemSerializer(serializers.ModelSerializer):
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    product_image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_name",
            "product_slug",
            "product_image",
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
        ]

    def get_product_image(self, obj):
        if obj.product and obj.product.image:
            return obj.product.image.url
        return None


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    discount_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    shipping_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_items_count = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    payment = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "can_cancel",
            "payment",
            "customer_name",
            "phone",
            "address",
            "city",
            "shipping_recipient_name",
            "shipping_phone",
            "shipping_address_line_1",
            "shipping_address_line_2",
            "shipping_area",
            "shipping_city",
            "shipping_state",
            "shipping_postal_code",
            "shipping_country",
            "subtotal",
            "discount_total",
            "shipping_fee",
            "total_amount",
            "total_items_count",
            "created_at",
            "updated_at",
            "items",
        ]

    def get_total_items_count(self, obj):
        return sum(item.quantity for item in obj.items.all())

    def get_can_cancel(self, obj):
        return obj.can_transition_to(Order.STATUS_CANCELLED)

    def get_payment(self, obj):
        current = obj.current_payment
        if not current:
            return None
        return {
            "payment_number": current.payment_number,
            "payment_method": current.payment_method,
            "status": current.status,
            "amount": str(current.amount),
            "currency": current.currency,
            "paid_at": current.paid_at,
            "is_paid": (current.status == Payment.STATUS_PAID),
        }


class OrderCancelSerializer(serializers.Serializer):
    """
    Input validation serializer for customer order cancellation.
    Allows optional cancellation reason. Rejects arbitrary status updates.
    """
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500,
        help_text="Optional customer reason for cancelling the order.",
    )


class OrderCreateSerializer(serializers.Serializer):
    """
    Input serializer for order creation from authenticated cart.
    Client-provided prices/totals/items are strictly ignored.
    """
    address_id = serializers.IntegerField(required=False, allow_null=True)
    customer_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    shipping_recipient_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    shipping_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    shipping_address_line_1 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    shipping_address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    shipping_area = serializers.CharField(max_length=100, required=False, allow_blank=True)
    shipping_city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    shipping_state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    shipping_postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    shipping_country = serializers.CharField(max_length=100, required=False, allow_blank=True)
    items = serializers.ListField(required=False, write_only=True)


# ---------------------------------------------------------------------------
# Seller Order Management Serializers
# ---------------------------------------------------------------------------

class SellerOrderItemSerializer(serializers.ModelSerializer):
    """
    Serializer for order items presented to a seller.
    Includes only product, shop, pricing, and quantity details relevant to the seller.
    """
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_name",
            "product_slug",
            "shop",
            "shop_name",
            "seller",
            "seller_name",
            "unit_price",
            "quantity",
            "line_total",
            "created_at",
        ]


class SellerOrderListSerializer(serializers.ModelSerializer):
    """
    Summary serializer for seller order listing.
    Filters items to only include items belonging to the requesting seller.
    """
    items = serializers.SerializerMethodField()
    seller_subtotal = serializers.SerializerMethodField()
    seller_item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "seller_subtotal",
            "seller_item_count",
            "total_amount",
            "created_at",
            "updated_at",
            "items",
        ]

    def _get_seller_items(self, obj):
        if hasattr(obj, "seller_items"):
            return obj.seller_items
        request = self.context.get("request")
        if request and hasattr(request.user, "seller_profile"):
            seller = request.user.seller_profile
            return [
                item for item in obj.items.all()
                if item.seller == seller or (item.shop and item.shop.owner == seller)
            ]
        return obj.items.all()

    def get_items(self, obj):
        items = self._get_seller_items(obj)
        return SellerOrderItemSerializer(items, many=True, context=self.context).data

    def get_seller_subtotal(self, obj):
        items = self._get_seller_items(obj)
        return str(sum(Decimal(str(item.line_total)) for item in items))

    def get_seller_item_count(self, obj):
        items = self._get_seller_items(obj)
        return sum(item.quantity for item in items)


class SellerOrderDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for seller order fulfillment.
    Provides shipping address snapshot, seller items, and seller-scoped totals.
    Strictly excludes customer auth, credentials, internal IDs, and unrelated merchant items.
    """
    items = serializers.SerializerMethodField()
    seller_subtotal = serializers.SerializerMethodField()
    seller_item_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "shipping_recipient_name",
            "shipping_phone",
            "shipping_address_line_1",
            "shipping_address_line_2",
            "shipping_area",
            "shipping_city",
            "shipping_state",
            "shipping_postal_code",
            "shipping_country",
            "customer_name",
            "phone",
            "address",
            "city",
            "seller_subtotal",
            "seller_item_count",
            "total_amount",
            "created_at",
            "updated_at",
            "items",
        ]

    def _get_seller_items(self, obj):
        if hasattr(obj, "seller_items"):
            return obj.seller_items
        request = self.context.get("request")
        if request and hasattr(request.user, "seller_profile"):
            seller = request.user.seller_profile
            return [
                item for item in obj.items.all()
                if item.seller == seller or (item.shop and item.shop.owner == seller)
            ]
        return obj.items.all()

    def get_items(self, obj):
        items = self._get_seller_items(obj)
        return SellerOrderItemSerializer(items, many=True, context=self.context).data

    def get_seller_subtotal(self, obj):
        items = self._get_seller_items(obj)
        return str(sum(Decimal(str(item.line_total)) for item in items))

    def get_seller_item_count(self, obj):
        items = self._get_seller_items(obj)
        return sum(item.quantity for item in items)


class SellerOrderStatusUpdateSerializer(serializers.Serializer):
    """
    Input serializer for seller order status update.
    Validates status parameter and rejects unauthorized client mutations.
    """
    status = serializers.ChoiceField(choices=Order.STATUS_CHOICES)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class ProductInventorySerializer(serializers.ModelSerializer):
    """
    Authoritative representation of a product's current inventory status.
    """
    product_id = serializers.ReadOnlyField(source="product.id")
    product_name = serializers.ReadOnlyField(source="product.name")
    product_slug = serializers.ReadOnlyField(source="product.slug")
    total_quantity = serializers.ReadOnlyField()

    class Meta:
        model = ProductInventory
        fields = [
            "id",
            "product_id",
            "product_name",
            "product_slug",
            "available_quantity",
            "reserved_quantity",
            "sold_quantity",
            "total_quantity",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "product_id",
            "product_name",
            "product_slug",
            "reserved_quantity",
            "sold_quantity",
            "total_quantity",
            "created_at",
            "updated_at",
        ]


class InventoryAdjustmentSerializer(serializers.Serializer):
    """
    Input serializer for authorized seller stock adjustments.
    Requires signed quantity delta (non-zero) and optional reason note.
    """
    quantity = serializers.IntegerField(
        required=True,
        help_text="Signed stock quantity change (positive to increment, negative to decrement). Cannot be 0.",
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500,
        help_text="Operational justification for the stock adjustment.",
    )

    def validate_quantity(self, value):
        if value == 0:
            raise serializers.ValidationError("Adjustment quantity cannot be zero.")
        return value


class InventoryTransactionSerializer(serializers.ModelSerializer):
    """
    Serializer for immutable inventory transaction audit records.
    """
    product_id = serializers.ReadOnlyField(source="product.id")
    product_name = serializers.ReadOnlyField(source="product.name")
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = InventoryTransaction
        fields = [
            "id",
            "product_id",
            "product_name",
            "transaction_type",
            "quantity",
            "before_available",
            "after_available",
            "before_reserved",
            "after_reserved",
            "before_sold",
            "after_sold",
            "actor_name",
            "reason",
            "created_at",
        ]
        read_only_fields = fields

    def get_actor_name(self, obj):
        if obj.actor:
            return obj.actor.get_full_name() or obj.actor.username
        return "System"


class RefundSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    payment_number = serializers.CharField(source="payment.payment_number", read_only=True)
    processed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Refund
        fields = [
            "id",
            "refund_number",
            "order_id",
            "order_number",
            "payment_id",
            "payment_number",
            "amount",
            "currency",
            "reason",
            "status",
            "processed_by_name",
            "transaction_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_processed_by_name(self, obj):
        if obj.processed_by:
            return obj.processed_by.get_full_name() or obj.processed_by.username
        return "System"


class PaymentSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    refunds = RefundSerializer(many=True, read_only=True)
    refundable_amount = serializers.SerializerMethodField()
    is_paid = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id",
            "payment_number",
            "order_id",
            "order_number",
            "payment_method",
            "status",
            "amount",
            "currency",
            "transaction_id",
            "provider",
            "failure_reason",
            "metadata",
            "is_paid",
            "refundable_amount",
            "refunds",
            "paid_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_is_paid(self, obj):
        return obj.status == Payment.STATUS_PAID

    def get_refundable_amount(self, obj):
        completed_refunds_sum = sum(r.amount for r in obj.refunds.filter(status=Refund.STATUS_COMPLETED))
        return max(Decimal("0.00"), obj.amount - completed_refunds_sum)


class PaymentInitiateSerializer(serializers.Serializer):
    """
    Validates customer payment initiation.
    Server calculates amount strictly from the Order.
    Client amount or status is strictly forbidden/ignored.
    """
    payment_method = serializers.ChoiceField(
        choices=Payment.METHOD_CHOICES,
        default=Payment.METHOD_CASH_ON_DELIVERY,
        help_text="Chosen payment method for the order.",
    )


class PaymentVerifySerializer(serializers.Serializer):
    """
    Validates administrative/staff payment verification.
    """
    status = serializers.ChoiceField(
        choices=[Payment.STATUS_PAID, Payment.STATUS_FAILED],
        help_text="Target payment status (PAID or FAILED).",
    )
    transaction_id = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=100,
        help_text="Optional transaction or reference ID from payment provider.",
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500,
        help_text="Notes or failure justification.",
    )


class RefundCreateSerializer(serializers.Serializer):
    """
    Validates administrative/staff refund requests.
    """
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        help_text="Refund amount. Defaults to remaining full refundable amount if omitted.",
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500,
        help_text="Justification for this refund.",
    )


# -------------------------------------------------------------------------
# Staff & Admin Order Serializers (Task 16)
# -------------------------------------------------------------------------

class StaffOrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="product.id", allow_null=True, read_only=True)
    shop_id = serializers.IntegerField(source="shop.id", allow_null=True, read_only=True)
    seller_id = serializers.IntegerField(source="seller.id", allow_null=True, read_only=True)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product_id",
            "product_name",
            "product_slug",
            "shop_id",
            "shop_name",
            "seller_id",
            "seller_name",
            "unit_price",
            "price",
            "quantity",
            "line_total",
            "subtotal",
            "created_at",
        ]


class StaffOrderPaymentSummarySerializer(serializers.ModelSerializer):
    is_paid = serializers.BooleanField(read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "payment_number",
            "payment_method",
            "status",
            "amount",
            "currency",
            "transaction_id",
            "provider",
            "failure_reason",
            "paid_at",
            "is_paid",
            "created_at",
        ]


class StaffOrderRefundSummarySerializer(serializers.ModelSerializer):
    processed_by = serializers.SerializerMethodField()

    class Meta:
        model = Refund
        fields = [
            "id",
            "refund_number",
            "amount",
            "currency",
            "status",
            "reason",
            "transaction_id",
            "processed_by",
            "created_at",
        ]

    def get_processed_by(self, obj):
        return obj.processed_by.username if obj.processed_by else None


class StaffOrderListSerializer(serializers.ModelSerializer):
    """
    Concise, operationally-focused representation for staff order listing.
    """
    customer = serializers.SerializerMethodField()
    total_items_count = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    discount_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    shipping_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "customer",
            "subtotal",
            "discount_total",
            "shipping_fee",
            "total_amount",
            "total_items_count",
            "payment_status",
            "payment_method",
            "shipping_city",
            "created_at",
            "updated_at",
        ]

    def get_customer(self, obj):
        user = obj.user
        profile = getattr(user, "customer_profile", None) if user else None
        name = (
            obj.shipping_recipient_name
            or (profile.display_name if profile else "")
            or (user.get_full_name() if user else "")
            or obj.customer_name
        )
        phone = obj.shipping_phone or (profile.phone if profile else "") or obj.phone
        return {
            "id": user.id if user else None,
            "username": user.username if user else "",
            "email": user.email if user else "",
            "name": name,
            "phone": phone,
        }

    def get_total_items_count(self, obj):
        return sum(item.quantity for item in obj.items.all())

    def get_payment_status(self, obj):
        current = obj.current_payment
        return current.status if current else None

    def get_payment_method(self, obj):
        current = obj.current_payment
        return current.payment_method if current else None


class StaffOrderDetailSerializer(serializers.ModelSerializer):
    """
    Comprehensive staff order detail representation with full audit,
    payment summary, refunds history, shipping snapshot, and allowed transitions.
    Never exposes raw passwords, tokens, or card CVVs.
    """
    customer = serializers.SerializerMethodField()
    shipping_address = serializers.SerializerMethodField()
    items = StaffOrderItemSerializer(many=True, read_only=True)
    payment = serializers.SerializerMethodField()
    refunds = serializers.SerializerMethodField()
    allowed_transitions = serializers.SerializerMethodField()
    total_items_count = serializers.SerializerMethodField()
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    discount_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    shipping_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "allowed_transitions",
            "customer",
            "shipping_address",
            "items",
            "subtotal",
            "discount_total",
            "shipping_fee",
            "total_amount",
            "total_items_count",
            "payment",
            "refunds",
            "created_at",
            "updated_at",
        ]

    def get_customer(self, obj):
        user = obj.user
        profile = getattr(user, "customer_profile", None) if user else None
        name = (
            obj.shipping_recipient_name
            or (profile.display_name if profile else "")
            or (user.get_full_name() if user else "")
            or obj.customer_name
        )
        phone = obj.shipping_phone or (profile.phone if profile else "") or obj.phone
        return {
            "id": user.id if user else None,
            "username": user.username if user else "",
            "email": user.email if user else "",
            "name": name,
            "phone": phone,
        }

    def get_shipping_address(self, obj):
        return {
            "recipient_name": obj.shipping_recipient_name or obj.customer_name,
            "phone": obj.shipping_phone or obj.phone,
            "address_line_1": obj.shipping_address_line_1 or obj.address,
            "address_line_2": obj.shipping_address_line_2,
            "area": obj.shipping_area,
            "city": obj.shipping_city or obj.city,
            "state": obj.shipping_state,
            "postal_code": obj.shipping_postal_code,
            "country": obj.shipping_country,
        }

    def get_payment(self, obj):
        current = obj.current_payment
        if not current:
            return None
        return StaffOrderPaymentSummarySerializer(current).data

    def get_refunds(self, obj):
        refunds_qs = obj.refunds.all().order_by("-created_at")
        return StaffOrderRefundSummarySerializer(refunds_qs, many=True).data

    def get_allowed_transitions(self, obj):
        return Order.VALID_TRANSITIONS.get(obj.status.upper() if obj.status else "", [])

    def get_total_items_count(self, obj):
        return sum(item.quantity for item in obj.items.all())


class StaffOrderStatusUpdateSerializer(serializers.Serializer):
    """
    Validates staff order status transition requests.
    Rejects arbitrary status values.
    """
    status = serializers.ChoiceField(
        choices=[
            Order.STATUS_CONFIRMED,
            Order.STATUS_PROCESSING,
            Order.STATUS_SHIPPED,
            Order.STATUS_DELIVERED,
            Order.STATUS_CANCELLED,
        ],
        help_text="Target order status.",
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500,
        help_text="Operational note or reason for the status transition.",
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500,
        help_text="Alternative alias for operational note.",
    )


# Re-export Admin Governance Serializers (Task 17)
from .admin_serializers import (
    AdminUserListSerializer,
    AdminUserDetailSerializer,
    AdminUserUpdateSerializer,
    AdminRoleSerializer,
    AdminRoleCreateSerializer,
    AdminRoleUpdateSerializer,
    AdminSellerSerializer,
    AdminSellerStatusUpdateSerializer,
    AdminShopSerializer,
    AdminShopStatusUpdateSerializer,
    AdminProductSerializer,
    AdminProductStatusUpdateSerializer,
    AdminCategorySerializer,
    AdminCustomerListSerializer,
    AdminCustomerDetailSerializer,
)

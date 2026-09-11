from decimal import Decimal
from rest_framework import serializers
from shops.models import Shop
from .models import Category, Product, ProductImage, Order, OrderItem


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
            "created_at",
        ]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and hasattr(obj.image, "url"):
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class ProductDetailSerializer(ProductListSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    all_image_urls = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + [
            "images",
            "all_image_urls",
        ]

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
    shop_id = serializers.IntegerField()
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
            "price",
            "quantity",
            "line_total",
            "subtotal",
            "created_at",
        ]


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    discount_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    shipping_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_items_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
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


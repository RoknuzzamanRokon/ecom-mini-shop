from decimal import Decimal

from rest_framework import serializers

from shop.models import Category, Product
from shop.serializers import CategorySerializer, ShopSummarySerializer
from .models import Cart, CartItem


class CartProductSummarySerializer(serializers.ModelSerializer):
    """
    Compact product summary for cart item representation.
    Omits sensitive internal fields and exposes public catalog attributes.
    """
    category = CategorySerializer(read_only=True)
    shop = ShopSummarySerializer(read_only=True)
    image_url = serializers.SerializerMethodField()
    in_stock = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "category",
            "shop",
            "price",
            "old_price",
            "image_url",
            "stock",
            "badge",
            "in_stock",
        ]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and hasattr(obj.image, "url"):
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class CartItemSerializer(serializers.ModelSerializer):
    """
    Serializer for individual line items in a cart.
    Calculates unit_price, line_total, and availability dynamically.
    """
    product = CartProductSummarySerializer(read_only=True)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    unavailable_reason = serializers.CharField(read_only=True)

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product",
            "quantity",
            "unit_price",
            "line_total",
            "is_available",
            "unavailable_reason",
            "created_at",
            "updated_at",
        ]


class CartSerializer(serializers.ModelSerializer):
    """
    Complete cart representation including items and calculated totals.
    """
    items = CartItemSerializer(many=True, read_only=True)
    total_items_count = serializers.IntegerField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    has_unavailable_items = serializers.BooleanField(read_only=True)

    class Meta:
        model = Cart
        fields = [
            "id",
            "items",
            "total_items_count",
            "total_amount",
            "has_unavailable_items",
            "created_at",
            "updated_at",
        ]


class CartItemCreateSerializer(serializers.Serializer):
    """
    Input validation for adding an item to the cart.
    Client-provided prices/totals are strictly rejected.
    """
    product_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(
        default=CartItem.MIN_QUANTITY,
        min_value=CartItem.MIN_QUANTITY,
        max_value=CartItem.MAX_QUANTITY,
    )


class CartItemUpdateSerializer(serializers.Serializer):
    """
    Input validation for modifying cart item quantity.
    """
    quantity = serializers.IntegerField(
        min_value=CartItem.MIN_QUANTITY,
        max_value=CartItem.MAX_QUANTITY,
    )

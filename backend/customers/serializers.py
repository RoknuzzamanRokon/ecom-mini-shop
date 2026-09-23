from decimal import Decimal
from rest_framework import serializers

from shop.models import Product
from shop.serializers import ProductListSerializer
from shops.models import Shop
from .models import Address, CustomerProfile, Favorite, Review, ShopReview


class CustomerProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for viewing customer profile and account details.
    """
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

    class Meta:
        model = CustomerProfile
        fields = [
            "id",
            "user_id",
            "username",
            "email",
            "first_name",
            "last_name",
            "display_name",
            "phone",
            "avatar",
            "date_of_birth",
            "gender",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CustomerProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for modifying customer profile and associated user identity fields.
    """
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    avatar = serializers.ImageField(required=False, allow_null=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=CustomerProfile.GENDER_CHOICES,
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = CustomerProfile
        fields = [
            "first_name",
            "last_name",
            "display_name",
            "phone",
            "avatar",
            "date_of_birth",
            "gender",
        ]


class AddressSerializer(serializers.ModelSerializer):
    """
    Serializer for viewing address details.
    """
    class Meta:
        model = Address
        fields = [
            "id",
            "label",
            "recipient_name",
            "phone",
            "address_line_1",
            "address_line_2",
            "area",
            "city",
            "state",
            "postal_code",
            "country",
            "latitude",
            "longitude",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AddressCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating customer delivery addresses with coordinate validation.
    """
    label = serializers.ChoiceField(
        choices=Address.LABEL_CHOICES,
        default=Address.LABEL_HOME,
        required=False,
    )
    country = serializers.CharField(max_length=100, default="Bangladesh", required=False)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    area = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    is_default = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = Address
        fields = [
            "label",
            "recipient_name",
            "phone",
            "address_line_1",
            "address_line_2",
            "area",
            "city",
            "state",
            "postal_code",
            "country",
            "latitude",
            "longitude",
            "is_default",
        ]

    def validate(self, attrs):
        lat = attrs.get("latitude")
        lng = attrs.get("longitude")

        # In partial updates, inspect instance if one coordinate is provided
        if self.instance:
            if "latitude" in attrs and "longitude" not in attrs:
                lng = self.instance.longitude
            elif "longitude" in attrs and "latitude" not in attrs:
                lat = self.instance.latitude

        if (lat is not None and lng is None) or (lng is not None and lat is None):
            raise serializers.ValidationError(
                "Both latitude and longitude must be provided together, or both left blank."
            )

        if lat is not None and not (Decimal("-90.0") <= Decimal(str(lat)) <= Decimal("90.0")):
            raise serializers.ValidationError({"latitude": "Latitude must be between -90 and 90 degrees."})

        if lng is not None and not (Decimal("-180.0") <= Decimal(str(lng)) <= Decimal("180.0")):
            raise serializers.ValidationError({"longitude": "Longitude must be between -180 and 180 degrees."})

        return attrs


class FavoriteSerializer(serializers.ModelSerializer):
    """
    Wishlist entry with the full public product payload so the storefront can
    render favourites with the same card component used across the catalog.
    """
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = Favorite
        fields = ["id", "product", "created_at"]
        read_only_fields = fields


class FavoriteCreateSerializer(serializers.Serializer):
    """
    Accepts a product id and resolves it against the public catalog only, so
    unpublished or suspended-shop products can never enter a wishlist.
    """
    product_id = serializers.IntegerField()

    def validate_product_id(self, value):
        if not Product.objects.public().filter(pk=value).exists():
            raise serializers.ValidationError("Product not found.")
        return value


class ReviewSerializer(serializers.ModelSerializer):
    """
    Read serializer for a product review.
    is_hidden / hidden_reason matter only to the author: public lists never
    include hidden reviews, and unhiding clears the reason, so every public row
    carries false / "".
    """
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    reviewer_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "user_id",
            "reviewer_name",
            "rating",
            "comment",
            "is_verified_purchase",
            "is_hidden",
            "hidden_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_reviewer_name(self, obj):
        """
        Public name shown beside the review: the display name the customer chose
        in their profile, then their full name, then their username. List
        querysets should select_related("user__customer_profile") so this costs
        no extra query per review.
        """
        # A missing profile raises RelatedObjectDoesNotExist, an AttributeError.
        profile = getattr(obj.user, "customer_profile", None)
        display_name = (profile.display_name or "").strip() if profile else ""
        return display_name or obj.user.get_full_name() or obj.user.username


class ReviewCreateSerializer(serializers.Serializer):
    """
    Accepts a product id and resolves it against the public catalog only, so
    unpublished or suspended-shop products can never receive a review.
    """
    product_id = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")

    def validate_product_id(self, value):
        if not Product.objects.public().filter(pk=value).exists():
            raise serializers.ValidationError("Product not found.")
        return value


class ReviewUpdateSerializer(serializers.Serializer):
    """
    Partial-update serializer for a product or shop review's rating/comment.
    Ownership is enforced at the view/permission layer, not here.
    """
    rating = serializers.IntegerField(min_value=1, max_value=5, required=False)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class ShopReviewSerializer(ReviewSerializer):
    """
    Read serializer for a shop review: the same public fields and reviewer-name
    rule as a product review.
    """

    class Meta(ReviewSerializer.Meta):
        model = ShopReview


class ShopReviewCreateSerializer(serializers.Serializer):
    """
    Accepts a shop id and resolves it against publicly visible shops only
    (APPROVED/ACTIVE, the same rule as the public shop endpoints), so draft,
    pending, rejected or suspended shops can never receive a review.
    """
    shop_id = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=2000, default="")

    def validate_shop_id(self, value):
        if not Shop.objects.filter(
            pk=value, status__in=[Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE]
        ).exists():
            raise serializers.ValidationError("Shop not found.")
        return value


def _media_url(request, file_field):
    """Absolute URL for an image field when a request is available, else its relative URL."""
    if not file_field or not hasattr(file_field, "url"):
        return None
    return request.build_absolute_uri(file_field.url) if request else file_field.url


class MyProductReviewSerializer(ReviewSerializer):
    """The caller's own product review, with enough of the product to show and link it."""
    product = serializers.SerializerMethodField()

    class Meta(ReviewSerializer.Meta):
        fields = ReviewSerializer.Meta.fields + ["product"]
        read_only_fields = fields

    def get_product(self, obj):
        product = obj.product
        return {
            "id": product.id,
            "name": product.name,
            "slug": product.slug,
            "image_url": _media_url(self.context.get("request"), product.image),
        }


class MyShopReviewSerializer(ReviewSerializer):
    """The caller's own shop review, with enough of the shop to show and link it."""
    shop = serializers.SerializerMethodField()

    class Meta(ReviewSerializer.Meta):
        model = ShopReview
        fields = ReviewSerializer.Meta.fields + ["shop"]
        read_only_fields = fields

    def get_shop(self, obj):
        shop = obj.shop
        return {
            "id": shop.id,
            "name": shop.name,
            "slug": shop.slug,
            "logo_url": _media_url(self.context.get("request"), shop.logo),
        }

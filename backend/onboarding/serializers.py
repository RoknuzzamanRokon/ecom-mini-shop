from rest_framework import serializers

from rbac.models import LoginPhone
from rbac.phone import INVALID_PHONE, PHONE_TAKEN, normalize_phone
from rbac.serializers import login_phone_number
from shop.admin_serializers import (
    AdminAccountFieldsSerializer,
    AdminSellerCreateSerializer,
    AdminShopCreateSerializer,
)
from shop.models import Product
from shops.models import Shop
from .models import TokenTransaction


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

class OnboardingAccountSerializer(AdminAccountFieldsSerializer):
    """
    The new seller's login account. Shop owners in the field often have no
    email address, so it takes an email or a Bangladeshi mobile number (or
    both), as public registration does; a number becomes the account's
    LoginPhone, so the seller signs in with it.
    """

    email = serializers.EmailField(max_length=254, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")

    def validate_username(self, value):
        # The sign-in field takes a username or a phone number (rbac.backends).
        if normalize_phone(value.strip()):
            raise serializers.ValidationError("A username cannot be a phone number.")
        return super().validate_username(value)

    def validate_email(self, value):
        if not value.strip():
            return ""
        return super().validate_email(value)

    def validate_phone(self, value):
        if not value.strip():
            return ""
        phone = normalize_phone(value)
        if phone is None:
            raise serializers.ValidationError(INVALID_PHONE)
        if LoginPhone.objects.filter(number=phone).exists():
            raise serializers.ValidationError(PHONE_TAKEN)
        return phone

    def validate(self, attrs):
        if not attrs.get("email") and not attrs.get("phone"):
            raise serializers.ValidationError("Enter an email address or a mobile number for the seller's account.")
        return super().validate(attrs)


class OnboardSellerSerializer(AdminSellerCreateSerializer):
    """
    POST /api/onboarding/sellers/: always a new account (no `user_id`), and
    no governance `reason`, since who onboarded the seller is recorded on it.
    """

    user_id = None
    reason = None
    account = OnboardingAccountSerializer()

    def validate(self, attrs):
        return attrs


class OnboardingShopSerializer(AdminShopCreateSerializer):
    """POST /api/onboarding/sellers/<pk>/shops/: the seller comes from the URL."""

    seller_id = None
    reason = None


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

class OnboardedProductSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source="category.name", default=None)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "category",
            "price",
            "old_price",
            "stock",
            "status",
            "rejection_reason",
            "image_url",
            "created_at",
        ]

    def get_image_url(self, obj):
        if not obj.image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url


class OnboardedShopSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(read_only=True)
    longitude = serializers.FloatField(read_only=True)
    products = OnboardedProductSerializer(many=True, read_only=True)

    class Meta:
        model = Shop
        fields = [
            "id",
            "name",
            "slug",
            "status",
            "rejection_reason",
            "phone",
            "additional_phones",
            "address",
            "latitude",
            "longitude",
            "created_at",
            "products",
        ]


class OnboardedSellerSerializer(serializers.Serializer):
    """One row of an onboarder's seller list, or of the review queue."""

    id = serializers.IntegerField()
    business_name = serializers.CharField()
    seller_type = serializers.CharField()
    status = serializers.CharField()
    rejection_reason = serializers.CharField()
    username = serializers.CharField(source="user.username")
    phone = serializers.SerializerMethodField()
    onboarded_by = serializers.CharField(source="created_by.username", default=None)
    shop_count = serializers.IntegerField()
    product_count = serializers.IntegerField()
    starting_points = serializers.IntegerField(source="onboarding.starting_points")
    tokens_awarded = serializers.IntegerField(source="onboarding.tokens_awarded")
    created_at = serializers.DateTimeField()

    def get_phone(self, obj):
        return login_phone_number(obj.user)


class OnboardedSellerDetailSerializer(OnboardedSellerSerializer):
    """GET /api/onboarding/sellers/<pk>/ and /api/onboarding/review/<pk>/."""

    business_email = serializers.CharField()
    business_phone = serializers.CharField()
    tax_id = serializers.CharField()
    description = serializers.CharField()
    email = serializers.CharField(source="user.email")
    first_name = serializers.CharField(source="user.first_name")
    last_name = serializers.CharField(source="user.last_name")
    points_balance = serializers.IntegerField(
        help_text="Points the seller has left for product creation fees.",
    )
    approved_at = serializers.DateTimeField(source="onboarding.approved_at")
    reversed_at = serializers.DateTimeField(source="onboarding.reversed_at")
    points_returned = serializers.IntegerField(source="onboarding.points_returned")
    tokens_taken_back = serializers.IntegerField(source="onboarding.tokens_taken_back")
    shops = OnboardedShopSerializer(many=True)


class TokenTransactionSerializer(serializers.ModelSerializer):
    seller_name = serializers.CharField(source="seller.business_name", default=None)

    class Meta:
        model = TokenTransaction
        fields = [
            "id",
            "transaction_type",
            "amount",
            "balance_before",
            "balance_after",
            "reason",
            "seller",
            "seller_name",
            "created_at",
        ]

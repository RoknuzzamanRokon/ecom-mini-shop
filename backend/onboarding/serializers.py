from rest_framework import serializers

from points.serializers import MAX_POINTS_PER_MOVE
from rbac.models import LoginPhone
from rbac.phone import INVALID_PHONE, PHONE_TAKEN, normalize_phone
from rbac.serializers import login_phone_number
from shop.admin_serializers import (
    AdminAccountFieldsSerializer,
    AdminSellerCreateSerializer,
    AdminSellerUpdateSerializer,
    AdminShopCreateSerializer,
    AdminShopUpdateSerializer,
)
from shop.models import Product
from shop.serializers import SellerProductUpdateSerializer
from shops.models import Shop
from .models import TokenPayoutRequest, TokenTransaction


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


class PointSaleSerializer(serializers.Serializer):
    """POST /api/onboarding/sellers/<pk>/points/. The minimum purchase is PointService's rule."""

    amount = serializers.IntegerField(min_value=1, max_value=MAX_POINTS_PER_MOVE)


class OnboardingSellerUpdateSerializer(AdminSellerUpdateSerializer):
    """PATCH /api/onboarding/sellers/<pk>/ in an edit session: the business details, no `reason`."""

    reason = None


class OnboardingShopUpdateSerializer(AdminShopUpdateSerializer):
    """PATCH /api/onboarding/shops/<pk>/ in an edit session: profile and location, no `reason`."""

    reason = None


class OnboardingProductUpdateSerializer(SellerProductUpdateSerializer):
    """
    PATCH /api/onboarding/products/<pk>/ in an edit session: the seller's own
    product edit (stock with `expected_stock`), without moving it to another shop.
    """

    shop_id = None


class EditCodeSerializer(serializers.Serializer):
    """POST /api/onboarding/sellers/<pk>/edit-session/verify/: the 6-digit code the seller received."""

    code = serializers.RegexField(r"^\s*\d{6}\s*$", error_messages={"invalid": "Enter the 6-digit code."})


class PayoutRequestSerializer(serializers.Serializer):
    """POST /api/onboarding/payouts/."""

    tokens = serializers.IntegerField(min_value=1, max_value=1_000_000)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class PayoutAcceptSerializer(serializers.Serializer):
    """POST /api/onboarding/payouts/review/<pk>/accept/: how it was paid, optional."""

    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class PayoutRejectSerializer(serializers.Serializer):
    """POST /api/onboarding/payouts/review/<pk>/reject/."""

    reason = serializers.CharField(max_length=500)

    def validate_reason(self, value):
        if not value.strip():
            raise serializers.ValidationError("A reason is required to reject a payout request.")
        return value.strip()


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


class OnboardedProductDetailSerializer(OnboardedProductSerializer):
    """GET and PATCH /api/onboarding/products/<pk>/: everything the edit form needs."""

    category_id = serializers.IntegerField(read_only=True)
    shop_id = serializers.IntegerField(read_only=True)
    shop_name = serializers.CharField(source="shop.name", read_only=True)
    seller_id = serializers.IntegerField(source="shop.owner_id", read_only=True)
    seller_name = serializers.CharField(source="shop.owner.business_name", read_only=True)

    class Meta(OnboardedProductSerializer.Meta):
        fields = OnboardedProductSerializer.Meta.fields + [
            "category_id",
            "description",
            "badge",
            "is_active",
            "live_until",
            "shop_id",
            "shop_name",
            "seller_id",
            "seller_name",
        ]


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
            "description",
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
    product_count = serializers.IntegerField(
        allow_null=True,
        help_text=(
            "For an onboarder, the products they added; null without 'onboarding.products.view'. "
            "In the review queue, every product."
        ),
    )
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
            "payout_request",
            "created_at",
        ]


class TokenPayoutSerializer(serializers.ModelSerializer):
    requested_by = serializers.CharField(source="requested_by.username")
    decided_by = serializers.CharField(source="decided_by.username", default=None)

    class Meta:
        model = TokenPayoutRequest
        fields = [
            "id",
            "requested_by",
            "tokens",
            "taka_per_token",
            "amount_taka",
            "note",
            "status",
            "decided_by",
            "decided_at",
            "decision_note",
            "created_at",
        ]

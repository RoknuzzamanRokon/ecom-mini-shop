from rest_framework import serializers
from .models import Shop


class PublicShopSerializer(serializers.ModelSerializer):
    """
    Public shop representation for customer browsing.
    Excludes internal administrative and seller audit fields.
    """
    class Meta:
        model = Shop
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "logo",
            "cover_image",
            "phone",
            "address",
            "location",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class SellerShopSerializer(serializers.ModelSerializer):
    """
    Full view for the owning seller, including rejection/suspension reasons and visibility state.
    """
    owner_id = serializers.IntegerField(source="owner.id", read_only=True)
    owner_name = serializers.CharField(source="owner.business_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_publicly_visible = serializers.BooleanField(read_only=True)

    class Meta:
        model = Shop
        fields = [
            "id",
            "owner_id",
            "owner_name",
            "name",
            "slug",
            "description",
            "logo",
            "cover_image",
            "phone",
            "address",
            "location",
            "status",
            "status_display",
            "rejection_reason",
            "suspension_reason",
            "is_publicly_visible",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner_id",
            "owner_name",
            "slug",
            "status",
            "status_display",
            "rejection_reason",
            "suspension_reason",
            "is_publicly_visible",
            "created_at",
            "updated_at",
        ]


class SellerShopCreateSerializer(serializers.Serializer):
    """
    Validates payload for creating a new shop.
    """
    name = serializers.CharField(max_length=200, required=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    address = serializers.CharField(required=False, allow_blank=True, default="")
    location = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    logo = serializers.ImageField(required=False, allow_null=True)
    cover_image = serializers.ImageField(required=False, allow_null=True)
    submit_for_review = serializers.BooleanField(required=False, default=False)


class SellerShopUpdateSerializer(serializers.ModelSerializer):
    """
    Validates seller updates to existing shops. Prohibits altering owner or status directly.
    """
    class Meta:
        model = Shop
        fields = [
            "name",
            "description",
            "phone",
            "address",
            "location",
            "logo",
            "cover_image",
        ]


class StaffShopSerializer(serializers.ModelSerializer):
    """
    Comprehensive view for staff including review metadata and audit trails.
    """
    owner_id = serializers.IntegerField(source="owner.id", read_only=True)
    owner_name = serializers.CharField(source="owner.business_name", read_only=True)
    owner_username = serializers.CharField(source="owner.user.username", read_only=True)
    reviewed_by_username = serializers.CharField(source="reviewed_by.username", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Shop
        fields = [
            "id",
            "owner_id",
            "owner_name",
            "owner_username",
            "name",
            "slug",
            "description",
            "logo",
            "cover_image",
            "phone",
            "address",
            "location",
            "status",
            "status_display",
            "rejection_reason",
            "suspension_reason",
            "reviewed_by_username",
            "reviewed_at",
            "approved_at",
            "suspended_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ShopActionReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=True,
        min_length=3,
        error_messages={"required": "A reason must be provided for this action."},
    )

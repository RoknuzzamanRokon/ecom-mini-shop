from rest_framework import serializers
from .models import SellerProfile


class SellerProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    seller_type_display = serializers.CharField(source="get_seller_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_operational = serializers.BooleanField(read_only=True)
    is_suspended = serializers.BooleanField(read_only=True)

    class Meta:
        model = SellerProfile
        fields = [
            "id",
            "user",
            "username",
            "user_email",
            "seller_type",
            "seller_type_display",
            "status",
            "status_display",
            "business_name",
            "business_email",
            "business_phone",
            "tax_id",
            "description",
            "is_operational",
            "is_suspended",
            "rejection_reason",
            "suspension_reason",
            "reviewed_at",
            "approved_at",
            "suspended_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "status",
            "rejection_reason",
            "suspension_reason",
            "reviewed_at",
            "approved_at",
            "suspended_at",
            "created_at",
            "updated_at",
        ]


class SellerProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerProfile
        fields = [
            "business_name",
            "business_email",
            "business_phone",
            "tax_id",
            "description",
        ]


class SellerActionReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=True,
        min_length=3,
        error_messages={"required": "A reason must be provided for this action."},
    )

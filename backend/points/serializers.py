from rest_framework import serializers
from .models import PointTransaction, SellerWallet


class SellerWalletSerializer(serializers.ModelSerializer):
    seller_id = serializers.IntegerField(source="seller.id", read_only=True)
    business_name = serializers.CharField(source="seller.business_name", read_only=True)

    class Meta:
        model = SellerWallet
        fields = [
            "id",
            "seller_id",
            "business_name",
            "balance",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PointTransactionSerializer(serializers.ModelSerializer):
    seller_id = serializers.IntegerField(source="seller.id", read_only=True)
    business_name = serializers.CharField(source="seller.business_name", read_only=True)
    transaction_type_display = serializers.CharField(source="get_transaction_type_display", read_only=True)
    actor_id = serializers.IntegerField(source="actor.id", read_only=True, default=None)
    actor_username = serializers.CharField(source="actor.username", read_only=True, default=None)

    class Meta:
        model = PointTransaction
        fields = [
            "id",
            "wallet_id",
            "seller_id",
            "business_name",
            "transaction_type",
            "transaction_type_display",
            "amount",
            "balance_before",
            "balance_after",
            "reason",
            "reference_type",
            "reference_id",
            "actor_id",
            "actor_username",
            "created_at",
        ]
        read_only_fields = fields


class PointAdjustmentRequestSerializer(serializers.Serializer):
    ACTION_CHOICES = ["CREDIT", "DEBIT"]

    action = serializers.ChoiceField(
        choices=ACTION_CHOICES,
        required=True,
        help_text="Either 'CREDIT' to add points or 'DEBIT' to deduct points.",
    )
    amount = serializers.IntegerField(
        min_value=1,
        required=True,
        help_text="Positive integer amount of points to adjust.",
    )
    reason = serializers.CharField(
        min_length=3,
        required=True,
        help_text="Mandatory business reason for this adjustment.",
    )
    reference_type = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=100,
    )
    reference_id = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=100,
    )

from rest_framework import serializers
from .models import PointTransaction, SellerWallet
from .services import PointService


class SellerWalletSerializer(serializers.ModelSerializer):
    seller_id = serializers.IntegerField(source="seller.id", read_only=True)
    business_name = serializers.CharField(source="seller.business_name", read_only=True)

    # Known Issue #3. Both totals are aggregated from the PointTransaction ledger
    # on read, never stored on SellerWallet -- the ledger stays the single source
    # of truth for point movement (see PointService.get_ledger_totals).
    total_earned = serializers.SerializerMethodField()
    total_spent = serializers.SerializerMethodField()

    # Known Issue #11. The configured ProductCreationCost, so the seller UI can
    # stop hardcoding it. It belongs on this payload rather than a new endpoint:
    # it is a points-domain value, and this is the points resource the seller
    # already fetches before spending them.
    product_creation_cost = serializers.SerializerMethodField()

    class Meta:
        model = SellerWallet
        fields = [
            "id",
            "seller_id",
            "business_name",
            "balance",
            "total_earned",
            "total_spent",
            "product_creation_cost",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def _ledger_totals(self, obj):
        """One aggregate query per wallet, shared by both total fields."""
        cached = getattr(obj, "_cached_ledger_totals", None)
        if cached is None:
            cached = PointService.get_ledger_totals(obj.seller)
            obj._cached_ledger_totals = cached
        return cached

    def get_total_earned(self, obj) -> int:
        return self._ledger_totals(obj)["total_earned"]

    def get_total_spent(self, obj) -> int:
        return self._ledger_totals(obj)["total_spent"]

    def get_product_creation_cost(self, obj) -> int:
        return PointService.get_product_creation_cost()


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

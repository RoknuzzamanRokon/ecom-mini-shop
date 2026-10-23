from rest_framework import serializers
from .models import PointExpiryPolicy, PointTransaction, SellerWallet, StaffPointTransaction
from .services import PointService, seller_points_expire


# The most points one adjustment or transfer may move. Wallet balances are
# 32-bit columns; an unbounded amount overflowed them as a 500 (BUG-066).
MAX_POINTS_PER_MOVE = 1_000_000


class UpcomingExpirySerializer(serializers.Serializer):
    points = serializers.IntegerField()
    expires_at = serializers.DateTimeField()


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

    # Expiry: whether this seller's points expire at all (a Full Shop Owner's
    # never do), how long a batch lasts, the soonest batches to go, and what
    # has already expired unused.
    total_expired = serializers.SerializerMethodField()
    points_expire = serializers.SerializerMethodField()
    expiry_months = serializers.SerializerMethodField()
    upcoming_expiries = serializers.SerializerMethodField()

    class Meta:
        model = SellerWallet
        fields = [
            "id",
            "seller_id",
            "business_name",
            "balance",
            "total_earned",
            "total_spent",
            "total_expired",
            "product_creation_cost",
            "points_expire",
            "expiry_months",
            "upcoming_expiries",
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

    def get_total_expired(self, obj) -> int:
        return self._ledger_totals(obj)["total_expired"]

    def get_points_expire(self, obj) -> bool:
        return seller_points_expire(obj.seller)

    def get_expiry_months(self, obj) -> int:
        return PointExpiryPolicy.get_months()

    def get_upcoming_expiries(self, obj) -> list:
        if not seller_points_expire(obj.seller):
            return []
        return UpcomingExpirySerializer(PointService.upcoming_expiries(obj), many=True).data


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


class StaffPointTransactionSerializer(serializers.ModelSerializer):
    """One movement in the caller's own StaffWallet, for the Console profile."""

    transaction_type_display = serializers.CharField(source="get_transaction_type_display", read_only=True)
    # `amount` is always positive; the direction is read from the balances, as
    # get_ledger_totals and StaffPointTransaction.__str__ already do.
    direction = serializers.SerializerMethodField()
    counterparty_username = serializers.CharField(source="counterparty.username", read_only=True, default=None)
    seller_business_name = serializers.CharField(
        source="seller_transaction.seller.business_name", read_only=True, default=None
    )

    class Meta:
        model = StaffPointTransaction
        fields = [
            "id",
            "transaction_type",
            "transaction_type_display",
            "direction",
            "amount",
            "balance_before",
            "balance_after",
            "reason",
            "counterparty_username",
            "seller_business_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_direction(self, obj) -> str:
        return "IN" if obj.balance_after >= obj.balance_before else "OUT"


class PointAdjustmentRequestSerializer(serializers.Serializer):
    ACTION_CHOICES = ["CREDIT", "DEBIT"]

    action = serializers.ChoiceField(
        choices=ACTION_CHOICES,
        required=True,
        help_text="Either 'CREDIT' to add points or 'DEBIT' to deduct points.",
    )
    amount = serializers.IntegerField(
        min_value=1,
        max_value=MAX_POINTS_PER_MOVE,
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


class StaffPointExpiryRequestSerializer(serializers.Serializer):
    """A superuser turning point expiry on or off for one staff member."""

    enabled = serializers.BooleanField(required=True)
    reason = serializers.CharField(
        min_length=3,
        required=True,
        help_text="Mandatory business reason for the change.",
    )


class StaffPointTransferRequestSerializer(serializers.Serializer):
    """A superuser giving a staff member points (CREDIT) or taking them back (DEBIT)."""

    ACTION_CHOICES = ["CREDIT", "DEBIT"]

    action = serializers.ChoiceField(
        choices=ACTION_CHOICES,
        required=True,
        help_text="'CREDIT' to give the staff member points, 'DEBIT' to take them back.",
    )
    amount = serializers.IntegerField(
        min_value=1,
        max_value=MAX_POINTS_PER_MOVE,
        required=True,
        help_text="Positive integer amount of points to move.",
    )
    reason = serializers.CharField(
        min_length=3,
        required=True,
        help_text="Mandatory business reason for this transfer.",
    )

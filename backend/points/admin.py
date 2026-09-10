from django.contrib import admin
from .models import PointTransaction, SellerWallet


@admin.register(SellerWallet)
class SellerWalletAdmin(admin.ModelAdmin):
    list_display = ("seller", "balance", "created_at", "updated_at")
    search_fields = (
        "seller__business_name",
        "seller__user__username",
        "seller__user__email",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(PointTransaction)
class PointTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "seller",
        "transaction_type",
        "amount",
        "balance_before",
        "balance_after",
        "actor",
        "created_at",
    )
    list_filter = ("transaction_type", "created_at")
    search_fields = (
        "seller__business_name",
        "reason",
        "reference_type",
        "reference_id",
        "actor__username",
    )
    readonly_fields = (
        "wallet",
        "seller",
        "transaction_type",
        "amount",
        "balance_before",
        "balance_after",
        "reason",
        "reference_type",
        "reference_id",
        "actor",
        "created_at",
    )

    def has_add_permission(self, request):
        # Ledger records should only be created via PointService, not manually through admin form
        return False

    def has_delete_permission(self, request, obj=None):
        # Prevent manual tampering with immutable financial ledger entries
        return False

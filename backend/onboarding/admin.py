from django.contrib import admin

from .models import OnboardingSettings, SellerOnboarding, TokenTransaction, TokenWallet


@admin.register(OnboardingSettings)
class OnboardingSettingsAdmin(admin.ModelAdmin):
    list_display = ("starting_points", "tokens_per_seller", "updated_at")
    readonly_fields = ("updated_at",)

    def has_add_permission(self, request):
        # Singleton (pk=1) enforced in OnboardingSettings.save().
        return not OnboardingSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class ReadOnlyLedgerAdmin(admin.ModelAdmin):
    """Rows written only by OnboardingService and TokenService."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SellerOnboarding)
class SellerOnboardingAdmin(ReadOnlyLedgerAdmin):
    list_display = (
        "seller", "onboarded_by", "starting_points", "tokens_awarded", "approved_at", "reversed_at", "created_at",
    )
    list_filter = ("created_at", "approved_at", "reversed_at")
    search_fields = ("seller__business_name", "seller__user__username", "seller__created_by__username")
    readonly_fields = (
        "seller", "onboarded_by", "starting_points", "tokens_awarded", "approved_by", "approved_at",
        "reversed_at", "points_returned", "tokens_taken_back", "created_at",
    )
    list_select_related = ("seller", "seller__created_by")

    @admin.display(description="Onboarded by", ordering="seller__created_by__username")
    def onboarded_by(self, obj):
        return obj.seller.created_by


@admin.register(TokenWallet)
class TokenWalletAdmin(ReadOnlyLedgerAdmin):
    list_display = ("user", "balance", "updated_at")
    search_fields = ("user__username",)
    readonly_fields = ("user", "balance", "created_at", "updated_at")
    list_select_related = ("user",)


@admin.register(TokenTransaction)
class TokenTransactionAdmin(ReadOnlyLedgerAdmin):
    list_display = ("wallet", "transaction_type", "amount", "balance_after", "seller", "created_at")
    list_filter = ("transaction_type", "created_at")
    search_fields = ("wallet__user__username", "seller__business_name", "reason")
    readonly_fields = (
        "wallet", "transaction_type", "amount", "balance_before", "balance_after",
        "reason", "seller", "actor", "created_at",
    )
    list_select_related = ("wallet", "wallet__user", "seller")

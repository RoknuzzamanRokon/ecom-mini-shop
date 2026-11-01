from django.contrib import admin

from audit.admin_mixins import ConsoleManagedRuleMixin
from .models import (
    EditSession,
    OnboardingSettings,
    SellerOnboarding,
    TokenPayoutRequest,
    TokenTransaction,
    TokenWallet,
)


@admin.register(OnboardingSettings)
class OnboardingSettingsAdmin(ConsoleManagedRuleMixin, admin.ModelAdmin):
    list_display = (
        "starting_points", "tokens_per_seller", "taka_per_token", "edit_code_minutes", "edit_window_minutes",
        "updated_at",
    )


class ReadOnlyLedgerAdmin(admin.ModelAdmin):
    """Rows written only by OnboardingService, EditSessionService and TokenService."""

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
        "reason", "seller", "payout_request", "actor", "created_at",
    )
    list_select_related = ("wallet", "wallet__user", "seller")


@admin.register(TokenPayoutRequest)
class TokenPayoutRequestAdmin(ReadOnlyLedgerAdmin):
    """Settled in the Console (Token Payouts), which moves the tokens and audits the decision."""

    list_display = ("requested_by", "tokens", "amount_taka", "status", "decided_by", "decided_at", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("requested_by__username", "decided_by__username", "note", "decision_note")
    readonly_fields = (
        "requested_by", "tokens", "taka_per_token", "amount_taka", "note", "status",
        "decided_by", "decided_at", "decision_note", "created_at",
    )
    list_select_related = ("requested_by", "decided_by")


@admin.register(EditSession)
class EditSessionAdmin(ReadOnlyLedgerAdmin):
    """Who asked to edit which seller, and when it was open. The code itself is kept only as a digest."""

    list_display = ("seller", "onboarder", "created_at", "opened_at", "expires_at", "closed_at", "failed_attempts")
    list_filter = ("created_at",)
    search_fields = ("seller__business_name", "onboarder__username")
    readonly_fields = (
        "seller", "onboarder", "code_expires_at", "failed_attempts", "opened_at", "expires_at", "closed_at",
        "created_at",
    )
    exclude = ("code_digest",)
    list_select_related = ("seller", "onboarder")

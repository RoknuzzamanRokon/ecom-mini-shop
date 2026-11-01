"""
Field onboarding: a Sales Team member opens a seller account, adds its shop
and products, and staff approve the lot in one step.

Opening an account moves OnboardingSettings.starting_points from the
onboarder's StaffWallet to the new seller's wallet, and earns the onboarder
OnboardingSettings.tokens_per_seller tokens. Rejecting the seller gives both
back (OnboardingService.reverse_rewards).
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from points.models import SellerPointPolicy


class OnboardingSettings(models.Model):
    """
    What one onboarding costs and earns. Singleton (pk=1), changed on the
    Console Rules page (rules/registry.py). A change applies to sellers
    onboarded afterwards; SellerOnboarding keeps what each one was given.
    """
    starting_points = models.PositiveIntegerField(
        default=200,
        help_text=(
            "Points that move from the onboarder's wallet to each new seller's wallet. "
            "The seller spends them on product creation fees. 0 gives none."
        ),
    )
    tokens_per_seller = models.PositiveIntegerField(
        default=51,
        help_text="Tokens the onboarder earns for each seller they open. 0 gives none.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Onboarding Settings"
        verbose_name_plural = "Onboarding Settings"

    def __str__(self):
        return f"Onboarding: {self.starting_points} points per seller, {self.tokens_per_seller} tokens earned"

    def clean(self):
        # Starting points are a staff credit, which is a sale of at least the
        # minimum (PointService.adjust_points); fewer would fail every onboarding.
        minimum = SellerPointPolicy.current().minimum_purchase
        if 0 < self.starting_points < minimum:
            raise ValidationError(
                {"starting_points": f"Give 0 or at least {minimum} points (the Seller Point Policy minimum)."}
            )

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def current(cls) -> "OnboardingSettings":
        """The saved settings, or the defaults when nobody has changed them."""
        return cls.objects.filter(pk=1).first() or cls()


class SellerOnboarding(models.Model):
    """
    A seller the Sales Team opened in the field, and what that granted. Who
    opened it is SellerProfile.created_by. The amounts are recorded as given,
    so a rejection returns exactly those, whatever the settings say by then.
    """
    seller = models.OneToOneField(
        "sellers.SellerProfile",
        on_delete=models.CASCADE,
        related_name="onboarding",
    )
    starting_points = models.PositiveIntegerField(
        help_text="Points moved from the onboarder's wallet to the seller's.",
    )
    tokens_awarded = models.PositiveIntegerField(
        help_text="Tokens the onboarder earned for this seller.",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_onboardings",
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When staff approved the seller, shop and products in one step.",
    )
    reversed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the seller was rejected and the points and tokens went back.",
    )
    points_returned = models.PositiveIntegerField(
        default=0,
        help_text="Starting points that went back to the onboarder on rejection.",
    )
    tokens_taken_back = models.PositiveIntegerField(
        default=0,
        help_text="Tokens taken back from the onboarder on rejection.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Seller Onboarding"
        verbose_name_plural = "Seller Onboardings"

    def __str__(self):
        return f"Onboarding of {self.seller.business_name}"


class TokenWallet(models.Model):
    """
    The tokens a staff member has earned. For now tokens are only earned, by
    onboarding sellers, and taken back when such a seller is rejected; how
    they are spent is still to be decided.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="token_wallet",
    )
    balance = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Token Wallet"
        verbose_name_plural = "Token Wallets"
        constraints = [
            models.CheckConstraint(
                check=models.Q(balance__gte=0),
                name="token_wallet_balance_gte_zero",
            )
        ]

    def __str__(self):
        return f"{self.user.username} ({self.balance} tokens)"

    def clean(self):
        if self.balance < 0:
            raise ValidationError({"balance": "Token balance cannot be negative."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TokenTransaction(models.Model):
    """Immutable ledger entry for every movement in or out of a TokenWallet."""
    TYPE_EARNED = "EARNED"
    TYPE_TAKEN_BACK = "TAKEN_BACK"

    TRANSACTION_TYPE_CHOICES = [
        (TYPE_EARNED, "Earned for onboarding a seller"),
        (TYPE_TAKEN_BACK, "Taken back: onboarded seller rejected"),
    ]

    wallet = models.ForeignKey(
        TokenWallet,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    transaction_type = models.CharField(
        max_length=30,
        choices=TRANSACTION_TYPE_CHOICES,
        db_index=True,
    )
    amount = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Magnitude of tokens moved (always positive).",
    )
    balance_before = models.IntegerField()
    balance_after = models.IntegerField(validators=[MinValueValidator(0)])
    reason = models.TextField()
    seller = models.ForeignKey(
        "sellers.SellerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="token_transactions",
        help_text="The onboarded seller this movement is for.",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_token_transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Token Transaction"
        verbose_name_plural = "Token Transactions"

    def __str__(self):
        direction = "IN" if self.balance_after >= self.balance_before else "OUT"
        return f"{self.wallet.user.username} | {self.transaction_type} ({direction} {self.amount}) -> {self.balance_after} tokens"

    def clean(self):
        if self.amount <= 0:
            raise ValidationError({"amount": "Token amount must be strictly greater than 0."})
        if not self.reason or not self.reason.strip():
            raise ValidationError({"reason": "A non-empty reason is required."})
        if self.balance_after < 0:
            raise ValidationError({"balance_after": "Balance after transaction cannot be negative."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

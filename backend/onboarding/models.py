"""
Field onboarding: a Sales Team member opens a seller account, adds its shop
and products, and staff approve the lot in one step.

Opening an account moves OnboardingSettings.starting_points from the
onboarder's StaffWallet to the new seller's wallet, and earns the onboarder
OnboardingSettings.tokens_per_seller tokens. Rejecting the seller gives both
back (OnboardingService.reverse_rewards).

Later corrections go through an EditSession, opened with a code the seller
receives. Tokens are cashed through a TokenPayoutRequest that an admin
accepts, which moves them to that admin.
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
    edit_code_minutes = models.PositiveSmallIntegerField(
        default=10,
        validators=[MinValueValidator(1)],
        help_text="Minutes the code sent to the seller can be used to open an edit session.",
    )
    edit_window_minutes = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(1)],
        help_text="Minutes the onboarder may edit once the seller's code is accepted.",
    )
    taka_per_token = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="What one token is worth in ৳ when the onboarder asks for a payout.",
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


class EditSession(models.Model):
    """
    The seller's consent to an onboarder's corrections. The onboarder asks for
    a code, which goes to the seller's account; the seller tells it to them,
    and entering it opens the session for OnboardingSettings.edit_window_minutes.
    The code is kept only as an HMAC (OnboardingService.edit_code_digest).

    Waiting: no opened_at, code not expired, fewer than MAX_CODE_ATTEMPTS
    wrong tries. Open: opened_at set and expires_at ahead. A closed_at, or
    either time behind, ends it.
    """

    MAX_CODE_ATTEMPTS = 5

    seller = models.ForeignKey(
        "sellers.SellerProfile",
        on_delete=models.CASCADE,
        related_name="edit_sessions",
    )
    onboarder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="onboarding_edit_sessions",
    )
    code_digest = models.CharField(max_length=128)
    code_expires_at = models.DateTimeField()
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    opened_at = models.DateTimeField(null=True, blank=True, help_text="When the seller's code was accepted.")
    expires_at = models.DateTimeField(null=True, blank=True, help_text="When editing stops.")
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When it ended early: closed, replaced by a new code, or too many wrong codes.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Edit Session"
        verbose_name_plural = "Edit Sessions"

    def __str__(self):
        return f"Edit session for {self.seller.business_name} by {self.onboarder.username}"

    def is_waiting(self, now) -> bool:
        return (
            self.closed_at is None
            and self.opened_at is None
            and self.code_expires_at > now
            and self.failed_attempts < self.MAX_CODE_ATTEMPTS
        )

    def is_open(self, now) -> bool:
        return self.closed_at is None and self.opened_at is not None and self.expires_at > now

    def state(self, now) -> str:
        if self.is_open(now):
            return "open"
        if self.is_waiting(now):
            return "waiting"
        return "ended"


class TokenWallet(models.Model):
    """
    The tokens a staff member holds. An onboarder earns them by onboarding
    sellers (taken back if such a seller is rejected) and cashes them through
    a TokenPayoutRequest; an admin who accepts one receives its tokens.
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
    TYPE_PAYOUT_HELD = "PAYOUT_HELD"
    TYPE_PAYOUT_RELEASED = "PAYOUT_RELEASED"
    TYPE_PAYOUT_RECEIVED = "PAYOUT_RECEIVED"

    TRANSACTION_TYPE_CHOICES = [
        (TYPE_EARNED, "Earned for onboarding a seller"),
        (TYPE_TAKEN_BACK, "Taken back: onboarded seller rejected"),
        (TYPE_PAYOUT_HELD, "Held for a payout request"),
        (TYPE_PAYOUT_RELEASED, "Returned: payout request rejected or cancelled"),
        (TYPE_PAYOUT_RECEIVED, "Received by accepting a payout request"),
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
    payout_request = models.ForeignKey(
        "TokenPayoutRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="token_transactions",
        help_text="The payout request this movement is for.",
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


class TokenPayoutRequest(models.Model):
    """
    An onboarder hands tokens to the admins and asks to be paid for them in
    real money, outside the system. Asking holds the tokens (out of the
    onboarder's wallet); accepting moves them to the admin who accepted;
    rejecting or cancelling gives them back. The ৳ value is fixed when asked,
    from OnboardingSettings.taka_per_token.

    One pending request per onboarder: TokenService.request_payout checks it
    under the token wallet's lock (MySQL has no partial unique index).
    """

    STATUS_PENDING = "PENDING"
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_REJECTED = "REJECTED"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="token_payout_requests",
    )
    tokens = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    taka_per_token = models.PositiveIntegerField(help_text="The token value in ৳ when the request was made.")
    amount_taka = models.PositiveIntegerField(help_text="tokens × taka_per_token: what the onboarder is owed, in ৳.")
    note = models.CharField(max_length=500, blank=True, help_text="From the onboarder, e.g. how to pay them.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="token_payouts_decided",
        help_text="The admin who accepted or rejected it, and who received the tokens on acceptance.",
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(
        max_length=500,
        blank=True,
        help_text="From the admin: how it was paid, or why it was rejected.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "Token Payout Request"
        verbose_name_plural = "Token Payout Requests"

    def __str__(self):
        return f"Payout of {self.tokens} tokens (৳{self.amount_taka}) for {self.requested_by.username}: {self.status}"

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class SellerWallet(models.Model):
    """
    Tracks point balance for a registered seller.
    Guarantees non-negative balance through service logic, model validation, and DB constraints.
    """
    seller = models.OneToOneField(
        "sellers.SellerProfile",
        on_delete=models.CASCADE,
        related_name="point_wallet",
    )
    balance = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Current available point balance for the seller.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Seller Wallet"
        verbose_name_plural = "Seller Wallets"
        constraints = [
            models.CheckConstraint(
                check=models.Q(balance__gte=0),
                name="seller_wallet_balance_gte_zero",
            )
        ]

    def __str__(self):
        return f"{self.seller.business_name} Wallet ({self.balance} pts)"

    def clean(self):
        if self.balance < 0:
            raise ValidationError({"balance": "Point balance cannot be negative."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class PointTransaction(models.Model):
    """
    Immutable ledger entry for all credit and debit point operations.
    Every balance modification MUST produce a corresponding PointTransaction.
    """
    TYPE_BONUS = "BONUS"
    TYPE_ADMIN_CREDIT = "ADMIN_CREDIT"
    TYPE_ADMIN_DEBIT = "ADMIN_DEBIT"
    TYPE_PRODUCT_CREATION = "PRODUCT_CREATION"
    TYPE_REFUND = "REFUND"
    TYPE_ADJUSTMENT = "ADJUSTMENT"

    TRANSACTION_TYPE_CHOICES = [
        (TYPE_BONUS, "Bonus / Promotional Credit"),
        (TYPE_ADMIN_CREDIT, "Admin Staff Credit"),
        (TYPE_ADMIN_DEBIT, "Admin Staff Debit"),
        (TYPE_PRODUCT_CREATION, "Product Creation Fee"),
        (TYPE_REFUND, "Point Refund"),
        (TYPE_ADJUSTMENT, "Administrative Adjustment"),
    ]

    wallet = models.ForeignKey(
        SellerWallet,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    seller = models.ForeignKey(
        "sellers.SellerProfile",
        on_delete=models.CASCADE,
        related_name="point_transactions",
    )
    transaction_type = models.CharField(
        max_length=30,
        choices=TRANSACTION_TYPE_CHOICES,
        db_index=True,
    )
    amount = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Magnitude of points credited or debited (always positive).",
    )
    balance_before = models.IntegerField(
        help_text="Point balance before this transaction was executed.",
    )
    balance_after = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Point balance after this transaction was executed.",
    )
    reason = models.TextField(
        help_text="Mandatory business reason or description for this point change.",
    )
    reference_type = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Optional domain identifier (e.g. 'PRODUCT', 'ORDER', 'PROMOTION').",
    )
    reference_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Optional external ID linking this transaction to a domain record.",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_point_transactions",
        help_text="The staff user or system actor who triggered this transaction.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Point Transaction"
        verbose_name_plural = "Point Transactions"

    def __str__(self):
        direction = "CREDIT" if self.balance_after >= self.balance_before else "DEBIT"
        return f"{self.seller.business_name} | {self.transaction_type} ({direction} {self.amount}) -> {self.balance_after} pts"

    def clean(self):
        if self.amount <= 0:
            raise ValidationError({"amount": "Transaction amount must be strictly greater than 0."})
        if not self.reason or not self.reason.strip():
            raise ValidationError({"reason": "A non-empty transaction reason is required."})
        if self.balance_after < 0:
            raise ValidationError({"balance_after": "Balance after transaction cannot be negative."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

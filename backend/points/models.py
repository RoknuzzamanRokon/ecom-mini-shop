import calendar
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


def add_months(moment, months: int):
    """`moment` moved `months` calendar months on, clamping the day (Jan 31 + 1 -> Feb 28/29)."""
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


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
    TYPE_EXPIRY = "EXPIRY"
    TYPE_LISTING_RENEWAL = "LISTING_RENEWAL"

    TRANSACTION_TYPE_CHOICES = [
        (TYPE_BONUS, "Bonus / Promotional Credit"),
        (TYPE_ADMIN_CREDIT, "Admin Staff Credit"),
        (TYPE_ADMIN_DEBIT, "Admin Staff Debit"),
        (TYPE_PRODUCT_CREATION, "Product Creation Fee"),
        (TYPE_REFUND, "Point Refund"),
        (TYPE_ADJUSTMENT, "Administrative Adjustment"),
        (TYPE_EXPIRY, "Points Expired"),
        (TYPE_LISTING_RENEWAL, "Listing Renewal Fee"),
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


class StaffWallet(models.Model):
    """
    The points a staff member holds and can hand to sellers.

    A staff credit is a transfer out of this wallet, never a mint: someone with
    an empty wallet cannot give anyone points. The points staff hand out are
    created by PointService.mint_points, which only a superuser may call.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_point_wallet",
    )
    balance = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Points this staff member can still give to sellers.",
    )
    points_expire = models.BooleanField(
        default=True,
        help_text=(
            "Whether points in this wallet expire. A superuser's never do, whatever this says. "
            "Change it from the Console user page, which records why and restarts the clock."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Staff Wallet"
        verbose_name_plural = "Staff Wallets"
        constraints = [
            models.CheckConstraint(
                check=models.Q(balance__gte=0),
                name="staff_wallet_balance_gte_zero",
            )
        ]

    def __str__(self):
        return f"{self.user.username} Staff Wallet ({self.balance} pts)"

    def clean(self):
        if self.balance < 0:
            raise ValidationError({"balance": "Point balance cannot be negative."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class StaffPointTransaction(models.Model):
    """
    Immutable ledger entry for every movement in or out of a StaffWallet.

    Movements to and from a seller are linked to the seller-side
    PointTransaction, so the two halves of one adjustment can be read together.
    """
    TYPE_MINT = "MINT"
    TYPE_TRANSFER_OUT = "TRANSFER_OUT"
    TYPE_TRANSFER_IN = "TRANSFER_IN"
    TYPE_SELLER_CREDIT = "SELLER_CREDIT"
    TYPE_SELLER_DEBIT = "SELLER_DEBIT"
    TYPE_RECLAIM_OUT = "RECLAIM_OUT"
    TYPE_RECLAIM_IN = "RECLAIM_IN"
    TYPE_EXPIRY = "EXPIRY"

    TRANSACTION_TYPE_CHOICES = [
        (TYPE_MINT, "Created by Superuser"),
        (TYPE_TRANSFER_OUT, "Sent to Staff"),
        (TYPE_TRANSFER_IN, "Received from Superuser"),
        (TYPE_SELLER_CREDIT, "Given to Seller"),
        (TYPE_SELLER_DEBIT, "Taken back from Seller"),
        (TYPE_RECLAIM_OUT, "Taken back by Superuser"),
        (TYPE_RECLAIM_IN, "Taken back from Staff"),
        (TYPE_EXPIRY, "Expired"),
    ]

    wallet = models.ForeignKey(
        StaffWallet,
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
        help_text="Magnitude of points moved (always positive).",
    )
    balance_before = models.IntegerField()
    balance_after = models.IntegerField(validators=[MinValueValidator(0)])
    reason = models.TextField()
    counterparty = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="counterparty_staff_point_transactions",
        help_text="The other staff wallet's owner, on a staff-to-staff transfer or take-back.",
    )
    seller_transaction = models.OneToOneField(
        PointTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_counterpart",
        help_text="The seller-side ledger entry, on a seller credit or debit.",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="initiated_staff_point_transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Staff Point Transaction"
        verbose_name_plural = "Staff Point Transactions"

    def __str__(self):
        direction = "IN" if self.balance_after >= self.balance_before else "OUT"
        return f"{self.wallet.user.username} | {self.transaction_type} ({direction} {self.amount}) -> {self.balance_after} pts"

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


class ProductCreationCost(models.Model):
    """
    Points required to create a new product. Singleton (pk=1), changed on the
    Console Rules page (rules/registry.py).
    """
    # At least 1: every new product costs its seller points, whatever their type.
    required_points = models.PositiveIntegerField(
        default=5,
        validators=[MinValueValidator(1)],
        help_text="Number of points debited from seller wallet for each new product creation (at least 1).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Product Creation Cost"
        verbose_name_plural = "Product Creation Cost"

    def __str__(self):
        return f"Product Creation Cost: {self.required_points} points"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_cost(cls) -> int:
        cost = cls().required_points
        try:
            config = cls.objects.filter(pk=1).first()
            if config:
                cost = config.required_points
        except Exception:
            pass
        # A product is never free, even if a row predates the validator.
        return max(cost, 1)


class PointExpiryPolicy(models.Model):
    """
    How long points received into a staff wallet last before they expire.
    Singleton (pk=1), changed on the Console Rules page (rules/registry.py).
    A change applies to points received afterwards; points already held keep
    their date. Seller wallets follow SellerPointPolicy instead.
    """
    expiry_months = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(1)],
        help_text="Months a batch of points received into a staff wallet lasts before it expires.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Point Expiry Policy"
        verbose_name_plural = "Point Expiry Policy"

    def __str__(self):
        return f"Point Expiry Policy: {self.expiry_months} months"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_months(cls) -> int:
        return (cls.objects.filter(pk=1).first() or cls()).expiry_months

    @classmethod
    def expiry_for(cls, received_at):
        return add_months(received_at, cls.get_months())


class SellerPointPolicy(models.Model):
    """
    How sellers buy points and how long they last. Singleton (pk=1), changed
    on the Console Rules page (rules/registry.py).

    A seller's unspent points share one expiry date: each purchase moves it
    to the later of now and the current date, plus `validity_days`
    (PointService.credit). Every staff credit to a seller is a sale of at
    least `minimum_purchase` points (PointService.adjust_points).
    """
    validity_days = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(1)],
        help_text="Days a purchase adds to the expiry date of the seller's points.",
    )
    minimum_purchase = models.PositiveIntegerField(
        default=100,
        validators=[MinValueValidator(1)],
        help_text="The fewest points staff may give a seller at once.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Seller Point Policy"
        verbose_name_plural = "Seller Point Policy"

    def __str__(self):
        return f"Seller Point Policy: {self.validity_days} days, at least {self.minimum_purchase} points"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def current(cls) -> "SellerPointPolicy":
        """The saved policy, or an unsaved one holding the defaults."""
        return cls.objects.filter(pk=1).first() or cls()

    def expiry_from(self, moment):
        return moment + timedelta(days=self.validity_days)


class PointLot(models.Model):
    """
    One receipt of points. A wallet's lots say when each of its points
    expires; the wallet's `balance` stays the authoritative total. Spending
    takes from the lot that expires first. Every lot carries a date, and
    PointService decides at expiry time whether the holder's points expire
    at all (a Full Shop Owner's and a superuser's never do). A seller's
    unspent lots share one date, which each purchase moves on.
    """
    amount = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Points received in this batch.",
    )
    remaining = models.PositiveIntegerField(
        help_text="Points from this batch not yet spent, moved or expired.",
    )
    received_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        abstract = True
        ordering = ["expires_at", "id"]


class SellerPointLot(PointLot):
    wallet = models.ForeignKey(SellerWallet, on_delete=models.CASCADE, related_name="lots")
    source = models.OneToOneField(
        PointTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lot",
        help_text="The credit that brought these points in.",
    )
    origin_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "When the staff points this credit came from would have expired. A take-back "
            "returns the points with this date, not a fresh one. Empty when the giver's "
            "points never expire."
        ),
    )

    class Meta(PointLot.Meta):
        verbose_name = "Seller Point Lot"
        verbose_name_plural = "Seller Point Lots"


class StaffPointLot(PointLot):
    wallet = models.ForeignKey(StaffWallet, on_delete=models.CASCADE, related_name="lots")
    source = models.OneToOneField(
        StaffPointTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lot",
        help_text="The movement that brought these points in.",
    )

    class Meta(PointLot.Meta):
        verbose_name = "Staff Point Lot"
        verbose_name_plural = "Staff Point Lots"


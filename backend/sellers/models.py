from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class SellerTransitionError(ValidationError):
    """A staff lifecycle action was asked of a seller in a status it cannot start from."""

    def __init__(self, action: str, status: str, allowed):
        self.action = action
        self.status = status
        super().__init__(
            f"Cannot {action} a seller who is {status}; "
            f"{action} applies only to {' or '.join(allowed)} sellers."
        )


class SellerProfile(models.Model):
    # Seller Types
    TYPE_FULL_SHOP_OWNER = "FULL_SHOP_OWNER"
    TYPE_LIMITED_SHOP_OWNER = "LIMITED_SHOP_OWNER"

    # A Full Shop Owner may own any number of shops and products. A Limited Shop
    # Owner is capped at one shop and LimitedShopOwnerProductLimit products.
    SELLER_TYPE_CHOICES = [
        (TYPE_FULL_SHOP_OWNER, "Full Shop Owner"),
        (TYPE_LIMITED_SHOP_OWNER, "Limited Shop Owner"),
    ]

    # Seller Status Lifecycle
    STATUS_PENDING = "PENDING"
    STATUS_UNDER_REVIEW = "UNDER_REVIEW"
    STATUS_APPROVED = "APPROVED"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_SUSPENDED = "SUSPENDED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_UNDER_REVIEW, "Under Review"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspended"),
        (STATUS_REJECTED, "Rejected"),
    ]
    #: Not yet approved or rejected. Field onboarding may still add a shop and
    #: products in these; nothing is public until the seller is approved.
    AWAITING_APPROVAL_STATUSES = (STATUS_PENDING, STATUS_UNDER_REVIEW)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="seller_profile",
    )
    seller_type = models.CharField(
        max_length=30,
        choices=SELLER_TYPE_CHOICES,
        default=TYPE_FULL_SHOP_OWNER,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    business_name = models.CharField(max_length=200)
    business_email = models.EmailField(blank=True)
    business_phone = models.CharField(max_length=30, blank=True)
    tax_id = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)

    rejection_reason = models.TextField(blank=True)
    suspension_reason = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="created_sellers",
        help_text="The staff member who created this seller: in the Console, the Django admin or field onboarding.",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_sellers",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Seller Profile"
        verbose_name_plural = "Seller Profiles"

    def __str__(self):
        return f"{self.business_name} ({self.get_seller_type_display()}) - {self.status}"

    @property
    def is_operational(self) -> bool:
        """APPROVED or ACTIVE sellers are operational for catalog/selling actions."""
        return self.status in (self.STATUS_APPROVED, self.STATUS_ACTIVE)

    @property
    def is_suspended(self) -> bool:
        return self.status == self.STATUS_SUSPENDED

    def clean(self):
        valid_types = [choice[0] for choice in self.SELLER_TYPE_CHOICES]
        if self.seller_type not in valid_types:
            raise ValidationError(
                {"seller_type": f"Invalid seller type '{self.seller_type}'. Must be one of: {valid_types}"}
            )

        valid_statuses = [choice[0] for choice in self.STATUS_CHOICES]
        if self.status not in valid_statuses:
            raise ValidationError(
                {"status": f"Invalid status '{self.status}'. Must be one of: {valid_statuses}"}
            )

        if self.status == self.STATUS_REJECTED and not self.rejection_reason:
            raise ValidationError(
                {"rejection_reason": "A rejection reason is mandatory when rejecting a seller."}
            )

        if self.status == self.STATUS_SUSPENDED and not self.suspension_reason:
            raise ValidationError(
                {"suspension_reason": "A suspension reason is mandatory when suspending a seller."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    # Lifecycle State Transitions
    #
    # The statuses each staff transition may start from (BUG-017). A
    # suspension is lifted only by reactivate (sellers.suspend), and an
    # applicant is admitted only by approve (sellers.approve), so neither
    # authority can stand in for the other.
    TRANSITION_SOURCES = {
        "approve": (STATUS_PENDING, STATUS_UNDER_REVIEW, STATUS_REJECTED),
        "reject": (STATUS_PENDING, STATUS_UNDER_REVIEW),
        "suspend": (STATUS_APPROVED, STATUS_ACTIVE),
        "reactivate": (STATUS_SUSPENDED,),
    }

    def require_transition(self, action: str):
        """Raise SellerTransitionError unless `action` may start from the current status."""
        allowed = self.TRANSITION_SOURCES[action]
        if self.status not in allowed:
            raise SellerTransitionError(action, self.status, allowed)

    def approve(self, staff_user):
        self.require_transition("approve")
        self.status = self.STATUS_APPROVED
        self.reviewed_by = staff_user
        self.reviewed_at = timezone.now()
        self.approved_at = timezone.now()
        self.rejection_reason = ""
        self.save(update_fields=["status", "reviewed_by", "reviewed_at", "approved_at", "rejection_reason", "updated_at"])

    def activate(self, staff_user=None):
        if self.status not in (self.STATUS_APPROVED, self.STATUS_SUSPENDED):
            raise ValidationError("Only approved or suspended sellers can be activated.")
        self.status = self.STATUS_ACTIVE
        self.suspension_reason = ""
        self.save(update_fields=["status", "suspension_reason", "updated_at"])

    def reactivate(self, staff_user=None):
        """Lift a suspension: SUSPENDED -> ACTIVE."""
        self.require_transition("reactivate")
        self.activate(staff_user)

    def suspend(self, staff_user, reason: str):
        self.require_transition("suspend")
        if not reason or not reason.strip():
            raise ValidationError("A non-empty suspension reason is required.")
        self.status = self.STATUS_SUSPENDED
        self.suspension_reason = reason.strip()
        self.suspended_at = timezone.now()
        self.save(update_fields=["status", "suspension_reason", "suspended_at", "updated_at"])

    def reject(self, staff_user, reason: str):
        self.require_transition("reject")
        if not reason or not reason.strip():
            raise ValidationError("A non-empty rejection reason is required.")
        self.status = self.STATUS_REJECTED
        self.rejection_reason = reason.strip()
        self.reviewed_by = staff_user
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at", "updated_at"])


class LimitedShopOwnerProductLimit(models.Model):
    """
    Maximum number of products a Limited Shop Owner may hold across their shop.
    Singleton (pk=1), administrator-adjustable like points.ProductCreationCost.
    """
    max_products = models.PositiveIntegerField(
        default=10,
        validators=[MinValueValidator(0)],
        help_text="Number of products a Limited Shop Owner may hold. Deleting a product frees a slot.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Limited Shop Owner Product Limit"
        verbose_name_plural = "Limited Shop Owner Product Limit"

    def __str__(self):
        return f"Limited Shop Owner Product Limit: {self.max_products} products"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_limit(cls) -> int:
        config = cls.objects.filter(pk=1).first()
        if config:
            return config.max_products
        return getattr(settings, "LIMITED_SHOP_OWNER_PRODUCT_LIMIT", 10)

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class SellerProfile(models.Model):
    # Seller Types
    TYPE_FULL_SHOP_OWNER = "FULL_SHOP_OWNER"
    TYPE_LIMITED_SHOP_OWNER = "LIMITED_SHOP_OWNER"
    TYPE_PRODUCT_OWNER = "PRODUCT_OWNER"

    SELLER_TYPE_CHOICES = [
        (TYPE_FULL_SHOP_OWNER, "Full Shop Owner"),
        (TYPE_LIMITED_SHOP_OWNER, "Limited Shop Owner"),
        (TYPE_PRODUCT_OWNER, "Product Owner"),
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
    def submit_for_review(self):
        if self.status in (self.STATUS_PENDING, self.STATUS_REJECTED):
            self.status = self.STATUS_UNDER_REVIEW
            self.save(update_fields=["status", "updated_at"])

    def approve(self, staff_user):
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

    def suspend(self, staff_user, reason: str):
        if not reason or not reason.strip():
            raise ValidationError("A non-empty suspension reason is required.")
        self.status = self.STATUS_SUSPENDED
        self.suspension_reason = reason.strip()
        self.suspended_at = timezone.now()
        self.save(update_fields=["status", "suspension_reason", "suspended_at", "updated_at"])

    def reject(self, staff_user, reason: str):
        if not reason or not reason.strip():
            raise ValidationError("A non-empty rejection reason is required.")
        self.status = self.STATUS_REJECTED
        self.rejection_reason = reason.strip()
        self.reviewed_by = staff_user
        self.reviewed_at = timezone.now()
        self.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at", "updated_at"])

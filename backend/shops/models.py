from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.text import slugify


from shops.fields import MySQLPointField, Point


class Shop(models.Model):
    """
    Represents a commercial store owned by an approved seller.
    Enforces a strict lifecycle, seller ownership, and public visibility rules.
    """
    STATUS_DRAFT = "DRAFT"
    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_SUSPENDED = "SUSPENDED"
    STATUS_REJECTED = "REJECTED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PENDING, "Pending Review"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspended"),
        (STATUS_REJECTED, "Rejected"),
    ]

    owner = models.ForeignKey(
        "sellers.SellerProfile",
        on_delete=models.CASCADE,
        related_name="shops",
        help_text="The seller profile that owns and manages this shop.",
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, db_index=True)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to="shops/logos/", blank=True, null=True)
    cover_image = models.ImageField(upload_to="shops/covers/", blank=True, null=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    location = MySQLPointField(
        srid=4326,
        default="POINT(0 0)",
        help_text="Spatial coordinate POINT(lng lat) with SRID 4326.",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )

    rejection_reason = models.TextField(blank=True)
    suspension_reason = models.TextField(blank=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_shops",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Shop"
        verbose_name_plural = "Shops"

    def __str__(self):
        return f"{self.name} ({self.status}) - Owner: {self.owner.business_name}"

    @property
    def is_publicly_visible(self) -> bool:
        """Only APPROVED or ACTIVE shops are visible to anonymous/public customers."""
        return self.status in (self.STATUS_APPROVED, self.STATUS_ACTIVE)

    @property
    def latitude(self):
        """Returns latitude (float) or None if unassigned."""
        if isinstance(self.location, Point) and not self.location.is_empty_or_zero:
            return self.location.latitude
        return None

    @property
    def longitude(self):
        """Returns longitude (float) or None if unassigned."""
        if isinstance(self.location, Point) and not self.location.is_empty_or_zero:
            return self.location.longitude
        return None

    @property
    def has_coordinates(self) -> bool:
        """Returns True if the shop has a valid non-zero geographic coordinate."""
        return isinstance(self.location, Point) and not self.location.is_empty_or_zero

    def clean(self):
        if self.status == self.STATUS_REJECTED and not self.rejection_reason:
            raise ValidationError({"rejection_reason": "A rejection reason is mandatory when rejecting a shop."})

        if self.status == self.STATUS_SUSPENDED and not self.suspension_reason:
            raise ValidationError({"suspension_reason": "A suspension reason is mandatory when suspending a shop."})

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or "shop"
            slug_candidate = base_slug
            counter = 1
            while Shop.objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
                slug_candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug_candidate

        self.full_clean()
        super().save(*args, **kwargs)

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils.text import slugify


from shops.fields import MySQLPointField, Point


class ShopQuerySet(models.QuerySet):
    def public(self):
        """
        Shops the public may see: the shop is APPROVED or ACTIVE, and so is its
        seller. Suspending or rejecting a seller hides their shops (BUG-018), the
        same rule Product.objects.public() applies to their products.
        """
        return self.filter(
            status__in=["APPROVED", "ACTIVE"],
            owner__status__in=["APPROVED", "ACTIVE"],
        )


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

    objects = ShopQuerySet.as_manager()

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
    additional_phones = models.JSONField(
        default=list,
        blank=True,
        help_text="Extra contact numbers beyond `phone`, as a list of strings.",
    )
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
        """The same rule as Shop.objects.public(): the shop and its seller are APPROVED or ACTIVE."""
        return (
            self.status in (self.STATUS_APPROVED, self.STATUS_ACTIVE)
            and self.owner.status in ("APPROVED", "ACTIVE")
        )

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

    MAX_ADDITIONAL_PHONES = 4
    PHONE_MAX_LENGTH = 30

    @staticmethod
    def normalize_additional_phones(phones, primary: str = "") -> list:
        """
        Trims each number and drops blanks, repeats, and copies of `primary`,
        keeping the given order. Non-string entries are left in place for
        clean() to reject rather than being silently coerced.
        """
        seen = {primary.strip()} if primary else set()
        normalized = []
        for phone in phones or []:
            if isinstance(phone, str):
                phone = phone.strip()
                if not phone or phone in seen:
                    continue
                seen.add(phone)
            normalized.append(phone)
        return normalized

    def clean(self):
        self.additional_phones = self.normalize_additional_phones(self.additional_phones, self.phone)
        if any(
            not isinstance(phone, str) or len(phone) > self.PHONE_MAX_LENGTH
            for phone in self.additional_phones
        ):
            raise ValidationError(
                {"additional_phones": f"Each phone number must be text of at most {self.PHONE_MAX_LENGTH} characters."}
            )
        if len(self.additional_phones) > self.MAX_ADDITIONAL_PHONES:
            raise ValidationError(
                {"additional_phones": f"A shop can list at most {self.MAX_ADDITIONAL_PHONES} additional phone numbers."}
            )

        if self.status == self.STATUS_REJECTED and not self.rejection_reason:
            raise ValidationError({"rejection_reason": "A rejection reason is mandatory when rejecting a shop."})

        if self.status == self.STATUS_SUSPENDED and not self.suspension_reason:
            raise ValidationError({"suspension_reason": "A suspension reason is mandatory when suspending a shop."})

    # How many generated slugs save() tries when concurrent saves keep taking them first.
    SLUG_ATTEMPTS = 5

    def _free_slug(self) -> str:
        base_slug = slugify(self.name) or "shop"
        slug_candidate = base_slug
        counter = 1
        while Shop.objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
            slug_candidate = f"{base_slug}-{counter}"
            counter += 1
        return slug_candidate

    def save(self, *args, **kwargs):
        if self.slug:
            self.full_clean()
            super().save(*args, **kwargs)
            return

        # A concurrent save can take the free slug between the check and the
        # insert. The insert then fails on the unique index; take the next
        # free slug instead of returning a 500 (BUG-059).
        for attempt in range(1, self.SLUG_ATTEMPTS + 1):
            self.slug = self._free_slug()
            self.full_clean()
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return
            except IntegrityError:
                taken = Shop.objects.filter(slug=self.slug).exclude(pk=self.pk).exists()
                if attempt == self.SLUG_ATTEMPTS or not taken:
                    raise
                self.slug = ""

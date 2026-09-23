from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class CustomerProfile(models.Model):
    """
    Extends the authentication User model with customer-specific profile details.
    Allows any user (customer, seller, or staff) to maintain customer profile information.
    """
    GENDER_MALE = "MALE"
    GENDER_FEMALE = "FEMALE"
    GENDER_OTHER = "OTHER"
    GENDER_PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY"

    GENDER_CHOICES = [
        (GENDER_MALE, "Male"),
        (GENDER_FEMALE, "Female"),
        (GENDER_OTHER, "Other"),
        (GENDER_PREFER_NOT_TO_SAY, "Prefer not to say"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    display_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to="customers/avatars/", null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=20, choices=GENDER_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Customer Profile"
        verbose_name_plural = "Customer Profiles"
        ordering = ["-created_at"]

    def __str__(self):
        return self.display_name or self.user.get_full_name() or self.user.username


class Address(models.Model):
    """
    Delivery and billing address record for customers.
    Enforces a deterministic single-default address per user at the MySQL database engine level
    using a nullable default_flag combined with a UniqueConstraint.
    """
    LABEL_HOME = "Home"
    LABEL_WORK = "Work"
    LABEL_OFFICE = "Office"
    LABEL_OTHER = "Other"

    LABEL_CHOICES = [
        (LABEL_HOME, "Home"),
        (LABEL_WORK, "Work"),
        (LABEL_OFFICE, "Office"),
        (LABEL_OTHER, "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
    )
    label = models.CharField(max_length=50, choices=LABEL_CHOICES, default=LABEL_HOME)
    recipient_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    area = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default="Bangladesh")

    # Standard coordinates with decimal validation (not GIS POINT)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-90.0")),
            MaxValueValidator(Decimal("90.0")),
        ],
        help_text="Latitude coordinate (-90.0 to 90.0)",
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-180.0")),
            MaxValueValidator(Decimal("180.0")),
        ],
        help_text="Longitude coordinate (-180.0 to 180.0)",
    )

    is_default = models.BooleanField(default=False)
    # default_flag is 1 when is_default is True, and NULL when is_default is False.
    # In MySQL, UNIQUE constraints ignore NULLs, allowing unlimited non-default addresses,
    # but strictly allowing only ONE row with default_flag=1 per user.
    default_flag = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        editable=False,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Address"
        verbose_name_plural = "Addresses"
        ordering = ["-is_default", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "default_flag"],
                name="unique_default_address_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_default"], name="cust_addr_user_def_idx"),
        ]

    def clean(self):
        super().clean()
        # Ensure coordinates are paired
        if (self.latitude is not None and self.longitude is None) or (
            self.longitude is not None and self.latitude is None
        ):
            raise ValidationError(
                "Both latitude and longitude must be provided together, or both left blank."
            )
        if self.latitude is not None and not (Decimal("-90.0") <= self.latitude <= Decimal("90.0")):
            raise ValidationError({"latitude": "Latitude must be between -90 and 90 degrees."})
        if self.longitude is not None and not (Decimal("-180.0") <= self.longitude <= Decimal("180.0")):
            raise ValidationError({"longitude": "Longitude must be between -180 and 180 degrees."})

    def save(self, *args, **kwargs):
        self.default_flag = 1 if self.is_default else None
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        prefix = "[DEFAULT] " if self.is_default else ""
        return f"{prefix}{self.label}: {self.recipient_name}, {self.city}"


class Favorite(models.Model):
    """
    Wishlist entry linking a customer to a product they want to revisit.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorites",
    )
    product = models.ForeignKey(
        "shop.Product",
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Favorite"
        verbose_name_plural = "Favorites"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_favorite_per_user_product",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="cust_fav_user_created_idx"),
        ]

    def __str__(self):
        return f"{self.user.username} -> {self.product.name}"


class ReviewQuerySet(models.QuerySet):
    def visible(self):
        """Reviews the public may see: everything a moderator has not hidden."""
        return self.filter(is_hidden=False)


class ReviewModeration(models.Model):
    """
    Staff moderation state shared by product and shop reviews. A hidden review
    is kept (not deleted) but left out of every public list and every rating
    average, count and breakdown; its author still sees it, marked as hidden.
    """
    is_hidden = models.BooleanField(default=False)
    hidden_reason = models.CharField(max_length=500, blank=True)
    hidden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hidden_%(class)ss",
    )
    hidden_at = models.DateTimeField(null=True, blank=True)

    objects = ReviewQuerySet.as_manager()

    class Meta:
        abstract = True


class Review(ReviewModeration):
    """
    Customer rating and comment for a product. related_name is deliberately
    "customer_reviews", not "reviews" — Product already has reviewed_by/
    reviewed_at fields for the unrelated admin-approval workflow.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="product_reviews",
    )
    product = models.ForeignKey(
        "shop.Product",
        on_delete=models.CASCADE,
        related_name="customer_reviews",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(
        default=False,
        help_text="Computed once at creation time; never recomputed afterward.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Review"
        verbose_name_plural = "Reviews"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_review_per_user_product",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "-created_at"], name="cust_review_prod_created_idx"),
        ]

    def clean(self):
        super().clean()
        if self.rating is not None and not (1 <= self.rating <= 5):
            raise ValidationError({"rating": "Rating must be between 1 and 5."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} rated {self.product.name}: {self.rating}/5"


class ShopReview(ReviewModeration):
    """
    Customer rating and comment for a shop as a whole, independent of the
    shop's product reviews. related_name on the shop FK is "customer_reviews",
    matching Product — Shop already has reviewed_by/reviewed_at for the
    unrelated staff-approval workflow.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shop_reviews",
    )
    shop = models.ForeignKey(
        "shops.Shop",
        on_delete=models.CASCADE,
        related_name="customer_reviews",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(
        default=False,
        help_text="Computed once at creation time; never recomputed afterward.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Shop Review"
        verbose_name_plural = "Shop Reviews"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "shop"],
                name="unique_review_per_user_shop",
            ),
        ]
        indexes = [
            models.Index(fields=["shop", "-created_at"], name="cust_shoprev_shop_created_idx"),
        ]

    def clean(self):
        super().clean()
        if self.rating is not None and not (1 <= self.rating <= 5):
            raise ValidationError({"rating": "Rating must be between 1 and 5."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} rated shop {self.shop.name}: {self.rating}/5"

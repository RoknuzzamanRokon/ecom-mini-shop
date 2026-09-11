from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True)
    icon = models.CharField(
        max_length=50,
        blank=True,
        help_text="Material Symbols icon name, e.g. checkroom",
    )
    image = models.ImageField(
        upload_to="categories/",
        blank=True,
        null=True,
        help_text="Category hero / banner image",
    )
    description = models.TextField(
        blank=True,
        help_text="Short description for category banners and headers",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("shop:category", args=[self.slug])


class ProductQuerySet(models.QuerySet):
    def public(self):
        """
        Authoritative queryset for publicly visible catalog products.
        Enforces:
          1. Product is active (is_active=True).
          2. Product status is PUBLISHED.
          3. Category is active (category__is_active=True).
          4. Product belongs to an approved/active shop (shop__status in [APPROVED, ACTIVE]).
          5. Shop owner (seller) is operational (shop__owner__status in [APPROVED, ACTIVE]).
        """
        return self.filter(
            is_active=True,
            status="PUBLISHED",
            category__is_active=True,
            shop__isnull=False,
            shop__status__in=["APPROVED", "ACTIVE"],
            shop__owner__status__in=["APPROVED", "ACTIVE"],
        )


class Product(models.Model):
    # Lifecycle & Publishing Statuses
    STATUS_DRAFT = "DRAFT"
    STATUS_SUBMITTED = "SUBMITTED"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_PUBLISHED = "PUBLISHED"
    STATUS_UNPUBLISHED = "UNPUBLISHED"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_UNPUBLISHED, "Unpublished"),
    ]

    objects = ProductQuerySet.as_manager()

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="products",
    )
    shop = models.ForeignKey(
        "shops.Shop",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    old_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    image = models.ImageField(upload_to="products/", blank=True)
    stock = models.PositiveIntegerField(default=0)
    badge = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
        help_text="Product approval and publishing lifecycle status.",
    )
    rejection_reason = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_products",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def clean(self):
        if not self.slug and self.name:
            self.slug = slugify(self.name)
        if self.price is not None and self.price <= 0:
            raise ValidationError({"price": "Price must be strictly greater than 0."})
        if self.old_price is not None and self.old_price <= 0:
            raise ValidationError({"old_price": "Old price must be strictly greater than 0."})
        if self.status == self.STATUS_REJECTED and not self.rejection_reason:
            raise ValidationError({"rejection_reason": "A rejection reason is required when rejecting a product."})

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            self.slug = slugify(self.name)
        self.clean()
        super().save(*args, **kwargs)


    @property
    def seller(self):
        """
        Derives the product's seller via Product -> Shop -> Seller.
        Single source of truth for seller ownership.
        """
        return self.shop.owner if self.shop else None

    @property
    def owner(self):
        """Alias for seller property."""
        return self.seller

    @property
    def is_publicly_visible(self) -> bool:
        """
        Determines whether this product is visible in the public catalog.
        Corresponds exactly with ProductQuerySet.public() criteria.
        """
        return bool(
            self.is_active
            and self.status == self.STATUS_PUBLISHED
            and self.category_id
            and self.category.is_active
            and self.shop_id is not None
            and self.shop
            and self.shop.status in ("APPROVED", "ACTIVE")
            and self.shop.owner_id is not None
            and self.shop.owner
            and self.shop.owner.status in ("APPROVED", "ACTIVE")
        )

    def get_absolute_url(self):
        return reverse("shop:product_detail", args=[self.slug])


    @property
    def in_stock(self):
        return self.stock > 0

    @property
    def discount_percent(self):
        if self.old_price and self.old_price > self.price:
            return int(
                ((self.old_price - self.price) * Decimal("100") / self.old_price).quantize(
                    Decimal("1")
                )
            )
        return 0

    @property
    def savings_amount(self):
        if self.old_price and self.old_price > self.price:
            return self.old_price - self.price
        return None

    @property
    def all_images(self):
        gallery = [product_image.image for product_image in self.images.all()]
        if self.image:
            return [self.image] + gallery
        return gallery


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="products/gallery/")
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.product.name} image #{self.order}"


class Order(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_CONFIRMED = "CONFIRMED"
    STATUS_PROCESSING = "PROCESSING"
    STATUS_SHIPPED = "SHIPPED"
    STATUS_DELIVERED = "DELIVERED"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_SHIPPED, "Shipped"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_CANCELLED, "Cancelled"),
        # Legacy lowercase support for backwards compatibility
        ("pending", "Pending (Legacy)"),
        ("processing", "Processing (Legacy)"),
        ("shipped", "Shipped (Legacy)"),
        ("delivered", "Delivered (Legacy)"),
        ("cancelled", "Cancelled (Legacy)"),
    ]

    VALID_TRANSITIONS = {
        STATUS_PENDING: [STATUS_CONFIRMED, STATUS_CANCELLED],
        STATUS_CONFIRMED: [STATUS_PROCESSING, STATUS_CANCELLED],
        STATUS_PROCESSING: [STATUS_SHIPPED],
        STATUS_SHIPPED: [STATUS_DELIVERED],
        STATUS_DELIVERED: [],
        STATUS_CANCELLED: [],
        # Legacy lowercase mapping
        "pending": [STATUS_CONFIRMED, STATUS_CANCELLED],
        "processing": [STATUS_SHIPPED],
        "shipped": [STATUS_DELIVERED],
        "delivered": [],
        "cancelled": [],
    }

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        db_index=True,
        help_text="The authenticated user who placed this order. Preserved upon user deletion.",
    )
    order_number = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    # Shipping Address Historical Snapshot
    shipping_recipient_name = models.CharField(max_length=150, blank=True)
    shipping_phone = models.CharField(max_length=20, blank=True)
    shipping_address_line_1 = models.CharField(max_length=255, blank=True)
    shipping_address_line_2 = models.CharField(max_length=255, blank=True)
    shipping_area = models.CharField(max_length=100, blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_state = models.CharField(max_length=100, blank=True)
    shipping_postal_code = models.CharField(max_length=20, blank=True)
    shipping_country = models.CharField(max_length=100, default="Bangladesh")
    shipping_address = models.ForeignKey(
        "customers.Address",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Optional reference to the original address; snapshot fields remain authoritative.",
    )

    # Backwards-compatible legacy address fields
    customer_name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)

    # Server-Authoritative Monetary Totals
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Order"
        verbose_name_plural = "Orders"

    def __str__(self):
        return f"{self.order_number} ({self.status})"

    def can_transition_to(self, new_status: str) -> bool:
        """Checks whether the requested status transition is allowed."""
        current = self.status.upper() if self.status else ""
        target = new_status.upper() if new_status else ""
        return target in self.VALID_TRANSITIONS.get(current, [])

    def transition_to(self, new_status: str):
        """Transitions order status or raises ValidationError if invalid."""
        target = new_status.upper()
        if not self.can_transition_to(target):
            raise ValidationError(
                f"Invalid order status transition from '{self.status}' to '{target}'."
            )
        self.status = target
        self.save(update_fields=["status", "updated_at"])


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
        help_text="Reference to product; snapshot fields remain authoritative.",
    )
    product_name = models.CharField(max_length=200)
    product_slug = models.CharField(max_length=200, blank=True)

    shop = models.ForeignKey(
        "shops.Shop",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    shop_name = models.CharField(max_length=200, blank=True)

    seller = models.ForeignKey(
        "sellers.SellerProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    seller_name = models.CharField(max_length=200, blank=True)

    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    quantity = models.PositiveIntegerField(default=1)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    def save(self, *args, **kwargs):
        # Sync unit_price/price and line_total/subtotal
        if not self.unit_price and self.price:
            self.unit_price = self.price
        elif not self.price and self.unit_price:
            self.price = self.unit_price

        if not self.line_total and self.subtotal:
            self.line_total = self.subtotal
        elif not self.subtotal and self.line_total:
            self.subtotal = self.line_total
        elif self.unit_price and self.quantity and not self.line_total:
            self.line_total = self.unit_price * self.quantity
            self.subtotal = self.line_total

        super().save(*args, **kwargs)

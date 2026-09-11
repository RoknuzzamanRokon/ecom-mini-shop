from decimal import Decimal

from django.conf import settings
from django.db import models


class Cart(models.Model):
    """
    Persistent shopping cart for an authenticated user.
    Enforces a strict 1-to-1 relationship per user at the database engine level.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cart",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cart"
        verbose_name_plural = "Carts"

    def __str__(self):
        return f"Cart ({self.user.username})"

    @property
    def total_items_count(self) -> int:
        """Sum of quantities for currently available items."""
        return sum(item.quantity for item in self.items.all() if item.is_available)

    @property
    def total_amount(self) -> Decimal:
        """Authoritative sum of line totals for currently available items."""
        total = Decimal("0.00")
        for item in self.items.all():
            if item.is_available:
                total += item.line_total
        return total

    @property
    def has_unavailable_items(self) -> bool:
        """Returns True if any item in the cart is no longer publicly purchasable."""
        return any(not item.is_available for item in self.items.all())


class CartItem(models.Model):
    """
    Line item inside a user's persistent cart.
    Enforces uniqueness per (cart, product) and positive quantity constraints.
    """
    MIN_QUANTITY = 1
    MAX_QUANTITY = 99

    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        "shop.Product",
        on_delete=models.CASCADE,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cart Item"
        verbose_name_plural = "Cart Items"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"],
                name="unique_cart_product",
            ),
            models.CheckConstraint(
                check=models.Q(quantity__gte=1),
                name="check_positive_cart_quantity",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} (x{self.quantity}) in {self.cart}"

    @property
    def unit_price(self) -> Decimal:
        """Authoritative current unit price from product model."""
        return Decimal(str(self.product.price))

    @property
    def line_total(self) -> Decimal:
        """Authoritative line total calculated server-side."""
        return self.unit_price * self.quantity

    @property
    def is_available(self) -> bool:
        """
        Validates whether the referenced product is still publicly purchasable
        under authoritative public catalog visibility rules.
        """
        return bool(getattr(self.product, "is_publicly_visible", False))

    @property
    def unavailable_reason(self) -> str:
        """Descriptive reason if the item is no longer purchasable."""
        if self.is_available:
            return ""
        if not self.product.is_active:
            return "This product has been deactivated."
        if self.product.status != "PUBLISHED":
            return "This product is no longer published."
        if not self.product.category or not self.product.category.is_active:
            return "This product's category is currently unavailable."
        if not self.product.shop or self.product.shop.status not in ("APPROVED", "ACTIVE"):
            return "The shop selling this product is currently unavailable."
        if not self.product.shop.owner or self.product.shop.owner.status not in ("APPROVED", "ACTIVE"):
            return "The merchant selling this product is currently inactive."
        return "This product is currently unavailable for purchase."

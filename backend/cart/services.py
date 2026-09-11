import logging
from decimal import Decimal
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch
from rest_framework.exceptions import NotFound, ValidationError as DRFValidationError

from shop.models import Product
from shop.services import ProductService
from .models import Cart, CartItem

logger = logging.getLogger(__name__)


class CartService:
    """
    Domain service for customer shopping cart operations.
    Enforces atomic transaction boundaries, row-level locking,
    product eligibility verification, and authoritative price calculation.
    """

    MIN_QUANTITY_PER_ITEM = CartItem.MIN_QUANTITY
    MAX_QUANTITY_PER_ITEM = CartItem.MAX_QUANTITY

    @classmethod
    def get_or_create_cart(cls, user) -> Cart:
        """
        Retrieves or creates a persistent cart for the authenticated user.
        """
        cart, _ = Cart.objects.get_or_create(user=user)
        return cart

    @classmethod
    def get_cart_with_items(cls, user) -> Cart:
        """
        Retrieves the user's cart with items and products prefetched for optimal performance.
        """
        cls.get_or_create_cart(user)
        return (
            Cart.objects.filter(user=user)
            .prefetch_related(
                Prefetch(
                    "items",
                    queryset=CartItem.objects.select_related(
                        "product",
                        "product__category",
                        "product__shop",
                        "product__shop__owner",
                    ),
                )
            )
            .first()
        )

    @classmethod
    def validate_quantity(cls, quantity: int) -> int:
        """
        Validates that quantity is a strictly positive integer within limits.
        """
        try:
            qty = int(quantity)
        except (ValueError, TypeError):
            raise DRFValidationError({"quantity": "Quantity must be a valid integer."})

        if qty < cls.MIN_QUANTITY_PER_ITEM:
            raise DRFValidationError({"quantity": f"Quantity must be at least {cls.MIN_QUANTITY_PER_ITEM}."})

        if qty > cls.MAX_QUANTITY_PER_ITEM:
            raise DRFValidationError(
                {"quantity": f"Quantity cannot exceed {cls.MAX_QUANTITY_PER_ITEM} per item."}
            )

        return qty

    @classmethod
    def add_item(cls, user, product_id: int, quantity: int = 1) -> CartItem:
        """
        Adds a product to the user's cart or increments its quantity.
        Enforces:
          1. Product is currently publicly purchasable (ProductService public rules)
          2. Quantity is valid and within limits
          3. Atomic locking and race reconciliation
        """
        qty = cls.validate_quantity(quantity)

        # 1. Authoritative product eligibility check
        public_product = (
            ProductService.get_public_products_queryset()
            .filter(pk=product_id)
            .first()
        )
        if not public_product:
            raise DRFValidationError(
                {"product_id": "This product is not currently available for purchase."}
            )

        # 2. Atomic mutation with row-level locking
        with transaction.atomic():
            cart = cls.get_or_create_cart(user)

            # Check if CartItem already exists with row-level lock
            item = (
                CartItem.objects.select_for_update()
                .filter(cart=cart, product=public_product)
                .first()
            )

            if item:
                new_qty = item.quantity + qty
                if new_qty > cls.MAX_QUANTITY_PER_ITEM:
                    raise DRFValidationError(
                        {"quantity": f"Total quantity for '{public_product.name}' cannot exceed {cls.MAX_QUANTITY_PER_ITEM}."}
                    )
                item.quantity = new_qty
                item.save(update_fields=["quantity", "updated_at"])
            else:
                item = CartItem.objects.create(
                    cart=cart,
                    product=public_product,
                    quantity=qty,
                )

            logger.info(
                "CartItem added: user=%s product='%s' qty=%s",
                user.username,
                public_product.name,
                item.quantity,
            )
            return item

    @classmethod
    def update_item_quantity(cls, user, item_id: int, quantity: int) -> CartItem:
        """
        Updates the quantity of an existing item in the user's cart.
        Enforces ownership and quantity bounds.
        """
        qty = cls.validate_quantity(quantity)

        with transaction.atomic():
            item = (
                CartItem.objects.select_for_update()
                .select_related("product")
                .filter(pk=item_id, cart__user=user)
                .first()
            )
            if not item:
                raise NotFound("Cart item not found in your cart.")

            item.quantity = qty
            item.save(update_fields=["quantity", "updated_at"])

            logger.info(
                "CartItem updated: user=%s item_id=%s new_qty=%s",
                user.username,
                item_id,
                qty,
            )
            return item

    @classmethod
    def remove_item(cls, user, item_id: int) -> None:
        """
        Removes an item from the user's cart.
        Enforces ownership.
        """
        with transaction.atomic():
            item = CartItem.objects.filter(pk=item_id, cart__user=user).first()
            if not item:
                raise NotFound("Cart item not found in your cart.")

            item.delete()
            logger.info("CartItem removed: user=%s item_id=%s", user.username, item_id)

    @classmethod
    def clear_cart(cls, user) -> None:
        """
        Clears all items from the user's cart.
        """
        with transaction.atomic():
            cart = Cart.objects.filter(user=user).first()
            if cart:
                cart.items.all().delete()
                logger.info("Cart cleared: user=%s", user.username)

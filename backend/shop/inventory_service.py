import logging
from typing import Any, List, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from audit.services import AuditService
from shop.models import InventoryTransaction, Order, OrderItem, Product, ProductInventory

logger = logging.getLogger(__name__)


class InventoryService:
    """
    Server-authoritative domain service for Product inventory management,
    atomic row-level locking, stock adjustments, order reservation,
    and lifecycle synchronization (cancellation release, delivery finalization).
    """

    @classmethod
    def get_or_create_inventory(
        cls,
        product: Product,
        default_available: Optional[int] = None,
    ) -> ProductInventory:
        """
        Retrieves or creates the single authoritative ProductInventory for a product.
        Initializes available_quantity with existing product.stock or default_available.
        """
        inventory = ProductInventory.objects.filter(product=product).first()
        if not inventory:
            with transaction.atomic():
                init_stock = max(0, product.stock if default_available is None else default_available)
                inventory, created = ProductInventory.objects.select_for_update().get_or_create(
                    product=product,
                    defaults={
                        "available_quantity": init_stock,
                        "reserved_quantity": 0,
                        "sold_quantity": 0,
                    },
                )
                if created and init_stock > 0:
                    InventoryTransaction.objects.create(
                        inventory=inventory,
                        product=product,
                        transaction_type=InventoryTransaction.TYPE_INITIAL_STOCK,
                        quantity=init_stock,
                        before_available=0,
                        after_available=init_stock,
                        before_reserved=0,
                        after_reserved=0,
                        before_sold=0,
                        after_sold=0,
                        reason="Initial product stock on inventory creation.",
                    )
        return inventory

    @classmethod
    def adjust_stock(
        cls,
        product: Product,
        quantity_delta: int,
        actor: Optional[Any] = None,
        reason: str = "",
        ip_address: Optional[str] = None,
    ) -> ProductInventory:
        """
        Atomically adjusts available stock for a product by quantity_delta (+/-).
        Enforces:
          1. Row-level concurrency locking via select_for_update().
          2. available_quantity + quantity_delta >= 0 (no negative stock).
          3. Immutably records InventoryTransaction ledger entry.
          4. Records system AuditLog entry.
          5. Backwards-compatible synchronization of Product.stock.
        """
        if quantity_delta == 0:
            raise ValidationError({"quantity": "Adjustment quantity cannot be zero."})

        with transaction.atomic():
            # Ensure inventory row exists and lock it
            cls.get_or_create_inventory(product)
            inventory = ProductInventory.objects.select_for_update().get(product=product)

            new_available = inventory.available_quantity + quantity_delta
            if new_available < 0:
                raise ValidationError({
                    "quantity": (
                        f"Insufficient stock for adjustment. "
                        f"Current available: {inventory.available_quantity}, requested: {quantity_delta}."
                    )
                })

            before_available = inventory.available_quantity
            before_reserved = inventory.reserved_quantity
            before_sold = inventory.sold_quantity

            inventory.available_quantity = new_available
            inventory.save(update_fields=["available_quantity", "updated_at"])

            # Synchronize product.stock for backwards compatibility
            product.stock = new_available
            product.save(update_fields=["stock"])

            # Append immutable transaction record
            tx_type = InventoryTransaction.TYPE_ADJUSTMENT
            InventoryTransaction.objects.create(
                inventory=inventory,
                product=product,
                transaction_type=tx_type,
                quantity=quantity_delta,
                before_available=before_available,
                after_available=new_available,
                before_reserved=before_reserved,
                after_reserved=before_reserved,
                before_sold=before_sold,
                after_sold=before_sold,
                actor=actor,
                reason=reason,
            )

            # Record domain AuditLog
            seller = product.shop.owner if product.shop else None
            AuditService.log(
                action="INVENTORY_ADJUSTED",
                target=product,
                actor=actor,
                shop=product.shop,
                seller=seller,
                metadata={
                    "product_id": product.id,
                    "product_name": product.name,
                    "quantity_delta": quantity_delta,
                    "before_available": before_available,
                    "after_available": new_available,
                    "reason": reason,
                },
                ip_address=ip_address,
            )

            logger.info(
                "Inventory adjusted: product=%s (id=%d) delta=%+d avail=%d->%d by=%s",
                product.name,
                product.id,
                quantity_delta,
                before_available,
                new_available,
                getattr(actor, "username", "system"),
            )
            return inventory

    @classmethod
    def reserve_stock_for_cart(
        cls,
        order: Order,
        cart_items: List[Any],
        actor: Optional[Any] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """
        Atomically reserves stock for each item in the order creation transaction.
        Must be executed within an existing transaction.atomic() block.
        Rejects order creation if any product has available_quantity < item.quantity.
        """
        for item in cart_items:
            product = item.product
            qty = item.quantity

            # Ensure inventory exists and lock row
            cls.get_or_create_inventory(product)
            inventory = ProductInventory.objects.select_for_update().get(product=product)

            if inventory.available_quantity < qty:
                raise ValidationError({
                    "cart": (
                        f"Insufficient stock for '{product.name}'. "
                        f"Available: {inventory.available_quantity}, requested: {qty}."
                    )
                })

            before_available = inventory.available_quantity
            before_reserved = inventory.reserved_quantity
            before_sold = inventory.sold_quantity

            inventory.available_quantity -= qty
            inventory.reserved_quantity += qty
            inventory.save(update_fields=["available_quantity", "reserved_quantity", "updated_at"])

            # Synchronize product.stock
            product.stock = inventory.available_quantity
            product.save(update_fields=["stock"])

            # Match created OrderItem if available
            order_item = order.items.filter(product=product).first() if order.pk else None

            # Append immutable transaction record
            InventoryTransaction.objects.create(
                inventory=inventory,
                product=product,
                transaction_type=InventoryTransaction.TYPE_RESERVATION,
                quantity=qty,
                before_available=before_available,
                after_available=inventory.available_quantity,
                before_reserved=before_reserved,
                after_reserved=inventory.reserved_quantity,
                before_sold=before_sold,
                after_sold=before_sold,
                order=order,
                order_item=order_item,
                actor=actor,
                reason=f"Reserved {qty} units for Order {order.order_number}",
            )

        AuditService.log(
            action="INVENTORY_RESERVED",
            target=order,
            actor=actor,
            metadata={
                "order_number": order.order_number,
                "items_count": len(cart_items),
            },
            ip_address=ip_address,
        )

    @classmethod
    def _order_reserved_quantity(cls, order: Order, product: Product) -> int:
        """
        Units of `product` that *this* order still holds reserved, according to the
        immutable InventoryTransaction ledger.

        An order only ever owns the units its own RESERVATION rows took out of
        available stock, minus whatever has since been released or sold back out of
        that reservation. Orders created outside the reservation flow -- the legacy
        storefront checkout in shop/views.py writes Order/OrderItem rows directly and
        never reserves -- have no RESERVATION row and therefore own nothing.

        Without this bound, releasing such an order would hand back stock that a
        *different* order is holding, inventing availability and opening an oversell
        path.
        """
        totals = {
            row["transaction_type"]: row["total"] or 0
            for row in (
                InventoryTransaction.objects.filter(
                    order=order,
                    product=product,
                    transaction_type__in=[
                        InventoryTransaction.TYPE_RESERVATION,
                        InventoryTransaction.TYPE_RELEASE,
                        InventoryTransaction.TYPE_SALE,
                    ],
                )
                .values("transaction_type")
                .annotate(total=Sum("quantity"))
            )
        }
        reserved = totals.get(InventoryTransaction.TYPE_RESERVATION, 0)
        consumed = (
            totals.get(InventoryTransaction.TYPE_RELEASE, 0)
            + totals.get(InventoryTransaction.TYPE_SALE, 0)
        )
        return max(0, reserved - consumed)

    @classmethod
    def release_order_reservation(
        cls,
        order: Order,
        actor: Optional[Any] = None,
        note: str = "",
        ip_address: Optional[str] = None,
    ) -> None:
        """
        Atomically releases reserved stock back to available stock when an order is CANCELLED.
        Enforces idempotency: does not release twice if already released.
        Releases only what this order itself reserved -- an order with no RESERVATION
        ledger entry releases nothing, so it cannot free another order's stock.
        """
        # Idempotency check: did we already record a RELEASE transaction for this order?
        already_released = InventoryTransaction.objects.filter(
            order=order,
            transaction_type=InventoryTransaction.TYPE_RELEASE,
        ).exists()

        if already_released:
            logger.warning("Order %s inventory reservation already released; skipping duplicate release.", order.order_number)
            return

        order_items = list(order.items.select_for_update().select_related("product"))
        released_count = 0
        unreserved_count = 0

        for item in order_items:
            product = item.product
            if not product:
                continue

            cls.get_or_create_inventory(product)
            inventory = ProductInventory.objects.select_for_update().get(product=product)

            # Never give back more than this order itself reserved. `reserved_quantity`
            # is shared across every open order for the product, so bounding by it alone
            # lets a reservation-less order release someone else's stock.
            owned_reserved = cls._order_reserved_quantity(order, product)
            if owned_reserved <= 0:
                unreserved_count += 1
                logger.warning(
                    "Order %s has no outstanding reservation for product %s (id=%d); "
                    "releasing 0 units and leaving reserved_quantity=%d untouched.",
                    order.order_number,
                    product.name,
                    product.id,
                    inventory.reserved_quantity,
                )
                continue

            # Release up to item.quantity, this order's own reservation, or remaining reserved_quantity
            qty = min(inventory.reserved_quantity, item.quantity, owned_reserved)
            if qty <= 0:
                continue

            before_available = inventory.available_quantity
            before_reserved = inventory.reserved_quantity
            before_sold = inventory.sold_quantity

            inventory.reserved_quantity -= qty
            inventory.available_quantity += qty
            inventory.save(update_fields=["available_quantity", "reserved_quantity", "updated_at"])

            # Synchronize product.stock
            product.stock = inventory.available_quantity
            product.save(update_fields=["stock"])

            InventoryTransaction.objects.create(
                inventory=inventory,
                product=product,
                transaction_type=InventoryTransaction.TYPE_RELEASE,
                quantity=qty,
                before_available=before_available,
                after_available=inventory.available_quantity,
                before_reserved=before_reserved,
                after_reserved=inventory.reserved_quantity,
                before_sold=before_sold,
                after_sold=before_sold,
                order=order,
                order_item=item,
                actor=actor,
                reason=f"Reservation released on order cancellation. Note: {note}".strip(),
            )
            released_count += 1

        AuditService.log(
            action="INVENTORY_RELEASED",
            target=order,
            actor=actor,
            metadata={
                "order_number": order.order_number,
                "released_items_count": released_count,
                "unreserved_items_count": unreserved_count,
                "note": note,
            },
            ip_address=ip_address,
        )
        logger.info(
            "Released inventory reservation for order %s (%d items released, %d items without reservation)",
            order.order_number,
            released_count,
            unreserved_count,
        )

    @classmethod
    def finalize_order_delivery(
        cls,
        order: Order,
        actor: Optional[Any] = None,
        note: str = "",
        ip_address: Optional[str] = None,
    ) -> None:
        """
        Atomically finalizes reserved stock into sold stock when an order transitions to DELIVERED.
        Enforces idempotency: does not record duplicate sales if already delivered.
        """
        # Idempotency check: did we already record a SALE transaction for this order?
        already_finalized = InventoryTransaction.objects.filter(
            order=order,
            transaction_type=InventoryTransaction.TYPE_SALE,
        ).exists()

        if already_finalized:
            logger.warning("Order %s inventory sale already finalized; skipping duplicate sale.", order.order_number)
            return

        order_items = list(order.items.select_for_update().select_related("product"))
        finalized_count = 0

        for item in order_items:
            product = item.product
            if not product:
                continue

            cls.get_or_create_inventory(product)
            inventory = ProductInventory.objects.select_for_update().get(product=product)

            # Move up to item.quantity or remaining reserved_quantity into sold
            qty = min(inventory.reserved_quantity, item.quantity)
            if qty <= 0:
                continue

            before_available = inventory.available_quantity
            before_reserved = inventory.reserved_quantity
            before_sold = inventory.sold_quantity

            inventory.reserved_quantity -= qty
            inventory.sold_quantity += qty
            inventory.save(update_fields=["reserved_quantity", "sold_quantity", "updated_at"])

            InventoryTransaction.objects.create(
                inventory=inventory,
                product=product,
                transaction_type=InventoryTransaction.TYPE_SALE,
                quantity=qty,
                before_available=before_available,
                after_available=before_available,
                before_reserved=before_reserved,
                after_reserved=inventory.reserved_quantity,
                before_sold=before_sold,
                after_sold=inventory.sold_quantity,
                order=order,
                order_item=item,
                actor=actor,
                reason=f"Sale finalized on order delivery. Note: {note}".strip(),
            )
            finalized_count += 1

        AuditService.log(
            action="INVENTORY_DELIVERED",
            target=order,
            actor=actor,
            metadata={
                "order_number": order.order_number,
                "finalized_items_count": finalized_count,
                "note": note,
            },
            ip_address=ip_address,
        )
        logger.info("Finalized inventory delivery for order %s (%d items)", order.order_number, finalized_count)

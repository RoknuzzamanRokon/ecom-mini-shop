import logging
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional, Union

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import NotFound, PermissionDenied

from audit.services import AuditService
from cart.models import Cart, CartItem
from customers.models import Address
from points.models import PointTransaction
from points.services import InsufficientPointsError, PointService
from rbac.models import Role
from rbac.services import get_user_role_codes, has_user_permission
from sellers.models import SellerProfile
from shops.models import Shop
from .models import Category, Order, OrderItem, Product

logger = logging.getLogger(__name__)


class ProductServiceError(Exception):
    """Base exception for product domain services."""
    pass


class IneligibleSellerError(ProductServiceError):
    """Raised when an inactive, unapproved, or suspended seller attempts product actions."""
    pass


class ProductOwnershipError(ProductServiceError):
    """Raised when a seller attempts to manage a product or assign a shop they do not own."""
    pass


class ProductService:
    """
    Centralized domain service for Product mutations, lifecycle transitions,
    point deduction, and audit logging.
    Enforces atomic transaction boundaries and guarantees consistent rollback on failure.
    """

    @classmethod
    def create_product(
        cls,
        seller: SellerProfile,
        name: str,
        category: Category,
        shop: Shop,
        description: str,
        price: Decimal,
        old_price: Optional[Decimal] = None,
        stock: int = 0,
        badge: str = "",
        image=None,
        is_active: bool = True,
        actor=None,
        ip_address: Optional[str] = None,
    ) -> Product:
        """
        Creates a new product belonging to a seller's shop in an atomic transaction.
        Enforces:
          1. Seller operational status (APPROVED or ACTIVE)
          2. RBAC permission ('products.create')
          3. Shop ownership (shop.owner == seller)
          4. Authoritative point creation cost determination
          5. Concurrency-safe point balance verification & atomic debit
          6. Comprehensive audit log entry
        Rolls back all changes if any step fails.
        """
        # 1. Validate seller profile & operational status
        if not seller or not seller.is_operational:
            status_desc = seller.status if seller else "Unknown"
            raise IneligibleSellerError(
                f"Seller is currently '{status_desc}'. Only active/approved sellers can create products."
            )

        # 2. Validate shop relationship & ownership
        if not shop:
            raise ProductOwnershipError("A valid shop must be specified for product creation.")

        if shop.owner != seller:
            raise ProductOwnershipError("You can only create products for shops that you own.")

        if shop.status not in (Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE):
            raise ProductOwnershipError(
                f"Shop '{shop.name}' is currently '{shop.status}'. Products can only be created for active/approved shops."
            )

        # 3. Validate RBAC permission on actor
        if actor and getattr(actor, "is_authenticated", False):
            if not has_user_permission(actor, "products.create"):
                raise PermissionDenied("You do not have permission to create products ('products.create' required).")

        # 4. Determine authoritative required point cost
        required_points = PointService.get_product_creation_cost()

        # 5. Check seller wallet balance before starting creation
        current_balance = PointService.get_balance(seller)
        if current_balance < required_points:
            raise InsufficientPointsError(
                f"Insufficient points: creating a product requires {required_points} points, "
                f"but your wallet currently has {current_balance} points."
            )

        # 6. Execute atomic creation, point debit, and audit logging
        with transaction.atomic():
            # A. Generate unique slug
            base_slug = slugify(name.strip())
            slug = base_slug
            counter = 1
            while Product.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            # B. Create and save the Product
            product = Product(
                name=name.strip(),
                slug=slug,
                category=category,
                shop=shop,
                description=description.strip(),
                price=price,
                old_price=old_price,
                stock=max(0, stock),
                badge=badge.strip() if badge else "",
                is_active=is_active,
                status=Product.STATUS_DRAFT,
            )
            if image:
                product.image = image
            product.full_clean()
            product.save()

            # Initialize authoritative ProductInventory record
            from shop.inventory_service import InventoryService
            InventoryService.get_or_create_inventory(product, default_available=product.stock)

            # B. Atomically debit points via PointService (enforces row locking & ledger append)
            if required_points > 0:
                PointService.debit(
                    seller=seller,
                    amount=required_points,
                    transaction_type=PointTransaction.TYPE_PRODUCT_CREATION,
                    reason=f"Product creation fee for '{product.name}'",
                    actor=actor,
                    reference_type="PRODUCT",
                    reference_id=str(product.id),
                )

            # C. Record immutable audit log entry
            AuditService.log(
                action="PRODUCT_CREATED",
                target=product,
                actor=actor,
                shop=shop,
                seller=seller,
                metadata={
                    "name": product.name,
                    "price": str(product.price),
                    "category": category.name,
                    "shop": shop.name,
                    "points_debited": required_points,
                },
                ip_address=ip_address,
            )

            logger.info(
                "Product created: id=%s name='%s' shop=%s seller=%s cost=%s pts",
                product.id,
                product.name,
                shop.name,
                seller.business_name,
                required_points,
            )
            return product

    @classmethod
    def update_product(
        cls,
        product: Product,
        seller: SellerProfile,
        data: Dict[str, Any],
        actor=None,
        ip_address: Optional[str] = None,
    ) -> Product:
        """
        Updates an existing product with strict ownership verification.
        Disallows reassigning the product to another seller's shop.
        """
        if not product.shop or product.shop.owner != seller:
            raise ProductOwnershipError("You do not own the shop associated with this product.")

        if not seller.is_operational:
            raise IneligibleSellerError("Suspended or unapproved sellers cannot update products.")

        if actor and getattr(actor, "is_authenticated", False):
            if not has_user_permission(actor, "products.update"):
                raise PermissionDenied("You do not have permission to update products.")

        with transaction.atomic():
            changed_fields = []

            # If shop reassignment is requested, ensure target shop belongs to same seller
            if "shop" in data:
                new_shop = data["shop"]
                if new_shop != product.shop:
                    if not new_shop or new_shop.owner != seller:
                        raise ProductOwnershipError("Cannot assign product to a shop you do not own.")
                    product.shop = new_shop
                    changed_fields.append("shop")

            updatable_fields = [
                "name",
                "category",
                "description",
                "price",
                "old_price",
                "stock",
                "badge",
                "is_active",
                "image",
            ]
            for field in updatable_fields:
                if field in data:
                    setattr(product, field, data[field])
                    changed_fields.append(field)

            product.full_clean()
            product.save()

            AuditService.log(
                action="PRODUCT_UPDATED",
                target=product,
                actor=actor,
                shop=product.shop,
                seller=seller,
                metadata={"changed_fields": changed_fields},
                ip_address=ip_address,
            )

            logger.info("Product updated: id=%s by seller=%s", product.id, seller.business_name)
            return product

    @classmethod
    def delete_product(
        cls,
        product: Product,
        seller: SellerProfile,
        actor=None,
        ip_address: Optional[str] = None,
    ):
        """
        Deletes a product with strict ownership verification.
        """
        if not product.shop or product.shop.owner != seller:
            raise ProductOwnershipError("You do not own the shop associated with this product.")

        if not seller.is_operational:
            raise IneligibleSellerError("Suspended or unapproved sellers cannot delete products.")

        if actor and getattr(actor, "is_authenticated", False):
            if not has_user_permission(actor, "products.delete"):
                raise PermissionDenied("You do not have permission to delete products.")

        with transaction.atomic():
            AuditService.log(
                action="PRODUCT_DELETED",
                target=product,
                actor=actor,
                shop=product.shop,
                seller=seller,
                metadata={"product_name": product.name, "product_id": product.id},
                ip_address=ip_address,
            )
            product.delete()
            logger.info("Product deleted: id=%s by seller=%s", product.id, seller.business_name)

    @classmethod
    def get_public_products_queryset(cls):
        """
        Authoritative public catalog queryset with optimal join prefetching.
        Enforces public visibility at database level:
          - product.is_active is True
          - product.status == 'PUBLISHED'
          - category.is_active is True
          - shop is not null and shop.status in ['APPROVED', 'ACTIVE']
          - shop.owner is operational (status in ['APPROVED', 'ACTIVE'])
        """
        return (
            Product.objects.public()
            .select_related("category", "shop", "shop__owner")
            .prefetch_related("images")
        )

    @classmethod
    def get_public_product_by_identifier(cls, identifier: Union[int, str]) -> Product:
        """
        Retrieves a single publicly visible product by its primary key (ID) or slug.
        Raises Http404 if the product does not exist or fails public visibility rules.
        """
        qs = cls.get_public_products_queryset()
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            return get_object_or_404(qs, pk=int(identifier))
        return get_object_or_404(qs, slug=identifier)

    @classmethod
    def get_public_categories_queryset(cls):
        """
        Returns active categories annotated with the count of publicly visible products only.
        """
        return (
            Category.objects.filter(is_active=True)
            .annotate(
                products_count=Count(
                    "products",
                    filter=Q(
                        products__is_active=True,
                        products__status=Product.STATUS_PUBLISHED,
                        products__shop__isnull=False,
                        products__shop__status__in=[Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE],
                        products__shop__owner__status__in=[SellerProfile.STATUS_APPROVED, SellerProfile.STATUS_ACTIVE],
                    ),
                )
            )
            .order_by("name")
        )


class OrderService:
    """
    Domain service for Order lifecycle, atomic Cart-to-Order conversion,
    concurrency control, authoritative snapshot recording, and audit logging.
    """

    @classmethod
    def generate_order_number(cls) -> str:
        """
        Generates a unique, server-controlled order reference string.
        Format: ORD<YYYYMMDD><6-HEX> (e.g. ORD20260911A1B2C3).
        """
        prefix = f"ORD{timezone.now():%Y%m%d}"
        for _ in range(10):
            candidate = f"{prefix}{uuid.uuid4().hex[:6].upper()}"
            if not Order.objects.filter(order_number=candidate).exists():
                return candidate
        return f"{prefix}{uuid.uuid4().hex[:10].upper()}"

    @classmethod
    def create_order_from_cart(
        cls,
        user,
        address_id: Optional[int] = None,
        address_data: Optional[Dict[str, Any]] = None,
        actor: Optional[Any] = None,
        ip_address: Optional[str] = None,
    ) -> Order:
        """
        Atomically converts the authenticated user's current Cart into a persistent Order snapshot.

        Enforces:
          1. Row-level locking on the user's Cart and CartItems to prevent duplicate orders.
          2. Re-validation of all cart products against authoritative public visibility.
          3. Rejection of empty or stale carts without clearing the cart.
          4. Historical snapshots of shipping address, products, shops, and sellers.
          5. Server-authoritative Decimal price calculation ignoring any client inputs.
          6. Atomic cart clearing upon successful order creation.
          7. AuditLog entry for ORDER_CREATED.
        """
        with transaction.atomic():
            # 1. Lock user's Cart with row-level lock
            cart = Cart.objects.select_for_update().filter(user=user).first()
            if not cart:
                raise ValidationError({"cart": "Shopping cart not found for this user."})

            # 2. Lock CartItems with row-level lock
            cart_items = list(
                CartItem.objects.select_for_update()
                .filter(cart=cart)
                .select_related(
                    "product",
                    "product__category",
                    "product__shop",
                    "product__shop__owner",
                )
            )
            if not cart_items:
                raise ValidationError({"cart": "Your shopping cart is empty."})

            # 3. Authoritative public product eligibility check
            for item in cart_items:
                product = item.product
                if not product or not product.is_active:
                    raise ValidationError(
                        {"cart": f"Product '{product.name if product else 'Unknown'}' is no longer active."}
                    )
                if product.status != Product.STATUS_PUBLISHED:
                    raise ValidationError(
                        {"cart": f"Product '{product.name}' is no longer published."}
                    )
                if not product.category or not product.category.is_active:
                    raise ValidationError(
                        {"cart": f"The category for product '{product.name}' is currently unavailable."}
                    )
                if not product.shop or product.shop.status not in (Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE):
                    raise ValidationError(
                        {"cart": f"The shop for product '{product.name}' is currently unavailable."}
                    )
                if not product.shop.owner or product.shop.owner.status not in (SellerProfile.STATUS_APPROVED, SellerProfile.STATUS_ACTIVE):
                    raise ValidationError(
                        {"cart": f"The merchant selling '{product.name}' is currently unavailable."}
                    )
                if item.quantity < 1:
                    raise ValidationError(
                        {"cart": f"Invalid quantity for '{product.name}'."}
                    )

            # 4. Resolve shipping address and historical snapshot
            shipping_address = None
            if address_id:
                shipping_address = Address.objects.filter(id=address_id, user=user).first()
                if not shipping_address:
                    raise ValidationError({"address_id": "Selected address does not exist or does not belong to you."})
                recipient_name = shipping_address.recipient_name
                phone = shipping_address.phone
                line_1 = shipping_address.address_line_1
                line_2 = shipping_address.address_line_2
                area = shipping_address.area
                city = shipping_address.city
                state = shipping_address.state
                postal = shipping_address.postal_code
                country = shipping_address.country
            elif address_data:
                recipient_name = (
                    address_data.get("shipping_recipient_name")
                    or address_data.get("customer_name")
                    or address_data.get("recipient_name")
                    or user.get_full_name()
                    or user.username
                )
                phone = address_data.get("shipping_phone") or address_data.get("phone") or ""
                line_1 = address_data.get("shipping_address_line_1") or address_data.get("address") or ""
                line_2 = address_data.get("shipping_address_line_2") or ""
                area = address_data.get("shipping_area") or address_data.get("area") or ""
                city = address_data.get("shipping_city") or address_data.get("city") or ""
                state = address_data.get("shipping_state") or address_data.get("state") or ""
                postal = address_data.get("shipping_postal_code") or address_data.get("postal_code") or ""
                country = address_data.get("shipping_country") or address_data.get("country") or "Bangladesh"
            else:
                default_addr = Address.objects.filter(user=user, is_default=True).first()
                if default_addr:
                    shipping_address = default_addr
                    recipient_name = default_addr.recipient_name
                    phone = default_addr.phone
                    line_1 = default_addr.address_line_1
                    line_2 = default_addr.address_line_2
                    area = default_addr.area
                    city = default_addr.city
                    state = default_addr.state
                    postal = default_addr.postal_code
                    country = default_addr.country
                else:
                    profile = getattr(user, "customer_profile", None)
                    recipient_name = (profile.display_name if profile else None) or user.get_full_name() or user.username
                    phone = (profile.phone if profile else "")
                    line_1 = "Standard Delivery Address"
                    line_2 = ""
                    area = ""
                    city = "Dhaka"
                    state = ""
                    postal = ""
                    country = "Bangladesh"

            # 5. Calculate authoritative Decimal totals and prepare OrderItem snapshots
            subtotal = Decimal("0.00")
            order_items_to_create = []
            for item in cart_items:
                product = item.product
                unit_price = Decimal(str(product.price))
                line_total = unit_price * item.quantity
                subtotal += line_total

                shop = product.shop
                seller = shop.owner if shop else None

                order_items_to_create.append({
                    "product": product,
                    "product_name": product.name,
                    "product_slug": product.slug,
                    "shop": shop,
                    "shop_name": shop.name if shop else "",
                    "seller": seller,
                    "seller_name": seller.business_name if seller else "",
                    "unit_price": unit_price,
                    "quantity": item.quantity,
                    "line_total": line_total,
                })

            discount_total = Decimal("0.00")
            shipping_fee = Decimal("0.00")
            total_amount = subtotal + shipping_fee - discount_total

            # 6. Generate order number
            order_number = cls.generate_order_number()

            # 7. Create Order snapshot
            order = Order.objects.create(
                user=user,
                order_number=order_number,
                status=Order.STATUS_PENDING,
                shipping_address=shipping_address,
                shipping_recipient_name=recipient_name,
                shipping_phone=phone,
                shipping_address_line_1=line_1,
                shipping_address_line_2=line_2,
                shipping_area=area,
                shipping_city=city,
                shipping_state=state,
                shipping_postal_code=postal,
                shipping_country=country,
                customer_name=recipient_name,
                phone=phone,
                address=line_1,
                city=city,
                subtotal=subtotal,
                discount_total=discount_total,
                shipping_fee=shipping_fee,
                total_amount=total_amount,
            )

            # 8. Create OrderItem snapshots
            for item_info in order_items_to_create:
                OrderItem.objects.create(
                    order=order,
                    product=item_info["product"],
                    product_name=item_info["product_name"],
                    product_slug=item_info["product_slug"],
                    shop=item_info["shop"],
                    shop_name=item_info["shop_name"],
                    seller=item_info["seller"],
                    seller_name=item_info["seller_name"],
                    unit_price=item_info["unit_price"],
                    price=item_info["unit_price"],
                    quantity=item_info["quantity"],
                    line_total=item_info["line_total"],
                    subtotal=item_info["line_total"],
                )

            # 9. Atomically reserve inventory stock for cart items
            from shop.inventory_service import InventoryService
            InventoryService.reserve_stock_for_cart(
                order=order,
                cart_items=cart_items,
                actor=actor or user,
                ip_address=ip_address,
            )

            # 10. Clear user's Cart items atomically
            CartItem.objects.filter(cart=cart).delete()

            # 11. Record immutable AuditLog entry
            AuditService.log(
                action="ORDER_CREATED",
                target=order,
                actor=actor or user,
                metadata={
                    "order_number": order.order_number,
                    "total_amount": str(order.total_amount),
                    "items_count": len(order_items_to_create),
                },
                ip_address=ip_address,
            )

            logger.info(
                "Order created: user=%s order_number=%s total=%s items=%d",
                user.username,
                order.order_number,
                order.total_amount,
                len(order_items_to_create),
            )
            return order

    @classmethod
    def transition_order_status(
        cls,
        order: Order,
        new_status: str,
        actor: Optional[Any] = None,
        note: str = "",
        ip_address: Optional[str] = None,
    ) -> Order:
        """
        Controlled state transition for an Order with row-level locking and audit logging.
        """
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().filter(pk=order.pk).first()
            if not locked_order:
                raise ValidationError({"order": "Order not found."})

            old_status = locked_order.status
            locked_order.transition_to(new_status)
            order.status = locked_order.status
            order.updated_at = locked_order.updated_at

            # Apply atomic inventory lifecycle transitions
            from shop.inventory_service import InventoryService
            if locked_order.status == Order.STATUS_CANCELLED:
                InventoryService.release_order_reservation(
                    order=locked_order,
                    actor=actor,
                    note=note,
                    ip_address=ip_address,
                )
            elif locked_order.status == Order.STATUS_DELIVERED:
                InventoryService.finalize_order_delivery(
                    order=locked_order,
                    actor=actor,
                    note=note,
                    ip_address=ip_address,
                )

            AuditService.log(
                action="ORDER_STATUS_UPDATED",
                target=locked_order,
                actor=actor,
                metadata={
                    "order_number": locked_order.order_number,
                    "old_status": old_status,
                    "new_status": locked_order.status,
                    "note": note,
                },
                ip_address=ip_address,
            )

            logger.info(
                "Order status updated: order=%s old=%s new=%s actor=%s",
                locked_order.order_number,
                old_status,
                locked_order.status,
                getattr(actor, "username", "system"),
            )
            return locked_order

    @classmethod
    def get_seller_orders_queryset(cls, seller: SellerProfile):
        """
        Returns authoritative queryset of orders containing items belonging to the seller.
        Prefetches only items owned by the seller to prevent data leaks.
        """
        seller_items_prefetch = Prefetch(
            "items",
            queryset=OrderItem.objects.filter(
                Q(seller=seller) | Q(shop__owner=seller)
            ).select_related("product", "shop", "seller"),
            to_attr="seller_items",
        )

        return (
            Order.objects.filter(
                Q(items__seller=seller) | Q(items__shop__owner=seller)
            )
            .distinct()
            .prefetch_related(seller_items_prefetch)
            .order_by("-created_at")
        )

    @classmethod
    def get_seller_order(cls, order_identifier: Union[int, str], seller: SellerProfile) -> Order:
        """
        Retrieves a single order for a seller by order_number or id.
        Enforces server-side ownership isolation. If the order does not contain
        items owned by this seller, raises NotFound.
        """
        seller_items_prefetch = Prefetch(
            "items",
            queryset=OrderItem.objects.filter(
                Q(seller=seller) | Q(shop__owner=seller)
            ).select_related("product", "shop", "seller"),
            to_attr="seller_items",
        )

        lookup_str = str(order_identifier).strip()
        qs = Order.objects.prefetch_related(seller_items_prefetch)
        if lookup_str.isdigit():
            order = qs.filter(id=int(lookup_str)).first()
        else:
            order = qs.filter(order_number=lookup_str).first()

        if not order:
            raise NotFound("Order not found.")

        # Verify seller ownership of at least one item in the order
        has_seller_item = OrderItem.objects.filter(
            order=order
        ).filter(
            Q(seller=seller) | Q(shop__owner=seller)
        ).exists()

        if not has_seller_item:
            raise NotFound("Order not found.")

        return order

    @classmethod
    def transition_seller_order_status(
        cls,
        order: Order,
        new_status: str,
        seller: SellerProfile,
        actor: Optional[Any] = None,
        note: str = "",
        ip_address: Optional[str] = None,
    ) -> Order:
        """
        Controlled state transition initiated by a seller.
        Enforces:
          1. Row-level concurrency locking via select_for_update().
          2. Seller owns items in this order.
          3. Multi-seller safety: If order contains items from other sellers,
             rejects unilateral status change by single seller (unless actor has staff override).
          4. Valid state machine transition via order.transition_to().
          5. Immutable audit logging via AuditService.
        """
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().filter(pk=order.pk).first()
            if not locked_order:
                raise ValidationError({"order": "Order not found."})

            # Check seller ownership of items in this order
            seller_items = locked_order.items.filter(
                Q(seller=seller) | Q(shop__owner=seller)
            )
            if not seller_items.exists():
                raise PermissionDenied("You do not have items in this order.")

            # Multi-seller safety check
            other_items = locked_order.items.exclude(
                Q(seller=seller) | Q(shop__owner=seller)
            )
            if other_items.exists():
                is_staff_override = False
                if actor and getattr(actor, "is_authenticated", False):
                    role_codes = get_user_role_codes(actor)
                    is_staff_override = (
                        actor.is_superuser
                        or Role.ROLE_SUPER_ADMINISTRATOR in role_codes
                        or has_user_permission(actor, "orders.update")
                    )
                if not is_staff_override:
                    raise ValidationError({
                        "order": "This order contains items from multiple merchants. "
                                 "Unilateral status updates are restricted to ensure fulfillment safety across all merchants. "
                                 "Please contact platform operations."
                    })

            old_status = locked_order.status
            locked_order.transition_to(new_status)
            order.status = locked_order.status
            order.updated_at = locked_order.updated_at

            # Apply atomic inventory lifecycle transitions
            from shop.inventory_service import InventoryService
            if locked_order.status == Order.STATUS_CANCELLED:
                InventoryService.release_order_reservation(
                    order=locked_order,
                    actor=actor,
                    note=note,
                    ip_address=ip_address,
                )
            elif locked_order.status == Order.STATUS_DELIVERED:
                InventoryService.finalize_order_delivery(
                    order=locked_order,
                    actor=actor,
                    note=note,
                    ip_address=ip_address,
                )

            AuditService.log(
                action="ORDER_STATUS_UPDATED",
                target=locked_order,
                actor=actor,
                seller=seller,
                metadata={
                    "order_number": locked_order.order_number,
                    "old_status": old_status,
                    "new_status": locked_order.status,
                    "initiator": "seller",
                    "seller_id": seller.id,
                    "seller_name": seller.business_name,
                    "note": note,
                },
                ip_address=ip_address,
            )

            logger.info(
                "Seller updated order status: order=%s seller=%s old=%s new=%s actor=%s",
                locked_order.order_number,
                seller.business_name,
                old_status,
                locked_order.status,
                getattr(actor, "username", "system"),
            )
            return locked_order

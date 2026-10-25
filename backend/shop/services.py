import logging
import uuid
from decimal import Decimal
from typing import Any, Dict, Optional, Union

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.exceptions import NotFound, PermissionDenied

from audit.services import AuditService
from cart.models import Cart, CartItem
from config.params import is_whole_number
from customers.models import Address
from notifications import events
from notifications.publisher import publish
from points.models import PointTransaction
from points.services import InsufficientPointsError, PointService
from rbac.models import Role
from rbac.services import get_user_role_codes, has_user_permission
from sellers.models import SellerProfile
from sellers.services import count_seller_products, get_product_limit
from shops.models import Shop
from .models import Category, Order, OrderItem, Payment, Product

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


class ProductLimitExceededError(ProductServiceError):
    """Raised when a Limited Shop Owner already holds their maximum number of products."""
    pass


class ProductModerationError(ProductServiceError):
    """Raised when staff moderation refuses an action, e.g. publishing for a shop that is not live."""
    pass


class StockConflictError(ProductServiceError):
    """Raised when a stock edit was made against a figure that has since changed."""

    def __init__(self, current_stock: int):
        super().__init__(
            f"Stock changed since you opened this product: {current_stock} available now. "
            "Nothing was saved. Check the stock and save again."
        )
        self.current_stock = current_stock


# Past tense of each moderation action, for the default audit reason.
MODERATION_ACTION_VERBS = {
    "approve": "approved",
    "reject": "rejected",
    "publish": "published",
    "unpublish": "unpublished",
}


class ProductService:
    """
    Centralized domain service for Product mutations, lifecycle transitions,
    point deduction, and audit logging.
    Enforces atomic transaction boundaries and guarantees consistent rollback on failure.
    """

    @staticmethod
    def _check_product_limit(seller: SellerProfile, product_limit: int) -> None:
        if count_seller_products(seller) >= product_limit:
            noun = "product" if product_limit == 1 else "products"
            raise ProductLimitExceededError(
                f"You have reached the Limited Shop Owner limit of {product_limit} {noun}. "
                "Delete a product to free a slot."
            )

    @classmethod
    def check_admin_creation_allowed(cls, seller: SellerProfile) -> None:
        """
        The Limited-owner product cap and the points balance, for a product
        about to be added in the Django admin (BUG-046). Takes the seller row
        lock that create_product takes; the admin's change form runs in one
        transaction, so the lock holds until the product is saved. Raises
        ProductLimitExceededError or InsufficientPointsError.
        """
        product_limit = get_product_limit(seller)
        if product_limit is not None:
            SellerProfile.objects.select_for_update().filter(pk=seller.pk).first()
            cls._check_product_limit(seller, product_limit)
        required_points = PointService.get_product_creation_cost()
        balance = PointService.get_balance(seller)
        if balance < required_points:
            raise InsufficientPointsError(
                f"Insufficient points: creating a product requires {required_points} points, "
                f"but {seller.business_name}'s wallet has {balance} points."
            )

    @classmethod
    def record_admin_created_product(cls, product: Product, actor=None, ip_address: Optional[str] = None) -> None:
        """
        What create_product does after saving, for a product the Django admin
        has just saved: the inventory row, the creation fee (every new product
        costs points, whoever adds it) and the PRODUCT_CREATED audit row. Call
        inside the admin's transaction, after check_admin_creation_allowed().
        """
        from shop.inventory_service import InventoryService

        seller = product.shop.owner
        InventoryService.get_or_create_inventory(product, default_available=product.stock)
        required_points = PointService.get_product_creation_cost()
        PointService.debit(
            seller=seller,
            amount=required_points,
            transaction_type=PointTransaction.TYPE_PRODUCT_CREATION,
            reason=f"Product creation fee for '{product.name}' (added in the Django admin)",
            actor=actor,
            reference_type="PRODUCT",
            reference_id=str(product.id),
        )
        AuditService.log(
            action="PRODUCT_CREATED",
            target=product,
            actor=actor,
            shop=product.shop,
            seller=seller,
            metadata={
                "name": product.name,
                "price": str(product.price),
                "category": product.category.name if product.category_id else None,
                "shop": product.shop.name,
                "points_debited": required_points,
                "created_via": "django_admin",
            },
            ip_address=ip_address,
        )

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
          2. (No RBAC code since TASK-005: seller status is the gate)
          3. Shop ownership (shop.owner == seller)
          4. The Limited Shop Owner product limit
          5. Authoritative point creation cost determination
          6. Concurrency-safe point balance verification & atomic debit
          7. Comprehensive audit log entry
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

        # 3. No RBAC code: an operational seller creating in their own shop is
        # the whole rule (TASK-005), checked above.

        # 4. Limited Shop Owners may hold only a fixed number of products. Checked
        # here so a seller at the limit hears about it before any points message,
        # and again under a lock inside the transaction below.
        product_limit = get_product_limit(seller)
        if product_limit is not None:
            cls._check_product_limit(seller, product_limit)

        # 5. Determine authoritative required point cost
        required_points = PointService.get_product_creation_cost()

        # 6. Check seller wallet balance before starting creation
        current_balance = PointService.get_balance(seller)
        if current_balance < required_points:
            raise InsufficientPointsError(
                f"Insufficient points: creating a product requires {required_points} points, "
                f"but your wallet currently has {current_balance} points."
            )

        # 7. Execute atomic creation, point debit, and audit logging
        with transaction.atomic():
            if product_limit is not None:
                # Lock the seller row so two concurrent creates cannot both pass the count.
                SellerProfile.objects.select_for_update().filter(pk=seller.pk).first()
                cls._check_product_limit(seller, product_limit)

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
            # Every new product costs points (ProductCreationCost is at least 1).
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

        An absolute ``stock`` is applied only if ``expected_stock`` (the figure
        the seller edited) still matches; otherwise StockConflictError, and
        nothing is saved.
        """
        if not product.shop or product.shop.owner != seller:
            raise ProductOwnershipError("You do not own the shop associated with this product.")

        if not seller.is_operational:
            raise IneligibleSellerError("Suspended or unapproved sellers cannot update products.")

        with transaction.atomic():
            changed_fields = []

            # A stale absolute stock would put units reserved since the form
            # was opened back on sale (BUG-008). Lock and compare before
            # anything is written.
            locked_inventory = None
            if "stock" in data:
                from shop.inventory_service import InventoryService
                from shop.models import ProductInventory

                InventoryService.get_or_create_inventory(product)
                locked_inventory = ProductInventory.objects.select_for_update().get(product=product)
                expected_stock = data.get("expected_stock")
                if expected_stock is not None and expected_stock != locked_inventory.available_quantity:
                    raise StockConflictError(locked_inventory.available_quantity)

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

            # Stock is authoritatively owned by ProductInventory. Route the requested
            # absolute stock value through InventoryService as a locked delta adjustment
            # so Product.stock and ProductInventory.available_quantity cannot desync
            # (see Known Issues #2 in docs/MINISHOP_REVIEW_STATE.md).
            if locked_inventory is not None:
                stock_delta = data["stock"] - locked_inventory.available_quantity
                if stock_delta != 0:
                    InventoryService.adjust_stock(
                        product=product,
                        quantity_delta=stock_delta,
                        actor=actor,
                        reason="Stock updated via product edit.",
                        ip_address=ip_address,
                    )
                    changed_fields.append("stock")

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
    def has_gone_live(cls, product: Product) -> bool:
        """
        Whether the product was ever published. Moderation can move a product
        to any status, so a REJECTED one may have been live before; the
        publish audit row is what tells.
        """
        from audit.models import AuditLog

        if product.status in (Product.STATUS_PUBLISHED, Product.STATUS_UNPUBLISHED):
            return True
        return AuditLog.objects.filter(
            action="ADMIN_PRODUCT_PUBLISH", target_type="Product", target_id=str(product.pk)
        ).exists()

    @classmethod
    def refund_creation_fee(cls, product: Product, actor=None) -> Optional[PointTransaction]:
        """
        Gives the seller back the creation fee of a product that never went
        live (TASK-048 decision 6), once. None when there is nothing to refund:
        no fee was charged, it was refunded already, or the product was live.
        """
        if not product.shop_id or cls.has_gone_live(product):
            return None
        reference = {"reference_type": "PRODUCT", "reference_id": str(product.pk)}
        fee = PointTransaction.objects.filter(
            transaction_type=PointTransaction.TYPE_PRODUCT_CREATION, **reference
        ).order_by("created_at").first()
        if fee is None or PointTransaction.objects.filter(
            transaction_type=PointTransaction.TYPE_REFUND, **reference
        ).exists():
            return None
        return PointService.credit(
            seller=product.shop.owner,
            amount=fee.amount,
            transaction_type=PointTransaction.TYPE_REFUND,
            reason=f"Creation fee refunded: '{product.name}' was deleted before it went live",
            actor=actor,
            **reference,
        )

    @classmethod
    def delete_by_staff(cls, product: Product, actor, ip_address: Optional[str] = None) -> None:
        """
        A staff deletion (the Django admin): refunds the creation fee when the
        product never went live, writes PRODUCT_DELETED, then deletes it, in
        one transaction. A seller deleting their own product gets no refund.
        """
        with transaction.atomic():
            refund = cls.refund_creation_fee(product, actor=actor)
            AuditService.log(
                action="PRODUCT_DELETED",
                target=product,
                actor=actor,
                shop=product.shop,
                seller=product.shop.owner if product.shop_id else None,
                metadata={
                    "product_name": product.name,
                    "product_id": product.id,
                    "deleted_by": "staff",
                    "fee_refunded": refund.amount if refund else 0,
                },
                ip_address=ip_address,
            )
            product.delete()
            logger.info("Product deleted by staff: id=%s refund=%s", product.id, refund.amount if refund else 0)

    # Statuses a seller may send to review: their own draft, or a listing
    # staff rejected and the seller has since corrected.
    SUBMITTABLE_STATUSES = (Product.STATUS_DRAFT, Product.STATUS_REJECTED)

    @classmethod
    def submit_for_review(
        cls,
        product: Product,
        seller: SellerProfile,
        actor=None,
        ip_address: Optional[str] = None,
    ) -> Product:
        """
        The seller's half of publication (TASK-048 decision 2): DRAFT or
        REJECTED -> SUBMITTED. Staff then approve or reject, and publish, in
        the Console. Writes one PRODUCT_SUBMITTED audit row.
        """
        if not product.shop or product.shop.owner != seller:
            raise ProductOwnershipError("You do not own the shop associated with this product.")

        if not seller.is_operational:
            raise IneligibleSellerError("Suspended or unapproved sellers cannot submit products for review.")

        with transaction.atomic():
            product = Product.objects.select_for_update().select_related("shop").get(pk=product.pk)
            if product.status not in cls.SUBMITTABLE_STATUSES:
                raise ProductModerationError(
                    f"Only a draft or rejected product can be submitted for review; this one is {product.status}."
                )
            previous_status = product.status
            previous_reason = product.rejection_reason
            product.status = Product.STATUS_SUBMITTED
            product.submitted_at = timezone.now()
            # The old reason answered the previous version; it stays in the audit row.
            product.rejection_reason = ""
            product.save(update_fields=["status", "submitted_at", "rejection_reason", "updated_at"])

            AuditService.log(
                action="PRODUCT_SUBMITTED",
                target=product,
                actor=actor,
                shop=product.shop,
                seller=seller,
                previous_state={"status": previous_status, "rejection_reason": previous_reason},
                new_state={"status": product.status},
                ip_address=ip_address,
            )
            logger.info("Product submitted for review: id=%s by seller=%s", product.id, seller.business_name)
            return product

    # --- Staff moderation --------------------------------------------------
    # Each action applies from any status; only publish has preconditions.
    # The caller authorizes the actor and locks the row. Each action writes
    # one ADMIN_PRODUCT_<ACTION> audit row in the same transaction.

    @classmethod
    @transaction.atomic
    def approve(cls, product: Product, actor, reason: str = "", ip_address: Optional[str] = None) -> Product:
        previous_status = product.status
        product.status = Product.STATUS_APPROVED
        product.reviewed_by = actor
        product.reviewed_at = timezone.now()
        product.rejection_reason = ""
        return cls._record_moderation(product, "approve", previous_status, actor, reason, ip_address)

    @classmethod
    @transaction.atomic
    def reject(cls, product: Product, actor, reason: str = "", ip_address: Optional[str] = None) -> Product:
        """Product.clean() refuses a REJECTED product without a reason."""
        previous_status = product.status
        product.status = Product.STATUS_REJECTED
        product.rejection_reason = (reason or "").strip()
        product.reviewed_by = actor
        product.reviewed_at = timezone.now()
        return cls._record_moderation(product, "reject", previous_status, actor, reason, ip_address)

    @classmethod
    @transaction.atomic
    def publish(cls, product: Product, actor, reason: str = "", ip_address: Optional[str] = None) -> Product:
        shop = product.shop
        if not shop or shop.status not in (Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE):
            raise ProductModerationError("Cannot publish product belonging to an unapproved or suspended shop.")
        if not shop.owner or not shop.owner.is_operational:
            raise ProductModerationError("Cannot publish product belonging to an inoperational seller.")
        previous_status = product.status
        product.status = Product.STATUS_PUBLISHED
        product.is_active = True
        return cls._record_moderation(product, "publish", previous_status, actor, reason, ip_address)

    @classmethod
    @transaction.atomic
    def unpublish(cls, product: Product, actor, reason: str = "", ip_address: Optional[str] = None) -> Product:
        previous_status = product.status
        product.status = Product.STATUS_UNPUBLISHED
        return cls._record_moderation(product, "unpublish", previous_status, actor, reason, ip_address)

    @classmethod
    def _record_moderation(cls, product, action, previous_status, actor, reason, ip_address) -> Product:
        product.save()
        AuditService.log(
            action=f"ADMIN_PRODUCT_{action.upper()}",
            target=product,
            actor=actor,
            shop=product.shop,
            seller=product.shop.owner if product.shop else None,
            reason=reason or f"Product {MODERATION_ACTION_VERBS[action]} by staff",
            previous_state={"status": previous_status},
            new_state={"status": product.status},
            ip_address=ip_address,
        )
        publish(
            events.PRODUCT_MODERATED,
            payload={
                "product_id": product.pk,
                "product_name": product.name,
                "action": action,
                "from_status": previous_status,
                "to_status": product.status,
                "reason": product.rejection_reason if action == "reject" else "",
            },
            aggregate=product,
            actor=actor,
        )
        return product

    @staticmethod
    def search_q(term: str) -> Q:
        """
        The public product text search: a case-insensitive phrase match on the
        product name, description or category name. Shared by the catalog
        (?q= on /api/products/) and the nearby shop search (?q= on
        /api/shops/nearby/) so the two always agree on what "matches" means.
        """
        return (
            Q(name__icontains=term)
            | Q(description__icontains=term)
            | Q(category__name__icontains=term)
        )

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
            # inventory: in_stock reads it for every row (TASK-043).
            .select_related("category", "shop", "shop__owner", "inventory")
            .prefetch_related("images")
            # Hidden (moderated) reviews never count toward public ratings.
            .with_ratings()
        )

    @classmethod
    def get_public_product_by_identifier(cls, identifier: Union[int, str]) -> Product:
        """
        Retrieves a single publicly visible product by its primary key (ID) or slug.
        Raises Http404 if the product does not exist or fails public visibility rules.
        """
        qs = cls.get_public_products_queryset()
        if isinstance(identifier, int) or (isinstance(identifier, str) and is_whole_number(identifier)):
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

    # Order fields that make up a typed delivery address (the legacy
    # customer_name/phone/address/city ones included).
    TYPED_ADDRESS_KEYS = (
        "shipping_recipient_name", "customer_name", "recipient_name",
        "shipping_phone", "phone",
        "shipping_address_line_1", "address", "shipping_address_line_2",
        "shipping_area", "area", "shipping_city", "city",
        "shipping_state", "state", "shipping_postal_code", "postal_code",
        "shipping_country", "country",
    )

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
             The address is address_id, a typed one with a non-blank recipient,
             phone, line 1 and city, or else the customer's default; never invented.
          5. Server-authoritative Decimal price calculation ignoring any client inputs.
          6. Atomic cart clearing upon successful order creation.
          7. AuditLog entry for ORDER_CREATED.
        """
        with transaction.atomic():
            # 1. Lock user's Cart with row-level lock
            cart = Cart.objects.select_for_update().filter(user=user).first()
            if not cart:
                raise ValidationError({"cart": "Shopping cart not found for this user."})

            # 2. Lock CartItems with row-level lock. Only the cart item rows:
            # without of=, MySQL also locks every joined category, shop and
            # seller row until the order commits (BUG-023).
            cart_items = list(
                CartItem.objects.select_for_update(of=("self",))
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

            # 3b. Lock the stock rows now, in product order, before the order
            # items' inserts share-lock the product rows (BUG-058).
            from shop.inventory_service import InventoryService
            InventoryService.lock_inventories([item.product for item in cart_items])

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
            elif address_data and any(key in address_data for key in cls.TYPED_ADDRESS_KEYS):
                def typed(*keys):
                    for key in keys:
                        value = (address_data.get(key) or "").strip()
                        if value:
                            return value
                    return ""

                recipient_name = typed("shipping_recipient_name", "customer_name", "recipient_name")
                phone = typed("shipping_phone", "phone")
                line_1 = typed("shipping_address_line_1", "address")
                line_2 = typed("shipping_address_line_2")
                area = typed("shipping_area", "area")
                city = typed("shipping_city", "city")
                state = typed("shipping_state", "state")
                postal = typed("shipping_postal_code", "postal_code")
                country = typed("shipping_country", "country") or "Bangladesh"
                # A typed address must be deliverable (BUG-053).
                missing = {
                    field: "This field is required."
                    for field, value in (
                        ("shipping_recipient_name", recipient_name),
                        ("shipping_phone", phone),
                        ("shipping_address_line_1", line_1),
                        ("shipping_city", city),
                    )
                    if not value
                }
                if missing:
                    raise ValidationError(missing)
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
                    # No invented placeholder address (BUG-053).
                    raise ValidationError(
                        {"address_id": "Choose a saved address or enter a delivery address."}
                    )

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
            InventoryService.reserve_stock_for_cart(
                order=order,
                cart_items=cart_items,
                actor=actor or user,
                ip_address=ip_address,
            )

            # 10. Open the order's cash-on-delivery payment (TASK-048 decision 3:
            # COD is the only method for now). Delivery marks it PAID.
            from shop.payment_service import PaymentService
            PaymentService.create_or_get_payment(
                order=order,
                payment_method=Payment.METHOD_CASH_ON_DELIVERY,
                actor=actor or user,
                ip_address=ip_address,
            )

            # 10b. Clear user's Cart items atomically
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

            # 12. Notify the customer and each seller (commits with the order)
            publish(
                events.ORDER_PLACED,
                payload={
                    "order_id": order.pk,
                    "order_number": order.order_number,
                    "total_amount": str(order.total_amount),
                    "items": [
                        {
                            "product_name": item_info["product_name"],
                            "quantity": item_info["quantity"],
                            "line_total": str(item_info["line_total"]),
                            "seller_id": item_info["seller"].pk if item_info["seller"] else None,
                        }
                        for item_info in order_items_to_create
                    ],
                },
                aggregate=order,
                actor=actor or user,
                idempotency_key=f"order:{order.order_number}:placed",
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

            cls._apply_transition_effects(locked_order, actor=actor, note=note, ip_address=ip_address)

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

            # The order's own customer acting means cancel_customer_order();
            # anyone else reaching this method is staff.
            is_customer = (
                locked_order.user_id is not None
                and getattr(actor, "pk", None) == locked_order.user_id
            )
            cls._publish_status_change(
                locked_order, old_status, actor, changed_by="CUSTOMER" if is_customer else "STAFF"
            )

            logger.info(
                "Order status updated: order=%s old=%s new=%s actor=%s",
                locked_order.order_number,
                old_status,
                locked_order.status,
                getattr(actor, "username", "system"),
            )
            return locked_order

    @staticmethod
    def _apply_transition_effects(order: Order, actor=None, note: str = "", ip_address: Optional[str] = None):
        """
        What every path that moves an order's status must do next, inside
        its transaction and with the order row locked:

        - CANCELLED releases the stock reservation, then cancels pending
          payments and refunds paid ones (PaymentService.handle_order_cancellation);
        - DELIVERED turns the reservation into a sale, and marks the cash on
          delivery payment PAID (PaymentService.handle_order_delivery).

        Shared by the staff/customer and the seller transitions, so the
        seller path can no longer cancel an order and keep its money (BUG-005).
        """
        from shop.inventory_service import InventoryService
        from shop.payment_service import PaymentService

        if order.status == Order.STATUS_CANCELLED:
            InventoryService.release_order_reservation(
                order=order, actor=actor, note=note, ip_address=ip_address
            )
            PaymentService.handle_order_cancellation(order=order, actor=actor, ip_address=ip_address)
        elif order.status == Order.STATUS_DELIVERED:
            InventoryService.finalize_order_delivery(
                order=order, actor=actor, note=note, ip_address=ip_address
            )
            PaymentService.handle_order_delivery(order=order, actor=actor, ip_address=ip_address)

    @staticmethod
    def _publish_status_change(order: Order, old_status: str, actor, changed_by: str):
        """One order.status_changed event, inside the transition's transaction."""
        publish(
            events.ORDER_STATUS_CHANGED,
            payload={
                "order_id": order.pk,
                "order_number": order.order_number,
                "from_status": old_status,
                "to_status": order.status,
                "changed_by": changed_by,
            },
            aggregate=order,
            actor=actor,
        )

    @classmethod
    def cancel_customer_order(
        cls,
        order: Order,
        customer: Any,
        reason: str = "",
        ip_address: Optional[str] = None,
    ) -> Order:
        """
        Safely cancels a customer order initiated by the customer (or staff override).
        Enforces:
          1. Row-level concurrency locking via select_for_update().
          2. Customer ownership: order.user == customer (or staff override).
          3. Idempotency: if order is already CANCELLED, raises ValidationError ("Order is already cancelled.").
          4. Transition eligibility: verifies order.can_transition_to(Order.STATUS_CANCELLED).
          5. Calls transition_order_status() which atomically:
             - advances status to CANCELLED
             - releases inventory reservation via InventoryService.release_order_reservation()
             - appends RELEASE ledger transaction
             - creates immutable AuditLog entry
          6. Preserves historical Order and OrderItem snapshots.
        """
        with transaction.atomic():
            locked_order = Order.objects.select_for_update().filter(pk=order.pk).first()
            if not locked_order:
                raise ValidationError({"order": "Order not found."})

            # Check customer ownership or staff override: the same RBAC rule as
            # the view's CanUpdateStaffOrders, so staff it lets through are not
            # refused here (BUG-056). is_staff alone no longer counts.
            role_codes = get_user_role_codes(customer) if customer and customer.is_authenticated else []
            is_staff_override = bool(customer) and (
                getattr(customer, "is_superuser", False)
                or Role.ROLE_SUPER_ADMINISTRATOR in role_codes
                or has_user_permission(customer, "orders.staff.update")
            )
            if locked_order.user != customer and not is_staff_override:
                raise PermissionDenied("You do not have permission to cancel this order.")

            if locked_order.status == Order.STATUS_CANCELLED:
                raise ValidationError({"order": "Order is already cancelled."})

            if not locked_order.can_transition_to(Order.STATUS_CANCELLED):
                raise ValidationError({
                    "order": f"Order in '{locked_order.status}' status cannot be cancelled."
                })

            note = f"Customer cancellation: {reason}".strip() if reason else "Customer cancellation"
            return cls.transition_order_status(
                order=locked_order,
                new_status=Order.STATUS_CANCELLED,
                actor=customer,
                note=note,
                ip_address=ip_address,
            )


    @classmethod
    def _other_merchant_items(cls, seller: SellerProfile) -> Exists:
        """
        Whether the order also holds another merchant's items. Such an order
        is not the seller's alone to move (transition_seller_order_status), so
        the seller APIs offer it no transitions (BUG-029).
        """
        return Exists(
            OrderItem.objects.filter(order=OuterRef("pk")).exclude(Q(seller=seller) | Q(shop__owner=seller))
        )

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
            .annotate(has_other_merchant_items=cls._other_merchant_items(seller))
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
        qs = Order.objects.prefetch_related(seller_items_prefetch).annotate(
            has_other_merchant_items=cls._other_merchant_items(seller)
        )
        if is_whole_number(lookup_str):
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
          5. The same stock and payment effects as the staff path
             (_apply_transition_effects): a cancellation refunds or cancels the payment.
          6. Immutable audit logging via AuditService.
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

            cls._apply_transition_effects(locked_order, actor=actor, note=note, ip_address=ip_address)

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
            cls._publish_status_change(locked_order, old_status, actor, changed_by="SELLER")

            logger.info(
                "Seller updated order status: order=%s seller=%s old=%s new=%s actor=%s",
                locked_order.order_number,
                seller.business_name,
                old_status,
                locked_order.status,
                getattr(actor, "username", "system"),
            )
            return locked_order

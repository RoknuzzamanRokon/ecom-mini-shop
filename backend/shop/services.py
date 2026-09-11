import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Union

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework.exceptions import PermissionDenied


from audit.services import AuditService
from points.models import PointTransaction
from points.services import InsufficientPointsError, PointService
from rbac.services import has_user_permission
from sellers.models import SellerProfile
from shops.models import Shop
from .models import Category, Product

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

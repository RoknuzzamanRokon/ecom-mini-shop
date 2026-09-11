from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from sellers.models import SellerProfile
from .models import Shop


class ShopError(Exception):
    """Base exception for shop domain errors."""
    pass


class InvalidShopTransitionError(ShopError):
    """Raised when an illegal lifecycle state transition is requested."""
    pass


class IneligibleSellerError(ShopError):
    """Raised when an ineligible seller attempts shop operations."""
    pass


class ShopLimitExceededError(ShopError):
    """Raised when a seller attempts to exceed their allowed shop quota."""
    pass


class ShopService:
    """
    Centralized domain service managing Shop lifecycle, ownership,
    seller type restrictions, and administrative transitions.
    """

    @classmethod
    def validate_seller_eligibility_for_creation(cls, seller: SellerProfile):
        """Verifies seller operational status and seller-type capabilities for shop creation."""
        if not seller.is_operational:
            raise IneligibleSellerError(
                f"Seller must be approved and active to create a shop. Current status: '{seller.status}'."
            )

        if seller.seller_type == SellerProfile.TYPE_PRODUCT_OWNER:
            raise IneligibleSellerError(
                "Product Owners are not permitted to create shops under system business rules."
            )

        # Limited Shop Owners are restricted to a single shop
        if seller.seller_type == SellerProfile.TYPE_LIMITED_SHOP_OWNER and seller.shops.count() >= 1:
            raise ShopLimitExceededError(
                "Limited Shop Owners are restricted to a maximum of 1 shop."
            )

    @classmethod
    @transaction.atomic
    def create_shop(
        cls,
        seller: SellerProfile,
        name: str,
        description: str = "",
        phone: str = "",
        address: str = "",
        location: str = "",
        logo=None,
        cover_image=None,
        submit_for_review: bool = False,
    ) -> Shop:
        """Creates a new Shop for an eligible seller, optionally submitting directly for staff review."""
        cls.validate_seller_eligibility_for_creation(seller)

        initial_status = Shop.STATUS_PENDING if submit_for_review else Shop.STATUS_DRAFT

        shop = Shop(
            owner=seller,
            name=name.strip(),
            description=description.strip(),
            phone=phone.strip(),
            address=address.strip(),
            location=location.strip(),
            status=initial_status,
        )

        if logo:
            shop.logo = logo
        if cover_image:
            shop.cover_image = cover_image

        shop.save()
        return shop

    @classmethod
    @transaction.atomic
    def update_shop(cls, shop: Shop, seller: SellerProfile, **fields) -> Shop:
        """Updates shop profile fields while enforcing ownership and operational seller status."""
        if shop.owner != seller:
            raise PermissionDenied("You do not have permission to modify this shop.")

        if not seller.is_operational:
            raise IneligibleSellerError("Suspended or inactive sellers cannot modify shop details.")

        allowed_fields = {
            "name",
            "description",
            "phone",
            "address",
            "location",
            "logo",
            "cover_image",
        }

        for key, value in fields.items():
            if key in allowed_fields:
                setattr(shop, key, value)

        shop.save()
        return shop

    @classmethod
    @transaction.atomic
    def submit_for_review(cls, shop: Shop, seller: SellerProfile) -> Shop:
        """Submits a DRAFT or REJECTED shop for staff review."""
        if shop.owner != seller:
            raise PermissionDenied("You do not have permission to submit this shop.")

        if not seller.is_operational:
            raise IneligibleSellerError("Suspended or inactive sellers cannot submit shops for review.")

        if shop.status not in (Shop.STATUS_DRAFT, Shop.STATUS_REJECTED):
            raise InvalidShopTransitionError(
                f"Cannot submit shop with status '{shop.status}'. Only DRAFT or REJECTED shops can be submitted."
            )

        shop.status = Shop.STATUS_PENDING
        shop.save()
        return shop

    @classmethod
    @transaction.atomic
    def approve_shop(cls, shop: Shop, staff_user) -> Shop:
        """Approves and activates a pending shop."""
        if shop.status not in (Shop.STATUS_PENDING, Shop.STATUS_DRAFT):
            raise InvalidShopTransitionError(
                f"Cannot approve shop with status '{shop.status}'. Only PENDING or DRAFT shops can be approved."
            )

        shop.status = Shop.STATUS_ACTIVE
        shop.reviewed_by = staff_user
        shop.reviewed_at = timezone.now()
        shop.approved_at = timezone.now()
        shop.rejection_reason = ""
        shop.save()
        return shop

    @classmethod
    @transaction.atomic
    def reject_shop(cls, shop: Shop, staff_user, reason: str) -> Shop:
        """Rejects a pending shop with a mandatory rejection reason."""
        if not reason or not reason.strip():
            raise ValidationError("A non-empty rejection reason is required.")

        if shop.status != Shop.STATUS_PENDING:
            raise InvalidShopTransitionError(
                f"Cannot reject shop with status '{shop.status}'. Only PENDING shops can be rejected."
            )

        shop.status = Shop.STATUS_REJECTED
        shop.rejection_reason = reason.strip()
        shop.reviewed_by = staff_user
        shop.reviewed_at = timezone.now()
        shop.save()
        return shop

    @classmethod
    @transaction.atomic
    def suspend_shop(cls, shop: Shop, staff_user, reason: str) -> Shop:
        """Suspends an active or approved shop with a mandatory reason."""
        if not reason or not reason.strip():
            raise ValidationError("A non-empty suspension reason is required.")

        if shop.status not in (Shop.STATUS_ACTIVE, Shop.STATUS_APPROVED):
            raise InvalidShopTransitionError(
                f"Cannot suspend shop with status '{shop.status}'. Only ACTIVE or APPROVED shops can be suspended."
            )

        shop.status = Shop.STATUS_SUSPENDED
        shop.suspension_reason = reason.strip()
        shop.suspended_at = timezone.now()
        shop.save()
        return shop

    @classmethod
    @transaction.atomic
    def reactivate_shop(cls, shop: Shop, staff_user) -> Shop:
        """Reactivates a suspended shop back to ACTIVE."""
        if shop.status != Shop.STATUS_SUSPENDED:
            raise InvalidShopTransitionError(
                f"Cannot reactivate shop with status '{shop.status}'. Only SUSPENDED shops can be reactivated."
            )

        shop.status = Shop.STATUS_ACTIVE
        shop.suspension_reason = ""
        shop.save()
        return shop

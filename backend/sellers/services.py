from django.core.exceptions import ValidationError
from django.db import transaction
from .models import SellerProfile


@transaction.atomic
def create_seller_profile(user, **fields) -> SellerProfile:
    """
    Creates a SellerProfile for `user` in the PENDING state.

    The single creation path for the domain, shared by seller self-registration
    (SellerRegistrationSerializer, where the target is always request.user) and
    by admin creation on behalf of an existing account. Centralising it means
    the initial status and the one-profile-per-user rule cannot diverge between
    the two entry points.

    WHO may create a profile for WHOM is deliberately not decided here — that is
    an authorization question, answered by the calling view's permission class.
    This function only enforces the domain invariants.

    SellerProfile.save() calls full_clean(), so seller_type and status choices,
    and the reason requirements on REJECTED/SUSPENDED, are validated by the
    model itself rather than re-implemented here.
    """
    if user is None:
        raise ValidationError({"user": "A seller profile requires a user account."})

    if SellerProfile.objects.filter(user=user).exists():
        raise ValidationError(
            {"user": "A seller profile already exists for this user account."}
        )

    return SellerProfile.objects.create(
        user=user,
        status=SellerProfile.STATUS_PENDING,
        **fields,
    )


def get_seller_capabilities(seller: SellerProfile) -> dict:
    """
    Returns capability flags determined by seller type.

    Known Issue #4: `can_create_shop` is False for **every** seller type, including
    FULL_SHOP_OWNER and LIMITED_SHOP_OWNER. Sellers do not create shops on this
    platform -- shop creation is a management action, and seller self-service is
    hard-denied with a 403. This flag previously claimed True for the two shop-owner
    types, which contradicted the enforced policy and misled any UI that trusted it.
    The fix is to report the truth here, not to relax the restriction.
    """
    capabilities = {
        "can_create_shop": False,
        "can_manage_products": False,
        "has_full_catalog": False,
        "seller_type": seller.seller_type,
    }

    if seller.seller_type == SellerProfile.TYPE_FULL_SHOP_OWNER:
        capabilities["can_manage_products"] = True
        capabilities["has_full_catalog"] = True
    elif seller.seller_type == SellerProfile.TYPE_LIMITED_SHOP_OWNER:
        capabilities["can_manage_products"] = True
        capabilities["has_full_catalog"] = False
    elif seller.seller_type == SellerProfile.TYPE_PRODUCT_OWNER:
        capabilities["can_manage_products"] = True
        capabilities["has_full_catalog"] = True

    return capabilities


@transaction.atomic
def approve_seller(seller: SellerProfile, staff_user) -> SellerProfile:
    seller.approve(staff_user)
    # Default to ACTIVE upon approval
    seller.activate(staff_user)
    return seller


@transaction.atomic
def reject_seller(seller: SellerProfile, staff_user, reason: str) -> SellerProfile:
    seller.reject(staff_user, reason)
    return seller


@transaction.atomic
def suspend_seller(seller: SellerProfile, staff_user, reason: str) -> SellerProfile:
    seller.suspend(staff_user, reason)
    return seller


@transaction.atomic
def reactivate_seller(seller: SellerProfile, staff_user) -> SellerProfile:
    seller.activate(staff_user)
    return seller

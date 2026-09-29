from django.core.exceptions import ValidationError
from django.db import transaction

from notifications import events
from notifications.publisher import publish

from .models import SellerProfile


@transaction.atomic
def create_seller_profile(user, **fields) -> SellerProfile:
    """
    Creates a SellerProfile for `user` in the PENDING state.

    The single creation path for the domain. Seller self-registration was
    removed in Phase 2L (Known Issue #5), so the one API caller left is admin
    creation on behalf of an existing account
    (AdminSellerListAPIView.post -> AdminSellerCreateSerializer): sellers are
    provisioned by authorized management, never by themselves. This stays a
    service rather than being folded into that view so the initial status and
    the one-profile-per-user rule live in one place for every caller, including
    seeds, management commands and tests.

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


def _publish_status_change(seller: SellerProfile, from_status: str, staff_user, reason: str = ""):
    """One seller.status_changed event, inside the transition's transaction."""
    publish(
        events.SELLER_STATUS_CHANGED,
        payload={
            "seller_id": seller.pk,
            "from_status": from_status,
            "to_status": seller.status,
            "reason": (reason or "").strip(),
        },
        aggregate=seller,
        actor=staff_user,
    )


@transaction.atomic
def approve_seller(seller: SellerProfile, staff_user) -> SellerProfile:
    from_status = seller.status
    seller.approve(staff_user)
    # Default to ACTIVE upon approval
    seller.activate(staff_user)
    _publish_status_change(seller, from_status, staff_user)
    return seller


@transaction.atomic
def reject_seller(seller: SellerProfile, staff_user, reason: str) -> SellerProfile:
    from_status = seller.status
    seller.reject(staff_user, reason)
    _publish_status_change(seller, from_status, staff_user, reason)
    return seller


@transaction.atomic
def suspend_seller(seller: SellerProfile, staff_user, reason: str) -> SellerProfile:
    from_status = seller.status
    seller.suspend(staff_user, reason)
    _publish_status_change(seller, from_status, staff_user, reason)
    return seller


@transaction.atomic
def reactivate_seller(seller: SellerProfile, staff_user) -> SellerProfile:
    from_status = seller.status
    seller.activate(staff_user)
    _publish_status_change(seller, from_status, staff_user)
    return seller

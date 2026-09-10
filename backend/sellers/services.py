from django.core.exceptions import ValidationError
from django.db import transaction
from .models import SellerProfile


def get_seller_capabilities(seller: SellerProfile) -> dict:
    """
    Returns capability flags determined by seller type.
    """
    capabilities = {
        "can_create_shop": False,
        "can_manage_products": False,
        "has_full_catalog": False,
        "seller_type": seller.seller_type,
    }

    if seller.seller_type == SellerProfile.TYPE_FULL_SHOP_OWNER:
        capabilities["can_create_shop"] = True
        capabilities["can_manage_products"] = True
        capabilities["has_full_catalog"] = True
    elif seller.seller_type == SellerProfile.TYPE_LIMITED_SHOP_OWNER:
        capabilities["can_create_shop"] = True
        capabilities["can_manage_products"] = True
        capabilities["has_full_catalog"] = False
    elif seller.seller_type == SellerProfile.TYPE_PRODUCT_OWNER:
        capabilities["can_create_shop"] = False
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

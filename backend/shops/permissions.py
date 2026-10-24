from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied

from rbac.services import has_user_permission


class CanViewStaffShops(BasePermission):
    """
    Staff permission to view all shops regardless of lifecycle status.
    Requires 'shops.view' RBAC permission.
    """
    message = "You do not have permission to view administrative shop records."

    def has_permission(self, request, view):
        return has_user_permission(request.user, "shops.view")


class CanApproveShops(BasePermission):
    """
    Staff permission to review, approve, reject, or suspend shops.
    Requires 'shops.approve' RBAC permission.
    """
    message = "You do not have permission to review or approve shops."

    def has_permission(self, request, view):
        return has_user_permission(request.user, "shops.approve")


class IsEligibleShopSeller(BasePermission):
    """
    Ensures an authenticated user is an active seller capable of owning a shop.
    Rejects users without a seller profile and inactive sellers.
    """
    message = "Only active shop owners can perform shop management operations."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if not hasattr(user, "seller_profile"):
            raise PermissionDenied("You do not have a registered seller account.")

        seller = user.seller_profile

        if not seller.is_operational:
            raise PermissionDenied(
                f"Your seller account is currently '{seller.status}'. Only active sellers can manage shops."
            )

        return True


class IsShopOwner(BasePermission):
    """
    Object-level permission ensuring a seller can only access or modify shops they own.

    Only for the seller-only /api/shops/mine/ views, which act as the user's
    own seller profile. Staff have no bypass here: they manage shops through
    the staff and Console endpoints. A bypass let staff without a seller
    profile reach request.user.seller_profile and get a 500 (BUG-045).
    """
    message = "You do not own this shop."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if not hasattr(user, "seller_profile"):
            return False

        return obj.owner == user.seller_profile

from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied

from rbac.models import Role
from rbac.services import get_user_role_codes, has_user_permission
from sellers.models import SellerProfile


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
    Rejects users without a seller profile, inactive sellers, and PRODUCT_OWNER sellers.
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

        if seller.seller_type == SellerProfile.TYPE_PRODUCT_OWNER:
            raise PermissionDenied("Product Owners are not permitted to create or manage shops.")

        return True


class IsShopOwner(BasePermission):
    """
    Object-level permission ensuring a seller can only access or modify shops they own.
    Allows staff with 'shops.update' or SUPER_ADMINISTRATOR to bypass.
    """
    message = "You do not own this shop."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True

        if has_user_permission(user, "shops.update"):
            return True

        if not hasattr(user, "seller_profile"):
            return False

        return obj.owner == user.seller_profile

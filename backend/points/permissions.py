from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from rbac.services import has_user_permission, get_user_role_codes
from rbac.models import Role


class CanViewPoints(BasePermission):
    """
    Staff permission to view seller point balances and ledgers.
    Requires 'points.view' RBAC permission.
    """
    message = "You do not have permission to view point records."

    def has_permission(self, request, view):
        return has_user_permission(request.user, "points.view")


class CanAdjustPoints(BasePermission):
    """
    Staff permission to execute administrative credit or debit adjustments.
    Requires 'points.adjust', 'points.add', or 'points.deduct' RBAC permission.
    """
    message = "You do not have permission to adjust seller points."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True

        return (
            has_user_permission(user, "points.adjust")
            or has_user_permission(user, "points.add")
            or has_user_permission(user, "points.deduct")
        )


class IsSellerWalletOwner(BasePermission):
    """
    Ensures an authenticated user has a registered SellerProfile.
    """
    message = "You must be a registered seller to access this resource."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if not hasattr(user, "seller_profile"):
            raise PermissionDenied("You do not have a seller account.")

        return True

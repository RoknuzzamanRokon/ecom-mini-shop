from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from rbac.services import has_user_permission, get_user_role_codes
from rbac.models import Role
from .models import SellerProfile


class CanViewSellers(BasePermission):
    message = "You do not have permission to view seller accounts."

    def has_permission(self, request, view):
        return has_user_permission(request.user, "sellers.view")


class CanApproveSeller(BasePermission):
    message = "You do not have permission to approve or reject sellers."

    def has_permission(self, request, view):
        return has_user_permission(request.user, "sellers.approve")


class CanSuspendSeller(BasePermission):
    message = "You do not have permission to suspend or reactivate sellers."

    def has_permission(self, request, view):
        return has_user_permission(request.user, "sellers.suspend")


class IsSellerOwner(BasePermission):
    """
    Ensures a user can only access or modify their own SellerProfile,
    unless they hold staff override permissions or superadmin status.
    """
    message = "You can only view or modify your own seller profile."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        # Superusers and Super Administrators bypass
        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True

        # Staff with sellers.update permission can modify
        if has_user_permission(user, "sellers.update"):
            return True

        # Ownership check
        target_user = getattr(obj, "user", None)
        return target_user == user


class IsOperationalSeller(BasePermission):
    """
    Enforces that the user is an active, non-suspended seller.
    Suspended or unapproved sellers are rejected from performing seller operations.
    """
    message = "Only active sellers can perform this operation."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        try:
            seller = user.seller_profile
        except SellerProfile.DoesNotExist:
            raise PermissionDenied("You do not have a seller profile.")

        if seller.status == SellerProfile.STATUS_SUSPENDED:
            reason = f": {seller.suspension_reason}" if seller.suspension_reason else ""
            raise PermissionDenied(f"Your seller account is currently suspended{reason}. Operations are restricted.")

        if seller.status in (SellerProfile.STATUS_PENDING, SellerProfile.STATUS_UNDER_REVIEW):
            raise PermissionDenied("Your seller application is currently pending approval.")

        if seller.status == SellerProfile.STATUS_REJECTED:
            reason = f": {seller.rejection_reason}" if seller.rejection_reason else ""
            raise PermissionDenied(f"Your seller application was rejected{reason}.")

        return seller.status in (SellerProfile.STATUS_APPROVED, SellerProfile.STATUS_ACTIVE)

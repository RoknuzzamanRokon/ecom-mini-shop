from rest_framework.permissions import BasePermission
from rbac.models import Role
from rbac.services import get_user_role_codes, has_user_permission


class CanViewProfile(BasePermission):
    """
    Enforces that the requesting user holds the 'profile.view' RBAC permission.
    """
    message = "You do not have permission to view profile details ('profile.view' required)."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_user_permission(request.user, "profile.view")


class CanUpdateProfile(BasePermission):
    """
    Enforces that the requesting user holds the 'profile.update' RBAC permission.
    """
    message = "You do not have permission to update profile details ('profile.update' required)."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_user_permission(request.user, "profile.update")


class CanViewAddress(BasePermission):
    """
    Enforces that the requesting user holds the 'address.view' RBAC permission.
    """
    message = "You do not have permission to view addresses ('address.view' required)."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_user_permission(request.user, "address.view")


class CanCreateAddress(BasePermission):
    """
    Enforces that the requesting user holds the 'address.create' RBAC permission.
    """
    message = "You do not have permission to create addresses ('address.create' required)."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_user_permission(request.user, "address.create")


class CanUpdateAddress(BasePermission):
    """
    Enforces that the requesting user holds the 'address.update' RBAC permission.
    """
    message = "You do not have permission to update addresses ('address.update' required)."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_user_permission(request.user, "address.update")


class CanDeleteAddress(BasePermission):
    """
    Enforces that the requesting user holds the 'address.delete' RBAC permission.
    """
    message = "You do not have permission to delete addresses ('address.delete' required)."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_user_permission(request.user, "address.delete")


class IsAddressOwner(BasePermission):
    """
    Object-level permission ensuring only the address owner (or super administrator)
    can view or modify an individual address record.
    """
    message = "You can only view or manage your own addresses."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True
        return obj.user == user

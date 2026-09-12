# admin_permissions.py
"""
Admin-specific DRF permission classes for platform governance.
These classes enforce RBAC permissions for admin actions on users, roles, sellers,
shops, products, categories, and customers.
"""

from rest_framework.permissions import BasePermission
from rbac.models import Role
from rbac.services import get_user_role_codes, has_user_permission


class CanViewAdminUsers(BasePermission):
    """Allows viewing admin user accounts."""
    message = "You do not have permission to view admin users."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True
        return has_user_permission(user, "users.admin.view")


class CanManageAdminUsers(BasePermission):
    """Allows managing admin user accounts, roles, and statuses."""
    message = "You do not have permission to manage admin users."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True
        return has_user_permission(user, "users.admin.manage")


class CanViewAdminRoles(BasePermission):
    """Allows viewing admin role definitions."""
    message = "You do not have permission to view admin roles."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True
        return has_user_permission(user, "roles.admin.view")


class CanManageAdminRoles(BasePermission):
    """Allows creating, updating, and deleting admin roles."""
    message = "You do not have permission to manage admin roles."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True
        return has_user_permission(user, "roles.admin.manage")


class CanManageAdminSellers(BasePermission):
    """Allows approving, rejecting, suspending, and reactivating sellers."""
    message = "You do not have permission to manage sellers as admin."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True
        return has_user_permission(user, "sellers.admin.manage")


class CanManageAdminShops(BasePermission):
    """Allows approving, rejecting, suspending, and reactivating shops."""
    message = "You do not have permission to manage shops as admin."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True
        return has_user_permission(user, "shops.admin.manage")


class CanManageAdminProducts(BasePermission):
    """Allows approving, rejecting, publishing, and unpublishing products."""
    message = "You do not have permission to manage products as admin."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True
        return has_user_permission(user, "products.admin.manage")


class CanManageAdminCategories(BasePermission):
    """Allows creating, updating, activating, and deactivating categories."""
    message = "You do not have permission to manage categories as admin."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True
        return has_user_permission(user, "categories.admin.manage")


class CanViewAdminCustomers(BasePermission):
    """Read‑only view of customer profiles for admin purposes."""
    message = "You do not have permission to view customer profiles as admin."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True
        return has_user_permission(user, "customers.admin.view")

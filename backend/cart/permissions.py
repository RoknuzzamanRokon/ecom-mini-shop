from rest_framework import permissions

from rbac.services import has_user_permission


class CanViewCart(permissions.BasePermission):
    """
    Requires authentication and 'cart.view' RBAC permission.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_user_permission(request.user, "cart.view")


class CanUpdateCart(permissions.BasePermission):
    """
    Requires authentication and 'cart.update' RBAC permission.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_user_permission(request.user, "cart.update")


class IsCartItemOwner(permissions.BasePermission):
    """
    Object-level permission ensuring the cart item belongs to the authenticated user.
    """
    def has_object_permission(self, request, view, obj):
        return obj.cart.user == request.user

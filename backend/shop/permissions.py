from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from rbac.models import Role
from rbac.services import get_user_role_codes, has_user_permission
from sellers.models import SellerProfile


class CanCreateProduct(BasePermission):
    """
    Enforces that the user holds the 'products.create' RBAC permission.
    """
    message = "You do not have permission to create products."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_user_permission(request.user, "products.create")


class CanUpdateProduct(BasePermission):
    """
    Enforces that the user holds the 'products.update' RBAC permission.
    """
    message = "You do not have permission to update products."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_user_permission(request.user, "products.update")


class CanDeleteProduct(BasePermission):
    """
    Enforces that the user holds the 'products.delete' RBAC permission.
    """
    message = "You do not have permission to delete products."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_user_permission(request.user, "products.delete")


class IsEligibleProductSeller(BasePermission):
    """
    Enforces that the user has an active, operational SellerProfile.
    Rejects users without a seller profile, suspended sellers, and pending sellers.
    """
    message = "Only active sellers can perform this product operation."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if not hasattr(user, "seller_profile"):
            raise PermissionDenied("You do not have a registered seller profile.")

        seller = user.seller_profile

        if seller.status == SellerProfile.STATUS_SUSPENDED:
            reason = f": {seller.suspension_reason}" if seller.suspension_reason else ""
            raise PermissionDenied(f"Your seller account is currently suspended{reason}. Product operations are restricted.")

        if seller.status in (SellerProfile.STATUS_PENDING, SellerProfile.STATUS_UNDER_REVIEW):
            raise PermissionDenied("Your seller application is currently pending approval.")

        if seller.status == SellerProfile.STATUS_REJECTED:
            reason = f": {seller.rejection_reason}" if seller.rejection_reason else ""
            raise PermissionDenied(f"Your seller application was rejected{reason}.")

        return seller.is_operational


class IsProductOwner(BasePermission):
    """
    Object-level permission enforcing that the product belongs to a shop owned by the authenticated seller.
    Allows staff with 'products.update' or SUPER_ADMINISTRATOR to bypass where applicable.
    """
    message = "You do not own the shop associated with this product."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        # Superuser and Super Administrator bypass
        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True

        # Staff with products.update permission can modify if performing a staff action
        if getattr(view, "allow_staff_override", False) and has_user_permission(user, "products.update"):
            return True

        if not hasattr(user, "seller_profile"):
            return False

        seller = user.seller_profile
        return bool(obj.shop and obj.shop.owner == seller)


class CanCreateOrder(BasePermission):
    """
    Enforces that the user holds the 'orders.create' RBAC permission.
    """
    message = "You do not have permission to place orders."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_user_permission(request.user, "orders.create")


class CanViewOrder(BasePermission):
    """
    Enforces that the user holds the 'orders.view' RBAC permission.
    """
    message = "You do not have permission to view orders."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return has_user_permission(request.user, "orders.view")


class IsOrderOwner(BasePermission):
    """
    Object-level permission enforcing that the order belongs to the authenticated customer.
    Staff/Admin with appropriate permissions may view any order.
    """
    message = "You do not have permission to access this order."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True

        if getattr(view, "allow_staff_override", False) and has_user_permission(user, "orders.view"):
            return True

        return obj.user == user


class IsEligibleOrderSeller(BasePermission):
    """
    Enforces that the user has an active, operational SellerProfile.
    Rejects users without a seller profile, suspended sellers, and pending sellers.
    """
    message = "Only active sellers can perform this seller order operation."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if not hasattr(user, "seller_profile"):
            raise PermissionDenied("You do not have a registered seller profile.")

        seller = user.seller_profile

        if seller.status == SellerProfile.STATUS_SUSPENDED:
            reason = f": {seller.suspension_reason}" if seller.suspension_reason else ""
            raise PermissionDenied(f"Your seller account is currently suspended{reason}. Order operations are restricted.")

        if seller.status in (SellerProfile.STATUS_PENDING, SellerProfile.STATUS_UNDER_REVIEW):
            raise PermissionDenied("Your seller application is currently pending approval.")

        if seller.status == SellerProfile.STATUS_REJECTED:
            reason = f": {seller.rejection_reason}" if seller.rejection_reason else ""
            raise PermissionDenied(f"Your seller application was rejected{reason}.")

        return seller.is_operational


class CanViewSellerOrder(BasePermission):
    """
    Enforces that the user holds 'orders.seller.view' or 'orders.view' permission.
    """
    message = "You do not have permission to view seller orders."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True

        return (
            has_user_permission(user, "orders.seller.view")
            or has_user_permission(user, "orders.view")
        )


class CanUpdateSellerOrder(BasePermission):
    """
    Enforces that the user holds 'orders.seller.update' or 'orders.update' permission.
    """
    message = "You do not have permission to update seller orders."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True

        return (
            has_user_permission(user, "orders.seller.update")
            or has_user_permission(user, "orders.update")
        )


class CanViewInventory(BasePermission):
    """
    Enforces that the user holds 'inventory.view' permission or admin/superuser bypass.
    """
    message = "You do not have permission to view inventory."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True

        return has_user_permission(user, "inventory.view")


class CanAdjustInventory(BasePermission):
    """
    Enforces that the user holds 'inventory.adjust' permission or admin/superuser bypass.
    """
    message = "You do not have permission to adjust inventory."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True

        return has_user_permission(user, "inventory.adjust")


class IsInventoryProductOwner(BasePermission):
    """
    Object-level permission enforcing that the product belongs to the seller's shop,
    unless staff override is granted.
    """
    message = "You do not own the product associated with this inventory record."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True

        if getattr(view, "allow_staff_override", False) and has_user_permission(user, "inventory.adjust"):
            return True

        if not hasattr(user, "seller_profile"):
            return False

        seller = user.seller_profile
        product = getattr(obj, "product", obj)
        return bool(product.shop and product.shop.owner == seller)


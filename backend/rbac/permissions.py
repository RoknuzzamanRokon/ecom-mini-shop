from rest_framework.permissions import BasePermission
from .services import has_user_permission, get_user_role_codes
from .models import Role


class HasPermission(BasePermission):
    """
    Checks if authenticated user has a specific granular RBAC permission (<resource>.<action>).
    Configurable via:
      - view.required_permission = "products.view"
      - view.required_permissions = ["products.view", "products.create"]
      - require_permission("products.view") factory
    """
    message = "You do not have permission to perform this action."

    def __init__(self, permission_code=None):
        self.permission_code = permission_code

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        required = self.permission_code or getattr(view, "required_permission", None)
        if required:
            return has_user_permission(request.user, required)

        required_list = getattr(view, "required_permissions", None)
        if required_list:
            return all(has_user_permission(request.user, p) for p in required_list)

        return True


def require_permission(permission_code: str):
    """
    Factory creating a DRF BasePermission class enforcing a specific permission code.
    Usage: permission_classes = [require_permission("products.approve")]
    """
    class _ConfiguredPermission(HasPermission):
        def __init__(self):
            super().__init__(permission_code=permission_code)

    _ConfiguredPermission.__name__ = f"Require_{permission_code.replace('.', '_')}"
    return _ConfiguredPermission


class HasObjectPermission(BasePermission):
    """
    Foundation for object-level authorization:
      1. Superusers and SUPER_ADMINISTRATOR role users always have full access.
      2. If a staff override permission is configured on the view (e.g. view.staff_permission),
         and the user holds that permission, access is granted.
      3. Otherwise, ownership is checked:
         - obj.user == request.user
         - obj.owner == request.user
         - obj.customer == request.user
         - obj.created_by == request.user
    """
    message = "You do not have permission to access or modify this object."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        # Superusers and Super Administrators have full access
        if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user):
            return True

        # Check staff override permission if view defines one
        staff_perm = getattr(view, "staff_permission", None) or getattr(view, "required_permission", None)
        if staff_perm and has_user_permission(user, staff_perm):
            return True

        # Check direct ownership on the object
        for attr in ("user", "owner", "customer", "created_by"):
            owner_val = getattr(obj, attr, None)
            if owner_val is not None:
                if owner_val == user or getattr(owner_val, "id", None) == user.id:
                    return True

        return False

from rest_framework.permissions import BasePermission

from rbac.services import has_user_permission


class _RequiresSupportCode(BasePermission):
    """Authenticated + one RBAC code (has_user_permission covers superuser / '*')."""

    code = ""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return has_user_permission(user, self.code)


class CanViewOwnSupportTickets(_RequiresSupportCode):
    code = "support.view"
    message = "You do not have permission to view support tickets ('support.view' required)."


class CanCreateSupportTickets(_RequiresSupportCode):
    code = "support.create"
    message = "You do not have permission to open or reply to support tickets ('support.create' required)."

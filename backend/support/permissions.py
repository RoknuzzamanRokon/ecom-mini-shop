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


class CanViewSupportTickets(_RequiresSupportCode):
    code = "support.staff.view"
    message = "You do not have permission to view support tickets ('support.staff.view' required)."


class CanReplySupportTickets(_RequiresSupportCode):
    code = "support.staff.reply"
    message = "You do not have permission to reply to support tickets ('support.staff.reply' required)."


class CanManageSupportTickets(_RequiresSupportCode):
    code = "support.staff.manage"
    message = "You do not have permission to manage support tickets ('support.staff.manage' required)."

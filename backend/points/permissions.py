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


# ==============================================================================
# POINT ACTION -> PERMISSION MAP
# ==============================================================================
# The single definition of which RBAC permission authorizes which direction of
# point movement. Both the entry gate (CanAdjustPoints) and the per-action check
# (can_perform_point_action) read this map, so an endpoint cannot end up
# accepting an action its permission class never considered.
#
# 'points.adjust' is the two-way permission; 'points.add' and 'points.deduct'
# are each one-way. Holding a one-way permission must not confer the other
# direction — crediting and debiting a seller's balance are different financial
# authorities.
POINT_ACTION_PERMISSIONS = {
    "CREDIT": ("points.add", "points.adjust"),
    "DEBIT": ("points.deduct", "points.adjust"),
}

# Every permission that can open the adjustment endpoint at all.
POINT_ADJUSTMENT_PERMISSIONS = tuple(
    sorted({code for codes in POINT_ACTION_PERMISSIONS.values() for code in codes})
)


def _has_point_wildcard(user) -> bool:
    """Superusers and SUPER_ADMINISTRATOR hold "*" and bypass the action map."""
    return bool(user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user))


def can_perform_point_action(user, action: str) -> bool:
    """
    Whether `user` may move points in the direction named by `action`
    ('CREDIT' or 'DEBIT').

    This is the check that makes the one-way permissions actually one-way. The
    permission class below can only gate ENTRY to the endpoint, because the
    requested action lives in the request body and is not known until the
    payload has been validated — so the view calls this afterwards, the same
    split CanChangeAdminProductStatus already uses for product transitions.

    An unknown action is refused rather than defaulted, so adding a direction to
    the serializer without adding it to the map fails closed.
    """
    if not user or not user.is_authenticated:
        return False

    if _has_point_wildcard(user):
        return True

    required = POINT_ACTION_PERMISSIONS.get(str(action).upper().strip())
    if not required:
        return False

    return any(has_user_permission(user, code) for code in required)


class CanAdjustPoints(BasePermission):
    """
    Entry gate for the point adjustment endpoint: the actor must hold at least
    one point-movement permission.

    Holding one is NOT sufficient to perform any given adjustment. The
    direction-specific decision is can_perform_point_action(), which the view
    applies to the validated action; this class only keeps callers with no
    points authority whatsoever from reaching it.
    """
    message = "You do not have permission to adjust seller points."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        if _has_point_wildcard(user):
            return True

        return any(has_user_permission(user, code) for code in POINT_ADJUSTMENT_PERMISSIONS)


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

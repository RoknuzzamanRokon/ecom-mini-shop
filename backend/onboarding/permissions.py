from rest_framework.permissions import BasePermission

from rbac.services import get_user_permissions, has_user_permission

#: What approving an onboarding does, one step per pair: approve the seller,
#: approve its shops, approve its products, publish them. Either code of a
#: pair covers its step, the same codes each step's own Console action takes,
#: so the one-step approval grants nothing those actions would not.
APPROVAL_PERMISSIONS = (
    ("sellers.approve", "sellers.admin.manage"),
    ("shops.approve", "shops.admin.manage"),
    ("products.approve", "products.admin.manage"),
    ("products.publish", "products.admin.manage"),
)


def can_approve_onboarding(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    held = get_user_permissions(user)
    if "*" in held:
        return True
    return all(any(code in held for code in pair) for pair in APPROVAL_PERMISSIONS)


class CanOnboardSellers(BasePermission):
    """Field onboarding: 'sellers.onboard'."""
    message = "You do not have permission to onboard sellers ('sellers.onboard' required)."

    def has_permission(self, request, view):
        return has_user_permission(request.user, "sellers.onboard")


#: Seeing the products an onboarder added (and so editing them).
PRODUCTS_VIEW = "onboarding.products.view"


def can_view_onboarded_products(user) -> bool:
    return has_user_permission(user, PRODUCTS_VIEW)


class CanViewOnboardedProducts(BasePermission):
    """The products an onboarder added: 'sellers.onboard' and 'onboarding.products.view'."""
    message = (
        "You do not have permission to see the products you added "
        "('onboarding.products.view' required); an admin may have turned it off."
    )

    def has_permission(self, request, view):
        return has_user_permission(request.user, "sellers.onboard") and can_view_onboarded_products(request.user)


class CanSettleTokenPayouts(BasePermission):
    """Accepting or rejecting token payout requests: 'onboarding.payouts.manage'."""
    message = "You do not have permission to settle token payouts ('onboarding.payouts.manage' required)."

    def has_permission(self, request, view):
        return has_user_permission(request.user, "onboarding.payouts.manage")


class CanApproveOnboarding(BasePermission):
    """The onboarding review queue and its one-step approval: every code in APPROVAL_PERMISSIONS."""
    message = (
        "Approving an onboarding approves the seller, its shops and its products at once, "
        "so it needs permission for all three."
    )

    def has_permission(self, request, view):
        return can_approve_onboarding(request.user)

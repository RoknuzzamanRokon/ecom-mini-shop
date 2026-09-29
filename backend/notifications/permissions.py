"""
Who may read which inbox (docs/NOTIFICATION_SYSTEM.md §4.7, §8).

Everyone reads only their own notifications. The audience only decides which
of them a surface shows, and each surface is open to the people it is for:

- CUSTOMER, the storefront: any signed-in user.
- SELLER, the Seller Center: users with a seller profile, in any status (a
  suspended or rejected seller still needs to read why).
- STAFF, the Management Console: Django staff and superusers, anyone holding
  an active role other than CUSTOMER, and anyone with an active direct
  permission grant (the single-account staff exception).
"""
from rbac.models import Role, UserPermission
from rbac.services import get_user_role_codes
from sellers.models import SellerProfile

from .models import Audience


def has_staff_access(user):
    if user.is_superuser or user.is_staff:
        return True
    if get_user_role_codes(user) - {Role.ROLE_CUSTOMER}:
        return True
    return UserPermission.objects.filter(user=user, is_active=True).exists()


def can_read_audience(user, audience):
    if not user or not user.is_authenticated:
        return False
    if audience == Audience.CUSTOMER:
        return True
    if audience == Audience.SELLER:
        return SellerProfile.objects.filter(user=user).exists()
    if audience == Audience.STAFF:
        return has_staff_access(user)
    return False


def readable_audiences(user):
    return [audience for audience in Audience.values if can_read_audience(user, audience)]

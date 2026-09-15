from typing import Set
from django.contrib.auth import get_user_model
from .models import Permission, Role, UserRole

User = get_user_model()


def get_user_role_codes(user) -> Set[str]:
    """
    Returns the set of active role codes currently assigned to the user.
    """
    if not user or not user.is_authenticated:
        return set()

    return set(
        UserRole.objects.filter(
            user=user,
            is_active=True,
            role__is_active=True,
        ).values_list("role__code", flat=True)
    )


def get_user_permissions(user) -> Set[str]:
    """
    Resolves the set of permission codes available to the user.

    - Superusers or users with SUPER_ADMINISTRATOR role receive all system permissions.
    - Everyone else receives the UNION of:
        1. every permission from their active assigned roles, and
        2. any permission granted directly to them via UserPermission.

    Roles stay the primary grant path; the direct grants are the single-account
    exception (see UserPermission's docstring). This function is the only place
    permissions are resolved, so unioning here is what makes a direct grant
    enforceable by every existing permission class without changing any of them.
    """
    if not user or not user.is_authenticated:
        return set()

    role_codes = get_user_role_codes(user)

    # Super administrator / superuser has all permissions
    if user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in role_codes:
        all_perms = set(Permission.objects.values_list("code", flat=True))
        all_perms.add("*")
        return all_perms

    role_permissions = set(
        Permission.objects.filter(
            role_permissions__role__user_roles__user=user,
            role_permissions__role__user_roles__is_active=True,
            role_permissions__role__is_active=True,
        ).values_list("code", flat=True)
    )

    direct_permissions = set(
        Permission.objects.filter(
            user_permissions__user=user,
            user_permissions__is_active=True,
        ).values_list("code", flat=True)
    )

    return role_permissions | direct_permissions


def has_user_permission(user, permission_code: str) -> bool:
    """
    Determines whether a user has a specific granular permission code (<resource>.<action>).
    Does NOT rely on hardcoded role checks, resolving through RBAC permissions.
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    user_perms = get_user_permissions(user)
    if "*" in user_perms:
        return True

    return permission_code in user_perms


def has_user_any_permission(user, *permission_codes: str) -> bool:
    """
    Returns True if user has at least one of the given permission codes.
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    user_perms = get_user_permissions(user)
    if "*" in user_perms:
        return True

    return bool(set(permission_codes).intersection(user_perms))


def assign_user_role(user, role_code: str, assigned_by=None) -> UserRole:
    """
    Idempotently assigns a role to a user.
    """
    role = Role.objects.get(code=role_code, is_active=True)
    user_role, created = UserRole.objects.get_or_create(
        user=user,
        role=role,
        defaults={"assigned_by": assigned_by, "is_active": True},
    )
    if not created and not user_role.is_active:
        user_role.is_active = True
        user_role.assigned_by = assigned_by
        user_role.save(update_fields=["is_active", "assigned_by"])
    return user_role


def remove_user_role(user, role_code: str) -> bool:
    """
    Deactivates a user's role assignment.
    """
    updated = UserRole.objects.filter(user=user, role__code=role_code, is_active=True).update(
        is_active=False
    )
    return bool(updated)

from typing import Set
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db.models import Q
from .models import Permission, Role, UserPermission, UserPermissionBlock, UserRole

User = get_user_model()

#: System roles only a wildcard holder may assign, revoke, edit or deactivate,
#: and that nobody may delete. The Console API and the Django admin both read
#: this one definition.
PROTECTED_ROLE_CODES = frozenset({Role.ROLE_SUPER_ADMINISTRATOR, Role.ROLE_ADMINISTRATOR})

#: Roles whose definition (permissions, active flag, name) only a Super
#: Administrator may change, in the Django admin, and which are never
#: deleted. CUSTOMER is one: switching it off or narrowing it would lock every
#: shopper out of cart and checkout (TASK-048 decision 9). Unlike
#: PROTECTED_ROLE_CODES, holding or assigning a role here needs nothing extra.
LOCKED_ROLE_CODES = PROTECTED_ROLE_CODES | {Role.ROLE_CUSTOMER}


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
        2. any permission granted directly to them via UserPermission,
      minus any permission turned off for them (UserPermissionBlock).

    Roles stay the primary grant path; the direct grants and the blocks are the
    single-account exceptions (see their docstrings). This function is the only
    place permissions are resolved, so applying them here is what makes them
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

    # A subquery, so the blocks cost no extra round trip.
    blocked = UserPermissionBlock.objects.filter(user=user, is_active=True).values("permission_id")

    role_permissions = set(
        Permission.objects.filter(
            role_permissions__role__user_roles__user=user,
            role_permissions__role__user_roles__is_active=True,
            role_permissions__role__is_active=True,
        ).exclude(pk__in=blocked).values_list("code", flat=True)
    )

    direct_permissions = set(
        Permission.objects.filter(
            user_permissions__user=user,
            user_permissions__is_active=True,
        ).exclude(pk__in=blocked).values_list("code", flat=True)
    )

    return role_permissions | direct_permissions


def get_blocked_permission_codes(user) -> Set[str]:
    """The codes turned off for `user` (UserPermissionBlock), whatever their roles say."""
    if not user or not user.is_authenticated:
        return set()
    return set(
        UserPermissionBlock.objects.filter(user=user, is_active=True).values_list("permission__code", flat=True)
    )


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


def users_with_permission(permission_code: str):
    """
    The reverse of has_user_permission(): every active user who holds
    `permission_code`, as a queryset. Used to find who to notify, so it follows
    the same rules through the same paths:

    - an active role, through an active assignment, that grants the code, the
      "*" wildcard, or is SUPER_ADMINISTRATOR (which holds every code);
    - an active direct grant of the code or of "*".

    Two deliberate differences, because this answers "who should be told"
    rather than "who may act" (docs/NOTIFICATION_SYSTEM.md §3 D5):
    is_superuser alone doesn't count, or superusers would receive every staff
    alert on the platform; and inactive accounts, which can't sign in, are
    left out.

    A block (UserPermissionBlock) on the code leaves its holder out, unless
    they hold the wildcard, which blocks never reach.
    """
    active_roles = UserRole.objects.filter(is_active=True, role__is_active=True)
    wildcard_holders = Q(
        pk__in=active_roles.filter(
            Q(role__code=Role.ROLE_SUPER_ADMINISTRATOR) | Q(role__role_permissions__permission__code="*")
        ).values("user_id")
    ) | Q(pk__in=UserPermission.objects.filter(is_active=True, permission__code="*").values("user_id"))
    code_holders = Q(
        pk__in=active_roles.filter(role__role_permissions__permission__code=permission_code).values("user_id")
    ) | Q(pk__in=UserPermission.objects.filter(is_active=True, permission__code=permission_code).values("user_id"))
    blocked = UserPermissionBlock.objects.filter(is_active=True, permission__code=permission_code).values("user_id")
    return User.objects.filter(is_active=True).filter(wildcard_holders | (code_holders & ~Q(pk__in=blocked)))


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


def has_wildcard_delegation(actor) -> bool:
    """
    Whether `actor` holds the "*" wildcard and may therefore delegate anything.

    True for Django superusers and SUPER_ADMINISTRATOR role holders — exactly
    the two cases get_user_permissions() answers with the "*" wildcard. This is
    the single definition of "full platform access": the delegation helpers
    below branch on it, and the admin permission catalogue reports it verbatim.
    """
    if not actor or not actor.is_authenticated:
        return False
    if actor.is_superuser:
        return True
    return "*" in get_user_permissions(actor)


def get_self_service_permission_codes() -> Set[str]:
    """
    The permissions of the active CUSTOMER role.

    Anyone can get these by registering, and each one acts only on the
    holder's own profile, cart, orders, reviews and tickets. The delegation
    checks below therefore leave them out: an operator need not hold
    'reviews.create' to give someone the CUSTOMER role or to deactivate a
    customer, and the ADMINISTRATOR role deliberately does not hold the
    customer-only codes (docs/SUPPORT_SYSTEM.md §4).
    """
    return set(
        Permission.objects.filter(
            role_permissions__role__code=Role.ROLE_CUSTOMER,
            role_permissions__role__is_active=True,
        ).values_list("code", flat=True)
    )


def get_user_management_denial(actor, target):
    """
    Why `actor` may not manage `target`'s account, or None when they may.

    "Manage" covers editing the account, changing its password, activating,
    deactivating or deleting it, and changing its roles or grants. A wildcard
    holder may manage anyone. Everyone else may only manage an account that
    has no protected role and whose effective permissions, self-service ones
    aside, are a subset of their own, so they can never act as, or lock out,
    someone above them. Only a Django superuser may manage another superuser:
    the flag also unlocks the whole Django admin, which the RBAC wildcard does
    not.

    Self-management is a separate question each caller answers: editing one's
    own profile is fine, changing one's own roles never is.
    """
    if not actor or not actor.is_authenticated:
        return "Not signed in."
    if target.is_superuser and not actor.is_superuser:
        return "Only a superuser can modify a superuser account."
    if has_wildcard_delegation(actor):
        return None
    if get_user_role_codes(target) & PROTECTED_ROLE_CODES:
        return "Only a Super Administrator can modify an account that holds a protected role."
    beyond = (
        get_user_permissions(target)
        - get_user_permissions(actor)
        - get_self_service_permission_codes()
    )
    if beyond:
        return "This account holds permissions you do not hold: " + ", ".join(sorted(beyond))
    return None


def assert_can_manage_user(actor, target) -> None:
    """get_user_management_denial() as a PermissionDenied (403 under DRF)."""
    denial = get_user_management_denial(actor, target)
    if denial:
        raise DjangoPermissionDenied(denial)


def assert_can_assign_roles(actor, target, desired_roles) -> None:
    """
    The delegation boundary for giving `target` the roles `desired_roles`
    (BUG-003). `target` is None for an account being created.

    - An existing target must be one the actor may manage at all
      (get_user_management_denial).
    - Every role being added must grant only permissions the actor holds,
      self-service ones aside -- "you may only give away what you hold", as
      for role editing. Otherwise an operator could hand a role above their
      own to an account they control, a new one they create included.

    Wildcard holders are unrestricted. Raises PermissionDenied; unknown role
    codes are left to the caller, which reports them as a 400.
    """
    if target is not None:
        assert_can_manage_user(actor, target)
    if has_wildcard_delegation(actor):
        return

    current = get_user_role_codes(target) if target is not None else set()
    added = set(desired_roles) - current
    if not added:
        return
    granted = set(
        Permission.objects.filter(role_permissions__role__code__in=added).values_list("code", flat=True)
    )
    beyond = granted - get_user_permissions(actor) - get_self_service_permission_codes()
    if beyond:
        raise DjangoPermissionDenied(
            "Cannot assign roles that grant permissions you do not hold: " + ", ".join(sorted(beyond))
        )


def get_delegatable_permission_codes(actor) -> Set[str]:
    """
    The permission codes `actor` is authorized to grant to a role.

    MiniShop defines the delegation boundary as "you may only give away what you
    already hold": a user creating or editing a role may attach a permission
    only if that permission is part of their own effective permission set. A
    wildcard holder (superuser / SUPER_ADMINISTRATOR) may delegate the entire
    seeded catalogue.

    This is the DISPLAY projection of the boundary, used by the admin permission
    catalogue endpoint to mark each permission selectable or locked. The
    ENFORCEMENT side is get_undelegatable_permission_codes(); both read the same
    effective permission set, so the console can never offer a permission the
    role endpoints would then reject.

    Note that this is deliberately not the same question as "what can this user
    do" — effective permissions are resolved by get_user_permissions() and
    include the "*" marker, which is not a real, assignable permission and is
    therefore never returned here.
    """
    if not actor or not actor.is_authenticated:
        return set()

    if has_wildcard_delegation(actor):
        return set(Permission.objects.values_list("code", flat=True))

    return {code for code in get_user_permissions(actor) if code != "*"}


def get_undelegatable_permission_codes(actor, requested_codes) -> Set[str]:
    """
    The subset of `requested_codes` that `actor` may NOT grant to a role.

    An empty result means the whole request is authorized. This is the single
    enforcement point behind the anti-escalation checks in
    AdminRoleListCreateAPIView.post and AdminRoleDetailAPIView.patch, so the
    rule cannot drift between role creation and role editing.

    A wildcard holder is unrestricted, including for codes that are not in the
    catalogue at all — those are silently dropped later by the
    Permission.objects.filter(code__in=...) lookup that actually attaches the
    grants, which is the behaviour this endpoint has always had.
    """
    requested = set(requested_codes)
    if not requested:
        return set()

    if not actor or not actor.is_authenticated:
        return requested

    if has_wildcard_delegation(actor):
        return set()

    return requested - get_user_permissions(actor)


def get_permission_block_denial(actor, target):
    """
    Why `actor` may not turn permissions off (or back on) for `target`, or None.

    Narrower than get_user_management_denial(): turning a code off only takes
    access away, and turning it back on only restores what the target's roles
    already grant, so neither can lift anyone above the actor. The subset rule
    is therefore not applied (an Administrator may limit a Sales Team member,
    who holds 'sellers.onboard'). What stays protected: one's own account, a
    superuser (from anyone but a superuser) and a protected role (from anyone
    below the wildcard).
    """
    if actor.pk == target.pk:
        return "You cannot change your own permissions."
    if target.is_superuser and not actor.is_superuser:
        return "Only a superuser can modify a superuser account."
    if not has_wildcard_delegation(actor) and get_user_role_codes(target) & PROTECTED_ROLE_CODES:
        return "Only a Super Administrator can modify an account that holds a protected role."
    return None


def block_user_permission(actor, target, code: str, reason: str) -> UserPermissionBlock:
    """
    Turns `code` off for `target` although their roles grant it
    (get_permission_block_denial() decides who may). Only a code `target`
    holds now; never on the wildcard, which blocks do not reach. Raises
    PermissionDenied or ValueError; the caller audits.
    """
    from django.utils import timezone

    denial = get_permission_block_denial(actor, target)
    if denial:
        raise DjangoPermissionDenied(denial)
    held = get_user_permissions(target)
    if "*" in held:
        raise ValueError("This account has full platform access, which a turned-off permission does not limit.")
    if code not in held:
        raise ValueError(f"This account does not hold '{code}', so there is nothing to turn off.")
    permission = Permission.objects.get(code=code)
    block, created = UserPermissionBlock.objects.get_or_create(
        user=target,
        permission=permission,
        defaults={"blocked_by": actor, "blocked_at": timezone.now(), "is_active": True, "reason": reason},
    )
    if not created:
        block.blocked_by = actor
        block.blocked_at = timezone.now()
        block.is_active = True
        block.reason = reason
        block.save(update_fields=["blocked_by", "blocked_at", "is_active", "reason"])
    return block


def unblock_user_permission(actor, target, code: str) -> UserPermissionBlock:
    """Turns a blocked `code` back on for `target`, with the checks of block_user_permission()."""
    denial = get_permission_block_denial(actor, target)
    if denial:
        raise DjangoPermissionDenied(denial)
    block = UserPermissionBlock.objects.filter(user=target, permission__code=code, is_active=True).first()
    if block is None:
        raise ValueError(f"'{code}' is not turned off for this account.")
    block.is_active = False
    block.save(update_fields=["is_active"])
    return block

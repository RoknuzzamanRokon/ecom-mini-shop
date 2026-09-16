# admin_views.py
"""
Admin & Platform Governance API Views (Task 17).
Provides secured administrative endpoints under /api/admin/ namespace.
Enforces strict RBAC authorization, anti-escalation safeguards, financial data tamper protection,
concurrency control, and comprehensive audit logging.
"""

import logging
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError as DRFValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .metrics import get_console_metrics
from audit.models import AuditLog
from audit.services import AuditService
from customers.models import CustomerProfile
from rbac.models import Permission, Role, RolePermission, UserRole
from rbac.services import (
    assign_user_role,
    get_delegatable_permission_codes,
    get_undelegatable_permission_codes,
    get_user_role_codes,
    has_wildcard_delegation,
    has_user_permission,
    remove_user_role,
)
from sellers.models import SellerProfile
from sellers.services import (
    approve_seller,
    create_seller_profile,
    reactivate_seller,
    reject_seller,
    suspend_seller,
)
from shop.admin_permissions import (
    CanChangeAdminProductStatus,
    CanChangeAdminShopStatus,
    CanManageAdminCategories,
    CanManageAdminProducts,
    CanManageAdminRoles,
    CanManageAdminSellers,
    CanManageAdminShops,
    CanManageAdminUsers,
    CanViewAdminAuditLogs,
    CanViewAdminCustomers,
    CanViewAdminProducts,
    CanViewAdminRoles,
    CanViewAdminSellers,
    CanViewAdminShops,
    CanViewAdminUsers,
)
from shop.admin_serializers import (
    PROTECTED_ROLE_CODES,
    AdminAuditLogSerializer,
    AdminPermissionSerializer,
    AdminCategorySerializer,
    AdminCustomerDetailSerializer,
    AdminCustomerListSerializer,
    AdminProductSerializer,
    AdminProductStatusUpdateSerializer,
    AdminSellerCreateSerializer,
    AdminRoleCreateSerializer,
    AdminRoleSerializer,
    AdminRoleUpdateSerializer,
    AdminSellerSerializer,
    AdminSellerStatusUpdateSerializer,
    AdminShopCreateSerializer,
    AdminShopSerializer,
    AdminShopStatusUpdateSerializer,
    AdminUserCreateSerializer,
    AdminUserDetailSerializer,
    AdminUserListSerializer,
    AdminUserUpdateSerializer,
)
from shop.models import Category, Order, Payment, Product
from shops.models import Shop
from shops.services import IneligibleSellerError, ShopLimitExceededError, ShopService

logger = logging.getLogger(__name__)
User = get_user_model()


class AdminPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# ==============================================================================
# 1. USER ADMINISTRATION VIEWS
# ==============================================================================

class AdminUserListAPIView(APIView):
    """
    GET  /api/admin/users/
    POST /api/admin/users/
    List users with search, role filters, active filters, and pagination, or
    create a new management/platform account.
    """
    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [IsAuthenticated(), CanManageAdminUsers()]
        return [IsAuthenticated(), CanViewAdminUsers()]

    def get(self, request):
        qs = User.objects.all().order_by("-date_joined")
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        is_active = request.query_params.get("is_active")
        if is_active is not None:
            if is_active.lower() in ("true", "1"):
                qs = qs.filter(is_active=True)
            elif is_active.lower() in ("false", "0"):
                qs = qs.filter(is_active=False)

        role = request.query_params.get("role", "").strip()
        if role:
            qs = qs.filter(user_roles__role__code=role, user_roles__is_active=True)

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AdminUserListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


    def post(self, request):
        """
        Creates a user account, optionally assigning roles in the same
        transaction.

        The role-assignment rules below are deliberately IDENTICAL to checks 3
        and 4 of AdminUserDetailAPIView.patch, evaluated against an empty
        starting role set (a new account holds nothing yet). Creation must not
        become a way around a restriction that applies to editing: an actor who
        may not grant SUPER_ADMINISTRATOR to an existing user must not be able
        to grant it by creating a user instead.

        Two of the patch checks have no counterpart here, because they cannot
        apply to an account that does not exist yet: the target cannot already
        be a Super Administrator, and the actor cannot be modifying themselves.
        The last-active-Super-Administrator rule likewise cannot be violated by
        a creation, which can only ever increase that count.
        """
        serializer = AdminUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        reason = data["reason"]

        actor = request.user
        actor_role_codes = get_user_role_codes(actor)
        actor_is_super = actor.is_superuser or (Role.ROLE_SUPER_ADMINISTRATOR in actor_role_codes)

        desired_roles = set(data.get("roles", []))

        # Check 1: only a Super Administrator may grant SUPER_ADMINISTRATOR.
        if (Role.ROLE_SUPER_ADMINISTRATOR in desired_roles) and not actor_is_super:
            raise PermissionDenied("Only a Super Administrator can grant the Super Administrator role.")

        # Check 2: only a Super Administrator may assign any protected role.
        for protected_code in PROTECTED_ROLE_CODES:
            if (protected_code in desired_roles) and not actor_is_super:
                raise PermissionDenied(f"Only a Super Administrator can assign the protected role '{protected_code}'.")

        # Check 3: every requested role must exist and be active, exactly as the
        # patch path resolves them.
        if desired_roles:
            existing_roles = {r.code for r in Role.objects.filter(code__in=desired_roles, is_active=True)}
            missing_codes = desired_roles - existing_roles
            if missing_codes:
                raise DRFValidationError({"roles": f"Unknown or inactive role codes: {sorted(list(missing_codes))}"})

        with transaction.atomic():
            new_user = User.objects.create_user(
                username=data["username"],
                email=data["email"],
                password=data["password"],
                first_name=data.get("first_name", "").strip(),
                last_name=data.get("last_name", "").strip(),
            )

            # create_user() defaults is_active=True; only touch it when the
            # caller asked for something else.
            if data.get("is_active") is False:
                new_user.is_active = False
                new_user.save(update_fields=["is_active"])

            for code in sorted(desired_roles):
                assign_user_role(new_user, code, assigned_by=actor)

            AuditService.log(
                action="ADMIN_USER_CREATED",
                target=new_user,
                actor=actor,
                reason=reason,
                new_state={
                    "username": new_user.username,
                    "email": new_user.email,
                    "is_active": new_user.is_active,
                    "roles": sorted(list(get_user_role_codes(new_user))),
                },
                ip_address=get_client_ip(request),
            )

        return Response(
            AdminUserDetailSerializer(User.objects.get(pk=new_user.pk)).data,
            status=status.HTTP_201_CREATED,
        )


class AdminUserDetailAPIView(APIView):
    """
    GET   /api/admin/users/<int:pk>/
    PATCH /api/admin/users/<int:pk>/
    Inspect user details and manage active state / role assignments.
    Prevents privilege escalation and self-escalation.
    """
    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT", "POST", "DELETE"):
            return [IsAuthenticated(), CanManageAdminUsers()]
        return [IsAuthenticated(), CanViewAdminUsers()]

    def get(self, request, pk):
        try:
            target_user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            raise NotFound("User not found.")
        serializer = AdminUserDetailSerializer(target_user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        serializer = AdminUserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        reason = data["reason"]

        actor = request.user
        actor_role_codes = get_user_role_codes(actor)
        actor_is_super = actor.is_superuser or (Role.ROLE_SUPER_ADMINISTRATOR in actor_role_codes)

        with transaction.atomic():
            try:
                target_user = User.objects.select_for_update().get(pk=pk)
            except User.DoesNotExist:
                raise NotFound("User not found.")

            target_role_codes = set(get_user_role_codes(target_user))
            target_is_super = target_user.is_superuser or (Role.ROLE_SUPER_ADMINISTRATOR in target_role_codes)

            # Check 1: Non-superadmin cannot modify a Super Administrator account
            if target_is_super and not actor_is_super:
                raise PermissionDenied("Only a Super Administrator can modify another Super Administrator account.")

            # Check 2: Self-modification of roles is strictly forbidden to prevent self-escalation
            if actor.id == target_user.id and "roles" in data:
                raise PermissionDenied("Self-modification of roles is strictly prohibited.")

            prev_state = {
                "is_active": target_user.is_active,
                "roles": sorted(list(target_role_codes)),
            }
            changed = False

            # Update is_active if provided
            if "is_active" in data:
                new_active = data["is_active"]
                if target_user.is_active != new_active:
                    # Prevent deactivating the last active superadmin
                    if not new_active and target_is_super:
                        active_superadmins = User.objects.filter(
                            is_active=True,
                            user_roles__role__code=Role.ROLE_SUPER_ADMINISTRATOR,
                            user_roles__is_active=True,
                        ).count()
                        if active_superadmins <= 1:
                            raise DRFValidationError({"is_active": "Cannot deactivate the last active Super Administrator."})

                    target_user.is_active = new_active
                    target_user.save(update_fields=["is_active"])
                    changed = True

            # Update roles if provided
            if "roles" in data:
                desired_roles = set(data["roles"])

                # Check 3: Only Super Administrator can assign or revoke SUPER_ADMINISTRATOR
                if (Role.ROLE_SUPER_ADMINISTRATOR in desired_roles) and not actor_is_super:
                    raise PermissionDenied("Only a Super Administrator can grant the Super Administrator role.")
                if (Role.ROLE_SUPER_ADMINISTRATOR in target_role_codes) and (Role.ROLE_SUPER_ADMINISTRATOR not in desired_roles) and not actor_is_super:
                    raise PermissionDenied("Only a Super Administrator can revoke the Super Administrator role.")

                # Check 4: Non-superadmins cannot assign protected roles
                for protected_code in PROTECTED_ROLE_CODES:
                    if (protected_code in desired_roles) and (protected_code not in target_role_codes) and not actor_is_super:
                        raise PermissionDenied(f"Only a Super Administrator can assign the protected role '{protected_code}'.")

                # Validate that all requested role codes exist in DB
                existing_roles = {r.code: r for r in Role.objects.filter(code__in=desired_roles, is_active=True)}
                missing_codes = desired_roles - set(existing_roles.keys())
                if missing_codes:
                    raise DRFValidationError({"roles": f"Unknown or inactive role codes: {sorted(list(missing_codes))}"})

                # Determine roles to add and remove
                roles_to_add = desired_roles - target_role_codes
                roles_to_remove = target_role_codes - desired_roles

                for code in roles_to_add:
                    assign_user_role(target_user, code, assigned_by=actor)
                    changed = True

                for code in roles_to_remove:
                    remove_user_role(target_user, code)
                    changed = True

            new_state = {
                "is_active": target_user.is_active,
                "roles": sorted(list(get_user_role_codes(target_user))),
            }

            if changed:
                AuditService.log(
                    action="ADMIN_USER_UPDATED",
                    target=target_user,
                    actor=actor,
                    reason=reason,
                    previous_state=prev_state,
                    new_state=new_state,
                    ip_address=get_client_ip(request),
                )

        reloaded = User.objects.get(pk=pk)
        return Response(AdminUserDetailSerializer(reloaded).data, status=status.HTTP_200_OK)


# ==============================================================================
# 2. ROLE MANAGEMENT VIEWS
# ==============================================================================

class AdminRoleListCreateAPIView(APIView):
    """
    GET  /api/admin/roles/
    POST /api/admin/roles/
    List roles or create a custom role.
    Prevents creating protected roles or assigning permissions the actor doesn't possess.
    """
    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [IsAuthenticated(), CanManageAdminRoles()]
        return [IsAuthenticated(), CanViewAdminRoles()]

    def get(self, request):
        roles = Role.objects.all().order_by("name")
        serializer = AdminRoleSerializer(roles, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = AdminRoleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        reason = data["reason"]

        actor = request.user
        requested_permissions = set(data.get("permissions", []))

        # Anti-escalation: a non-wildcard actor cannot create a role carrying
        # permissions outside their own delegation boundary. The boundary lives
        # in rbac.services so role creation and role editing can never diverge.
        unauthorized_perms = get_undelegatable_permission_codes(actor, requested_permissions)
        if unauthorized_perms:
            raise PermissionDenied(
                f"Cannot assign permissions you do not possess: {sorted(list(unauthorized_perms))}"
            )

        with transaction.atomic():
            role = Role.objects.create(
                code=data["code"],
                name=data["name"],
                description=data.get("description", ""),
                is_active=True,
            )

            if requested_permissions:
                perms_objs = Permission.objects.filter(code__in=requested_permissions)
                for p in perms_objs:
                    RolePermission.objects.create(role=role, permission=p)

            AuditService.log(
                action="ADMIN_ROLE_CREATED",
                target=role,
                actor=actor,
                reason=reason,
                new_state={
                    "code": role.code,
                    "name": role.name,
                    "permissions": sorted(list(requested_permissions)),
                },
                ip_address=get_client_ip(request),
            )

        return Response(AdminRoleSerializer(role).data, status=status.HTTP_201_CREATED)


class AdminRoleDetailAPIView(APIView):
    """
    GET    /api/admin/roles/<int:pk>/
    PATCH  /api/admin/roles/<int:pk>/
    DELETE /api/admin/roles/<int:pk>/
    Inspect, update, or delete role.
    Protects seeded/system roles and prevents deleting roles assigned to users.
    """
    def get_permissions(self):
        if self.request.method in ("PATCH", "PUT", "POST", "DELETE"):
            return [IsAuthenticated(), CanManageAdminRoles()]
        return [IsAuthenticated(), CanViewAdminRoles()]

    def get(self, request, pk):
        try:
            role = Role.objects.get(pk=pk)
        except Role.DoesNotExist:
            raise NotFound("Role not found.")
        return Response(AdminRoleSerializer(role).data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        try:
            role = Role.objects.get(pk=pk)
        except Role.DoesNotExist:
            raise NotFound("Role not found.")

        # Protected role check
        if role.code in PROTECTED_ROLE_CODES:
            raise PermissionDenied(f"Protected system role '{role.code}' cannot be modified.")

        serializer = AdminRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        reason = data["reason"]

        actor = request.user

        with transaction.atomic():
            role = Role.objects.select_for_update().get(pk=pk)
            prev_state = {
                "name": role.name,
                "description": role.description,
                "is_active": role.is_active,
                "permissions": list(role.permissions.values_list("code", flat=True)),
            }

            if "name" in data:
                role.name = data["name"]
            if "description" in data:
                role.description = data["description"]
            if "is_active" in data:
                role.is_active = data["is_active"]
            role.save()

            if "permissions" in data:
                requested_perms = set(data["permissions"])
                unauthorized = get_undelegatable_permission_codes(actor, requested_perms)
                if unauthorized:
                    raise PermissionDenied(f"Cannot grant permissions you do not hold: {sorted(list(unauthorized))}")

                RolePermission.objects.filter(role=role).delete()
                for perm in Permission.objects.filter(code__in=requested_perms):
                    RolePermission.objects.create(role=role, permission=perm)

            new_state = {
                "name": role.name,
                "description": role.description,
                "is_active": role.is_active,
                "permissions": list(role.permissions.values_list("code", flat=True)),
            }

            AuditService.log(
                action="ADMIN_ROLE_UPDATED",
                target=role,
                actor=actor,
                reason=reason,
                previous_state=prev_state,
                new_state=new_state,
                ip_address=get_client_ip(request),
            )

        return Response(AdminRoleSerializer(role).data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        try:
            role = Role.objects.get(pk=pk)
        except Role.DoesNotExist:
            raise NotFound("Role not found.")

        # Check 1: Cannot delete protected roles
        if role.code in PROTECTED_ROLE_CODES:
            raise PermissionDenied(f"Protected system role '{role.code}' cannot be deleted.")

        # Check 2: Cannot delete a role currently assigned to active users
        assigned_active_count = UserRole.objects.filter(role=role, is_active=True).count()
        if assigned_active_count > 0:
            raise DRFValidationError(
                f"Cannot delete role '{role.code}': it is currently assigned to {assigned_active_count} active user(s). "
                "Reassign or remove user roles before deleting."
            )

        reason = request.data.get("reason", "Admin role deletion") if isinstance(request.data, dict) else "Admin role deletion"

        with transaction.atomic():
            role = Role.objects.select_for_update().get(pk=pk)
            AuditService.log(
                action="ADMIN_ROLE_DELETED",
                target=role,
                actor=request.user,
                reason=reason,
                previous_state={"code": role.code, "name": role.name},
                ip_address=get_client_ip(request),
            )
            role.delete()

        return Response({"detail": f"Role '{role.code}' successfully deleted."}, status=status.HTTP_200_OK)


# ==============================================================================
# 2b. PERMISSION CATALOGUE VIEW
# ==============================================================================

class AdminPermissionCatalogAPIView(APIView):
    """
    GET /api/admin/permissions/

    The MiniShop RBAC permission catalogue, annotated with what the REQUESTING
    user is allowed to delegate.

    This exists so the Management Console's role permission selector can be
    driven entirely by backend data. Without it a client would have to hardcode
    the permission list, which would make the frontend a second source of truth
    for the catalogue, and would have to guess the delegation boundary, which
    would make its checkboxes disagree with the 403s the role endpoints return.

    `is_delegatable` is computed by get_delegatable_permission_codes(), the same
    rbac.services boundary that get_undelegatable_permission_codes() enforces on
    POST /api/admin/roles/ and PATCH /api/admin/roles/<pk>/. A locked checkbox
    in the console is therefore a faithful preview of a backend refusal — and
    never a substitute for it, since this endpoint is read-only and the role
    endpoints re-validate every submitted code themselves.

    Read access is gated by CanViewAdminRoles ('roles.admin.view'): the
    catalogue describes the RBAC system, so it belongs to role administration.
    """

    permission_classes = [IsAuthenticated, CanViewAdminRoles]

    def get(self, request):
        # Permission.Meta.ordering is ("resource", "action"), so the catalogue
        # arrives already grouped by resource for the console's selector.
        permissions_qs = Permission.objects.all()
        delegatable_codes = get_delegatable_permission_codes(request.user)

        serializer = AdminPermissionSerializer(
            permissions_qs,
            many=True,
            context={"delegatable_codes": delegatable_codes},
        )
        data = serializer.data

        return Response(
            {
                "count": len(data),
                # True only for superusers / SUPER_ADMINISTRATOR: the "*" holders
                # who may delegate the entire catalogue. The console renders this
                # as "Full platform access" rather than as 64 individual grants.
                "has_full_platform_access": has_wildcard_delegation(request.user),
                "delegatable_count": sum(1 for row in data if row["is_delegatable"]),
                "results": data,
            },
            status=status.HTTP_200_OK,
        )


# ==============================================================================
# 3. SELLER ADMINISTRATION VIEWS
# ==============================================================================

class AdminSellerListAPIView(APIView):
    """
    GET  /api/admin/sellers/
    POST /api/admin/sellers/
    Browse the seller directory, or create a seller profile on behalf of an
    existing user account.
    """
    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [IsAuthenticated(), CanManageAdminSellers()]
        return [IsAuthenticated(), CanViewAdminSellers()]

    def get(self, request):
        qs = SellerProfile.objects.select_related("user").prefetch_related("shops").all().order_by("-created_at")

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(business_name__icontains=search)
                | Q(business_email__icontains=search)
                | Q(business_phone__icontains=search)
                | Q(user__username__icontains=search)
            )

        seller_status = request.query_params.get("status", "").strip().upper()
        if seller_status:
            qs = qs.filter(status=seller_status)

        seller_type = request.query_params.get("seller_type", "").strip().upper()
        if seller_type:
            qs = qs.filter(seller_type=seller_type)

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AdminSellerSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


    def post(self, request):
        """
        Creates a SellerProfile for an existing user, in the PENDING state.

        Gated by CanManageAdminSellers ('sellers.admin.manage'), the permission
        that already governs every other arbitrary-target seller operation
        (AdminSellerStatusAPIView). The seeded but unreferenced 'sellers.create'
        is deliberately NOT wired up here: three roles hold it today on the
        understanding that it grants nothing, and giving it meaning would
        silently widen their authority without anyone assigning it.

        Creation is intentionally inert beyond the profile itself — the seller
        starts PENDING and must go through the existing approval endpoints. No
        role is assigned, no wallet or point transaction is created, and no shop
        or product is touched.
        """
        serializer = AdminSellerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        reason = data["reason"]

        with transaction.atomic():
            try:
                target_user = User.objects.select_for_update().get(pk=data["user_id"])
            except User.DoesNotExist:
                raise NotFound("User not found.")

            try:
                seller = create_seller_profile(
                    target_user,
                    seller_type=data["seller_type"],
                    business_name=data["business_name"],
                    business_email=data.get("business_email", ""),
                    business_phone=data.get("business_phone", ""),
                    tax_id=data.get("tax_id", ""),
                    description=data.get("description", ""),
                )
            except DjangoValidationError as exc:
                # The shared service and SellerProfile.full_clean() raise Django
                # validation errors; surface them as ordinary DRF 400 field
                # errors rather than letting them become a 500.
                raise DRFValidationError(
                    exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
                )

            AuditService.log(
                action="ADMIN_SELLER_CREATED",
                target=seller,
                actor=request.user,
                reason=reason,
                new_state={
                    "seller_id": seller.id,
                    "user_id": target_user.id,
                    "username": target_user.username,
                    "business_name": seller.business_name,
                    "seller_type": seller.seller_type,
                    "status": seller.status,
                },
                ip_address=get_client_ip(request),
            )

        return Response(AdminSellerSerializer(seller).data, status=status.HTTP_201_CREATED)


class AdminSellerDetailAPIView(APIView):
    """
    GET /api/admin/sellers/<int:pk>/
    Inspect seller application/profile detail.
    """
    permission_classes = [IsAuthenticated, CanViewAdminSellers]

    def get(self, request, pk):
        try:
            seller = SellerProfile.objects.select_related("user").prefetch_related("shops").get(pk=pk)
        except SellerProfile.DoesNotExist:
            raise NotFound("Seller profile not found.")
        return Response(AdminSellerSerializer(seller).data, status=status.HTTP_200_OK)


class AdminSellerStatusAPIView(APIView):
    """
    POST /api/admin/sellers/<int:pk>/status/
    PATCH /api/admin/sellers/<int:pk>/status/
    Transitions seller lifecycle (approve, reject, suspend, reactivate).
    Delegates strictly to domain service methods.
    """
    permission_classes = [IsAuthenticated, CanManageAdminSellers]

    def post(self, request, pk):
        return self._update_status(request, pk)

    def patch(self, request, pk):
        return self._update_status(request, pk)

    def _update_status(self, request, pk):
        serializer = AdminSellerStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("reason", "")

        with transaction.atomic():
            try:
                seller = SellerProfile.objects.select_for_update().get(pk=pk)
            except SellerProfile.DoesNotExist:
                raise NotFound("Seller profile not found.")

            old_status = seller.status

            if action == "approve":
                seller = approve_seller(seller, request.user)
            elif action == "reject":
                seller = reject_seller(seller, request.user, reason)
            elif action == "suspend":
                seller = suspend_seller(seller, request.user, reason)
            elif action == "reactivate":
                seller = reactivate_seller(seller, request.user)

            AuditService.log(
                action=f"ADMIN_SELLER_{action.upper()}",
                target=seller,
                actor=request.user,
                seller=seller,
                reason=reason or f"Seller {action}d by staff",
                previous_state={"status": old_status},
                new_state={"status": seller.status},
                ip_address=get_client_ip(request),
            )

        return Response(AdminSellerSerializer(seller).data, status=status.HTTP_200_OK)


# ==============================================================================
# 4. SHOP ADMINISTRATION VIEWS
# ==============================================================================

class AdminShopListAPIView(APIView):
    """
    GET  /api/admin/shops/
    POST /api/admin/shops/
    Paginated, searchable list of shops across the platform, or create a Shop
    and assign an existing SellerProfile as its owner.
    """
    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [IsAuthenticated(), CanManageAdminShops()]
        return [IsAuthenticated(), CanViewAdminShops()]

    def get(self, request):
        qs = Shop.objects.select_related("owner", "owner__user").prefetch_related("products").all().order_by("-created_at")

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(slug__icontains=search)
                | Q(owner__business_name__icontains=search)
            )

        shop_status = request.query_params.get("status", "").strip().upper()
        if shop_status:
            qs = qs.filter(status=shop_status)

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AdminShopSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        """
        Creates a Shop and assigns an existing SellerProfile as its owner —
        the "Admin creates Shop -> assigns Shop Owner" half of the Admin-created
        Shop Owner model. Delegates entirely to ShopService.create_shop so the
        same eligibility rules (operational seller, no PRODUCT_OWNER, single
        shop cap for every Shop Owner type) apply as for the (now seller-disabled)
        self-service path.
        """
        serializer = AdminShopCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        reason = data["reason"]

        with transaction.atomic():
            try:
                seller = SellerProfile.objects.select_for_update().get(pk=data["seller_id"])
            except SellerProfile.DoesNotExist:
                raise NotFound("Seller profile not found.")

            try:
                shop = ShopService.create_shop(
                    seller=seller,
                    name=data["name"],
                    description=data.get("description", ""),
                    phone=data.get("phone", ""),
                    address=data.get("address", ""),
                    latitude=data.get("latitude"),
                    longitude=data.get("longitude"),
                )
            except (IneligibleSellerError, ShopLimitExceededError) as exc:
                raise DRFValidationError({"seller_id": [str(exc)]})
            except DjangoValidationError as exc:
                raise DRFValidationError(
                    exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
                )

            AuditService.log(
                action="ADMIN_SHOP_CREATED",
                target=shop,
                actor=request.user,
                shop=shop,
                seller=seller,
                reason=reason,
                new_state={
                    "shop_id": shop.id,
                    "name": shop.name,
                    "slug": shop.slug,
                    "owner_id": seller.id,
                    "owner_business_name": seller.business_name,
                    "status": shop.status,
                },
                ip_address=get_client_ip(request),
            )

        return Response(AdminShopSerializer(shop).data, status=status.HTTP_201_CREATED)


class AdminShopDetailAPIView(APIView):
    """
    GET /api/admin/shops/<int:pk>/
    Inspect shop detail.
    """
    permission_classes = [IsAuthenticated, CanViewAdminShops]

    def get(self, request, pk):
        try:
            shop = Shop.objects.select_related("owner", "owner__user").prefetch_related("products").get(pk=pk)
        except Shop.DoesNotExist:
            raise NotFound("Shop not found.")
        return Response(AdminShopSerializer(shop).data, status=status.HTTP_200_OK)


class AdminShopStatusAPIView(APIView):
    """
    POST /api/admin/shops/<int:pk>/status/
    PATCH /api/admin/shops/<int:pk>/status/
    Transitions shop lifecycle (approve, reject, suspend, reactivate).
    """
    permission_classes = [IsAuthenticated, CanChangeAdminShopStatus]

    def post(self, request, pk):
        return self._update_status(request, pk)

    def patch(self, request, pk):
        return self._update_status(request, pk)

    def _update_status(self, request, pk):
        serializer = AdminShopStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("reason", "")

        # Granular RBAC enforcement: users holding only 'shops.approve' can only approve
        user = request.user
        actor_role_codes = get_user_role_codes(user)
        is_super = user.is_superuser or (Role.ROLE_SUPER_ADMINISTRATOR in actor_role_codes)
        if not is_super and not has_user_permission(user, "shops.admin.manage"):
            if action != "approve":
                raise PermissionDenied(
                    f"You do not have permission to {action} shops. Broader shop management permission ('shops.admin.manage') is required."
                )

        with transaction.atomic():
            try:
                shop = Shop.objects.select_for_update().get(pk=pk)
            except Shop.DoesNotExist:
                raise NotFound("Shop not found.")

            old_status = shop.status
            now = timezone.now()

            if action == "approve":
                shop.status = Shop.STATUS_ACTIVE
                shop.approved_at = now
                shop.reviewed_by = request.user
                shop.reviewed_at = now
            elif action == "reject":
                shop.status = Shop.STATUS_REJECTED
                shop.rejection_reason = reason
                shop.reviewed_by = request.user
                shop.reviewed_at = now
            elif action == "suspend":
                shop.status = Shop.STATUS_SUSPENDED
                shop.suspension_reason = reason
                shop.suspended_at = now
            elif action == "reactivate":
                shop.status = Shop.STATUS_ACTIVE
                shop.suspension_reason = ""
            shop.save()

            AuditService.log(
                action=f"ADMIN_SHOP_{action.upper()}",
                target=shop,
                actor=request.user,
                shop=shop,
                seller=shop.owner,
                reason=reason or f"Shop {action}d by staff",
                previous_state={"status": old_status},
                new_state={"status": shop.status},
                ip_address=get_client_ip(request),
            )

        return Response(AdminShopSerializer(shop).data, status=status.HTTP_200_OK)


# ==============================================================================
# 5. PRODUCT ADMINISTRATION VIEWS
# ==============================================================================

class AdminProductListAPIView(APIView):
    """
    GET /api/admin/products/
    Paginated, searchable list of products across the platform.
    Viewable by holders of 'products.view' as well as full product managers.
    """
    permission_classes = [IsAuthenticated, CanViewAdminProducts]

    def get(self, request):
        qs = Product.objects.select_related("category", "shop", "shop__owner").all().order_by("-created_at")

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(slug__icontains=search)
                | Q(shop__name__icontains=search)
            )

        prod_status = request.query_params.get("status", "").strip().upper()
        if prod_status:
            qs = qs.filter(status=prod_status)

        category_id = request.query_params.get("category")
        if category_id:
            qs = qs.filter(category_id=category_id)

        shop_id = request.query_params.get("shop")
        if shop_id:
            qs = qs.filter(shop_id=shop_id)

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AdminProductSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminProductDetailAPIView(APIView):
    """
    GET /api/admin/products/<int:pk>/
    Inspect product detail.
    Viewable by holders of 'products.view' as well as full product managers.
    """
    permission_classes = [IsAuthenticated, CanViewAdminProducts]

    def get(self, request, pk):
        try:
            product = Product.objects.select_related("category", "shop", "shop__owner").get(pk=pk)
        except Product.DoesNotExist:
            raise NotFound("Product not found.")
        return Response(AdminProductSerializer(product).data, status=status.HTTP_200_OK)


class AdminProductStatusAPIView(APIView):
    """
    POST /api/admin/products/<int:pk>/status/
    PATCH /api/admin/products/<int:pk>/status/
    Transitions product lifecycle (approve, reject, publish, unpublish).
    Enforces business rules (cannot publish unapproved or suspended shop products).
    """
    permission_classes = [IsAuthenticated, CanChangeAdminProductStatus]

    def post(self, request, pk):
        return self._update_status(request, pk)

    def patch(self, request, pk):
        return self._update_status(request, pk)

    def _update_status(self, request, pk):
        serializer = AdminProductStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]
        reason = serializer.validated_data.get("reason", "")

        # Granular RBAC enforcement: a user holding only one narrow permission
        # (products.approve / products.reject / products.publish) may perform
        # ONLY the matching action. 'unpublish' has no narrower permission of
        # its own, so it remains restricted to full product management.
        user = request.user
        actor_role_codes = get_user_role_codes(user)
        is_super = user.is_superuser or (Role.ROLE_SUPER_ADMINISTRATOR in actor_role_codes)
        has_full_manage = is_super or has_user_permission(user, "products.admin.manage")

        if not has_full_manage:
            action_permission_map = {
                "approve": "products.approve",
                "reject": "products.reject",
                "publish": "products.publish",
            }
            required_permission = action_permission_map.get(action)
            if not required_permission or not has_user_permission(user, required_permission):
                raise PermissionDenied(
                    f"You do not have permission to {action} products. Broader product management permission ('products.admin.manage') is required."
                )

        with transaction.atomic():
            try:
                product = Product.objects.select_for_update().select_related("shop", "shop__owner").get(pk=pk)
            except Product.DoesNotExist:
                raise NotFound("Product not found.")

            old_status = product.status
            now = timezone.now()

            if action == "approve":
                product.status = Product.STATUS_APPROVED
                product.reviewed_by = request.user
                product.reviewed_at = now
                product.rejection_reason = ""
            elif action == "reject":
                product.status = Product.STATUS_REJECTED
                product.rejection_reason = reason
                product.reviewed_by = request.user
                product.reviewed_at = now
            elif action == "publish":
                # Validate shop and seller operational status
                if not product.shop or product.shop.status not in (Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE):
                    raise DRFValidationError("Cannot publish product belonging to an unapproved or suspended shop.")
                if not product.shop.owner or not product.shop.owner.is_operational:
                    raise DRFValidationError("Cannot publish product belonging to an inoperational seller.")
                product.status = Product.STATUS_PUBLISHED
                product.is_active = True
            elif action == "unpublish":
                product.status = Product.STATUS_UNPUBLISHED

            product.save()

            AuditService.log(
                action=f"ADMIN_PRODUCT_{action.upper()}",
                target=product,
                actor=request.user,
                shop=product.shop,
                seller=product.shop.owner if product.shop else None,
                reason=reason or f"Product {action}ed by staff",
                previous_state={"status": old_status},
                new_state={"status": product.status},
                ip_address=get_client_ip(request),
            )

        return Response(AdminProductSerializer(product).data, status=status.HTTP_200_OK)


# ==============================================================================
# 6. CATEGORY ADMINISTRATION VIEWS
# ==============================================================================

class AdminCategoryListCreateAPIView(APIView):
    """
    GET  /api/admin/categories/
    POST /api/admin/categories/
    List all categories (including inactive) and create new categories.
    """
    permission_classes = [IsAuthenticated, CanManageAdminCategories]

    def get(self, request):
        qs = Category.objects.all().order_by("name")
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(slug__icontains=search))

        is_active = request.query_params.get("is_active")
        if is_active is not None:
            if is_active.lower() in ("true", "1"):
                qs = qs.filter(is_active=True)
            elif is_active.lower() in ("false", "0"):
                qs = qs.filter(is_active=False)

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AdminCategorySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        serializer = AdminCategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            category = serializer.save()
            AuditService.log(
                action="ADMIN_CATEGORY_CREATED",
                target=category,
                actor=request.user,
                reason=request.data.get("reason", "Created category via admin"),
                new_state={"name": category.name, "slug": category.slug},
                ip_address=get_client_ip(request),
            )
        return Response(AdminCategorySerializer(category).data, status=status.HTTP_201_CREATED)


class AdminCategoryDetailAPIView(APIView):
    """
    GET    /api/admin/categories/<int:pk>/
    PATCH  /api/admin/categories/<int:pk>/
    DELETE /api/admin/categories/<int:pk>/
    Inspect, update, or safely delete categories.
    CRITICAL SAFEGUARD: Prevents deletion of categories referenced by existing products.
    """
    permission_classes = [IsAuthenticated, CanManageAdminCategories]

    def get(self, request, pk):
        try:
            category = Category.objects.get(pk=pk)
        except Category.DoesNotExist:
            raise NotFound("Category not found.")
        return Response(AdminCategorySerializer(category).data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        try:
            category = Category.objects.get(pk=pk)
        except Category.DoesNotExist:
            raise NotFound("Category not found.")

        serializer = AdminCategorySerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            prev_state = {"name": category.name, "is_active": category.is_active}
            category = serializer.save()
            new_state = {"name": category.name, "is_active": category.is_active}

            AuditService.log(
                action="ADMIN_CATEGORY_UPDATED",
                target=category,
                actor=request.user,
                reason=request.data.get("reason", "Updated category via admin"),
                previous_state=prev_state,
                new_state=new_state,
                ip_address=get_client_ip(request),
            )
        return Response(AdminCategorySerializer(category).data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        try:
            category = Category.objects.get(pk=pk)
        except Category.DoesNotExist:
            raise NotFound("Category not found.")

        # SAFEGUARD: Check if category is referenced by products
        referenced_count = category.products.count()
        if referenced_count > 0:
            raise DRFValidationError(
                f"Cannot delete category '{category.name}' because it is referenced by {referenced_count} product(s). "
                "Deactivate the category (set is_active=False) instead."
            )

        with transaction.atomic():
            AuditService.log(
                action="ADMIN_CATEGORY_DELETED",
                target=category,
                actor=request.user,
                reason=request.data.get("reason", "Deleted unused category via admin"),
                previous_state={"name": category.name, "slug": category.slug},
                ip_address=get_client_ip(request),
            )
            category.delete()

        return Response({"detail": f"Category '{category.name}' deleted successfully."}, status=status.HTTP_200_OK)


# ==============================================================================
# 7. CUSTOMER ADMINISTRATION VIEWS (STRICTLY READ-ONLY)
# ==============================================================================

class AdminCustomerListAPIView(APIView):
    """
    GET /api/admin/customers/
    Read-only listing of customers for administrative inspection.
    Excludes sensitive credentials (passwords, hashes, tokens).
    """
    permission_classes = [IsAuthenticated, CanViewAdminCustomers]

    def get(self, request):
        qs = CustomerProfile.objects.select_related("user").all().order_by("-created_at")

        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(user__username__icontains=search)
                | Q(user__email__icontains=search)
                | Q(display_name__icontains=search)
                | Q(phone__icontains=search)
            )

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AdminCustomerListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class AdminCustomerDetailAPIView(APIView):
    """
    GET /api/admin/customers/<int:pk>/
    Read-only detail view of a customer profile.
    Strictly forbids direct tampering with orders, totals, payments, or point balances.
    """
    permission_classes = [IsAuthenticated, CanViewAdminCustomers]

    def get(self, request, pk):
        try:
            customer = CustomerProfile.objects.select_related("user").get(pk=pk)
        except CustomerProfile.DoesNotExist:
            raise NotFound("Customer profile not found.")
        serializer = AdminCustomerDetailSerializer(customer)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminMetricsAPIView(APIView):
    """
    GET /api/admin/metrics/
    Returns aggregated platform metrics for the Next.js management console:
    - total_orders: platform-wide order count
    - total_revenue: platform-wide revenue from completed/paid transactions (৳)
    - pending_shops: shops awaiting approval
    - pending_sellers: seller applications awaiting verification
    - total_shops: total registered shops
    - total_sellers: total registered sellers
    - total_products: total active product catalog
    Enforces strict management role or admin:access permission.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role_codes = get_user_role_codes(user)
        is_management = (
            user.is_superuser
            or user.is_staff
            or bool(
                role_codes.intersection(
                    {
                        Role.ROLE_SUPER_ADMINISTRATOR,
                        Role.ROLE_ADMINISTRATOR,
                        Role.ROLE_OPERATION_MANAGER,
                        Role.ROLE_SALES_MANAGER,
                        Role.ROLE_SALES_TEAM,
                        Role.ROLE_FINANCE,
                        Role.ROLE_SUPPORT_TEAM,
                    }
                )
            )
            or has_user_permission(user, "admin:access")
        )
        if not is_management:
            raise PermissionDenied("You do not have management portal permissions.")

        return Response(get_console_metrics(), status=status.HTTP_200_OK)


# ==============================================================================
# 9. AUDIT LOG ADMINISTRATION VIEWS
# ==============================================================================

class AdminAuditLogListAPIView(APIView):
    """
    GET /api/admin/audit-logs/
    Read-only, paginated, searchable, and filterable audit log stream for platform governance.
    Strictly forbids mutations (POST, PUT, PATCH, DELETE).
    Returns real AuditLog database records, newest first.
    """
    permission_classes = [IsAuthenticated, CanViewAdminAuditLogs]
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        qs = AuditLog.objects.select_related("actor", "shop", "seller").all().order_by("-created_at")

        # 1. Action filter
        action = request.query_params.get("action", "").strip()
        if action:
            qs = qs.filter(action__icontains=action)

        # 2. Resource / Target Type filter
        resource_type = request.query_params.get("resource_type") or request.query_params.get("target_type")
        if resource_type:
            qs = qs.filter(target_type__iexact=resource_type.strip())

        # 3. Resource / Target ID filter
        resource_id = request.query_params.get("resource_id") or request.query_params.get("target_id")
        if resource_id:
            qs = qs.filter(target_id=str(resource_id).strip())

        # 4. Actor filter (by user ID or username/email)
        actor_param = request.query_params.get("actor", "").strip()
        if actor_param:
            if actor_param.isdigit():
                qs = qs.filter(actor_id=int(actor_param))
            else:
                qs = qs.filter(
                    Q(actor__username__icontains=actor_param)
                    | Q(actor__email__icontains=actor_param)
                )

        # 5. Shop / Seller context filters
        shop_id = request.query_params.get("shop_id")
        if shop_id and str(shop_id).isdigit():
            qs = qs.filter(shop_id=int(shop_id))

        seller_id = request.query_params.get("seller_id")
        if seller_id and str(seller_id).isdigit():
            qs = qs.filter(seller_id=int(seller_id))

        # 6. General Search
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(action__icontains=search)
                | Q(target_type__icontains=search)
                | Q(target_repr__icontains=search)
                | Q(actor__username__icontains=search)
                | Q(actor__email__icontains=search)
            )

        # 7. Date range filters
        start_date = request.query_params.get("start_date", "").strip()
        if start_date:
            qs = qs.filter(created_at__date__gte=start_date)

        end_date = request.query_params.get("end_date", "").strip()
        if end_date:
            qs = qs.filter(created_at__date__lte=end_date)

        paginator = AdminPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = AdminAuditLogSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)



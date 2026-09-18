from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import AuditService
from audit.utils import get_client_ip

from .models import SellerProfile
from .permissions import (
    CanApproveSeller,
    CanSuspendSeller,
    CanViewSellers,
    IsOperationalSeller,
    IsSellerOwner,
)
from .serializers import (
    SellerActionReasonSerializer,
    SellerProfileSerializer,
    SellerProfileUpdateSerializer,
    SellerRegistrationSerializer,
)
from .services import (
    approve_seller,
    get_seller_capabilities,
    reactivate_seller,
    reject_seller,
    suspend_seller,
)


class SellerRegistrationView(generics.CreateAPIView):
    """
    Allows an authenticated user to submit an application for a seller account.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SellerRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        seller = serializer.save()
        output_serializer = SellerProfileSerializer(seller)
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


class SellerMeView(generics.RetrieveUpdateAPIView):
    """
    Allows a seller to inspect or update their own profile.
    Sellers cannot modify profiles belonging to other users.
    """
    permission_classes = [permissions.IsAuthenticated, IsSellerOwner]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return SellerProfileUpdateSerializer
        return SellerProfileSerializer

    def get_object(self):
        try:
            seller = self.request.user.seller_profile
        except SellerProfile.DoesNotExist:
            raise PermissionDenied("You do not have a seller profile.")
        self.check_object_permissions(self.request, seller)
        return seller


class SellerDashboardView(APIView):
    """
    Authenticated dashboard endpoint providing status, capabilities, and health metrics.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            seller = request.user.seller_profile
        except SellerProfile.DoesNotExist:
            return Response(
                {"detail": "No seller profile associated with this account.", "has_seller_profile": False},
                status=status.HTTP_404_NOT_FOUND,
            )

        capabilities = get_seller_capabilities(seller)
        profile_data = SellerProfileSerializer(seller).data

        dashboard_data = {
            "has_seller_profile": True,
            "seller": profile_data,
            "capabilities": capabilities,
            "status": seller.status,
            "is_operational": seller.is_operational,
            "is_suspended": seller.is_suspended,
        }

        if seller.is_suspended:
            dashboard_data["warning"] = f"Account suspended: {seller.suspension_reason}"
        elif seller.status in (SellerProfile.STATUS_PENDING, SellerProfile.STATUS_UNDER_REVIEW):
            dashboard_data["info"] = "Application is currently pending review by staff."
        elif seller.status == SellerProfile.STATUS_REJECTED:
            dashboard_data["warning"] = f"Application rejected: {seller.rejection_reason}"

        return Response(dashboard_data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Staff / Administrative Endpoints (Enforced through RBAC)
# ---------------------------------------------------------------------------

class SellerListView(generics.ListAPIView):
    """
    Staff directory listing all registered sellers with status/type filtering.
    Requires 'sellers.view' RBAC permission.
    """
    permission_classes = [CanViewSellers]
    serializer_class = SellerProfileSerializer

    def get_queryset(self):
        queryset = SellerProfile.objects.select_related("user").order_by("-created_at")
        status_param = self.request.query_params.get("status")
        seller_type_param = self.request.query_params.get("seller_type")
        q = self.request.query_params.get("q")

        if status_param:
            queryset = queryset.filter(status=status_param.upper())
        if seller_type_param:
            queryset = queryset.filter(seller_type=seller_type_param.upper())
        if q:
            queryset = queryset.filter(business_name__icontains=q.strip())

        return queryset


class SellerDetailView(generics.RetrieveAPIView):
    """
    Staff detail view for a specific seller.
    Requires 'sellers.view' RBAC permission.
    """
    permission_classes = [CanViewSellers]
    serializer_class = SellerProfileSerializer
    queryset = SellerProfile.objects.select_related("user")


class SellerApproveView(APIView):
    """
    Staff approval endpoint for seller applications.
    Requires 'sellers.approve' RBAC permission.
    """
    permission_classes = [CanApproveSeller]

    def post(self, request, pk):
        with transaction.atomic():
            seller = get_object_or_404(SellerProfile, pk=pk)
            previous_state = {"status": seller.status}
            approve_seller(seller, request.user)
            AuditService.log(
                action="ADMIN_SELLER_APPROVE",
                target=seller,
                actor=request.user,
                seller=seller,
                previous_state=previous_state,
                new_state={"status": seller.status},
                ip_address=get_client_ip(request),
            )
        return Response(
            {"message": f"Seller '{seller.business_name}' approved successfully.", "seller": SellerProfileSerializer(seller).data},
            status=status.HTTP_200_OK,
        )


class SellerRejectView(APIView):
    """
    Staff rejection endpoint for seller applications.
    Requires 'sellers.approve' RBAC permission and non-empty reason.
    """
    permission_classes = [CanApproveSeller]

    def post(self, request, pk):
        seller = get_object_or_404(SellerProfile, pk=pk)
        serializer = SellerActionReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data["reason"]

        with transaction.atomic():
            previous_state = {"status": seller.status}
            reject_seller(seller, request.user, reason)
            AuditService.log(
                action="ADMIN_SELLER_REJECT",
                target=seller,
                actor=request.user,
                seller=seller,
                reason=reason,
                previous_state=previous_state,
                new_state={"status": seller.status},
                ip_address=get_client_ip(request),
            )
        return Response(
            {"message": f"Seller '{seller.business_name}' rejected.", "seller": SellerProfileSerializer(seller).data},
            status=status.HTTP_200_OK,
        )


class SellerSuspendView(APIView):
    """
    Staff suspension endpoint for active sellers.
    Requires 'sellers.suspend' RBAC permission and non-empty reason.
    """
    permission_classes = [CanSuspendSeller]

    def post(self, request, pk):
        seller = get_object_or_404(SellerProfile, pk=pk)
        serializer = SellerActionReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data["reason"]

        with transaction.atomic():
            previous_state = {"status": seller.status}
            suspend_seller(seller, request.user, reason)
            AuditService.log(
                action="ADMIN_SELLER_SUSPEND",
                target=seller,
                actor=request.user,
                seller=seller,
                reason=reason,
                previous_state=previous_state,
                new_state={"status": seller.status},
                ip_address=get_client_ip(request),
            )
        return Response(
            {"message": f"Seller '{seller.business_name}' suspended.", "seller": SellerProfileSerializer(seller).data},
            status=status.HTTP_200_OK,
        )


class SellerReactivateView(APIView):
    """
    Staff reactivation endpoint for suspended sellers.
    Requires 'sellers.suspend' RBAC permission.
    """
    permission_classes = [CanSuspendSeller]

    def post(self, request, pk):
        seller = get_object_or_404(SellerProfile, pk=pk)
        if not seller.is_suspended:
            raise ValidationError("Only suspended sellers can be reactivated.")

        with transaction.atomic():
            previous_state = {"status": seller.status}
            reactivate_seller(seller, request.user)
            AuditService.log(
                action="ADMIN_SELLER_REACTIVATE",
                target=seller,
                actor=request.user,
                seller=seller,
                previous_state=previous_state,
                new_state={"status": seller.status},
                ip_address=get_client_ip(request),
            )
        return Response(
            {"message": f"Seller '{seller.business_name}' reactivated.", "seller": SellerProfileSerializer(seller).data},
            status=status.HTTP_200_OK,
        )

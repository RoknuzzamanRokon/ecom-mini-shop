from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Shop
from .permissions import (
    CanApproveShops,
    CanViewStaffShops,
    IsEligibleShopSeller,
    IsShopOwner,
)
from .serializers import (
    PublicShopSerializer,
    SellerShopCreateSerializer,
    SellerShopSerializer,
    SellerShopUpdateSerializer,
    ShopActionReasonSerializer,
    StaffShopSerializer,
)
from .services import (
    IneligibleSellerError,
    InvalidShopTransitionError,
    ShopError,
    ShopLimitExceededError,
    ShopService,
)


# ---------------------------------------------------------------------------
# Public Views (Anonymous / Customer)
# ---------------------------------------------------------------------------

class PublicShopListView(generics.ListAPIView):
    """
    Public listing of approved/active shops.
    Supports '?q=' query to search by name, description, or address.
    Draft, pending, suspended, and rejected shops are strictly excluded.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicShopSerializer

    def get_queryset(self):
        queryset = Shop.objects.filter(
            status__in=[Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE]
        ).order_by("-created_at")

        q = self.request.query_params.get("q")
        if q:
            term = q.strip()
            queryset = queryset.filter(
                Q(name__icontains=term)
                | Q(description__icontains=term)
                | Q(address__icontains=term)
                | Q(location__icontains=term)
            )

        return queryset


class PublicShopDetailView(generics.RetrieveAPIView):
    """
    Public retrieval of an active/approved shop by slug.
    Returns 404 for any shop that is not APPROVED or ACTIVE.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicShopSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return Shop.objects.filter(
            status__in=[Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE]
        )


# ---------------------------------------------------------------------------
# Seller Self-Service Views
# ---------------------------------------------------------------------------

class SellerShopListView(generics.ListAPIView):
    """
    Lists shops owned by the authenticated seller.
    """
    permission_classes = [permissions.IsAuthenticated, IsEligibleShopSeller]
    serializer_class = SellerShopSerializer

    def get_queryset(self):
        return Shop.objects.filter(owner=self.request.user.seller_profile)


class SellerShopCreateView(APIView):
    """
    Allows an eligible seller (FULL_SHOP_OWNER, LIMITED_SHOP_OWNER) to create a shop.
    Rejects PRODUCT_OWNER sellers and suspended sellers.
    """
    permission_classes = [permissions.IsAuthenticated, IsEligibleShopSeller]

    def post(self, request):
        serializer = SellerShopCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            shop = ShopService.create_shop(
                seller=request.user.seller_profile,
                name=data["name"],
                description=data.get("description", ""),
                phone=data.get("phone", ""),
                address=data.get("address", ""),
                location=data.get("location", ""),
                logo=request.FILES.get("logo") or data.get("logo"),
                cover_image=request.FILES.get("cover_image") or data.get("cover_image"),
                submit_for_review=data.get("submit_for_review", False),
            )
        except (IneligibleSellerError, ShopLimitExceededError) as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except ShopError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(SellerShopSerializer(shop).data, status=status.HTTP_201_CREATED)


class SellerShopDetailView(generics.RetrieveAPIView):
    """
    Retrieves full details for a shop owned by the authenticated seller.
    """
    permission_classes = [permissions.IsAuthenticated, IsShopOwner]
    serializer_class = SellerShopSerializer
    queryset = Shop.objects.all()

    def get_object(self):
        obj = get_object_or_404(Shop, pk=self.kwargs["pk"])
        self.check_object_permissions(self.request, obj)
        return obj


class SellerShopUpdateView(generics.UpdateAPIView):
    """
    Updates profile details of an owned shop.
    """
    permission_classes = [permissions.IsAuthenticated, IsShopOwner]
    serializer_class = SellerShopUpdateSerializer
    queryset = Shop.objects.all()

    def get_object(self):
        obj = get_object_or_404(Shop, pk=self.kwargs["pk"])
        self.check_object_permissions(self.request, obj)
        return obj

    def perform_update(self, serializer):
        shop = self.get_object()
        seller = self.request.user.seller_profile
        try:
            ShopService.update_shop(shop, seller, **serializer.validated_data)
        except IneligibleSellerError as e:
            raise PermissionDenied(str(e))


class SellerShopSubmitView(APIView):
    """
    Transitions a DRAFT or REJECTED shop to PENDING review by staff.
    """
    permission_classes = [permissions.IsAuthenticated, IsShopOwner]

    def post(self, request, pk):
        shop = get_object_or_404(Shop, pk=pk)
        self.check_object_permissions(request, shop)

        try:
            shop = ShopService.submit_for_review(shop, request.user.seller_profile)
        except InvalidShopTransitionError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except IneligibleSellerError as e:
            raise PermissionDenied(str(e))

        return Response(
            {"message": f"Shop '{shop.name}' submitted for staff review.", "shop": SellerShopSerializer(shop).data},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Staff / Administrative Endpoints (RBAC-enforced)
# ---------------------------------------------------------------------------

class StaffShopListView(generics.ListAPIView):
    """
    Lists all shops across all lifecycle states.
    Requires 'shops.view' RBAC permission.
    """
    permission_classes = [CanViewStaffShops]
    serializer_class = StaffShopSerializer

    def get_queryset(self):
        queryset = Shop.objects.select_related("owner", "owner__user", "reviewed_by").order_by("-created_at")
        status_filter = self.request.query_params.get("status")
        q = self.request.query_params.get("q")

        if status_filter:
            queryset = queryset.filter(status=status_filter.upper().strip())
        if q:
            term = q.strip()
            queryset = queryset.filter(
                Q(name__icontains=term)
                | Q(owner__business_name__icontains=term)
                | Q(owner__user__username__icontains=term)
            )

        return queryset


class StaffShopDetailView(generics.RetrieveAPIView):
    """
    Inspects full administrative shop details.
    Requires 'shops.view' RBAC permission.
    """
    permission_classes = [CanViewStaffShops]
    serializer_class = StaffShopSerializer
    queryset = Shop.objects.select_related("owner", "owner__user", "reviewed_by")


class StaffShopApproveView(APIView):
    """
    Approves and activates a pending shop.
    Requires 'shops.approve' RBAC permission.
    """
    permission_classes = [CanApproveShops]

    def post(self, request, pk):
        shop = get_object_or_404(Shop, pk=pk)
        try:
            ShopService.approve_shop(shop, request.user)
        except InvalidShopTransitionError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"message": f"Shop '{shop.name}' approved and activated successfully.", "shop": StaffShopSerializer(shop).data},
            status=status.HTTP_200_OK,
        )


class StaffShopRejectView(APIView):
    """
    Rejects a pending shop with mandatory reason.
    Requires 'shops.approve' RBAC permission.
    """
    permission_classes = [CanApproveShops]

    def post(self, request, pk):
        shop = get_object_or_404(Shop, pk=pk)
        serializer = ShopActionReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data["reason"]

        try:
            ShopService.reject_shop(shop, request.user, reason)
        except InvalidShopTransitionError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"message": f"Shop '{shop.name}' rejected.", "shop": StaffShopSerializer(shop).data},
            status=status.HTTP_200_OK,
        )


class StaffShopSuspendView(APIView):
    """
    Suspends an active shop with mandatory reason.
    Requires 'shops.approve' RBAC permission.
    """
    permission_classes = [CanApproveShops]

    def post(self, request, pk):
        shop = get_object_or_404(Shop, pk=pk)
        serializer = ShopActionReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data["reason"]

        try:
            ShopService.suspend_shop(shop, request.user, reason)
        except InvalidShopTransitionError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"message": f"Shop '{shop.name}' suspended.", "shop": StaffShopSerializer(shop).data},
            status=status.HTTP_200_OK,
        )


class StaffShopReactivateView(APIView):
    """
    Reactivates a suspended shop back to ACTIVE.
    Requires 'shops.approve' RBAC permission.
    """
    permission_classes = [CanApproveShops]

    def post(self, request, pk):
        shop = get_object_or_404(Shop, pk=pk)
        try:
            ShopService.reactivate_shop(shop, request.user)
        except InvalidShopTransitionError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"message": f"Shop '{shop.name}' reactivated.", "shop": StaffShopSerializer(shop).data},
            status=status.HTTP_200_OK,
        )

from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from customers.models import ShopReview
from customers.serializers import ShopReviewSerializer
from customers.services import review_ordering
from .models import Shop
from .permissions import (
    CanApproveShops,
    CanViewStaffShops,
    IsEligibleShopSeller,
    IsShopOwner,
)
from .serializers import (
    NearbyShopSerializer,
    PublicShopDetailSerializer,
    PublicShopSerializer,
    SellerShopSerializer,
    SellerShopUpdateSerializer,
    ShopActionReasonSerializer,
    ShopLocationUpdateSerializer,
    StaffShopSerializer,
)
from .services import (
    IneligibleSellerError,
    InvalidShopTransitionError,
    ShopService,
    validate_coordinates,
    validate_radius,
)


# ---------------------------------------------------------------------------
# Public Views (Anonymous / Customer)
# ---------------------------------------------------------------------------

class PublicShopListView(generics.ListAPIView):
    """
    Public listing of approved/active shops.
    Supports '?q=' query to search by name, description, or address, and
    '?ordering=-rating' (alias 'rating_desc') for top rated first; anything
    else lists newest first.
    Draft, pending, suspended, and rejected shops are strictly excluded.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicShopSerializer

    # Unrated shops have a NULL average and sort last; equal averages go to the
    # shop with more reviews, then the newest.
    TOP_RATED = (F("average_rating").desc(nulls_last=True), "-review_count", "-created_at")

    def get_queryset(self):
        queryset = ShopService.get_public_shops_queryset()

        q = self.request.query_params.get("q")
        if q:
            term = q.strip()
            queryset = queryset.filter(
                Q(name__icontains=term)
                | Q(description__icontains=term)
                | Q(address__icontains=term)
            )

        if self.request.query_params.get("ordering") in ("-rating", "rating_desc"):
            return queryset.order_by(*self.TOP_RATED)
        return queryset.order_by("-created_at")


class PublicNearbyShopListView(APIView):
    """
    Public nearby search for approved/active shops within a given radius in kilometers.
    Query parameters:
      - lat: float (latitude: [-90, 90])
      - lng: float (longitude: [-180, 180])
      - radius: float (kilometers: > 0, max 1000)
    Results are sorted nearest to farthest via MySQL ST_Distance_Sphere.
    Draft, pending, suspended, and rejected shops are strictly excluded.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        lat = request.query_params.get("lat")
        lng = request.query_params.get("lng")
        radius = request.query_params.get("radius")

        if lat is None or lng is None or radius is None:
            return Response(
                {"error": "Missing required query parameters: 'lat', 'lng', and 'radius' are all required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            shops = ShopService.get_nearby_shops(latitude=lat, longitude=lng, radius_km=radius)
            data = NearbyShopSerializer(shops, many=True).data
            return Response({
                "count": len(data),
                "results": data,
            }, status=status.HTTP_200_OK)
        except ValidationError as e:
            msg = e.message if hasattr(e, "message") else str(e)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PublicShopDetailView(generics.RetrieveAPIView):
    """
    Public retrieval of an active/approved shop by slug.
    Returns 404 for any shop that is not APPROVED or ACTIVE.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = PublicShopDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return ShopService.get_public_shops_queryset()


class PublicShopReviewListView(generics.ListAPIView):
    """
    Public listing of customer reviews for a single shop.
    GET /api/shops/<slug>/reviews/?ordering=newest|oldest|highest|lowest
    404s for shops that are not APPROVED/ACTIVE, exactly like PublicShopDetailView.
    Unknown ordering values fall back to newest first.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = ShopReviewSerializer

    def get_queryset(self):
        shop = get_object_or_404(
            Shop,
            slug=self.kwargs["slug"],
            status__in=[Shop.STATUS_APPROVED, Shop.STATUS_ACTIVE],
        )
        return (
            ShopReview.objects.visible()
            .filter(shop=shop)
            .select_related("user__customer_profile")
            .order_by(*review_ordering(self.request.query_params.get("ordering")))
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
    Shops are no longer self-service. Under the Admin-created Shop Owner
    model, a Shop is always created by an administrator (see
    AdminShopListAPIView.post in shop/admin_views.py) with the owning
    SellerProfile assigned at creation time. This endpoint is kept in place
    (rather than removed from urls.py) so any direct API call — not just the
    removed frontend button — gets an explicit, authoritative 403 instead of
    a bare 404 that could look like a routing bug.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        raise PermissionDenied(
            "Shops are created and assigned by platform administrators. "
            "Contact an administrator to have a shop assigned to your account."
        )


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


class SellerShopLocationUpdateView(APIView):
    """
    Allows an authenticated seller to update their own shop's geographic coordinates.
    Requires seller ownership and operational seller status.
    """
    permission_classes = [permissions.IsAuthenticated, IsShopOwner]

    def patch(self, request, pk):
        return self._update_location(request, pk)

    def put(self, request, pk):
        return self._update_location(request, pk)

    def _update_location(self, request, pk):
        shop = get_object_or_404(Shop, pk=pk)
        self.check_object_permissions(request, shop)

        serializer = ShopLocationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            shop = ShopService.update_shop_location(
                shop=shop,
                seller=request.user.seller_profile,
                latitude=serializer.validated_data["latitude"],
                longitude=serializer.validated_data["longitude"],
            )
        except IneligibleSellerError as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except PermissionDenied as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except ValidationError as e:
            msg = e.message if hasattr(e, "message") else str(e)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "Shop location updated successfully.",
                "shop": SellerShopSerializer(shop).data,
            },
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

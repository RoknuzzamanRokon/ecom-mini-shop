"""
/api/onboarding/: field onboarding for the Sales Team (sellers.onboard), and
the review queue where staff approve an onboarding in one step.

An onboarder only ever reaches the sellers they onboarded: every lookup is
scoped to OnboardingService.sellers_of(request.user), so another seller's id
answers 404, not 403.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import AuditService
from audit.utils import get_client_ip
from points.services import InsufficientPointsError, InsufficientStaffPointsError, PointService
from sellers.services import reject_seller
from shop.models import Product
from shop.serializers import SellerProductCreateSerializer
from shop.services import IneligibleSellerError, ProductLimitExceededError, ProductOwnershipError
from shops.models import Shop
from shops.services import IneligibleSellerError as IneligibleShopSellerError
from shops.services import ShopLimitExceededError
from .models import OnboardingSettings, TokenTransaction, TokenWallet
from .permissions import CanApproveOnboarding, CanOnboardSellers
from .serializers import (
    OnboardedProductSerializer,
    OnboardedSellerDetailSerializer,
    OnboardedSellerSerializer,
    OnboardedShopSerializer,
    OnboardingShopSerializer,
    OnboardSellerSerializer,
    TokenTransactionSerializer,
)
from .services import OnboardingError, OnboardingService, TokenService


def django_errors(exc: DjangoValidationError) -> ValidationError:
    return ValidationError(exc.message_dict if hasattr(exc, "message_dict") else {"detail": " ".join(exc.messages)})


def refused(exc: Exception) -> ValidationError:
    """A domain rule said no: 400 with the rule's own message as `detail`."""
    return ValidationError({"detail": str(exc)})


def with_counts(sellers):
    """The list columns: account, onboarder, onboarding record, shop and product counts."""
    return sellers.select_related("user", "user__login_phone", "created_by", "onboarding").annotate(
        shop_count=Count("shops", distinct=True),
        product_count=Count("shops__products", distinct=True),
    )


def with_catalog(sellers):
    """with_counts() plus every shop and its products, for a detail page."""
    products = Product.objects.select_related("category").order_by("created_at", "pk")
    shops = Shop.objects.order_by("created_at", "pk").prefetch_related(Prefetch("products", queryset=products))
    return with_counts(sellers).prefetch_related(Prefetch("shops", queryset=shops))


def detail_response(seller, request, status_code=status.HTTP_200_OK):
    seller.points_balance = PointService.get_balance(seller)
    return Response(OnboardedSellerDetailSerializer(seller, context={"request": request}).data, status=status_code)


# ---------------------------------------------------------------------------
# The onboarder's side
# ---------------------------------------------------------------------------

class OnboardingSummaryView(APIView):
    """
    GET /api/onboarding/me/
    The onboarder's points (what they can still give to new sellers), tokens,
    what one onboarding costs and earns, and their sellers counted by state.
    """
    permission_classes = [IsAuthenticated, CanOnboardSellers]

    def get(self, request):
        return Response(OnboardingService.summary(request.user))


class OnboardedSellerListCreateView(generics.ListAPIView):
    """
    GET  /api/onboarding/sellers/        the caller's onboarded sellers (?status=)
    POST /api/onboarding/sellers/        open a seller account

    POST takes `account` (username, email and/or phone, password,
    password_confirm, first_name, last_name) and the business fields of
    POST /api/admin/sellers/. It moves OnboardingSettings.starting_points from
    the caller's wallet to the new seller and credits the caller's tokens;
    400 with `required_points` and `available_points` when the wallet holds
    too few.
    """
    permission_classes = [IsAuthenticated, CanOnboardSellers]
    serializer_class = OnboardedSellerSerializer

    def get_queryset(self):
        sellers = OnboardingService.sellers_of(self.request.user)
        wanted = self.request.query_params.get("status")
        if wanted:
            sellers = sellers.filter(status__iexact=wanted.strip())
        return with_counts(sellers)

    def post(self, request):
        serializer = OnboardSellerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        account = data.pop("account")
        try:
            seller = OnboardingService.onboard_seller(
                request.user, account=account, seller_fields=data, ip_address=get_client_ip(request)
            )
        except InsufficientStaffPointsError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "required_points": OnboardingSettings.current().starting_points,
                    "available_points": PointService.get_staff_balance(request.user),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DjangoValidationError as exc:
            raise django_errors(exc)
        seller = get_object_or_404(with_catalog(OnboardingService.sellers_of(request.user)), pk=seller.pk)
        return detail_response(seller, request, status.HTTP_201_CREATED)


class OnboardedSellerDetailView(APIView):
    """GET /api/onboarding/sellers/<pk>/: one of the caller's sellers, with its shops and products."""
    permission_classes = [IsAuthenticated, CanOnboardSellers]

    def get(self, request, pk):
        seller = get_object_or_404(with_catalog(OnboardingService.sellers_of(request.user)), pk=pk)
        return detail_response(seller, request)


class OnboardedShopCreateView(APIView):
    """
    POST /api/onboarding/sellers/<pk>/shops/
    Adds a shop for one of the caller's sellers, submitted for review: the
    fields of POST /api/admin/shops/, latitude and longitude included. Allowed
    while the seller awaits approval or is live; a Limited Shop Owner gets one.
    """
    permission_classes = [IsAuthenticated, CanOnboardSellers]

    def post(self, request, pk):
        seller = get_object_or_404(OnboardingService.sellers_of(request.user), pk=pk)
        serializer = OnboardingShopSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            shop = OnboardingService.add_shop(
                request.user, seller, ip_address=get_client_ip(request), **serializer.validated_data
            )
        except (IneligibleShopSellerError, ShopLimitExceededError) as exc:
            raise refused(exc)
        except DjangoValidationError as exc:
            raise django_errors(exc)
        return Response(OnboardedShopSerializer(shop, context={"request": request}).data, status=status.HTTP_201_CREATED)


class OnboardedProductCreateView(APIView):
    """
    POST /api/onboarding/shops/<pk>/products/ (multipart for the `image`)
    Adds a product to a shop of one of the caller's sellers, with the fields
    of POST /api/products/mine/. The seller's wallet pays the creation fee:
    400 with `required_points` and `available_points` when it cannot. The
    product starts SUBMITTED and goes live when the onboarding is approved.
    """
    permission_classes = [IsAuthenticated, CanOnboardSellers]

    def post(self, request, pk):
        shop = get_object_or_404(
            Shop.objects.select_related("owner").filter(owner__in=OnboardingService.sellers_of(request.user)), pk=pk
        )
        serializer = SellerProductCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            product = OnboardingService.add_product(
                request.user,
                shop,
                data,
                image=request.FILES.get("image") or data.get("image"),
                ip_address=get_client_ip(request),
            )
        except InsufficientPointsError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "required_points": PointService.get_product_creation_cost(),
                    "available_points": PointService.get_balance(shop.owner),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (IneligibleSellerError, ProductOwnershipError, ProductLimitExceededError) as exc:
            raise refused(exc)
        except DjangoValidationError as exc:
            raise django_errors(exc)
        return Response(
            OnboardedProductSerializer(product, context={"request": request}).data, status=status.HTTP_201_CREATED
        )


class TokenHistoryView(generics.ListAPIView):
    """GET /api/onboarding/tokens/: the caller's token balance and movements, newest first."""
    permission_classes = [IsAuthenticated, CanOnboardSellers]
    serializer_class = TokenTransactionSerializer

    def get_queryset(self):
        wallet = TokenWallet.objects.filter(user=self.request.user).first()
        if wallet is None:
            return TokenTransaction.objects.none()
        return wallet.transactions.select_related("seller").order_by("-created_at", "-pk")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data["balance"] = TokenService.get_balance(request.user)
        return response


# ---------------------------------------------------------------------------
# The reviewer's side
# ---------------------------------------------------------------------------

class OnboardingReviewListView(generics.ListAPIView):
    """GET /api/onboarding/review/: onboarded sellers awaiting approval, oldest first."""
    permission_classes = [IsAuthenticated, CanApproveOnboarding]
    serializer_class = OnboardedSellerSerializer

    def get_queryset(self):
        return with_counts(OnboardingService.awaiting_approval())


class OnboardingReviewDetailView(APIView):
    """GET /api/onboarding/review/<pk>/: any onboarded seller, with its shops and products."""
    permission_classes = [IsAuthenticated, CanApproveOnboarding]

    def get(self, request, pk):
        seller = get_object_or_404(with_catalog(OnboardingService.onboarded_sellers()), pk=pk)
        return detail_response(seller, request)


class OnboardingApproveView(APIView):
    """
    POST /api/onboarding/review/<pk>/approve/
    Approves the seller, its waiting shops and its submitted products in one
    step, so they go live together. 400 unless the seller awaits approval.
    """
    permission_classes = [IsAuthenticated, CanApproveOnboarding]

    def post(self, request, pk):
        seller = get_object_or_404(OnboardingService.onboarded_sellers(), pk=pk)
        try:
            result = OnboardingService.approve(seller, request.user, ip_address=get_client_ip(request))
        except OnboardingError as exc:
            raise refused(exc)
        except DjangoValidationError as exc:
            raise django_errors(exc)
        response = detail_response(get_object_or_404(with_catalog(OnboardingService.onboarded_sellers()), pk=pk), request)
        response.data.update(result)
        return response


class OnboardingRejectView(APIView):
    """
    POST /api/onboarding/review/<pk>/reject/ {"reason": "..."}
    Rejects the seller, which returns its starting points to the onboarder
    and takes back the onboarder's tokens (OnboardingService.reverse_rewards).
    The same as rejecting it in the Console; offered here beside approve.
    """
    permission_classes = [IsAuthenticated, CanApproveOnboarding]

    def post(self, request, pk):
        reason = str(request.data.get("reason") or "").strip()
        if not reason:
            raise ValidationError({"reason": "A reason is required to reject a seller."})
        with transaction.atomic():
            seller = get_object_or_404(OnboardingService.onboarded_sellers().select_for_update(), pk=pk)
            previous_status = seller.status
            try:
                reject_seller(seller, request.user, reason)
            except DjangoValidationError as exc:
                raise django_errors(exc)
            AuditService.log(
                action="ADMIN_SELLER_REJECT",
                target=seller,
                actor=request.user,
                seller=seller,
                reason=reason,
                previous_state={"status": previous_status},
                new_state={"status": seller.status},
                ip_address=get_client_ip(request),
            )
        return detail_response(get_object_or_404(with_catalog(OnboardingService.onboarded_sellers()), pk=pk), request)

"""
/api/onboarding/: field onboarding for the Sales Team (sellers.onboard), and
the review queue where staff approve an onboarding in one step.

An onboarder only ever reaches the sellers they onboarded: every lookup is
scoped to OnboardingService.sellers_of(request.user), so another seller's id
answers 404, not 403. Of those sellers' products they reach only the ones
they added (OnboardingService.products_of), and only with
'onboarding.products.view'. Edits need an open EditSession: 403 with
`code: "edit_session_required"` without one.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, IntegerField, Prefetch, Q, Value
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import AuditService
from audit.utils import get_client_ip
from points.services import (
    InsufficientPointsError,
    InsufficientStaffPointsError,
    InvalidAmountError,
    PointService,
)
from sellers.services import reject_seller
from shop.admin_serializers import validate_additional_phones
from shop.listing_service import ListingError
from shop.models import Product
from shop.serializers import SellerProductCreateSerializer
from shop.services import (
    IneligibleSellerError,
    ProductLimitExceededError,
    ProductOwnershipError,
    StockConflictError,
)
from shops.models import Shop
from shops.services import IneligibleSellerError as IneligibleShopSellerError
from shops.services import ShopLimitExceededError, validate_coordinates
from .models import OnboardingSettings, TokenPayoutRequest, TokenTransaction, TokenWallet
from .permissions import (
    CanApproveOnboarding,
    CanOnboardSellers,
    CanSettleTokenPayouts,
    CanViewOnboardedProducts,
    can_view_onboarded_products,
)
from .serializers import (
    EditCodeSerializer,
    OnboardedProductDetailSerializer,
    OnboardedProductSerializer,
    OnboardedSellerDetailSerializer,
    OnboardedSellerSerializer,
    OnboardedShopSerializer,
    OnboardingProductUpdateSerializer,
    OnboardingSellerUpdateSerializer,
    OnboardingShopSerializer,
    OnboardingShopUpdateSerializer,
    OnboardSellerSerializer,
    PayoutAcceptSerializer,
    PayoutRejectSerializer,
    PayoutRequestSerializer,
    PointSaleSerializer,
    TokenPayoutSerializer,
    TokenTransactionSerializer,
)
from .services import (
    EditCodeTooSoon,
    EditSessionError,
    EditSessionRequired,
    EditSessionService,
    OnboardingError,
    OnboardingService,
    PayoutError,
    TokenService,
)


def django_errors(exc: DjangoValidationError) -> ValidationError:
    return ValidationError(exc.message_dict if hasattr(exc, "message_dict") else {"detail": " ".join(exc.messages)})


def refused(exc: Exception) -> ValidationError:
    """A domain rule said no: 400 with the rule's own message as `detail`."""
    return ValidationError({"detail": str(exc)})


def edit_session_required(exc: EditSessionRequired) -> PermissionDenied:
    return PermissionDenied({"detail": str(exc), "code": "edit_session_required"})


def with_counts(sellers, onboarder=None):
    """
    The list columns: account, onboarder, onboarding record, shop and product
    counts. For an `onboarder`, products are the ones they added, and none
    (a null count) without 'onboarding.products.view'.
    """
    sellers = sellers.select_related("user", "user__login_phone", "created_by", "onboarding").annotate(
        shop_count=Count("shops", distinct=True),
    )
    if onboarder is None:
        return sellers.annotate(product_count=Count("shops__products", distinct=True))
    if not can_view_onboarded_products(onboarder):
        return sellers.annotate(product_count=Value(None, output_field=IntegerField()))
    return sellers.annotate(
        product_count=Count("shops__products", filter=Q(shops__products__onboarded_by=onboarder), distinct=True)
    )


def with_catalog(sellers, onboarder=None):
    """with_counts() plus every shop and its products, for a detail page."""
    products = Product.objects.select_related("category").order_by("created_at", "pk")
    if onboarder is not None:
        if can_view_onboarded_products(onboarder):
            products = products.filter(onboarded_by=onboarder)
        else:
            products = products.none()
    shops = Shop.objects.order_by("created_at", "pk").prefetch_related(Prefetch("products", queryset=products))
    return with_counts(sellers, onboarder).prefetch_related(Prefetch("shops", queryset=shops))


def detail_response(seller, request, status_code=status.HTTP_200_OK):
    seller.points_balance = PointService.get_balance(seller)
    return Response(OnboardedSellerDetailSerializer(seller, context={"request": request}).data, status=status_code)


def onboarder_detail_response(request, pk, status_code=status.HTTP_200_OK):
    """One of the caller's sellers, with whether they see products and their edit session."""
    seller = get_object_or_404(with_catalog(OnboardingService.sellers_of(request.user), request.user), pk=pk)
    response = detail_response(seller, request, status_code)
    response.data["can_view_products"] = can_view_onboarded_products(request.user)
    response.data["edit_session"] = EditSessionService.describe(EditSessionService.latest(seller, request.user))
    return response


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
        return with_counts(sellers, self.request.user)

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
        return onboarder_detail_response(request, seller.pk, status.HTTP_201_CREATED)


class OnboardedSellerDetailView(APIView):
    """
    GET   /api/onboarding/sellers/<pk>/: one of the caller's sellers, with its
          shops, the products the caller added (with 'onboarding.products.view'),
          `can_view_products` and the `edit_session` state.
    PATCH /api/onboarding/sellers/<pk>/: business name, email, phone, tax ID and
          description, in an open edit session.
    """
    permission_classes = [IsAuthenticated, CanOnboardSellers]

    def get(self, request, pk):
        return onboarder_detail_response(request, pk)

    def patch(self, request, pk):
        seller = get_object_or_404(OnboardingService.sellers_of(request.user), pk=pk)
        serializer = OnboardingSellerUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            OnboardingService.edit_seller(
                request.user, seller, serializer.validated_data, ip_address=get_client_ip(request)
            )
        except EditSessionRequired as exc:
            raise edit_session_required(exc)
        except EditSessionError as exc:
            raise refused(exc)
        except DjangoValidationError as exc:
            raise django_errors(exc)
        return onboarder_detail_response(request, pk)


class EditSessionView(APIView):
    """
    GET    /api/onboarding/sellers/<pk>/edit-session/: none, waiting (until
           `code_expires_at`) or open (until `expires_at`).
    POST   /api/onboarding/sellers/<pk>/edit-session/: sends a new code to the
           seller's account. 429 with `wait_seconds` within a minute of the last.
    DELETE /api/onboarding/sellers/<pk>/edit-session/: ends it early.
    """
    permission_classes = [IsAuthenticated, CanOnboardSellers]

    def get(self, request, pk):
        seller = get_object_or_404(OnboardingService.sellers_of(request.user), pk=pk)
        return Response(EditSessionService.describe(EditSessionService.latest(seller, request.user)))

    def post(self, request, pk):
        seller = get_object_or_404(OnboardingService.sellers_of(request.user), pk=pk)
        try:
            session = EditSessionService.request_code(request.user, seller, ip_address=get_client_ip(request))
        except EditCodeTooSoon as exc:
            return Response(
                {"detail": str(exc), "wait_seconds": exc.wait_seconds},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(exc.wait_seconds)},
            )
        except EditSessionError as exc:
            raise refused(exc)
        return Response(EditSessionService.describe(session), status=status.HTTP_201_CREATED)

    def delete(self, request, pk):
        seller = get_object_or_404(OnboardingService.sellers_of(request.user), pk=pk)
        EditSessionService.close(request.user, seller)
        return Response(EditSessionService.describe(EditSessionService.latest(seller, request.user)))


class EditSessionVerifyView(APIView):
    """
    POST /api/onboarding/sellers/<pk>/edit-session/verify/ {"code": "123456"}
    Opens the session with the code the seller received. 400 for a wrong code
    (`detail` says how many tries are left), an expired one or none waiting.
    """
    permission_classes = [IsAuthenticated, CanOnboardSellers]

    def post(self, request, pk):
        seller = get_object_or_404(OnboardingService.sellers_of(request.user), pk=pk)
        serializer = EditCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = EditSessionService.verify(
                request.user, seller, serializer.validated_data["code"], ip_address=get_client_ip(request)
            )
        except EditSessionError as exc:
            raise refused(exc)
        return Response(EditSessionService.describe(session))


class OnboardedShopDetailView(APIView):
    """
    PATCH /api/onboarding/shops/<pk>/: a shop of one of the caller's sellers, in
    an open edit session: name, description, phone, additional_phones, address,
    and latitude with longitude.
    """
    permission_classes = [IsAuthenticated, CanOnboardSellers]

    def patch(self, request, pk):
        shop = get_object_or_404(
            Shop.objects.select_related("owner").filter(owner__in=OnboardingService.sellers_of(request.user)), pk=pk
        )
        serializer = OnboardingShopUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if "phone" in data or "additional_phones" in data:
            data["additional_phones"] = validate_additional_phones(
                data.get("additional_phones", shop.additional_phones), data.get("phone", shop.phone)
            )
        location = None
        if data.get("latitude") is not None:
            try:
                location = validate_coordinates(data["latitude"], data["longitude"])
            except DjangoValidationError as exc:
                raise django_errors(exc)
        try:
            shop = OnboardingService.edit_shop(
                request.user, shop, data, location=location, ip_address=get_client_ip(request)
            )
        except EditSessionRequired as exc:
            raise edit_session_required(exc)
        except EditSessionError as exc:
            raise refused(exc)
        except DjangoValidationError as exc:
            raise django_errors(exc)
        if can_view_onboarded_products(request.user):
            products = OnboardingService.products_of(request.user).select_related("category")
        else:
            products = Product.objects.none()
        shop = Shop.objects.prefetch_related(Prefetch("products", queryset=products)).get(pk=shop.pk)
        return Response(OnboardedShopSerializer(shop, context={"request": request}).data)


class OnboardedProductListView(generics.ListAPIView):
    """
    GET /api/onboarding/products/ (?seller=<pk>): the products the caller added
    for their sellers, newest first. Needs 'onboarding.products.view'.
    """
    permission_classes = [IsAuthenticated, CanViewOnboardedProducts]
    serializer_class = OnboardedProductDetailSerializer

    def get_queryset(self):
        products = OnboardingService.products_of(self.request.user).select_related("category", "shop__owner")
        seller = self.request.query_params.get("seller")
        if seller:
            if not seller.isdigit():
                raise ValidationError({"seller": "A seller id is a number."})
            products = products.filter(shop__owner_id=int(seller))
        return products.order_by("-created_at", "-pk")


class OnboardedProductDetailView(APIView):
    """
    GET   /api/onboarding/products/<pk>/: one product the caller added.
    PATCH /api/onboarding/products/<pk>/ (multipart for the `image`): the
          seller's own product edit, in an open edit session; `stock` needs
          `expected_stock` (409 with `current_stock` when it has changed).
    Both need 'onboarding.products.view'.
    """
    permission_classes = [IsAuthenticated, CanViewOnboardedProducts]

    def get_object(self, request, pk):
        return get_object_or_404(
            OnboardingService.products_of(request.user).select_related("category", "shop__owner"), pk=pk
        )

    def get(self, request, pk):
        product = self.get_object(request, pk)
        return Response(OnboardedProductDetailSerializer(product, context={"request": request}).data)

    def patch(self, request, pk):
        product = self.get_object(request, pk)
        serializer = OnboardingProductUpdateSerializer(data=request.data, context={"request": request}, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            product = OnboardingService.edit_product(
                request.user, product, serializer.validated_data, ip_address=get_client_ip(request)
            )
        except EditSessionRequired as exc:
            raise edit_session_required(exc)
        except StockConflictError as exc:
            return Response(
                {"detail": str(exc), "current_stock": exc.current_stock}, status=status.HTTP_409_CONFLICT
            )
        except (EditSessionError, IneligibleSellerError, ProductOwnershipError, ListingError) as exc:
            raise refused(exc)
        except DjangoValidationError as exc:
            raise django_errors(exc)
        product = self.get_object(request, pk)
        return Response(OnboardedProductDetailSerializer(product, context={"request": request}).data)


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


class OnboardedSellerPointsView(APIView):
    """
    POST /api/onboarding/sellers/<pk>/points/ {"amount": 100}
    Sells points from the caller's wallet to one of their approved sellers,
    who paid the caller outside the system. 400 below the minimum purchase
    (SellerPointPolicy), for a seller not yet approved, or with
    `available_points` when the caller's wallet holds too few.
    """
    permission_classes = [IsAuthenticated, CanOnboardSellers]

    def post(self, request, pk):
        seller = get_object_or_404(OnboardingService.sellers_of(request.user), pk=pk)
        serializer = PointSaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            txn = OnboardingService.sell_points(
                request.user, seller, serializer.validated_data["amount"], ip_address=get_client_ip(request)
            )
        except InsufficientStaffPointsError as exc:
            return Response(
                {"detail": str(exc), "available_points": PointService.get_staff_balance(request.user)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (InvalidAmountError, OnboardingError) as exc:
            raise refused(exc)
        return Response(
            {
                "seller_id": seller.pk,
                "amount": txn.amount,
                "points_balance": txn.balance_after,
                "points_expire_at": txn.lot.expires_at,
                "your_points": txn.staff_counterpart.balance_after,
            }
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


class PayoutListCreateView(generics.ListAPIView):
    """
    GET  /api/onboarding/payouts/: the caller's payout requests, newest first.
    POST /api/onboarding/payouts/ {"tokens": 51, "note": "..."}: hands tokens in
         for real payment, held until an admin decides. One pending at a time.
    """
    permission_classes = [IsAuthenticated, CanOnboardSellers]
    serializer_class = TokenPayoutSerializer

    def get_queryset(self):
        return TokenPayoutRequest.objects.filter(requested_by=self.request.user).select_related(
            "requested_by", "decided_by"
        )

    def post(self, request):
        serializer = PayoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payout = TokenService.request_payout(
                request.user,
                serializer.validated_data["tokens"],
                note=serializer.validated_data["note"],
                ip_address=get_client_ip(request),
            )
        except PayoutError as exc:
            raise refused(exc)
        return Response(TokenPayoutSerializer(payout).data, status=status.HTTP_201_CREATED)


class PayoutCancelView(APIView):
    """POST /api/onboarding/payouts/<pk>/cancel/: withdraws the caller's pending request."""
    permission_classes = [IsAuthenticated, CanOnboardSellers]

    def post(self, request, pk):
        get_object_or_404(TokenPayoutRequest, pk=pk, requested_by=request.user)
        try:
            payout = TokenService.cancel_payout(request.user, pk, ip_address=get_client_ip(request))
        except PayoutError as exc:
            raise refused(exc)
        return Response(TokenPayoutSerializer(payout).data)


# ---------------------------------------------------------------------------
# The reviewer's side
# ---------------------------------------------------------------------------

class PayoutReviewListView(generics.ListAPIView):
    """
    GET /api/onboarding/payouts/review/ (?status=PENDING): every payout request,
    pending ones first, oldest first among them.
    """
    permission_classes = [IsAuthenticated, CanSettleTokenPayouts]
    serializer_class = TokenPayoutSerializer

    def get_queryset(self):
        payouts = TokenPayoutRequest.objects.select_related("requested_by", "decided_by")
        wanted = self.request.query_params.get("status")
        if wanted:
            return payouts.filter(status__iexact=wanted.strip()).order_by("created_at", "pk")
        return payouts.order_by("-created_at", "-pk")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data["your_tokens"] = TokenService.get_balance(request.user)
        return response


class PayoutAcceptView(APIView):
    """
    POST /api/onboarding/payouts/review/<pk>/accept/ {"note": "Paid by bKash, TrxID ..."}
    Accepts a pending request: its tokens move to the caller's token wallet.
    """
    permission_classes = [IsAuthenticated, CanSettleTokenPayouts]

    def post(self, request, pk):
        get_object_or_404(TokenPayoutRequest, pk=pk)
        serializer = PayoutAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payout = TokenService.accept_payout(
                request.user, pk, note=serializer.validated_data["note"], ip_address=get_client_ip(request)
            )
        except PayoutError as exc:
            raise refused(exc)
        return Response(TokenPayoutSerializer(payout).data)


class PayoutRejectView(APIView):
    """POST /api/onboarding/payouts/review/<pk>/reject/ {"reason": "..."}: the tokens go back."""
    permission_classes = [IsAuthenticated, CanSettleTokenPayouts]

    def post(self, request, pk):
        get_object_or_404(TokenPayoutRequest, pk=pk)
        serializer = PayoutRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payout = TokenService.reject_payout(
                request.user, pk, serializer.validated_data["reason"], ip_address=get_client_ip(request)
            )
        except PayoutError as exc:
            raise refused(exc)
        return Response(TokenPayoutSerializer(payout).data)


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

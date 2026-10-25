from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import AuditService
from audit.utils import get_client_ip
from sellers.models import SellerProfile
from .models import PointExpiryPolicy, PointTransaction, SellerWallet, StaffWallet
from .permissions import (
    CanAdjustPoints,
    CanViewPoints,
    CanViewStaffWallets,
    IsPointSuperuser,
    IsSellerWalletOwner,
    can_perform_point_action,
)
from .serializers import (
    PointAdjustmentRequestSerializer,
    PointTransactionSerializer,
    SellerWalletSerializer,
    StaffPointExpiryRequestSerializer,
    StaffPointTransactionSerializer,
    StaffPointTransferRequestSerializer,
    UpcomingExpirySerializer,
)
from .services import (
    InsufficientPointsError,
    InsufficientStaffPointsError,
    PointError,
    PointService,
    SelfAdjustmentError,
    staff_points_expire,
)

User = get_user_model()


class SellerWalletView(APIView):
    """
    Returns the authenticated seller's own point wallet and balance.
    """
    permission_classes = [permissions.IsAuthenticated, IsSellerWalletOwner]

    def get(self, request):
        seller = request.user.seller_profile
        wallet = PointService.expire_due_seller_points(PointService.get_or_create_wallet(seller))
        return Response(SellerWalletSerializer(wallet).data, status=status.HTTP_200_OK)


class SellerTransactionHistoryView(generics.ListAPIView):
    """
    Lists the authenticated seller's own point transaction history (newest first).
    Supports filtering by '?type=BONUS|ADMIN_CREDIT|ADMIN_DEBIT|PRODUCT_CREATION|REFUND|ADJUSTMENT'.
    """
    permission_classes = [permissions.IsAuthenticated, IsSellerWalletOwner]
    serializer_class = PointTransactionSerializer

    def get_queryset(self):
        seller = self.request.user.seller_profile
        txn_type = self.request.query_params.get("type")
        return PointService.get_transaction_history(seller, transaction_type=txn_type)


STAFF_WALLET_RECENT_LIMIT = 5


def staff_wallet_summary(user) -> dict:
    """
    One account's StaffWallet: its balance, the lifetime totals behind it and
    the newest movements. An account without a wallet reads as 0 and is not
    given one, because every caller is a GET: filter(), never
    get_or_create_staff_wallet().
    """
    wallet = StaffWallet.objects.filter(user=user).first()
    if wallet is not None:
        wallet = PointService.expire_due_staff_points(wallet)
    # A superuser's points never expire; anyone else's do unless a superuser
    # turned it off for them (`expiry_enabled`, the per-wallet switch).
    points_expire = staff_points_expire(wallet) if wallet else not user.is_superuser
    data = {
        "has_wallet": wallet is not None,
        "balance": wallet.balance if wallet else 0,
        "received": 0,
        "given_to_sellers": 0,
        "sent_to_staff": 0,
        "taken_back": 0,
        "expired": 0,
        "transaction_count": 0,
        "can_mint": bool(user.is_superuser),
        "points_expire": points_expire,
        "expiry_enabled": wallet.points_expire if wallet else True,
        "expiry_months": PointExpiryPolicy.get_months(),
        "upcoming_expiries": [],
        "recent": [],
    }
    if wallet is not None:
        data.update(PointService.get_staff_ledger_totals(wallet))
        if points_expire:
            data["upcoming_expiries"] = UpcomingExpirySerializer(
                PointService.upcoming_expiries(wallet), many=True
            ).data
        entries = wallet.transactions.select_related(
            "counterparty", "seller_transaction__seller"
        ).order_by("-created_at", "-pk")
        data["transaction_count"] = entries.count()
        data["recent"] = StaffPointTransactionSerializer(
            entries[:STAFF_WALLET_RECENT_LIMIT], many=True
        ).data
    return data


class StaffOwnWalletView(APIView):
    """
    The caller's own StaffWallet: what they can still give to sellers, the
    lifetime totals behind it and the newest movements. It backs the points
    tile on the Console profile.

    Any signed-in user may ask, because it only ever describes their own
    wallet. An account without one reads as 0 and is not given a wallet.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(staff_wallet_summary(request.user), status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Staff / Administrative Endpoints (RBAC-enforced)
# ---------------------------------------------------------------------------

class StaffSellerWalletView(APIView):
    """
    Staff endpoint to inspect a specific seller's wallet and balance.
    Requires 'points.view' RBAC permission.
    """
    permission_classes = [CanViewPoints]

    def get(self, request, seller_id):
        seller = get_object_or_404(SellerProfile, pk=seller_id)
        wallet = PointService.expire_due_seller_points(PointService.get_or_create_wallet(seller))
        return Response(SellerWalletSerializer(wallet).data, status=status.HTTP_200_OK)


class StaffSellerHistoryView(generics.ListAPIView):
    """
    Staff endpoint to inspect a specific seller's point transaction ledger.
    Requires 'points.view' RBAC permission.
    """
    permission_classes = [CanViewPoints]
    serializer_class = PointTransactionSerializer

    def get_queryset(self):
        seller = get_object_or_404(SellerProfile, pk=self.kwargs["seller_id"])
        txn_type = self.request.query_params.get("type")
        return PointService.get_transaction_history(seller, transaction_type=txn_type)


class StaffPointAdjustmentView(APIView):
    """
    Staff endpoint to execute an auditable credit or debit adjustment.

    Authorization is TWO-STAGE. CanAdjustPoints gates entry on holding any
    point-movement permission; this view then checks the specific direction,
    because 'points.add' and 'points.deduct' are one-way authorities and the
    direction is only known once the body is validated. Without the second
    stage an actor holding 'points.add' alone could debit a seller's balance.

    Points move to and from the actor's own StaffWallet (see
    PointService.adjust_points), so a CREDIT is refused when that wallet does
    not hold enough — permission alone is not enough to give points.
    """
    permission_classes = [CanAdjustPoints]

    def post(self, request, seller_id):
        seller = get_object_or_404(SellerProfile, pk=seller_id)
        serializer = PointAdjustmentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not can_perform_point_action(request.user, data["action"]):
            # Deliberately non-specific: naming the permission the actor is
            # missing would let a caller enumerate the point authorities by
            # probing this endpoint.
            raise PermissionDenied("You do not have permission to perform this point operation.")

        # PointTransaction remains the authoritative points ledger; the central
        # AuditLog entry records the same act as a GOVERNANCE decision, which is
        # where every other admin mutation is already reviewed. Both are written
        # in one atomic block so a staff adjustment can never appear in the
        # ledger without its governance record, or the reverse.
        #
        # PointService.adjust_points opens its own atomic block, which nests as a
        # savepoint here; its select_for_update locks on the staff and seller
        # wallets are held until this outer block commits.
        try:
            with transaction.atomic():
                txn = PointService.adjust_points(
                    seller=seller,
                    amount=data["amount"],
                    action=data["action"],
                    reason=data["reason"],
                    actor=request.user,
                    reference_type=data.get("reference_type", ""),
                    reference_id=data.get("reference_id", ""),
                )
                AuditService.log(
                    action=f"ADMIN_POINTS_{data['action'].upper()}",
                    target=txn,
                    actor=request.user,
                    seller=seller,
                    reason=data["reason"],
                    previous_state={"balance": txn.balance_before},
                    new_state={"balance": txn.balance_after},
                    metadata={
                        "amount": txn.amount,
                        "transaction_type": txn.transaction_type,
                        "point_transaction_id": txn.id,
                        "reference_type": txn.reference_type,
                        "reference_id": txn.reference_id,
                        "actor_wallet_balance": txn.staff_counterpart.balance_after,
                    },
                    ip_address=get_client_ip(request),
                )
        except InsufficientPointsError as e:
            return Response(
                {
                    "error": str(e),
                    "detail": "Seller does not have enough points for this deduction.",
                    "available_balance": PointService.get_balance(seller),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except InsufficientStaffPointsError as e:
            return Response(
                {
                    "error": str(e),
                    "detail": "Your own wallet does not hold enough points for this credit.",
                    "available_balance": PointService.get_staff_balance(request.user),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except SelfAdjustmentError as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except PointError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        actor_balance = txn.staff_counterpart.balance_after
        return Response(
            {
                "message": (
                    f"Successfully {data['action'].lower()}ed {data['amount']} points for {seller.business_name}. "
                    f"Your wallet now holds {actor_balance} points."
                ),
                "transaction": PointTransactionSerializer(txn).data,
                "current_balance": txn.balance_after,
                "actor_balance": actor_balance,
            },
            status=status.HTTP_200_OK,
        )


class StaffUserWalletView(APIView):
    """
    GET /api/points/staff/<user_id>/

    Any account's StaffWallet, in the same shape as /api/points/staff/me/, for
    the Console's user page. Requires 'points.view' and 'users.admin.view'
    (CanViewStaffWallets): it answers for every user id, so it must not reach
    further than the user directory itself.

    `can_receive_transfers` says whether a superuser may send this account
    points: transfer_to_staff refuses anyone inactive or unable to credit
    sellers, because points in their wallet could never be spent.
    """
    permission_classes = [CanViewStaffWallets]

    def get(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        data = staff_wallet_summary(target)
        data.update(
            {
                "user_id": target.pk,
                "username": target.username,
                "can_receive_transfers": bool(
                    target.is_active and can_perform_point_action(target, "CREDIT")
                ),
            }
        )
        return Response(data, status=status.HTTP_200_OK)


class StaffPointTransferView(APIView):
    """
    POST /api/points/staff/<user_id>/transfer/

    A superuser gives a staff member points out of their own wallet (CREDIT,
    PointService.transfer_to_staff) or takes points back into it (DEBIT,
    PointService.reclaim_from_staff). Only an active superuser may do either;
    holding every points permission is not enough, as the service already
    insists for transfers made with utils/add_points.py.

    The ledger entries and the SUPERUSER_POINTS_* audit entry are written in
    one atomic block, as StaffPointAdjustmentView does for seller adjustments.
    """
    permission_classes = [IsPointSuperuser]

    def post(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        serializer = StaffPointTransferRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        actor = request.user
        giving = data["action"] == "CREDIT"

        try:
            with transaction.atomic():
                if giving:
                    outgoing, incoming = PointService.transfer_to_staff(
                        actor, target, data["amount"], data["reason"]
                    )
                    actor_txn, target_txn = outgoing, incoming
                else:
                    outgoing, incoming = PointService.reclaim_from_staff(
                        actor, target, data["amount"], data["reason"]
                    )
                    actor_txn, target_txn = incoming, outgoing
                AuditService.log(
                    action="SUPERUSER_POINTS_TRANSFER" if giving else "SUPERUSER_POINTS_RECLAIM",
                    target=target_txn,
                    actor=actor,
                    reason=data["reason"],
                    previous_state={"balance": target_txn.balance_before},
                    new_state={"balance": target_txn.balance_after},
                    metadata={
                        "amount": data["amount"],
                        "staff_member": target.username,
                        "actor_balance_after": actor_txn.balance_after,
                        "staff_balance_after": target_txn.balance_after,
                        "staff_point_transaction_ids": [outgoing.pk, incoming.pk],
                    },
                    ip_address=get_client_ip(request),
                )
        except InsufficientStaffPointsError as e:
            # The same 400 shape as StaffPointAdjustmentView, so the Console
            # reads it with getInsufficientPointsInfo.
            return Response(
                {
                    "error": str(e),
                    "detail": (
                        "Your own wallet does not hold enough points for this transfer."
                        if giving
                        else "This staff member's wallet does not hold that many points."
                    ),
                    # Read without get_or_create: a refused take-back must
                    # not leave the staff member an empty wallet behind.
                    "available_balance": StaffWallet.objects.filter(user=actor if giving else target)
                    .values_list("balance", flat=True)
                    .first()
                    or 0,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except PointError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        points = f"{data['amount']} point{'' if data['amount'] == 1 else 's'}"
        if giving:
            message = f"Gave {points} to {target.username}."
        else:
            message = f"Took back {points} from {target.username}."
        return Response(
            {
                "message": f"{message} Your wallet now holds {actor_txn.balance_after:,} points.",
                "transaction": StaffPointTransactionSerializer(target_txn).data,
                "staff_balance": target_txn.balance_after,
                "actor_balance": actor_txn.balance_after,
            },
            status=status.HTTP_200_OK,
        )


class StaffPointExpiryView(APIView):
    """
    POST /api/points/staff/<user_id>/expiry/

    A superuser turns point expiry on or off for one staff member's wallet
    (PointService.set_staff_points_expire). Turning it back on gives what
    they hold a fresh expiry period. A superuser's own points never expire,
    so their wallet cannot be switched. Audited like a transfer.
    """
    permission_classes = [IsPointSuperuser]

    def post(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        serializer = StaffPointExpiryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        enabled = serializer.validated_data["enabled"]
        reason = serializer.validated_data["reason"]

        previous = (
            StaffWallet.objects.filter(user=target).values_list("points_expire", flat=True).first()
        )
        previous = True if previous is None else previous
        try:
            with transaction.atomic():
                wallet = PointService.set_staff_points_expire(target, enabled)
                if previous != enabled:
                    AuditService.log(
                        action="SUPERUSER_POINTS_EXPIRY_ENABLED" if enabled else "SUPERUSER_POINTS_EXPIRY_DISABLED",
                        target=wallet,
                        actor=request.user,
                        reason=reason,
                        previous_state={"points_expire": previous},
                        new_state={"points_expire": enabled},
                        metadata={"staff_member": target.username, "balance": wallet.balance},
                        ip_address=get_client_ip(request),
                    )
        except PointError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if previous == enabled:
            message = f"Point expiry was already {'on' if enabled else 'off'} for {target.username}."
        elif enabled:
            message = (
                f"Point expiry is on for {target.username}. What they hold now lasts at least "
                f"{PointExpiryPolicy.get_months()} months."
            )
        else:
            message = f"Point expiry is off for {target.username}. Their points no longer expire."
        return Response({"message": message, "points_expire": wallet.points_expire}, status=status.HTTP_200_OK)

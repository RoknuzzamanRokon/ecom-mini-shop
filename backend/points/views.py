from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from sellers.models import SellerProfile
from .models import PointTransaction, SellerWallet
from .permissions import CanAdjustPoints, CanViewPoints, IsSellerWalletOwner
from .serializers import (
    PointAdjustmentRequestSerializer,
    PointTransactionSerializer,
    SellerWalletSerializer,
)
from .services import InsufficientPointsError, PointError, PointService


class SellerWalletView(APIView):
    """
    Returns the authenticated seller's own point wallet and balance.
    """
    permission_classes = [permissions.IsAuthenticated, IsSellerWalletOwner]

    def get(self, request):
        seller = request.user.seller_profile
        wallet = PointService.get_or_create_wallet(seller)
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
        wallet = PointService.get_or_create_wallet(seller)
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
    Requires 'points.adjust', 'points.add', or 'points.deduct' RBAC permission.
    """
    permission_classes = [CanAdjustPoints]

    def post(self, request, seller_id):
        seller = get_object_or_404(SellerProfile, pk=seller_id)
        serializer = PointAdjustmentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            txn = PointService.adjust_points(
                seller=seller,
                amount=data["amount"],
                action=data["action"],
                reason=data["reason"],
                actor=request.user,
                reference_type=data.get("reference_type", ""),
                reference_id=data.get("reference_id", ""),
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
        except PointError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": f"Successfully {data['action'].lower()}ed {data['amount']} points for {seller.business_name}.",
                "transaction": PointTransactionSerializer(txn).data,
                "current_balance": txn.balance_after,
            },
            status=status.HTTP_200_OK,
        )

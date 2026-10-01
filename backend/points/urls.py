from django.urls import path
from .views import (
    SellerTransactionHistoryView,
    SellerWalletView,
    StaffOwnWalletView,
    StaffPointAdjustmentView,
    StaffPointTransferView,
    StaffSellerHistoryView,
    StaffSellerWalletView,
    StaffUserWalletView,
)

app_name = "points"

urlpatterns = [
    # Seller self-service endpoints
    path("wallet/", SellerWalletView.as_view(), name="seller-wallet"),
    path("history/", SellerTransactionHistoryView.as_view(), name="seller-history"),

    # Staff self-service: the caller's own staff wallet
    path("staff/me/", StaffOwnWalletView.as_view(), name="staff-my-wallet"),

    # Any account's staff wallet ('points.view'), and a superuser moving
    # points into or out of it
    path("staff/<int:user_id>/", StaffUserWalletView.as_view(), name="staff-user-wallet"),
    path("staff/<int:user_id>/transfer/", StaffPointTransferView.as_view(), name="staff-user-transfer"),

    # Staff / Admin RBAC endpoints
    path("sellers/<int:seller_id>/", StaffSellerWalletView.as_view(), name="staff-seller-wallet"),
    path("sellers/<int:seller_id>/history/", StaffSellerHistoryView.as_view(), name="staff-seller-history"),
    path("sellers/<int:seller_id>/adjust/", StaffPointAdjustmentView.as_view(), name="staff-seller-adjust"),
]

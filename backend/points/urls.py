from django.urls import path
from .views import (
    SellerTransactionHistoryView,
    SellerWalletView,
    StaffPointAdjustmentView,
    StaffSellerHistoryView,
    StaffSellerWalletView,
)

app_name = "points"

urlpatterns = [
    # Seller self-service endpoints
    path("wallet/", SellerWalletView.as_view(), name="seller-wallet"),
    path("history/", SellerTransactionHistoryView.as_view(), name="seller-history"),

    # Staff / Admin RBAC endpoints
    path("sellers/<int:seller_id>/", StaffSellerWalletView.as_view(), name="staff-seller-wallet"),
    path("sellers/<int:seller_id>/history/", StaffSellerHistoryView.as_view(), name="staff-seller-history"),
    path("sellers/<int:seller_id>/adjust/", StaffPointAdjustmentView.as_view(), name="staff-seller-adjust"),
]

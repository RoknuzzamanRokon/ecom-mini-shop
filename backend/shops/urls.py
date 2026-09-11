from django.urls import path
from .views import (
    PublicShopDetailView,
    PublicShopListView,
    SellerShopCreateView,
    SellerShopDetailView,
    SellerShopListView,
    SellerShopSubmitView,
    SellerShopUpdateView,
    StaffShopApproveView,
    StaffShopDetailView,
    StaffShopListView,
    StaffShopReactivateView,
    StaffShopRejectView,
    StaffShopSuspendView,
)

app_name = "shops"

urlpatterns = [
    # Seller self-service routes (placed before slug to avoid collisions)
    path("mine/", SellerShopListView.as_view(), name="seller-shop-list"),
    path("mine/create/", SellerShopCreateView.as_view(), name="seller-shop-create"),
    path("mine/<int:pk>/", SellerShopDetailView.as_view(), name="seller-shop-detail"),
    path("mine/<int:pk>/update/", SellerShopUpdateView.as_view(), name="seller-shop-update"),
    path("mine/<int:pk>/submit/", SellerShopSubmitView.as_view(), name="seller-shop-submit"),

    # Staff / Admin RBAC routes
    path("staff/", StaffShopListView.as_view(), name="staff-shop-list"),
    path("staff/<int:pk>/", StaffShopDetailView.as_view(), name="staff-shop-detail"),
    path("staff/<int:pk>/approve/", StaffShopApproveView.as_view(), name="staff-shop-approve"),
    path("staff/<int:pk>/reject/", StaffShopRejectView.as_view(), name="staff-shop-reject"),
    path("staff/<int:pk>/suspend/", StaffShopSuspendView.as_view(), name="staff-shop-suspend"),
    path("staff/<int:pk>/reactivate/", StaffShopReactivateView.as_view(), name="staff-shop-reactivate"),

    # Public browsing routes
    path("", PublicShopListView.as_view(), name="public-shop-list"),
    path("<slug:slug>/", PublicShopDetailView.as_view(), name="public-shop-detail"),
]

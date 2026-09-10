from django.urls import path
from .views import (
    SellerApproveView,
    SellerDashboardView,
    SellerDetailView,
    SellerListView,
    SellerMeView,
    SellerReactivateView,
    SellerRegistrationView,
    SellerRejectView,
    SellerSuspendView,
)

app_name = "sellers"

urlpatterns = [
    path("", SellerListView.as_view(), name="seller-list"),
    path("register/", SellerRegistrationView.as_view(), name="seller-register"),
    path("me/", SellerMeView.as_view(), name="seller-me"),
    path("dashboard/", SellerDashboardView.as_view(), name="seller-dashboard"),
    path("<int:pk>/", SellerDetailView.as_view(), name="seller-detail"),
    path("<int:pk>/approve/", SellerApproveView.as_view(), name="seller-approve"),
    path("<int:pk>/reject/", SellerRejectView.as_view(), name="seller-reject"),
    path("<int:pk>/suspend/", SellerSuspendView.as_view(), name="seller-suspend"),
    path("<int:pk>/reactivate/", SellerReactivateView.as_view(), name="seller-reactivate"),
]

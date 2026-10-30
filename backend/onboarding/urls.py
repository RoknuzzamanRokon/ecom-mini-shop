from django.urls import path

from .views import (
    OnboardedProductCreateView,
    OnboardedSellerDetailView,
    OnboardedSellerListCreateView,
    OnboardedShopCreateView,
    OnboardingApproveView,
    OnboardingRejectView,
    OnboardingReviewDetailView,
    OnboardingReviewListView,
    OnboardingSummaryView,
    TokenHistoryView,
)

app_name = "onboarding"

urlpatterns = [
    # The onboarder (sellers.onboard)
    path("me/", OnboardingSummaryView.as_view(), name="summary"),
    path("sellers/", OnboardedSellerListCreateView.as_view(), name="sellers"),
    path("sellers/<int:pk>/", OnboardedSellerDetailView.as_view(), name="seller-detail"),
    path("sellers/<int:pk>/shops/", OnboardedShopCreateView.as_view(), name="seller-shops"),
    path("shops/<int:pk>/products/", OnboardedProductCreateView.as_view(), name="shop-products"),
    path("tokens/", TokenHistoryView.as_view(), name="tokens"),

    # The reviewer (seller, shop and product approval together)
    path("review/", OnboardingReviewListView.as_view(), name="review"),
    path("review/<int:pk>/", OnboardingReviewDetailView.as_view(), name="review-detail"),
    path("review/<int:pk>/approve/", OnboardingApproveView.as_view(), name="review-approve"),
    path("review/<int:pk>/reject/", OnboardingRejectView.as_view(), name="review-reject"),
]

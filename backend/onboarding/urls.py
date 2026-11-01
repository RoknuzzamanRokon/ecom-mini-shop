from django.urls import path

from .views import (
    EditSessionVerifyView,
    EditSessionView,
    OnboardedProductCreateView,
    OnboardedProductDetailView,
    OnboardedProductListView,
    OnboardedSellerPointsView,
    OnboardedSellerDetailView,
    OnboardedSellerListCreateView,
    OnboardedShopCreateView,
    OnboardedShopDetailView,
    OnboardingApproveView,
    OnboardingRejectView,
    OnboardingReviewDetailView,
    OnboardingReviewListView,
    OnboardingSummaryView,
    PayoutAcceptView,
    PayoutCancelView,
    PayoutListCreateView,
    PayoutRejectView,
    PayoutReviewListView,
    TokenHistoryView,
)

app_name = "onboarding"

urlpatterns = [
    # The onboarder (sellers.onboard)
    path("me/", OnboardingSummaryView.as_view(), name="summary"),
    path("sellers/", OnboardedSellerListCreateView.as_view(), name="sellers"),
    path("sellers/<int:pk>/", OnboardedSellerDetailView.as_view(), name="seller-detail"),
    path("sellers/<int:pk>/edit-session/", EditSessionView.as_view(), name="edit-session"),
    path("sellers/<int:pk>/edit-session/verify/", EditSessionVerifyView.as_view(), name="edit-session-verify"),
    path("sellers/<int:pk>/shops/", OnboardedShopCreateView.as_view(), name="seller-shops"),
    path("sellers/<int:pk>/points/", OnboardedSellerPointsView.as_view(), name="seller-points"),
    path("shops/<int:pk>/", OnboardedShopDetailView.as_view(), name="shop-detail"),
    path("shops/<int:pk>/products/", OnboardedProductCreateView.as_view(), name="shop-products"),
    # ... and onboarding.products.view
    path("products/", OnboardedProductListView.as_view(), name="products"),
    path("products/<int:pk>/", OnboardedProductDetailView.as_view(), name="product-detail"),
    path("tokens/", TokenHistoryView.as_view(), name="tokens"),
    path("payouts/", PayoutListCreateView.as_view(), name="payouts"),
    path("payouts/<int:pk>/cancel/", PayoutCancelView.as_view(), name="payout-cancel"),

    # Token payouts (onboarding.payouts.manage)
    path("payouts/review/", PayoutReviewListView.as_view(), name="payout-review"),
    path("payouts/review/<int:pk>/accept/", PayoutAcceptView.as_view(), name="payout-accept"),
    path("payouts/review/<int:pk>/reject/", PayoutRejectView.as_view(), name="payout-reject"),

    # The reviewer (seller, shop and product approval together)
    path("review/", OnboardingReviewListView.as_view(), name="review"),
    path("review/<int:pk>/", OnboardingReviewDetailView.as_view(), name="review-detail"),
    path("review/<int:pk>/approve/", OnboardingApproveView.as_view(), name="review-approve"),
    path("review/<int:pk>/reject/", OnboardingRejectView.as_view(), name="review-reject"),
]

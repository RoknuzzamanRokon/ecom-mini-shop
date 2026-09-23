from django.urls import path
from .views import (
    AddressDetailView,
    AddressListCreateView,
    AddressSetDefaultView,
    CustomerProfileView,
    FavoriteDetailView,
    FavoriteListCreateView,
    MyProductReviewView,
    MyShopReviewView,
    ReviewDetailView,
    ReviewListCreateView,
    ShopReviewCreateView,
    ShopReviewDetailView,
)

app_name = "customers"

urlpatterns = [
    path("profile/me/", CustomerProfileView.as_view(), name="customer-profile-me"),
    path("addresses/", AddressListCreateView.as_view(), name="address-list-create"),
    path("addresses/<int:pk>/", AddressDetailView.as_view(), name="address-detail"),
    path("addresses/<int:pk>/set-default/", AddressSetDefaultView.as_view(), name="address-set-default"),
    path("favorites/", FavoriteListCreateView.as_view(), name="favorite-list-create"),
    path("favorites/<int:product_id>/", FavoriteDetailView.as_view(), name="favorite-detail"),
    path("reviews/", ReviewListCreateView.as_view(), name="review-list-create"),
    path("reviews/mine/", MyProductReviewView.as_view(), name="review-mine"),
    path("reviews/<int:pk>/", ReviewDetailView.as_view(), name="review-detail"),
    path("shop-reviews/", ShopReviewCreateView.as_view(), name="shop-review-create"),
    path("shop-reviews/mine/", MyShopReviewView.as_view(), name="shop-review-mine"),
    path("shop-reviews/<int:pk>/", ShopReviewDetailView.as_view(), name="shop-review-detail"),
]

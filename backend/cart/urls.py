from django.urls import path

from . import views

app_name = "cart"

urlpatterns = [
    path("", views.CartView.as_view(), name="cart_detail"),
    path("items/", views.CartItemCreateView.as_view(), name="cart_items"),
    path("items/<int:pk>/", views.CartItemDetailView.as_view(), name="cart_item_detail"),
]

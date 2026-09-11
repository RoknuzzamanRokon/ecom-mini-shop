from django.urls import path
from .views import (
    AddressDetailView,
    AddressListCreateView,
    AddressSetDefaultView,
    CustomerProfileView,
)

app_name = "customers"

urlpatterns = [
    path("profile/me/", CustomerProfileView.as_view(), name="customer-profile-me"),
    path("addresses/", AddressListCreateView.as_view(), name="address-list-create"),
    path("addresses/<int:pk>/", AddressDetailView.as_view(), name="address-detail"),
    path("addresses/<int:pk>/set-default/", AddressSetDefaultView.as_view(), name="address-set-default"),
]

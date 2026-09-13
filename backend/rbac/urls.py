from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    CurrentUserView,
    CustomTokenObtainPairView,
    CustomerRegistrationView,
    PasswordChangeView,
    RBACPermissionTestView,
)

app_name = "rbac"

urlpatterns = [
    path("register/", CustomerRegistrationView.as_view(), name="customer_register"),
    path("token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", CurrentUserView.as_view(), name="current_user"),
    path("change-password/", PasswordChangeView.as_view(), name="change_password"),
    path("test-permission/", RBACPermissionTestView.as_view(), name="test_permission"),
]

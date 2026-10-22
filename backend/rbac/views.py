from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
)

from .permissions import HasPermission, require_permission
from .serializers import (
    CurrentUserSerializer,
    CustomerRegistrationResponseSerializer,
    CustomerRegistrationSerializer,
    PasswordChangeSerializer,
)
from .throttles import AuthRateThrottle


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Standard JWT token obtain view returning access and refresh tokens.
    """
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth_token"


class ThrottledTokenRefreshView(TokenRefreshView):
    """
    POST /api/auth/token/refresh/ — rotates the refresh token. The serializer
    (SIMPLE_JWT["TOKEN_REFRESH_SERIALIZER"]) blacklists the old one and
    refuses tokens issued before a password change.
    """
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth_refresh"


class LogoutView(TokenBlacklistView):
    """
    POST /api/auth/logout/ {"refresh": "<token>"} — blacklists that refresh
    token, so it can no longer mint access tokens.

    No access token is required: holding the refresh token is the proof, and
    an expired access token must not stop anyone from signing out. Access
    tokens already issued stay valid until they expire
    (SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]).
    """
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth_refresh"


class CurrentUserView(generics.RetrieveAPIView):
    """
    Returns authenticated user information along with assigned roles and resolved permissions.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CurrentUserSerializer

    def get_object(self):
        return self.request.user


class CustomerRegistrationView(generics.CreateAPIView):
    """
    Public endpoint for customer self-registration.
    Creates a standard customer account and assigns the default CUSTOMER RBAC role.
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = CustomerRegistrationSerializer
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth_register"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        output = CustomerRegistrationResponseSerializer(user)
        return Response(output.data, status=status.HTTP_201_CREATED)


class RBACPermissionTestView(APIView):
    """
    Verification endpoint enforcing a specific permission (products.approve).
    Used in automated test suite and manual verification.
    """
    permission_classes = [require_permission("products.approve")]

    def get(self, request):
        return Response(
            {
                "message": "Authorized",
                "user": request.user.username,
                "permission": "products.approve",
            },
            status=status.HTTP_200_OK,
        )



class PasswordChangeView(APIView):
    """
    Authenticated self-service password change.
    POST /api/auth/change-password/

    The new password revokes every token issued before it (CHECK_REVOKE_TOKEN),
    including the caller's own, so the response carries a fresh pair for the
    device that made the change. Every other device is signed out.
    """
    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AuthRateThrottle]
    throttle_scope = "auth_password"

    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "detail": "Password updated successfully.",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_200_OK,
        )

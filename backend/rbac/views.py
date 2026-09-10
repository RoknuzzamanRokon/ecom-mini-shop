from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .permissions import HasPermission, require_permission
from .serializers import CurrentUserSerializer


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Standard JWT token obtain view returning access and refresh tokens.
    """
    pass


class CurrentUserView(generics.RetrieveAPIView):
    """
    Returns authenticated user information along with assigned roles and resolved permissions.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CurrentUserSerializer

    def get_object(self):
        return self.request.user


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

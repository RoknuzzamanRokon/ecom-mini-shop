"""
JWT authentication that holds back an account still on its starting password
(rbac.models.StartingPassword).

The login puts STARTING_PASSWORD_CLAIM on the tokens of such an account, and
the claim travels into every access token minted from that refresh token.
Changing the password revokes those tokens (SIMPLE_JWT["CHECK_REVOKE_TOKEN"]),
and the new pair is issued without the claim, so no request needs a database
lookup to know.
"""
from django.urls import reverse
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import StartingPassword

STARTING_PASSWORD_CLAIM = "starting_password"

#: The only endpoints a starting-password token reaches (rbac/urls.py names).
OPEN_ENDPOINTS = ("rbac:current_user", "rbac:change_password", "rbac:logout")

PASSWORD_CHANGE_REQUIRED = (
    "Choose your own password first: the one you signed in with was set when your account was opened."
)


class PasswordChangeRequired(PermissionDenied):
    default_code = "password_change_required"

    def __init__(self):
        super().__init__({"detail": PASSWORD_CHANGE_REQUIRED, "code": self.default_code})


class StartingPasswordTokenObtainPairSerializer(TokenObtainPairSerializer):
    """POST /api/auth/token/ (SIMPLE_JWT["TOKEN_OBTAIN_SERIALIZER"]): marks a starting password."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        if StartingPassword.is_pending(user):
            token[STARTING_PASSWORD_CLAIM] = True
        return token


class StartingPasswordJWTAuthentication(JWTAuthentication):
    """SimpleJWT's authentication, refusing marked tokens outside OPEN_ENDPOINTS with 403."""

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None and result[1].get(STARTING_PASSWORD_CLAIM):
            if request.path not in {reverse(name) for name in OPEN_ENDPOINTS}:
                raise PasswordChangeRequired()
        return result

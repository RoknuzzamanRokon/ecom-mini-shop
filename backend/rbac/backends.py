"""Sign-in with a login phone number (rbac.LoginPhone) in the username field."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .phone import normalize_phone


class PhoneBackend(ModelBackend):
    """
    Lets the username field of every sign-in form -- POST /api/auth/token/
    and the Django admin -- take a login phone number instead.

    Listed after ModelBackend in AUTHENTICATION_BACKENDS, so a real username
    always wins: an older account whose username reads like a number keeps
    signing in with it, and the number's owner still gets in, because
    ModelBackend refuses their password for that other account and Django
    moves on to this backend.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        number = normalize_phone(username)
        if number is None or password is None:
            return None
        user = UserModel._default_manager.filter(login_phone__number=number).first()
        if user is None:
            # Hash anyway, as ModelBackend does: an unknown number takes as
            # long as a wrong password, so timing does not reveal which
            # numbers have accounts.
            UserModel().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

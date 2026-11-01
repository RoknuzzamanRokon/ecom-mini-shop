from django.contrib.auth import get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.utils import get_md5_hash_password

from .models import LoginPhone, StartingPassword
from .phone import INVALID_PHONE, PHONE_TAKEN, national_phone, normalize_phone
from .services import get_user_role_codes, get_user_permissions

User = get_user_model()

USERNAME_TAKEN = "A user with that username already exists."


def username_field():
    """
    The username input of every API path that creates an account: Django's
    own character rules, so the account stays editable in the Django admin
    (BUG-040). "john doe" used to be accepted, then refused by every save.
    """
    return serializers.CharField(max_length=150, required=True, validators=[UnicodeUsernameValidator()])


def create_login_account(**fields):
    """
    User.objects.create_user(), reporting a username taken by a concurrent
    request after the serializer's duplicate check as a 400 on `username`
    rather than a 500 (BUG-040).
    """
    try:
        with transaction.atomic():
            return User.objects.create_user(**fields)
    except IntegrityError:
        raise serializers.ValidationError({"username": [USERNAME_TAKEN]})


def create_login_phone(user, number):
    """
    LoginPhone.objects.create(), reporting a number taken by a concurrent
    request after the serializer's duplicate check as a 400 on `phone`.
    """
    try:
        with transaction.atomic():
            return LoginPhone.objects.create(user=user, number=number)
    except IntegrityError:
        raise serializers.ValidationError({"phone": [PHONE_TAKEN]})


def login_phone_number(user):
    """The number the account signs in with (E.164), or None."""
    login_phone = getattr(user, "login_phone", None)
    return login_phone.number if login_phone else None


class RevocationCheckingTokenRefreshSerializer(TokenRefreshSerializer):
    """SimpleJWT's refresh serializer, plus the password-change check (BUG-013).

    With CHECK_REVOKE_TOKEN, SimpleJWT compares the password-hash claim on
    access tokens only. A refresh token issued before a password change would
    keep minting access tokens that are each rejected on use, leaving the
    client half signed in, so it is refused here instead. A token whose user
    no longer exists also gets a 401, where the parent raises DoesNotExist.
    """

    def validate(self, attrs):
        refresh = self.token_class(attrs["refresh"])
        user_id = refresh.payload.get(jwt_settings.USER_ID_CLAIM)
        user = User.objects.filter(**{jwt_settings.USER_ID_FIELD: user_id}).first()
        if user is None:
            raise InvalidToken("No active account found for the given token.")
        if jwt_settings.CHECK_REVOKE_TOKEN and refresh.payload.get(
            jwt_settings.REVOKE_TOKEN_CLAIM
        ) != get_md5_hash_password(user.password):
            raise InvalidToken("The user's password has been changed.")
        return super().validate(attrs)


class CurrentUserSerializer(serializers.ModelSerializer):
    phone = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    must_change_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "phone",
            "first_name",
            "last_name",
            "is_staff",
            "is_superuser",
            "roles",
            "permissions",
            "must_change_password",
        ]

    def get_phone(self, obj):
        return login_phone_number(obj)

    def get_must_change_password(self, obj):
        """True while the account is on a password someone else set (StartingPassword)."""
        return StartingPassword.is_pending(obj)

    def get_roles(self, obj):
        return sorted(list(get_user_role_codes(obj)))

    def get_permissions(self, obj):
        return sorted(list(get_user_permissions(obj)))


class CustomerRegistrationSerializer(serializers.Serializer):
    """
    Public customer registration serializer.
    Enforces strict anti-escalation, uniqueness, and password validation,
    and assigns the default CUSTOMER RBAC role.

    The account needs an email address or a Bangladeshi mobile number (or
    both). A number becomes the account's LoginPhone, so the customer can
    later sign in with it in place of the username.
    """
    FORBIDDEN_FIELDS = {
        "role",
        "roles",
        "permissions",
        "is_staff",
        "is_superuser",
        "is_active",
    }

    username = username_field()
    email = serializers.EmailField(max_length=254, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        # 1. Anti-escalation check: reject any attempt to pass privileged or administrative fields
        for forbidden in self.FORBIDDEN_FIELDS:
            if forbidden in self.initial_data:
                raise serializers.ValidationError(
                    {forbidden: f"Field '{forbidden}' cannot be provided during customer registration."}
                )

        # 2. Username validation & uniqueness (case-insensitive)
        username = attrs.get("username", "").strip()
        if not username:
            raise serializers.ValidationError({"username": "Username cannot be empty."})
        # The sign-in field takes a username or a phone number, so a username
        # that reads as a number would make "which account?" ambiguous.
        if normalize_phone(username):
            raise serializers.ValidationError({"username": "A username cannot be a phone number."})
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError({"username": USERNAME_TAKEN})
        attrs["username"] = username

        # 3. An email address or a mobile number, each unused (email case-insensitive)
        email = attrs.get("email", "").strip().lower()
        raw_phone = attrs.get("phone", "").strip()
        if not email and not raw_phone:
            raise serializers.ValidationError("Enter an email address or a mobile number.")
        if email and User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError({"email": "A user with that email already exists."})
        attrs["email"] = email

        phone = None
        if raw_phone:
            phone = normalize_phone(raw_phone)
            if phone is None:
                raise serializers.ValidationError({"phone": INVALID_PHONE})
            if LoginPhone.objects.filter(number=phone).exists():
                raise serializers.ValidationError({"phone": PHONE_TAKEN})
            # OTP goes here once an SMS provider is set up: require the code
            # sent to this number, and stamp LoginPhone.verified_at in create().
        attrs["phone"] = phone

        # 4. Password confirmation check
        password = attrs.get("password")
        password_confirm = attrs.get("password_confirm")
        if password != password_confirm:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})

        # 5. Standard Django password policy validation
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        temp_user = User(username=username, email=email)
        try:
            validate_password(password, user=temp_user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

        return attrs

    def create(self, validated_data):
        from .models import Role
        from .services import assign_user_role

        with transaction.atomic():
            user = create_login_account(
                username=validated_data["username"],
                email=validated_data["email"],
                password=validated_data["password"],
                first_name=validated_data.get("first_name", "").strip(),
                last_name=validated_data.get("last_name", "").strip(),
            )
            phone = validated_data["phone"]
            if phone:
                create_login_phone(user, phone)

            # Ensure the user has the default CUSTOMER RBAC role
            assign_user_role(user, Role.ROLE_CUSTOMER)

            # Ensure customer profile is initialized
            try:
                from customers.services import CustomerService
                profile = CustomerService.get_or_create_profile(user)
                # The sign-in number is also the contact number until the
                # customer sets another one in their profile.
                if phone and not profile.phone:
                    profile.phone = national_phone(phone)
                    profile.save(update_fields=["phone", "updated_at"])
            except Exception:
                pass

            return user


class CustomerRegistrationResponseSerializer(serializers.ModelSerializer):
    phone = serializers.SerializerMethodField()
    message = serializers.CharField(default="Account created successfully.")

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "phone",
            "first_name",
            "last_name",
            "message",
        ]

    def get_phone(self, obj):
        return login_phone_number(obj)



class PasswordChangeSerializer(serializers.Serializer):
    """
    Authenticated self-service password change.
    """
    current_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True)
    new_password_confirm = serializers.CharField(write_only=True, required=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        # A starting password (StartingPassword) is known to whoever set it,
        # so "changing" it to itself would keep it.
        if attrs["new_password"] == attrs["current_password"]:
            raise serializers.ValidationError(
                {"new_password": "Choose a password different from your current one."}
            )

        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validate_password(attrs["new_password"], user=self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})

        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        with transaction.atomic():
            user.set_password(self.validated_data["new_password"])
            user.save(update_fields=["password"])
            StartingPassword.objects.filter(user=user, replaced_at__isnull=True).update(replaced_at=timezone.now())
        return user

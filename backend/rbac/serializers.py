from django.contrib.auth import get_user_model
from rest_framework import serializers
from .services import get_user_role_codes, get_user_permissions

User = get_user_model()


class CurrentUserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "is_superuser",
            "roles",
            "permissions",
        ]

    def get_roles(self, obj):
        return sorted(list(get_user_role_codes(obj)))

    def get_permissions(self, obj):
        return sorted(list(get_user_permissions(obj)))


class CustomerRegistrationSerializer(serializers.Serializer):
    """
    Public customer registration serializer.
    Enforces strict anti-escalation, uniqueness, and password validation,
    and assigns the default CUSTOMER RBAC role.
    """
    FORBIDDEN_FIELDS = {
        "role",
        "roles",
        "permissions",
        "is_staff",
        "is_superuser",
        "is_active",
    }

    username = serializers.CharField(max_length=150, required=True)
    email = serializers.EmailField(max_length=254, required=True)
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
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError({"username": "A user with that username already exists."})
        attrs["username"] = username

        # 3. Email validation & uniqueness (case-insensitive)
        email = attrs.get("email", "").strip().lower()
        if not email:
            raise serializers.ValidationError({"email": "Email cannot be empty."})
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError({"email": "A user with that email already exists."})
        attrs["email"] = email

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
        from django.db import transaction
        from .models import Role
        from .services import assign_user_role

        with transaction.atomic():
            user = User.objects.create_user(
                username=validated_data["username"],
                email=validated_data["email"],
                password=validated_data["password"],
                first_name=validated_data.get("first_name", "").strip(),
                last_name=validated_data.get("last_name", "").strip(),
            )
            # Ensure the user has the default CUSTOMER RBAC role
            assign_user_role(user, Role.ROLE_CUSTOMER)

            # Ensure customer profile is initialized
            try:
                from customers.services import CustomerService
                CustomerService.get_or_create_profile(user)
            except Exception:
                pass

            return user


class CustomerRegistrationResponseSerializer(serializers.ModelSerializer):
    message = serializers.CharField(default="Account created successfully.")

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "message",
        ]



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

        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            validate_password(attrs["new_password"], user=self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})

        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user

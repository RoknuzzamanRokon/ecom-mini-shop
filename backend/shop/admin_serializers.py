# admin_serializers.py
"""
Dedicated serializers for Admin & Platform Governance APIs.
Strictly excludes sensitive fields (passwords, hashes, tokens, auth secrets).
Provides safe representations for Users, Roles, Sellers, Shops, Products, Categories, and Customers.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model

from rbac.models import Role, Permission, UserRole
from rbac.services import get_user_permissions, get_user_role_codes
from sellers.models import SellerProfile
from shops.models import Shop
from shop.models import Category, Product, Order
from customers.models import CustomerProfile, Address
from audit.models import AuditLog

User = get_user_model()

PROTECTED_ROLE_CODES = {Role.ROLE_SUPER_ADMINISTRATOR, Role.ROLE_ADMINISTRATOR}


# ==============================================================================
# USER ADMIN SERIALIZERS
# ==============================================================================

class AdminUserListSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    customer_profile_id = serializers.SerializerMethodField()
    seller_profile_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "roles",
            "customer_profile_id",
            "seller_profile_id",
            "date_joined",
            "last_login",
        ]
        read_only_fields = fields

    def get_roles(self, obj):
        return sorted(list(get_user_role_codes(obj)))

    def get_customer_profile_id(self, obj):
        return obj.customer_profile.id if hasattr(obj, "customer_profile") else None

    def get_seller_profile_id(self, obj):
        return obj.seller_profile.id if hasattr(obj, "seller_profile") else None


class AdminUserDetailSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    has_full_platform_access = serializers.SerializerMethodField()
    customer_profile = serializers.SerializerMethodField()
    seller_profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "roles",
            "permissions",
            "has_full_platform_access",
            "customer_profile",
            "seller_profile",
            "date_joined",
            "last_login",
        ]
        read_only_fields = fields

    def get_roles(self, obj):
        return sorted(list(get_user_role_codes(obj)))

    def get_permissions(self, obj):
        """
        The user's EFFECTIVE MiniShop permissions, resolved by the one and only
        resolver the API authorization layer itself uses
        (rbac.services.get_user_permissions). The console displays this set; it
        never recomputes it from roles, which would make the frontend a second
        source of truth for authorization.

        The "*" wildcard is stripped: it is a full-access marker, not an
        assignable permission, and is reported separately by
        has_full_platform_access so a client cannot mistake it for a real grant.
        """
        return sorted(code for code in get_user_permissions(obj) if code != "*")

    def get_has_full_platform_access(self, obj):
        """True when this account resolves to the wildcard ("*") permission."""
        return "*" in get_user_permissions(obj)

    def get_customer_profile(self, obj):
        if not hasattr(obj, "customer_profile"):
            return None
        cp = obj.customer_profile
        return {
            "id": cp.id,
            "display_name": cp.display_name,
            "phone": cp.phone,
            "gender": cp.gender,
        }

    def get_seller_profile(self, obj):
        if not hasattr(obj, "seller_profile"):
            return None
        sp = obj.seller_profile
        return {
            "id": sp.id,
            "business_name": sp.business_name,
            "business_email": sp.business_email,
            "business_phone": sp.business_phone,
            "seller_type": sp.seller_type,
            "status": sp.status,
            "is_operational": sp.is_operational,
        }


class AdminUserCreateSerializer(serializers.Serializer):
    """
    Admin-governed user creation (POST /api/admin/users/).

    Deliberately NOT built on CustomerRegistrationSerializer: that serializer is
    a PUBLIC endpoint's contract. It forbids any privileged field outright and
    hardcodes the CUSTOMER role, because an anonymous caller must never
    influence either. An authorized administrator legitimately needs to set
    is_active and assign roles, so applying the public rules here would make the
    endpoint useless, and relaxing them there would weaken public registration.
    The two therefore stay separate on purpose.

    What IS shared with public registration is the account-quality policy —
    case-insensitive uniqueness of username and email, password confirmation,
    and Django's configured password validators — because those protect the
    account itself rather than the privilege boundary.

    `roles` and `is_active` are validated here only for shape. WHICH roles this
    actor may grant is an authorization decision and is enforced in the view,
    against the same rules as AdminUserDetailAPIView.patch.
    """

    username = serializers.CharField(max_length=150, required=True)
    email = serializers.EmailField(max_length=254, required=True)
    password = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )
    password_confirm = serializers.CharField(
        write_only=True, required=True, style={"input_type": "password"}
    )
    first_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    last_name = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    is_active = serializers.BooleanField(required=False, default=True)
    roles = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list,
        help_text="Role codes to assign atomically with creation.",
    )
    reason = serializers.CharField(
        required=True,
        max_length=500,
        help_text="Required justification for the administrative creation.",
    )

    def validate_username(self, value):
        username = value.strip()
        if not username:
            raise serializers.ValidationError("Username cannot be empty.")
        if User.objects.filter(username__iexact=username).exists():
            raise serializers.ValidationError("A user with that username already exists.")
        return username

    def validate_email(self, value):
        email = value.strip().lower()
        if not email:
            raise serializers.ValidationError("Email cannot be empty.")
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("A user with that email already exists.")
        return email

    def validate(self, attrs):
        if attrs.get("password") != attrs.get("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )

        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError

        temp_user = User(username=attrs["username"], email=attrs["email"])
        try:
            validate_password(attrs["password"], user=temp_user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

        # Duplicate role codes would make the assignment diff ambiguous.
        attrs["roles"] = sorted(set(attrs.get("roles", [])))
        return attrs


class AdminUserUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=False)
    roles = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        help_text="List of role codes to assign to the user.",
    )
    reason = serializers.CharField(
        required=True,
        max_length=500,
        help_text="Required justification for the administrative modification.",
    )


# ==============================================================================
# ROLE ADMIN SERIALIZERS
# ==============================================================================

class AdminRoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    user_count = serializers.SerializerMethodField()
    is_protected = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            "id",
            "code",
            "name",
            "description",
            "is_active",
            "is_protected",
            "permissions",
            "user_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_protected", "user_count", "created_at", "updated_at"]

    def get_permissions(self, obj):
        return list(obj.permissions.values_list("code", flat=True))

    def get_user_count(self, obj):
        return obj.user_roles.filter(is_active=True).count()

    def get_is_protected(self, obj):
        return obj.code in PROTECTED_ROLE_CODES


class AdminRoleCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    permissions = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
    )
    reason = serializers.CharField(required=True, max_length=500)

    def validate_code(self, value):
        code = value.strip().upper()
        if code in PROTECTED_ROLE_CODES:
            raise serializers.ValidationError(f"Cannot create role with protected code '{code}'.")
        if Role.objects.filter(code=code).exists():
            raise serializers.ValidationError(f"Role with code '{code}' already exists.")
        return code


class AdminRoleUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)
    permissions = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
    )
    reason = serializers.CharField(required=True, max_length=500)


# ==============================================================================
# PERMISSION CATALOGUE SERIALIZER
# ==============================================================================

class AdminPermissionSerializer(serializers.ModelSerializer):
    """
    Read-only projection of one rbac.Permission for the role permission
    selector, plus whether the REQUESTING user may delegate it.

    `is_delegatable` is supplied by the view from
    rbac.services.get_delegatable_permission_codes(request.user) — the same
    boundary the role create/update endpoints enforce — so it is a property of
    the (actor, permission) pair, not of the permission itself.
    """

    is_delegatable = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = [
            "id",
            "code",
            "name",
            "resource",
            "action",
            "description",
            "is_delegatable",
        ]
        read_only_fields = fields

    def get_is_delegatable(self, obj):
        return obj.code in self.context.get("delegatable_codes", set())


# ==============================================================================
# SELLER ADMIN SERIALIZERS
# ==============================================================================

class AdminSellerSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    shops_count = serializers.SerializerMethodField()

    class Meta:
        model = SellerProfile
        fields = [
            "id",
            "username",
            "email",
            "business_name",
            "business_email",
            "business_phone",
            "seller_type",
            "status",
            "tax_id",
            "description",
            "rejection_reason",
            "suspension_reason",
            "is_operational",
            "shops_count",
            "reviewed_at",
            "approved_at",
            "suspended_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_shops_count(self, obj):
        return obj.shops.count()


class AdminSellerCreateSerializer(serializers.Serializer):
    """
    Admin-governed SellerProfile creation for an EXISTING user
    (POST /api/admin/sellers/).

    Distinct from SellerRegistrationSerializer, which always targets
    request.user and cannot express "create a profile for someone else". The
    business field set is identical on purpose; only `user_id` and the
    governance `reason` are added.

    Seller-type validity, the initial status and the one-profile-per-user rule
    are NOT re-implemented here — they belong to SellerProfile.full_clean() and
    sellers.services.create_seller_profile, which this endpoint calls. The
    `user_id` check below exists so a bad reference fails as a clean 400 field
    error rather than surfacing from deeper in the stack.
    """

    user_id = serializers.IntegerField(
        required=True,
        help_text="Primary key of the existing user to attach the seller profile to.",
    )
    business_name = serializers.CharField(max_length=200, required=True)
    seller_type = serializers.ChoiceField(
        choices=[choice[0] for choice in SellerProfile.SELLER_TYPE_CHOICES],
        required=False,
        default=SellerProfile.TYPE_FULL_SHOP_OWNER,
    )
    business_email = serializers.EmailField(required=False, allow_blank=True, default="")
    business_phone = serializers.CharField(
        max_length=30, required=False, allow_blank=True, default=""
    )
    tax_id = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    description = serializers.CharField(required=False, allow_blank=True, default="")
    reason = serializers.CharField(
        required=True,
        max_length=500,
        help_text="Required justification for the administrative creation.",
    )

    def validate_user_id(self, value):
        if not User.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f"No user exists with id {value}.")
        return value

    def validate_business_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Business name cannot be empty.")
        return name


class AdminSellerStatusUpdateSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["approve", "reject", "suspend", "reactivate"],
        help_text="Target lifecycle transition for the seller.",
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500,
        help_text="Reason for rejection or suspension (required for those actions).",
    )

    def validate(self, attrs):
        action = attrs.get("action")
        reason = attrs.get("reason", "").strip()
        if action in ("reject", "suspend") and not reason:
            raise serializers.ValidationError(
                {"reason": f"A reason is required when {action}ing a seller."}
            )
        return attrs


# ==============================================================================
# SHOP ADMIN SERIALIZERS
# ==============================================================================

class AdminShopSerializer(serializers.ModelSerializer):
    owner_id = serializers.IntegerField(source="owner.id", read_only=True)
    owner_business_name = serializers.CharField(source="owner.business_name", read_only=True)
    products_count = serializers.SerializerMethodField()

    class Meta:
        model = Shop
        fields = [
            "id",
            "owner_id",
            "owner_business_name",
            "name",
            "slug",
            "description",
            "phone",
            "address",
            "status",
            "rejection_reason",
            "suspension_reason",
            "products_count",
            "reviewed_at",
            "approved_at",
            "suspended_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_products_count(self, obj):
        return obj.products.count()


class AdminShopCreateSerializer(serializers.Serializer):
    """
    Admin-governed Shop creation with immediate owner assignment
    (POST /api/admin/shops/), completing the Admin-created Shop Owner model:
    an administrator creates/approves a Seller, then creates a Shop and
    assigns that Seller as its owner in the same step.

    Seller eligibility (operational status, the PRODUCT_OWNER restriction,
    and the LIMITED_SHOP_OWNER single-shop cap) is NOT re-implemented here —
    it belongs to shops.services.ShopService.create_shop /
    validate_seller_eligibility_for_creation, which this endpoint calls, so
    the same rule applies whether a shop is self-created by a seller or
    assigned by an administrator.
    """

    seller_id = serializers.IntegerField(
        required=True,
        help_text="Primary key of the SellerProfile to assign as this shop's owner.",
    )
    name = serializers.CharField(max_length=200, required=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    address = serializers.CharField(required=False, allow_blank=True, default="")
    latitude = serializers.FloatField(required=False, allow_null=True, default=None)
    longitude = serializers.FloatField(required=False, allow_null=True, default=None)
    reason = serializers.CharField(
        required=True,
        max_length=500,
        help_text="Required justification for the administrative shop creation.",
    )

    def validate_seller_id(self, value):
        if not SellerProfile.objects.filter(pk=value).exists():
            raise serializers.ValidationError(f"No seller profile exists with id {value}.")
        return value

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Shop name cannot be empty.")
        return name

    def validate(self, attrs):
        lat = attrs.get("latitude")
        lng = attrs.get("longitude")
        if (lat is not None and lng is None) or (lat is None and lng is not None):
            raise serializers.ValidationError("Both latitude and longitude must be provided together.")
        return attrs


class AdminShopStatusUpdateSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["approve", "reject", "suspend", "reactivate"],
        help_text="Target lifecycle transition for the shop.",
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500,
        help_text="Reason for rejection or suspension.",
    )

    def validate(self, attrs):
        action = attrs.get("action")
        reason = attrs.get("reason", "").strip()
        if action in ("reject", "suspend") and not reason:
            raise serializers.ValidationError(
                {"reason": f"A reason is required when {action}ing a shop."}
            )
        return attrs


# ==============================================================================
# PRODUCT ADMIN SERIALIZERS
# ==============================================================================

class AdminProductSerializer(serializers.ModelSerializer):
    category_id = serializers.IntegerField(source="category.id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    shop_id = serializers.IntegerField(source="shop.id", read_only=True)
    shop_name = serializers.CharField(source="shop.name", read_only=True)
    seller_business_name = serializers.SerializerMethodField()
    is_publicly_visible = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "category_id",
            "category_name",
            "shop_id",
            "shop_name",
            "seller_business_name",
            "price",
            "old_price",
            "stock",
            "badge",
            "is_active",
            "status",
            "rejection_reason",
            "is_publicly_visible",
            "submitted_at",
            "reviewed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_seller_business_name(self, obj):
        return obj.shop.owner.business_name if obj.shop and obj.shop.owner else None


class AdminProductStatusUpdateSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=["approve", "reject", "publish", "unpublish"],
        help_text="Target lifecycle transition for the product.",
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500,
        help_text="Reason for rejection (required when rejecting).",
    )

    def validate(self, attrs):
        action = attrs.get("action")
        reason = attrs.get("reason", "").strip()
        if action == "reject" and not reason:
            raise serializers.ValidationError(
                {"reason": "A reason is required when rejecting a product."}
            )
        return attrs


# ==============================================================================
# CATEGORY ADMIN SERIALIZERS
# ==============================================================================

class AdminCategorySerializer(serializers.ModelSerializer):
    products_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "icon",
            "image",
            "description",
            "is_active",
            "products_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "products_count", "created_at", "updated_at"]

    def get_products_count(self, obj):
        return obj.products.count()


# ==============================================================================
# CUSTOMER ADMIN SERIALIZERS (READ-ONLY)
# ==============================================================================

class AdminCustomerListSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    orders_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomerProfile
        fields = [
            "id",
            "user_id",
            "username",
            "email",
            "display_name",
            "phone",
            "gender",
            "is_active",
            "orders_count",
            "created_at",
        ]
        read_only_fields = fields

    def get_orders_count(self, obj):
        return Order.objects.filter(user=obj.user).count()


class AdminCustomerDetailSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)
    date_joined = serializers.DateTimeField(source="user.date_joined", read_only=True)
    addresses = serializers.SerializerMethodField()
    recent_orders = serializers.SerializerMethodField()
    orders_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomerProfile
        fields = [
            "id",
            "user_id",
            "username",
            "email",
            "first_name",
            "last_name",
            "display_name",
            "phone",
            "gender",
            "date_of_birth",
            "is_active",
            "date_joined",
            "addresses",
            "orders_count",
            "recent_orders",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_addresses(self, obj):
        addresses_qs = Address.objects.filter(user=obj.user).order_by("-is_default", "-id")
        return [
            {
                "id": addr.id,
                "label": addr.label,
                "recipient_name": addr.recipient_name,
                "phone": addr.phone,
                "address_line_1": addr.address_line_1,
                "city": addr.city,
                "is_default": addr.is_default,
            }
            for addr in addresses_qs
        ]

    def get_orders_count(self, obj):
        return Order.objects.filter(user=obj.user).count()

    def get_recent_orders(self, obj):
        orders_qs = Order.objects.filter(user=obj.user).order_by("-created_at")[:5]
        return [
            {
                "id": o.id,
                "order_number": o.order_number,
                "status": o.status,
                "total_amount": str(o.total_amount),
                "created_at": o.created_at.isoformat(),
            }
            for o in orders_qs
        ]


# ==============================================================================
# AUDIT LOG ADMIN SERIALIZERS
# ==============================================================================

class AuditActorSerializer(serializers.ModelSerializer):
    """
    Safe read-only representation of user who initiated audit event.
    Strictly excludes sensitive auth/credential attributes.
    """
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
        ]
        read_only_fields = fields

    def get_full_name(self, obj):
        name = f"{obj.first_name} {obj.last_name}".strip()
        return name if name else obj.username


class AdminAuditLogSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for platform governance audit inspection.
    Exposes actor, action, target, metadata payload, IP, and timestamp.
    Sanitizes and redacts any sensitive credential keys within payload metadata.
    """
    actor = AuditActorSerializer(read_only=True)
    resource_type = serializers.CharField(source="target_type", read_only=True)
    resource_id = serializers.CharField(source="target_id", read_only=True)
    changes = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor",
            "action",
            "target_type",
            "resource_type",
            "target_id",
            "resource_id",
            "target_repr",
            "shop",
            "seller",
            "metadata",
            "changes",
            "ip_address",
            "created_at",
        ]
        read_only_fields = fields

    def get_changes(self, obj):
        return self._sanitize_data(obj.metadata or {})

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        ret["metadata"] = self._sanitize_data(ret.get("metadata") or {})
        return ret

    def _sanitize_data(self, data):
        if not isinstance(data, dict):
            return data
        SENSITIVE_KEYS = {"password", "token", "secret", "card", "cvv", "key", "authorization", "auth"}
        sanitized = {}
        for k, v in data.items():
            if any(s in str(k).lower() for s in SENSITIVE_KEYS):
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, dict):
                sanitized[k] = self._sanitize_data(v)
            else:
                sanitized[k] = v
        return sanitized

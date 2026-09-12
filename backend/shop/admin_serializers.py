# admin_serializers.py
"""
Dedicated serializers for Admin & Platform Governance APIs.
Strictly excludes sensitive fields (passwords, hashes, tokens, auth secrets).
Provides safe representations for Users, Roles, Sellers, Shops, Products, Categories, and Customers.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model

from rbac.models import Role, Permission, UserRole
from rbac.services import get_user_role_codes
from sellers.models import SellerProfile
from shops.models import Shop
from shop.models import Category, Product, Order
from customers.models import CustomerProfile, Address

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
            "customer_profile",
            "seller_profile",
            "date_joined",
            "last_login",
        ]
        read_only_fields = fields

    def get_roles(self, obj):
        return sorted(list(get_user_role_codes(obj)))

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

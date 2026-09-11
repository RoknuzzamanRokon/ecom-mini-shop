from decimal import Decimal
from rest_framework import serializers

from .models import Address, CustomerProfile


class CustomerProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for viewing customer profile and account details.
    """
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

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
            "avatar",
            "date_of_birth",
            "gender",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CustomerProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for modifying customer profile and associated user identity fields.
    """
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    avatar = serializers.ImageField(required=False, allow_null=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=CustomerProfile.GENDER_CHOICES,
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = CustomerProfile
        fields = [
            "first_name",
            "last_name",
            "display_name",
            "phone",
            "avatar",
            "date_of_birth",
            "gender",
        ]


class AddressSerializer(serializers.ModelSerializer):
    """
    Serializer for viewing address details.
    """
    class Meta:
        model = Address
        fields = [
            "id",
            "label",
            "recipient_name",
            "phone",
            "address_line_1",
            "address_line_2",
            "area",
            "city",
            "state",
            "postal_code",
            "country",
            "latitude",
            "longitude",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AddressCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating customer delivery addresses with coordinate validation.
    """
    label = serializers.ChoiceField(
        choices=Address.LABEL_CHOICES,
        default=Address.LABEL_HOME,
        required=False,
    )
    country = serializers.CharField(max_length=100, default="Bangladesh", required=False)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    area = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True,
    )
    is_default = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = Address
        fields = [
            "label",
            "recipient_name",
            "phone",
            "address_line_1",
            "address_line_2",
            "area",
            "city",
            "state",
            "postal_code",
            "country",
            "latitude",
            "longitude",
            "is_default",
        ]

    def validate(self, attrs):
        lat = attrs.get("latitude")
        lng = attrs.get("longitude")

        # In partial updates, inspect instance if one coordinate is provided
        if self.instance:
            if "latitude" in attrs and "longitude" not in attrs:
                lng = self.instance.longitude
            elif "longitude" in attrs and "latitude" not in attrs:
                lat = self.instance.latitude

        if (lat is not None and lng is None) or (lng is not None and lat is None):
            raise serializers.ValidationError(
                "Both latitude and longitude must be provided together, or both left blank."
            )

        if lat is not None and not (Decimal("-90.0") <= Decimal(str(lat)) <= Decimal("90.0")):
            raise serializers.ValidationError({"latitude": "Latitude must be between -90 and 90 degrees."})

        if lng is not None and not (Decimal("-180.0") <= Decimal(str(lng)) <= Decimal("180.0")):
            raise serializers.ValidationError({"longitude": "Longitude must be between -180 and 180 degrees."})

        return attrs

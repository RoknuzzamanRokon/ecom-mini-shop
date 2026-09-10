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

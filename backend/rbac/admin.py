from django.contrib import admin
from django.db.models import Count
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Permission, Role, RolePermission, UserRole


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 1
    autocomplete_fields = ["permission"]


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "user_count", "permission_count", "created_at")
    list_editable = ("is_active",)
    search_fields = ("code", "name", "description")
    list_filter = ("is_active", "created_at")
    inlines = [RolePermissionInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            user_count=Count("user_roles", distinct=True),
            permission_count=Count("role_permissions", distinct=True)
        )

    def user_count(self, obj):
        return obj.user_count
    user_count.short_description = "Users"
    user_count.admin_order_field = "user_count"

    def permission_count(self, obj):
        return obj.permission_count
    permission_count.short_description = "Permissions"
    permission_count.admin_order_field = "permission_count"


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "resource", "action", "created_at")
    search_fields = ("code", "name", "resource", "action", "description")
    list_filter = ("resource", "created_at")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "is_active", "assigned_at", "assigned_by")
    list_editable = ("is_active",)
    search_fields = ("user__username", "user__email", "role__code", "role__name")
    list_filter = ("role", "is_active", "assigned_at")
    autocomplete_fields = ["user", "role"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user", "role", "assigned_by")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission", "created_at")
    search_fields = ("role__code", "role__name", "permission__code", "permission__name")
    list_filter = ("role", "permission__resource")
    autocomplete_fields = ["role", "permission"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("role", "permission")


# --- Custom User Admin ---

class UserRoleInline(admin.TabularInline):
    model = UserRole
    extra = 0
    autocomplete_fields = ["role"]
    fk_name = "user"


admin.site.unregister(User)

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_superuser",
        "is_active",
        "role_list",
        "date_joined",
        "last_login",
    )
    list_filter = (
        "is_staff",
        "is_superuser",
        "is_active",
        "date_joined",
        "user_roles__role",
    )
    search_fields = ("username", "email", "first_name", "last_name")
    inlines = [UserRoleInline]

    def role_list(self, obj):
        roles = obj.user_roles.all()
        return ", ".join([ur.role.code for ur in roles if ur.is_active])
    
    role_list.short_description = "Roles"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("user_roles__role")

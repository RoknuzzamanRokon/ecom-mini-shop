from django.contrib import admin
from .models import Permission, Role, RolePermission, UserRole


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 1
    autocomplete_fields = ["permission"]


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "created_at")
    list_editable = ("is_active",)
    search_fields = ("code", "name", "description")
    list_filter = ("is_active", "created_at")
    inlines = [RolePermissionInline]


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


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission", "created_at")
    search_fields = ("role__code", "role__name", "permission__code", "permission__name")
    list_filter = ("role", "permission__resource")
    autocomplete_fields = ["role", "permission"]

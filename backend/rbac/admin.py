from django.contrib import admin
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.db.models import Count
from django.contrib.auth.models import Permission as AuthPermission, User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import Permission, Role, RolePermission, UserRole
from .widgets import GroupCardsWidget, PermissionMatrixWidget


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
    verbose_name = _("role assignment")
    verbose_name_plural = _("Role assignments")


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

    # The two-pane FilteredSelectMultiple is replaced by the permission board in
    # templates/admin/auth/user/change_form.html, so the horizontal filter that
    # BaseUserAdmin declares would only load selector.js for nothing.
    filter_horizontal = ()

    # `classes` is the routing key the change form reads: each fieldset is placed
    # in the tab (or, for the status switches, the identity hero) named here.
    # Unclassified fieldsets fall through to the Account tab, which is what keeps
    # BaseUserAdmin.add_fieldsets working untouched on the add view.
    fieldsets = (
        (_("Sign-in"), {
            "fields": ("username", "password"),
            "classes": ("mp-pane-account",),
        }),
        (_("Personal information"), {
            "fields": ("first_name", "last_name", "email"),
            "classes": ("mp-pane-account",),
        }),
        (_("Activity"), {
            "fields": ("last_login", "date_joined"),
            "classes": ("mp-pane-account",),
        }),
        (_("Account status"), {
            "fields": ("is_active", "is_staff", "is_superuser"),
            "classes": ("mp-pane-status",),
        }),
        (_("Admin panel permissions"), {
            "fields": ("user_permissions",),
            "classes": ("mp-pane-permissions",),
        }),
        (_("Permission groups"), {
            "fields": ("groups",),
            "classes": ("mp-pane-roles",),
        }),
    )

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "user_permissions":
            kwargs["widget"] = PermissionMatrixWidget()
            # The widget groups on content_type, so fetch it in the same query
            # and hand the rows over already sorted the way the board reads.
            kwargs["queryset"] = AuthPermission.objects.select_related(
                "content_type"
            ).order_by("content_type__app_label", "content_type__model", "codename")
        elif db_field.name == "groups":
            kwargs["widget"] = GroupCardsWidget()
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        # ModelAdmin wraps every related field in RelatedFieldWidgetWrapper for
        # the "add another" affordances. On a board of 120 checkboxes those links
        # have nothing to point at, and the wrapper's <div> breaks the grid.
        if db_field.name in ("user_permissions", "groups") and isinstance(
            getattr(formfield, "widget", None), RelatedFieldWidgetWrapper
        ):
            formfield.widget = formfield.widget.widget
        return formfield

    def role_list(self, obj):
        roles = obj.user_roles.all()
        return ", ".join([ur.role.code for ur in roles if ur.is_active])
    
    role_list.short_description = "Roles"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.prefetch_related("user_roles__role")

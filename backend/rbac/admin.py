from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.db.models import Count
from django.contrib.auth.models import Permission as AuthPermission, User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm as BaseUserChangeForm
from django.utils.translation import gettext_lazy as _
from .models import Permission, Role, RolePermission, UserPermission, UserRole
from .services import get_user_role_codes
from .widgets import (
    GroupCardsWidget,
    MiniShopPermissionWidget,
    PermissionMatrixWidget,
    render_minishop_permission_board,
)

#: Field name for the direct-grant board. Not a model field on auth.User --
#: it is handled by MiniShopUserChangeForm and persisted in save_related().
DIRECT_PERMS_FIELD = "minishop_direct_permissions"


def can_edit_minishop_permissions(user):
    """
    Who may grant a MiniShop permission directly to one account.

    Restricted to superusers / SUPER_ADMINISTRATOR. A direct grant bypasses the
    role catalogue entirely, so anyone able to make one can hand out any code in
    the system; keeping it to the tier that already has unrestricted access
    means the control adds no new escalation path. Everyone else keeps the
    read-only board.
    """
    if user is None or not user.is_authenticated:
        return False
    return user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user)


class MiniShopUserChangeForm(BaseUserChangeForm):
    """
    Adds the direct-grant board to the user change form.

    The field is NOT a model field, so nothing is written on form.save(); it is
    diffed against UserPermission in UserAdmin.save_related(). Only permissions
    the user does not already inherit from a role can be submitted -- inherited
    checkboxes render disabled, and a disabled checkbox posts nothing.
    """

    minishop_direct_permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.none(),
        required=False,
        label=_("MiniShop management permissions"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields[DIRECT_PERMS_FIELD]
        field.queryset = Permission.objects.all()
        field.widget = MiniShopPermissionWidget(user=self.instance)
        if self.instance and self.instance.pk:
            self.initial[DIRECT_PERMS_FIELD] = list(
                UserPermission.objects.filter(
                    user=self.instance, is_active=True
                ).values_list("permission_id", flat=True)
            )


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


@admin.register(UserPermission)
class UserPermissionAdmin(admin.ModelAdmin):
    """
    Direct per-user grants, listed the same way UserRole assignments are.

    The user change form is the usual way to make these, but having them here
    too means every exception is searchable, filterable and revocable in one
    place -- useful when auditing why an account can do something its roles do
    not explain.
    """
    list_display = ("user", "permission", "is_active", "granted_at", "granted_by", "note")
    list_editable = ("is_active",)
    search_fields = (
        "user__username",
        "user__email",
        "permission__code",
        "permission__name",
        "note",
    )
    list_filter = ("is_active", "permission__resource", "granted_at")
    autocomplete_fields = ["user", "permission"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user", "permission", "granted_by")


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
        (_("MiniShop management permissions"), {
            "fields": ("minishop_permissions",),
            "classes": ("mp-pane-roles",),
            "description": _(
                "Effective permissions enforced by the MiniShop API and "
                "Management Console. Read-only: they are granted by role, so "
                "edit the role assignments below to change them."
            ),
        }),
    )

    form = MiniShopUserChangeForm

    # The fallback board reports what the RBAC tables say; it never writes.
    readonly_fields = ("minishop_permissions",)

    @admin.display(description=_("MiniShop management permissions"))
    def minishop_permissions(self, obj=None):
        """
        Read-only view of the user's effective rbac.Permission codes, shown to
        operators who may not grant them (see can_edit_minishop_permissions).

        Permissions reach a user by two routes -- inherited through
        User -> UserRole -> Role -> RolePermission, or granted directly as a
        UserPermission row. This board shows both and attributes the inherited
        ones to their role.
        """
        return render_minishop_permission_board(obj)

    def get_fieldsets(self, request, obj=None):
        """
        Swap the read-only board for the editable one, for superusers only.

        The add view keeps BaseUserAdmin.add_fieldsets untouched: there is no
        user yet, so there is nothing to grant to.
        """
        fieldsets = super().get_fieldsets(request, obj)
        if obj is None or not can_edit_minishop_permissions(request.user):
            return fieldsets

        swapped = []
        for name, options in fieldsets:
            fields = options.get("fields", ())
            if "minishop_permissions" in fields:
                options = {
                    **options,
                    "fields": tuple(
                        DIRECT_PERMS_FIELD if f == "minishop_permissions" else f
                        for f in fields
                    ),
                }
            swapped.append((name, options))
        return swapped

    def save_related(self, request, form, formsets, change):
        """
        Persist the direct grants after the role inline has been written.

        Ordering matters: the inline is saved by super() first, so a role added
        in the same POST is already in effect and its permissions correctly read
        as inherited rather than being duplicated as direct grants.

        Revoking sets is_active=False rather than deleting, matching UserRole,
        so the grant history and its granted_by/granted_at survive.
        """
        super().save_related(request, form, formsets, change)

        # Re-checked server-side: the fieldset swap above is a UI affordance,
        # not the security boundary. A hand-crafted POST from a non-superuser
        # reaches here and must be ignored.
        if not can_edit_minishop_permissions(request.user):
            return
        if DIRECT_PERMS_FIELD not in form.fields:
            return

        user = form.instance
        submitted = {p.pk for p in form.cleaned_data.get(DIRECT_PERMS_FIELD, [])}

        # Anything the roles already grant is not an exception, so it never
        # becomes a direct row even if a crafted POST asserts it.
        inherited_ids = set(
            Permission.objects.filter(
                role_permissions__role__user_roles__user=user,
                role_permissions__role__user_roles__is_active=True,
                role_permissions__role__is_active=True,
            ).values_list("id", flat=True)
        )
        submitted -= inherited_ids

        existing = {
            row.permission_id: row
            for row in UserPermission.objects.filter(user=user)
        }

        for permission_id in submitted:
            row = existing.get(permission_id)
            if row is None:
                UserPermission.objects.create(
                    user=user,
                    permission_id=permission_id,
                    granted_by=request.user,
                )
            elif not row.is_active:
                row.is_active = True
                row.granted_by = request.user
                row.save(update_fields=["is_active", "granted_by"])

        for permission_id, row in existing.items():
            if row.is_active and permission_id not in submitted:
                row.is_active = False
                row.save(update_fields=["is_active"])

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

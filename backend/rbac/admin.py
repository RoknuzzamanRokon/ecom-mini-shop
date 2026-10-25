from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper
from django.db.models import Count
from django.contrib.auth.models import Group, Permission as AuthPermission, User
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin, UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm as BaseUserChangeForm
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from .models import Permission, Role, RolePermission, UserPermission, UserRole
from .services import (
    LOCKED_ROLE_CODES,
    PROTECTED_ROLE_CODES,
    get_delegatable_permission_codes,
    get_user_management_denial,
    get_user_permissions,
    get_user_role_codes,
    has_wildcard_delegation,
)
from .widgets import (
    GroupCardsWidget,
    MiniShopPermissionWidget,
    PermissionMatrixWidget,
    RolePermissionWidget,
    render_minishop_permission_board,
)

#: Field name for the direct-grant board. Not a model field on auth.User --
#: it is handled by MiniShopUserChangeForm and persisted in save_related().
DIRECT_PERMS_FIELD = "minishop_direct_permissions"

#: Field name for the role permission board. Role.permissions goes through
#: RolePermission, which keeps it out of the ModelForm entirely, so this is a
#: plain declared field on RoleAdminForm persisted in RoleAdmin.save_related().
ROLE_PERMS_FIELD = "role_permissions"


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


class WildcardOnlyWritesMixin:
    """
    Add, change and delete for wildcard holders only (BUG-002).

    These admins write RBAC rows directly -- a role assignment, a direct
    grant, a role's permission, the permission catalogue itself -- so any
    write is a way to hand out any permission, the actor's own included. The
    Django model permission alone is not enough; viewing still follows it.
    Role assignments and grants for everyone else go through the Console API,
    which applies the delegation rules.
    """

    def has_add_permission(self, request, *args):
        return super().has_add_permission(request, *args) and has_wildcard_delegation(request.user)

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and has_wildcard_delegation(request.user)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and has_wildcard_delegation(request.user)


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


class RoleAdminForm(forms.ModelForm):
    """
    Adds the permission board to the role add/change form.

    `Role.permissions` is a ManyToManyField through RolePermission, which Django
    leaves out of the generated ModelForm, so the board is a declared field:
    nothing is written on form.save(), and RoleAdmin.save_related() diffs the
    submitted set against the RolePermission rows.

    Diffing rather than clearing-and-recreating is deliberate -- an untouched
    grant keeps its original `created_at`, so the table stays a record of when
    each permission was actually added to the role.
    """

    #: Set per request by RoleAdmin.get_form; None means "no delegation limit",
    #: which is also the safe default for a form built outside the admin.
    actor = None

    role_permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.none(),
        required=False,
        label=_("Permissions"),
    )

    class Meta:
        model = Role
        fields = "__all__"

    def clean_code(self):
        """
        Only reached on add: RoleAdmin makes the code read-only afterwards,
        because permissions resolve by role code, so renaming a role into
        SUPER_ADMINISTRATOR would hand its holders the wildcard (BUG-002).
        """
        code = (self.cleaned_data.get("code") or "").strip()
        if code == "*":
            raise forms.ValidationError(_('"*" is not a role code.'))
        if code in PROTECTED_ROLE_CODES and (self.actor is None or not has_wildcard_delegation(self.actor)):
            raise forms.ValidationError(_("Only a Super Administrator can create a protected role."))
        return code

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields[ROLE_PERMS_FIELD]
        field.queryset = Permission.objects.all()

        # "You may only give away what you already hold" -- the same boundary
        # rbac.services applies to the role API. A wildcard holder (superuser /
        # SUPER_ADMINISTRATOR) is unrestricted, which is the usual case here;
        # everyone else gets the codes outside their own effective set locked.
        delegatable = None
        if self.actor is not None and not has_wildcard_delegation(self.actor):
            delegatable = get_delegatable_permission_codes(self.actor)
        field.widget = RolePermissionWidget(delegatable_codes=delegatable)

        if self.instance and self.instance.pk:
            self.initial[ROLE_PERMS_FIELD] = list(
                RolePermission.objects.filter(role=self.instance).values_list(
                    "permission_id", flat=True
                )
            )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "user_count", "permission_count", "created_at")
    list_editable = ("is_active",)
    search_fields = ("code", "name", "description")
    list_filter = ("is_active", "created_at")
    form = RoleAdminForm

    # The board replaces the RolePermission inline it used to carry: that was a
    # <select> of the whole catalogue per grant, one row at a time, with the
    # shape of the role readable only by opening every row. Individual rows are
    # still listed and auditable under RolePermissionAdmin.
    fieldsets = (
        (None, {
            "fields": ("code", "name", "description", "is_active"),
        }),
        (_("Role permissions"), {
            "fields": (ROLE_PERMS_FIELD,),
            # Routing key for admin_role_permission.css; see that file's §1.
            "classes": ("rp-fieldset",),
            "description": _(
                "Everything this role grants. Ticking a permission here gives it "
                "to every account holding the role, across the MiniShop API and "
                "the Management Console."
            ),
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = tuple(super().get_readonly_fields(request, obj))
        return readonly + ("code",) if obj is not None else readonly

    def has_change_permission(self, request, obj=None):
        """Protected roles are read-only to everyone below the wildcard."""
        if obj is not None and obj.code in LOCKED_ROLE_CODES and not has_wildcard_delegation(request.user):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        """Protected roles are never deleted here, matching the Console API."""
        if obj is not None and obj.code in LOCKED_ROLE_CODES:
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        # The changelist's bulk delete checks the model permission only.
        if queryset.filter(code__in=LOCKED_ROLE_CODES).exists():
            raise PermissionDenied("Protected roles cannot be deleted.")
        super().delete_queryset(request, queryset)

    def save_model(self, request, obj, form, change):
        """
        Re-checked here because the changelist's is_active column saves
        through this method without opening the change form.
        """
        if change and not has_wildcard_delegation(request.user):
            previous = Role.objects.filter(pk=obj.pk).values("code", "is_active").first()
            if previous and previous["code"] in LOCKED_ROLE_CODES:
                raise PermissionDenied("Only a Super Administrator can modify a protected role.")
            # Activating a role hands its permissions to every holder, so the
            # actor must hold all of them -- otherwise reactivating a role that
            # was switched off to revoke their own access would undo that.
            if previous and not previous["is_active"] and obj.is_active:
                beyond = set(obj.permissions.values_list("code", flat=True)) - get_user_permissions(request.user)
                if beyond:
                    raise PermissionDenied(
                        "Cannot activate a role that grants permissions you do not hold: "
                        + ", ".join(sorted(beyond))
                    )
        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        """
        Hand the form the operator, for the delegation boundary.

        modelform_factory builds a fresh subclass on every call, so setting the
        attribute here cannot leak between requests.
        """
        form = super().get_form(request, obj, **kwargs)
        form.actor = request.user
        return form

    def save_related(self, request, form, formsets, change):
        """
        Reconcile RolePermission with what the board submitted.

        Re-checked server-side: the locked checkboxes are a UI affordance, not
        the security boundary. A hand-crafted POST reaches here, so the actor's
        delegatable set is applied to BOTH directions -- they can neither add a
        permission they do not hold nor drop one, since a locked checkbox is
        disabled and a disabled checkbox submits nothing, which would otherwise
        read as "revoke it".
        """
        super().save_related(request, form, formsets, change)

        if ROLE_PERMS_FIELD not in form.fields:
            return

        role = form.instance
        submitted = {p.pk for p in form.cleaned_data.get(ROLE_PERMS_FIELD, [])}
        existing = set(
            RolePermission.objects.filter(role=role).values_list(
                "permission_id", flat=True
            )
        )

        if not has_wildcard_delegation(request.user):
            delegatable_ids = set(
                Permission.objects.filter(
                    code__in=get_delegatable_permission_codes(request.user)
                ).values_list("id", flat=True)
            )
            submitted &= delegatable_ids
            submitted |= existing - delegatable_ids

        added = submitted - existing
        removed = existing - submitted

        if added:
            RolePermission.objects.bulk_create(
                [
                    RolePermission(role=role, permission_id=permission_id)
                    for permission_id in sorted(added)
                ]
            )
        if removed:
            RolePermission.objects.filter(
                role=role, permission_id__in=removed
            ).delete()

    @admin.display(description=_("Permissions"))
    def role_permissions(self, obj):
        """
        What the board shows when the viewer may not edit the role (a
        protected role, below the wildcard). Django renders a read-only field
        through a ModelAdmin method of the same name.
        """
        codes = obj.permissions.order_by("code").values_list("code", flat=True) if obj else []
        return ", ".join(codes) or "-"

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


class PermissionAdminForm(forms.ModelForm):
    class Meta:
        model = Permission
        fields = "__all__"

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if code == "*":
            raise forms.ValidationError(_('"*" is the wildcard, not a permission code.'))
        return code


@admin.register(Permission)
class PermissionAdmin(WildcardOnlyWritesMixin, admin.ModelAdmin):
    list_display = ("code", "name", "resource", "action", "created_at")
    search_fields = ("code", "name", "resource", "action", "description")
    list_filter = ("resource", "created_at")
    form = PermissionAdminForm

    def get_readonly_fields(self, request, obj=None):
        # Grants and checks reference the code, so renaming a permission would
        # silently change what every holder can do.
        readonly = tuple(super().get_readonly_fields(request, obj))
        return readonly + ("code", "resource", "action") if obj is not None else readonly


@admin.register(UserRole)
class UserRoleAdmin(WildcardOnlyWritesMixin, admin.ModelAdmin):
    list_display = ("user", "role", "is_active", "assigned_at", "assigned_by")
    list_editable = ("is_active",)
    search_fields = ("user__username", "user__email", "role__code", "role__name")
    list_filter = ("role", "is_active", "assigned_at")
    autocomplete_fields = ["user", "role"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("user", "role", "assigned_by")


@admin.register(UserPermission)
class UserPermissionAdmin(WildcardOnlyWritesMixin, admin.ModelAdmin):
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
class RolePermissionAdmin(WildcardOnlyWritesMixin, admin.ModelAdmin):
    list_display = ("role", "permission", "created_at")
    search_fields = ("role__code", "role__name", "permission__code", "permission__name")
    list_filter = ("role", "permission__resource")
    autocomplete_fields = ["role", "permission"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("role", "permission")


# --- Custom User Admin ---

class UserRoleInline(WildcardOnlyWritesMixin, admin.TabularInline):
    """
    Role assignments, rendered as cards rather than Django's stock table.

    `assigned_by` is deliberately read-only and stamped in
    UserAdmin.save_formset: it records WHO made the assignment, which is an
    audit fact, not an operator choice. Leaving it editable also meant rendering
    an unfiltered <select> of every user in the system on this page.

    Each card shows what the role actually grants -- the question an operator
    has here is "what does this role give them", and the answer was previously
    nowhere on the page.
    """

    model = UserRole
    extra = 0
    # Two FKs point at AUTH_USER_MODEL (user, assigned_by), so the parent link
    # has to be named explicitly.
    fk_name = "user"
    autocomplete_fields = ["role"]
    # Only the genuinely editable fields. The card reads the permission count,
    # assigner and timestamp straight off the instance, so they need no
    # readonly_fields plumbing and no admin-rendered labels.
    fields = ("role", "is_active")
    verbose_name = _("role assignment")
    verbose_name_plural = _("Role assignments")
    template = "admin/edit_inline/mp_role.html"
    # Writes need the wildcard (WildcardOnlyWritesMixin): an inline row is a
    # role assignment, and the inline has no delegation rules of its own. Other
    # operators see the cards read-only and assign roles in the Console.

    def get_queryset(self, request):
        # The card shows the role's code, name and permission count per row.
        return super().get_queryset(request).select_related("role", "assigned_by")


admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin):
    """
    Groups carry Django-admin permissions, so editing one -- the actor's own
    included -- changes what its members may do in this admin. Superusers
    only, like the user form's group and permission fields.
    """

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


#: Fields on the user form that decide Django-admin access. Read-only for
#: everyone but superusers, or auth.change_user would be a path to any
#: permission, superuser status included (BUG-002 (f)).
SUPERUSER_ONLY_USER_FIELDS = ("is_superuser", "is_staff", "user_permissions", "groups")


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

    def get_readonly_fields(self, request, obj=None):
        readonly = tuple(super().get_readonly_fields(request, obj))
        if request.user.is_superuser:
            return readonly
        return readonly + SUPERUSER_ONLY_USER_FIELDS

    def _may_manage(self, request, obj):
        """
        The Console's boundary (rbac.services.get_user_management_denial),
        except that anyone may edit their own account here -- the fields that
        would let them raise their own access are read-only or wildcard-only.
        """
        if obj is None or obj.pk == request.user.pk:
            return True
        return get_user_management_denial(request.user, obj) is None

    def has_change_permission(self, request, obj=None):
        # Also guards the "change password" form, which asks this method.
        return super().has_change_permission(request, obj) and self._may_manage(request, obj)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and self._may_manage(request, obj)

    def delete_queryset(self, request, queryset):
        # The changelist's bulk delete checks the model permission only.
        for user in queryset:
            if not self._may_manage(request, user):
                raise PermissionDenied(f"You may not delete {user.username}.")
        super().delete_queryset(request, queryset)

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

    def save_model(self, request, obj, form, change):
        """
        Unticking is_superuser would make the user's points expire at once:
        a superuser's never do, but every lot is dated at receipt. The clock
        restarts on what they hold, in the same transaction (BUG-047).
        """
        from points.services import PointService
        from audit.utils import get_client_ip

        demoted = change and "is_superuser" in form.changed_data and not obj.is_superuser
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if demoted:
                PointService.keep_points_after_superuser_removed(
                    obj, actor=request.user, ip_address=get_client_ip(request)
                )

    def save_formset(self, request, form, formset, change):
        """
        Stamp assigned_by on new role assignments.

        The field is read-only in the inline because it records who performed
        the assignment rather than offering a choice, so it has to be filled in
        here. Existing rows keep whoever originally assigned them.
        """
        if formset.model is UserRole:
            instances = formset.save(commit=False)
            for instance in instances:
                if instance.assigned_by_id is None:
                    instance.assigned_by = request.user
                instance.save()
            for obj in formset.deleted_objects:
                obj.delete()
            formset.save_m2m()
            return
        super().save_formset(request, form, formset, change)

    def save_related(self, request, form, formsets, change):
        """
        Persist the direct grants after the role inline has been written.

        Ordering matters: the inline is saved by super() first, so a role added
        in the same POST is already in effect and its permissions correctly read
        as inherited rather than being duplicated as direct grants.

        Revoking sets is_active=False rather than deleting, matching UserRole,
        so the grant history and its granted_by/granted_at survive.

        Only the checkboxes the board rendered editable are reconciled
        (BUG-039). A locked one -- inherited from a role, or every one when
        the account has full access -- is disabled and posts nothing, which
        must read as "leave it alone", never as "revoke it". The lock is read
        before the role inline is saved, so it matches what the form showed.
        """
        user = form.instance
        locked_ids = self._locked_permission_ids(user)

        super().save_related(request, form, formsets, change)

        # Re-checked server-side: the fieldset swap above is a UI affordance,
        # not the security boundary. A hand-crafted POST from a non-superuser
        # reaches here and must be ignored.
        if not can_edit_minishop_permissions(request.user):
            return
        if DIRECT_PERMS_FIELD not in form.fields:
            return

        submitted = {p.pk for p in form.cleaned_data.get(DIRECT_PERMS_FIELD, [])}
        submitted -= locked_ids

        # Anything the roles grant now (a role added in this same POST
        # included) is not an exception, so it never becomes a direct row even
        # if a crafted POST asserts it. A ticked existing row is still kept.
        to_grant = submitted - self._locked_permission_ids(user, inherited_only=True)

        existing = {
            row.permission_id: row
            for row in UserPermission.objects.filter(user=user)
        }

        for permission_id in to_grant:
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
            if row.is_active and permission_id not in submitted and permission_id not in locked_ids:
                row.is_active = False
                row.save(update_fields=["is_active"])

    @staticmethod
    def _locked_permission_ids(user, inherited_only=False):
        """
        Ids the direct-grant board renders locked for `user`: those an active
        role grants, or every permission for a full-access account (the same
        rule as rbac.widgets). `inherited_only` skips the full-access case.
        """
        if not inherited_only and (
            user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in get_user_role_codes(user)
        ):
            return set(Permission.objects.values_list("id", flat=True))
        return set(
            Permission.objects.filter(
                role_permissions__role__user_roles__user=user,
                role_permissions__role__user_roles__is_active=True,
                role_permissions__role__is_active=True,
            ).values_list("id", flat=True)
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

"""
Widgets that turn the auth.User many-to-many fields into a readable board.

BaseUserAdmin renders `user_permissions` and `groups` with FilteredSelectMultiple
(its `filter_horizontal`), a two-pane list that asks the operator to read 120
dotted codenames in order to answer "what can this account touch?".

Both widgets below subclass CheckboxSelectMultiple, so the POST payload
(`getlist`), ModelMultipleChoiceField validation, `changed_data` and the admin's
change-message diffing all keep working exactly as before -- only the markup is
ours. Neither widget calls super().get_context(): that would build 120 throwaway
option dicts we never render.

Both also override render() to go through django.template.loader instead of the
form renderer. settings.FORM_RENDERER is Django's default DjangoTemplates, whose
engine is a standalone one that never sees TEMPLATES["DIRS"] -- it searches only
django/forms/templates plus each app's templates/ dir, and that app-dir list is
lru_cached process-wide. Rendering through the project engine puts these two
templates in backend/templates/admin/ with every other admin override, and takes
the lookup off the form renderer entirely.
"""
from django.forms import CheckboxSelectMultiple
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe


class _ProjectTemplateWidget(CheckboxSelectMultiple):
    """Renders `template_name` with the engines from settings.TEMPLATES."""

    def render(self, name, value, attrs=None, renderer=None):
        context = self.get_context(name, value, attrs)
        return mark_safe(render_to_string(self.template_name, context))


# app_label -> (rail label, Material Symbols icon, sort weight).
# Weight orders the rail by how often a section is actually edited; anything
# unlisted falls to the bottom under its own app label.
SECTION_META = {
    "shop": ("Commerce", "storefront", 10),
    "shops": ("Shops", "store", 20),
    "sellers": ("Sellers", "badge", 30),
    "customers": ("Customers", "groups", 40),
    "cart": ("Carts", "shopping_cart", 50),
    "points": ("Points & wallet", "toll", 60),
    "rbac": ("Roles & access", "admin_panel_settings", 70),
    "auth": ("Authentication", "key", 80),
    "audit": ("Audit trail", "history", 90),
    "admin": ("Admin log", "receipt_long", 100),
    "contenttypes": ("System types", "dns", 110),
    "sessions": ("Sessions", "schedule", 120),
}

# The four permissions Django creates for every model, in escalating order of
# blast radius, which is also the order they are read left to right.
ACTIONS = (
    ("view", "View", "visibility"),
    ("add", "Add", "add_circle"),
    ("change", "Edit", "edit"),
    ("delete", "Delete", "delete"),
)

DEFAULT_WEIGHT = 500


def _model_label(content_type):
    """Human plural for a row, e.g. "Product inventories"."""
    model = content_type.model_class()
    if model is not None:
        return str(model._meta.verbose_name_plural).capitalize()
    return str(content_type.model).capitalize()


class PermissionMatrixWidget(_ProjectTemplateWidget):
    """
    auth.Permission as an app -> model -> action board.

    Every checkbox is still `name="user_permissions" value="<pk>"`, so the field
    round-trips through Django untouched; the grouping exists only in the
    template context.
    """

    template_name = "admin/widgets/permission_matrix.html"

    def _permissions(self):
        queryset = getattr(self.choices, "queryset", None)
        if queryset is None:
            return []
        return list(queryset.select_related("content_type"))

    def get_context(self, name, value, attrs):
        selected = {str(v) for v in (value or []) if v not in (None, "")}
        final_attrs = self.build_attrs(self.attrs, attrs)
        base_id = final_attrs.get("id") or "id_%s" % name

        # app_label -> {"models": {model: row}, "granted": int, "total": int}
        sections = {}
        for permission in self._permissions():
            content_type = permission.content_type
            app = sections.setdefault(
                content_type.app_label,
                {"models": {}, "granted": 0, "total": 0},
            )
            row = app["models"].setdefault(
                content_type.model,
                {"content_type": content_type, "actions": {}, "extras": []},
            )

            checked = str(permission.pk) in selected
            cell = {
                "name": name,
                "value": permission.pk,
                "id": "%s_%s" % (base_id, permission.pk),
                "checked": checked,
                "codename": "%s.%s" % (content_type.app_label, permission.codename),
                "label": permission.name,
            }

            app["total"] += 1
            if checked:
                app["granted"] += 1

            # Exact match only: "change_productinventory" is the change action,
            # while a hand-written "approve_product" is not an action at all and
            # belongs in the row's extras strip.
            for action, _label, _icon in ACTIONS:
                if permission.codename == "%s_%s" % (action, content_type.model):
                    row["actions"][action] = cell
                    break
            else:
                cell["action_label"] = permission.name
                row["extras"].append(cell)

        rendered = []
        for app_label, app in sections.items():
            label, icon, weight = SECTION_META.get(
                app_label,
                (app_label.replace("_", " ").capitalize(), "folder", DEFAULT_WEIGHT),
            )
            rows = []
            for row in app["models"].values():
                content_type = row["content_type"]
                cells = []
                for action, action_label, action_icon in ACTIONS:
                    cell = row["actions"].get(action)
                    if cell is None:
                        # Placeholder keeps the four columns aligned when a model
                        # has had one of its default permissions removed.
                        cells.append({"action": action, "empty": True})
                        continue
                    cells.append(
                        {
                            **cell,
                            "action": action,
                            "action_label": action_label,
                            "action_icon": action_icon,
                            "empty": False,
                        }
                    )
                rows.append(
                    {
                        "key": "%s.%s" % (app_label, content_type.model),
                        "label": _model_label(content_type),
                        "hint": "%s.%s" % (app_label, content_type.model),
                        "cells": cells,
                        "extras": row["extras"],
                    }
                )
            rows.sort(key=lambda entry: entry["label"])
            rendered.append(
                {
                    "key": app_label,
                    "label": label,
                    "icon": icon,
                    "weight": weight,
                    "rows": rows,
                    "granted": app["granted"],
                    "total": app["total"],
                }
            )
        rendered.sort(key=lambda section: (section["weight"], section["label"]))

        return {
            "widget": {
                "name": name,
                "attrs": final_attrs,
                "sections": rendered,
                "actions": [
                    {"action": action, "label": label, "icon": icon}
                    for action, label, icon in ACTIONS
                ],
                "granted": sum(section["granted"] for section in rendered),
                "total": sum(section["total"] for section in rendered),
            }
        }


class GroupCardsWidget(_ProjectTemplateWidget):
    """auth.Group as selectable cards carrying each group's permission count."""

    template_name = "admin/widgets/group_cards.html"

    def get_context(self, name, value, attrs):
        selected = {str(v) for v in (value or []) if v not in (None, "")}
        final_attrs = self.build_attrs(self.attrs, attrs)
        base_id = final_attrs.get("id") or "id_%s" % name

        queryset = getattr(self.choices, "queryset", None)
        groups = []
        if queryset is not None:
            for group in queryset.prefetch_related("permissions"):
                groups.append(
                    {
                        "name": name,
                        "value": group.pk,
                        "id": "%s_%s" % (base_id, group.pk),
                        "checked": str(group.pk) in selected,
                        "label": group.name,
                        "count": len(group.permissions.all()),
                    }
                )

        return {
            "widget": {
                "name": name,
                "attrs": final_attrs,
                "groups": groups,
                "granted": sum(1 for group in groups if group["checked"]),
                "total": len(groups),
            }
        }


# ==============================================================================
# MiniShop RBAC permission board
# ==============================================================================
# The board above is Django's own auth.Permission M2M, which governs access to
# THIS admin site. MiniShop's API/console authorization is a separate system:
# rbac.Permission, resolved by rbac.services.get_user_permissions().
#
# A user holds a MiniShop permission by either of two routes:
#   1. INHERITED -- User -> UserRole -> Role -> RolePermission. The primary path;
#      editing it changes access for everyone holding that role.
#   2. DIRECT    -- a UserPermission row. The single-account exception.
#
# The board renders both. Inherited rows are locked, because unticking one here
# would be a lie: the permission comes from a role and would survive. Direct
# rows are the editable ones, and only a superuser sees them editable at all
# (see UserAdmin.get_fieldsets / save_related).

# resource -> (label, Material Symbols icon, sort weight). Resource is
# rbac.Permission.resource, the field the model already groups on; anything
# unlisted falls to the bottom under its own capitalized name.
RESOURCE_META = {
    "users": ("Users", "manage_accounts", 10),
    "roles": ("Roles & access", "admin_panel_settings", 20),
    "sellers": ("Sellers", "badge", 30),
    "shops": ("Shops", "store", 40),
    "products": ("Products", "inventory_2", 50),
    "categories": ("Categories", "category", 60),
    "customers": ("Customers", "groups", 70),
    "orders": ("Orders", "receipt_long", 80),
    "payments": ("Payments", "payments", 90),
    "points": ("Points & wallet", "toll", 100),
    "inventory": ("Inventory", "warehouse", 110),
    "reports": ("Reports", "monitoring", 120),
    "profile": ("Profile", "person", 130),
    "address": ("Addresses", "home_pin", 140),
    "cart": ("Carts", "shopping_cart", 150),
    "reviews": ("Reviews", "reviews", 160),
}

WILDCARD_CODE = "*"




def _minishop_permission_sections(user, direct_codes=None):
    """
    Shared context builder for both MiniShop boards.

    Returns (sections, meta). Every row carries the two routes separately:

      inherited -- granted by one of the user's active roles, listed in `roles`
      direct    -- granted by a UserPermission row (or, when rendering a bound
                   form, ticked in the POST that is being re-displayed)

    `direct_codes` lets the editable widget show what the operator just ticked
    rather than what is currently saved, so a validation error re-renders their
    edits instead of silently discarding them. Pass None to read the saved rows.
    """
    # Imported here rather than at module import time: widgets.py is imported
    # from admin.py during app loading, and rbac.models/services pull in the
    # user model, which is not ready at that point.
    from .models import Permission, RolePermission, Role, UserPermission
    from .services import get_user_role_codes

    if user is None or not getattr(user, "pk", None):
        return None, None

    role_codes = get_user_role_codes(user)
    full_access = user.is_superuser or Role.ROLE_SUPER_ADMINISTRATOR in role_codes

    # code -> [role code, ...], limited to the user's own active roles so the
    # attribution reflects this account, not the platform-wide role catalogue.
    granting_roles = {}
    if role_codes:
        pairs = RolePermission.objects.filter(
            role__code__in=role_codes,
            role__is_active=True,
        ).values_list("permission__code", "role__code")
        for perm_code, role_code in pairs:
            granting_roles.setdefault(perm_code, []).append(role_code)

    if direct_codes is None:
        direct_codes = set(
            UserPermission.objects.filter(user=user, is_active=True).values_list(
                "permission__code", flat=True
            )
        )

    sections = {}
    for permission in Permission.objects.all().order_by("resource", "action"):
        bucket = sections.setdefault(permission.resource, {"permissions": [], "granted": 0})
        inherited = permission.code in granting_roles
        direct = permission.code in direct_codes
        if inherited or direct:
            bucket["granted"] += 1
        bucket["permissions"].append(
            {
                "pk": permission.pk,
                "code": permission.code,
                "name": permission.name,
                "description": permission.description,
                "inherited": inherited,
                "direct": direct,
                "granted": inherited or direct,
                "roles": sorted(granting_roles.get(permission.code, [])),
            }
        )

    rendered = []
    for resource, bucket in sections.items():
        label, icon, weight = RESOURCE_META.get(
            resource,
            (resource.replace("_", " ").capitalize(), "folder", DEFAULT_WEIGHT),
        )
        rendered.append(
            {
                "key": resource,
                "label": label,
                "icon": icon,
                "weight": weight,
                "permissions": bucket["permissions"],
                "granted": bucket["granted"],
                "total": len(bucket["permissions"]),
            }
        )
    rendered.sort(key=lambda section: (section["weight"], section["label"]))

    meta = {
        "roles": [
            {"code": role.code, "name": role.name}
            for role in Role.objects.filter(code__in=role_codes).order_by("code")
        ],
        "full_access": full_access,
        "wildcard": WILDCARD_CODE,
        "is_superuser": user.is_superuser,
        "granted": sum(section["granted"] for section in rendered),
        "total": sum(section["total"] for section in rendered),
    }
    return rendered, meta


def build_minishop_permission_board(user):
    """
    Context for the READ-ONLY board, shown to operators who may not edit grants.

    Lists the whole rbac.Permission catalogue grouped by resource, marks what
    the account effectively holds, and says which role grants it -- so the page
    answers both "what can this account do" and "why".
    """
    sections, meta = _minishop_permission_sections(user)
    if sections is None:
        return {"board": None}
    return {"board": {"sections": sections, **meta}}


def render_minishop_permission_board(user):
    """Renders the read-only board for use as a ModelAdmin readonly field."""
    return mark_safe(
        render_to_string(
            "admin/widgets/minishop_permission_board.html",
            build_minishop_permission_board(user),
        )
    )


class MiniShopPermissionWidget(_ProjectTemplateWidget):
    """
    Editable board for a user's DIRECT MiniShop permission grants.

    Every editable checkbox is `name="<field>" value="<rbac.Permission pk>"`, so
    the field round-trips through ModelMultipleChoiceField untouched -- only the
    markup is ours.

    Inherited rows render `disabled`. A disabled checkbox submits nothing, so the
    browser itself guarantees a role-derived permission can never be turned into
    a direct grant by accident, and the saved set stays a clean record of the
    exceptions rather than a snapshot of everything the user happened to hold.
    """

    template_name = "admin/widgets/minishop_permission_matrix.html"

    def __init__(self, user=None, attrs=None):
        self.user = user
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        final_attrs = self.build_attrs(self.attrs, attrs)
        base_id = final_attrs.get("id") or "id_%s" % name

        # `value` is whatever the field currently holds -- saved pks on a fresh
        # GET, or the operator's unsaved ticks when a bound form re-renders.
        selected_pks = {str(v) for v in (value or []) if v not in (None, "")}

        from .models import Permission

        direct_codes = set(
            Permission.objects.filter(pk__in=[p for p in selected_pks]).values_list(
                "code", flat=True
            )
        ) if selected_pks else set()

        sections, meta = _minishop_permission_sections(self.user, direct_codes=direct_codes)
        if sections is None:
            return {"widget": {"name": name, "attrs": final_attrs, "board": None}}

        for section in sections:
            for permission in section["permissions"]:
                permission["input_name"] = name
                permission["id"] = "%s_%s" % (base_id, permission["pk"])
                # Locked when the role already grants it, or when the wildcard
                # makes an individual grant meaningless.
                permission["locked"] = permission["inherited"] or meta["full_access"]

        return {
            "widget": {
                "name": name,
                "attrs": final_attrs,
                "board": {"sections": sections, **meta},
            }
        }


# ==============================================================================
# Role permission board
# ==============================================================================
# The two boards above answer "what does this ACCOUNT hold". This one answers
# "what does this ROLE grant" -- the other end of the same relation, edited on
# /admin/rbac/role/add/ and /admin/rbac/role/<pk>/change/.
#
# It replaces a TabularInline over RolePermission: one <select> of the whole
# catalogue per row, one row per grant, and no way to read what a role covers
# without opening every row. The board renders the catalogue itself, grouped by
# rbac.Permission.resource, so a grant is a tick and the shape of the role is
# legible at a glance.
#
# Delegation: MiniShop's rule is "you may only give away what you already hold"
# (rbac.services.get_delegatable_permission_codes), which the role API already
# enforces. This board applies the same rule -- a code outside the actor's own
# effective set renders locked -- and RoleAdmin.save_related re-checks it, since
# the lock is an affordance and not the boundary.


def build_role_permission_sections(selected_pks, delegatable_codes=None):
    """
    The rbac.Permission catalogue grouped by resource, for one role.

    `selected_pks` is whatever the field currently holds: the role's saved
    grants on a fresh GET, or the operator's unsaved ticks when a bound form
    re-renders after a validation error.

    `delegatable_codes` of None means the actor may delegate anything (a
    wildcard holder, which is the usual case here); passing a set locks every
    code outside it. Locked rows still carry their real checkbox so the board
    reports the role truthfully -- they are `disabled`, which submits nothing
    and which save_related turns into "leave this grant exactly as it was".
    """
    # Imported here for the same reason the boards above do it: widgets.py is
    # imported from admin.py while the app registry is still loading.
    from .models import Permission

    selected = {str(pk) for pk in selected_pks if pk not in (None, "")}

    sections = {}
    for permission in Permission.objects.all():
        bucket = sections.setdefault(
            permission.resource, {"permissions": [], "granted": 0, "locked": 0}
        )
        granted = str(permission.pk) in selected
        locked = (
            delegatable_codes is not None and permission.code not in delegatable_codes
        )
        if granted:
            bucket["granted"] += 1
        if locked:
            bucket["locked"] += 1
        bucket["permissions"].append(
            {
                "pk": permission.pk,
                "code": permission.code,
                "name": permission.name,
                "description": permission.description,
                # `action` is free text on rbac.Permission ("approve",
                # "admin_manage"), not Django's fixed four, so it is shown as a
                # tag rather than used to build columns.
                "action": permission.action.replace("_", " "),
                "granted": granted,
                "locked": locked,
            }
        )

    rendered = []
    for resource, bucket in sections.items():
        label, icon, weight = RESOURCE_META.get(
            resource,
            (resource.replace("_", " ").capitalize(), "folder", DEFAULT_WEIGHT),
        )
        rendered.append(
            {
                "key": resource,
                "label": label,
                "icon": icon,
                "weight": weight,
                "permissions": bucket["permissions"],
                "granted": bucket["granted"],
                "locked": bucket["locked"],
                "total": len(bucket["permissions"]),
            }
        )
    rendered.sort(key=lambda section: (section["weight"], section["label"]))
    return rendered


class RolePermissionWidget(_ProjectTemplateWidget):
    """
    Editable board for the permissions one Role grants.

    Every checkbox is `name="<field>" value="<rbac.Permission pk>"`, so the
    field round-trips through ModelMultipleChoiceField exactly as a stock
    CheckboxSelectMultiple would; the resource grouping, the rail, the search
    box and the select-all controls are markup only and submit nothing.
    """

    template_name = "admin/widgets/role_permission_matrix.html"

    def __init__(self, delegatable_codes=None, attrs=None):
        # None == "may delegate anything"; see build_role_permission_sections.
        self.delegatable_codes = delegatable_codes
        super().__init__(attrs)

    def get_context(self, name, value, attrs):
        final_attrs = self.build_attrs(self.attrs, attrs)
        base_id = final_attrs.get("id") or "id_%s" % name

        sections = build_role_permission_sections(
            value or [], delegatable_codes=self.delegatable_codes
        )
        for section in sections:
            for permission in section["permissions"]:
                permission["input_name"] = name
                permission["id"] = "%s_%s" % (base_id, permission["pk"])

        return {
            "widget": {
                "name": name,
                "attrs": final_attrs,
                "sections": sections,
                "granted": sum(section["granted"] for section in sections),
                "locked": sum(section["locked"] for section in sections),
                "total": sum(section["total"] for section in sections),
                "restricted": self.delegatable_codes is not None,
            }
        }

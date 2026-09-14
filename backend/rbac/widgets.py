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

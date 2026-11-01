"""
The Console Rules page (rules/registry.py). rules.view shows the business
rules to ADMINISTRATOR, OPERATION_MANAGER and FINANCE; rules.manage lets
ADMINISTRATOR change them. seed_rbac does the same on a fresh database.
"""

from django.db import migrations

PERMISSIONS = {
    "rules.view": {
        "name": "View Business Rules",
        "resource": "rules",
        "action": "view",
        "description": "Can see the business rules: costs, periods, limits and onboarding values",
    },
    "rules.manage": {
        "name": "Change Business Rules",
        "resource": "rules",
        "action": "manage",
        "description": "Can change the business rules; every change is audited with a reason",
    },
}
GRANTS = {
    "ADMINISTRATOR": ("rules.view", "rules.manage"),
    "OPERATION_MANAGER": ("rules.view",),
    "FINANCE": ("rules.view",),
}


def add_rules_permissions(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")
    permissions = {
        code: Permission.objects.get_or_create(code=code, defaults=defaults)[0]
        for code, defaults in PERMISSIONS.items()
    }
    for role_code, codes in GRANTS.items():
        role = Role.objects.filter(code=role_code).first()
        if role is not None:
            for code in codes:
                RolePermission.objects.get_or_create(role=role, permission=permissions[code])


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0005_sellers_onboard_permission"),
    ]

    operations = [
        migrations.RunPython(add_rules_permissions, migrations.RunPython.noop),
    ]

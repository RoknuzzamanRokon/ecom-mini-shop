"""
TASK-048 decision 8: only audit.view (or audit.admin.view) opens the full
audit log. users.admin.view and roles.admin.view no longer do, so the new
code is created and given to ADMINISTRATOR, which held those two, so
existing administrators keep reading the log. seed_rbac does the same on a
fresh database.
"""

from django.db import migrations

CODE = "audit.view"


def add_audit_view(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")
    permission, _ = Permission.objects.get_or_create(
        code=CODE,
        defaults={
            "name": "View Audit Log",
            "resource": "audit",
            "action": "view",
            "description": "Can read the platform audit log, payment and refund details included",
        },
    )
    administrator = Role.objects.filter(code="ADMINISTRATOR").first()
    if administrator is not None:
        RolePermission.objects.get_or_create(role=administrator, permission=permission)


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0002_userpermission"),
    ]

    operations = [
        migrations.RunPython(add_audit_view, migrations.RunPython.noop),
    ]

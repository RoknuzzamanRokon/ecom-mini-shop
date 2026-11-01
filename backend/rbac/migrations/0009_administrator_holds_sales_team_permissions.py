"""
ADMINISTRATOR gets 'sellers.onboard' and 'onboarding.products.view', the two
SALES_TEAM codes it lacked. Below the wildcard, managing an account (its
roles, deactivating it) needs every permission it holds
(rbac.services.get_user_management_denial), so until now only a Super
Administrator could manage a Sales Team member. Administrators can onboard
sellers too.
"""

from django.db import migrations

CODES = ("sellers.onboard", "onboarding.products.view")


def grant(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")
    role = Role.objects.filter(code="ADMINISTRATOR").first()
    if role is None:
        return
    for permission in Permission.objects.filter(code__in=CODES):
        RolePermission.objects.get_or_create(role=role, permission=permission)


def revoke(apps, schema_editor):
    RolePermission = apps.get_model("rbac", "RolePermission")
    RolePermission.objects.filter(role__code="ADMINISTRATOR", permission__code__in=CODES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0008_sales_team_own_products"),
    ]

    operations = [
        migrations.RunPython(grant, revoke),
    ]

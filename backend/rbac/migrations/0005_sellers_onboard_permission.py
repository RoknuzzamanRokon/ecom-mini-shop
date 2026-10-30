"""
Field onboarding by the Sales Team. The new sellers.onboard code lets a Sales
Team member open seller accounts (paying each one's starting points from
their own wallet), add the shop and products before approval, and see the
sellers they onboarded. SALES_TEAM gets it, and loses sellers.view, which
showed every seller in the Console directory. seed_rbac does the same on a
fresh database, but it only ever adds grants, so the removal lives here.
"""

from django.db import migrations

CODE = "sellers.onboard"
SALES_TEAM = "SALES_TEAM"


def grant_sellers_onboard(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")
    permission, _ = Permission.objects.get_or_create(
        code=CODE,
        defaults={
            "name": "Onboard Sellers",
            "resource": "sellers",
            "action": "onboard",
            "description": (
                "Can open seller accounts in the field and add their shop and products before approval, "
                "paying each new seller's starting points from their own wallet; sees only the sellers they onboarded"
            ),
        },
    )
    sales_team = Role.objects.filter(code=SALES_TEAM).first()
    if sales_team is not None:
        RolePermission.objects.get_or_create(role=sales_team, permission=permission)
        RolePermission.objects.filter(role=sales_team, permission__code="sellers.view").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0004_loginphone"),
    ]

    operations = [
        # Not reversed: giving SALES_TEAM the whole seller directory back is a
        # grant someone should make on purpose, in the Console.
        migrations.RunPython(grant_sellers_onboard, migrations.RunPython.noop),
    ]

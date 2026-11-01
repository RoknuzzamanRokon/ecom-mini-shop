"""
docs/SALES_TEAM_EDITS_PAYOUTS_PLAN.md §2–3.

- onboarding.products.view: a Sales Team member sees the products they added
  for the sellers they onboarded. SALES_TEAM gets it.
- SALES_TEAM loses products.view (the Console product list and detail, every
  seller's products), inventory.view and inventory.adjust (every product's
  stock for an account marked is_staff), and products.create and
  products.update, which no view checks.
- onboarding.payouts.manage: accept or reject the Sales Team's token payout
  requests. ADMINISTRATOR gets it.

seed_rbac does the same on a fresh database, but it only ever adds grants, so
the removals live here.
"""

from django.db import migrations

PERMISSIONS = {
    "onboarding.products.view": {
        "name": "View Own Onboarded Products",
        "resource": "onboarding",
        "action": "products.view",
        "description": "Can see the products they added for the sellers they onboarded, and edit them in an edit session",
    },
    "onboarding.payouts.manage": {
        "name": "Settle Token Payouts",
        "resource": "onboarding",
        "action": "payouts.manage",
        "description": "Can accept or reject the Sales Team's token payout requests; accepted tokens move to them",
    },
}
GRANTS = {
    "SALES_TEAM": ("onboarding.products.view",),
    "ADMINISTRATOR": ("onboarding.payouts.manage",),
}
SALES_TEAM_LOSES = ("products.view", "products.create", "products.update", "inventory.view", "inventory.adjust")


def apply(apps, schema_editor):
    Permission = apps.get_model("rbac", "Permission")
    Role = apps.get_model("rbac", "Role")
    RolePermission = apps.get_model("rbac", "RolePermission")
    permissions = {
        code: Permission.objects.get_or_create(code=code, defaults=fields)[0]
        for code, fields in PERMISSIONS.items()
    }
    for role_code, codes in GRANTS.items():
        role = Role.objects.filter(code=role_code).first()
        if role is not None:
            for code in codes:
                RolePermission.objects.get_or_create(role=role, permission=permissions[code])
    RolePermission.objects.filter(role__code="SALES_TEAM", permission__code__in=SALES_TEAM_LOSES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("rbac", "0007_permission_blocks_starting_passwords"),
    ]

    operations = [
        # Not reversed: giving SALES_TEAM every product back is a grant someone
        # should make on purpose, in the Console.
        migrations.RunPython(apply, migrations.RunPython.noop),
    ]

"""
Take the SALES_TEAM staff role away from seller accounts (TASK-005, BUG-004).

Sellers used to need SALES_TEAM for 'products.create' and the other codes the
Seller Center checked. The role also carries 'sellers.view' and
'products.view', which open the staff Console's seller directory (other
sellers' business email, phone and tax id) and every shop's draft products.
The Seller Center now admits sellers by seller status instead, so the role has
no seller purpose left.

Only accounts that are plainly sellers are touched: a seller profile, no
is_staff or is_superuser flag, and no active role besides SALES_TEAM and
CUSTOMER. Anyone who also holds a real staff role keeps SALES_TEAM. The rows
are deactivated, not deleted, so the assignment history stays.
"""

from django.db import migrations

SALES_TEAM = "SALES_TEAM"
CUSTOMER = "CUSTOMER"


def deactivate_sales_team_for_sellers(apps, schema_editor):
    UserRole = apps.get_model("rbac", "UserRole")
    SellerProfile = apps.get_model("sellers", "SellerProfile")

    holds_other_staff_role = UserRole.objects.filter(is_active=True, role__is_active=True).exclude(
        role__code__in=[SALES_TEAM, CUSTOMER]
    )
    UserRole.objects.filter(
        role__code=SALES_TEAM,
        is_active=True,
        user_id__in=SellerProfile.objects.values("user_id"),
        user__is_staff=False,
        user__is_superuser=False,
    ).exclude(user_id__in=holds_other_staff_role.values("user_id")).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("sellers", "0002_remove_product_owner_add_product_limit"),
        ("rbac", "0002_userpermission"),
    ]

    operations = [
        # Not reversible: which rows this switched off is not recorded, and
        # switching every seller's SALES_TEAM back on would reopen BUG-004.
        migrations.RunPython(deactivate_sales_team_for_sellers, migrations.RunPython.noop),
    ]

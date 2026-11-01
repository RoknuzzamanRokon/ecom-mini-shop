"""
Every seller account opened through field onboarding so far got its password
from the onboarder: record a StartingPassword for each, so its owner chooses
their own at the next sign-in.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    SellerOnboarding = apps.get_model("onboarding", "SellerOnboarding")
    StartingPassword = apps.get_model("rbac", "StartingPassword")
    for onboarding in SellerOnboarding.objects.select_related("seller"):
        StartingPassword.objects.get_or_create(
            user_id=onboarding.seller.user_id, defaults={"set_by_id": onboarding.seller.created_by_id}
        )


class Migration(migrations.Migration):

    dependencies = [
        ("onboarding", "0002_edit_sessions_token_payouts"),
        ("rbac", "0007_permission_blocks_starting_passwords"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]

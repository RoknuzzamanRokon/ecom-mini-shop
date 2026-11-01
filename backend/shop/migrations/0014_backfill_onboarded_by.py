"""
Fills Product.onboarded_by for products added through field onboarding before
the field existed: the PRODUCT_CREATED audit row says `created_via:
onboarding`, and its actor is the onboarder when that is also who opened the
seller (SellerProfile.created_by).
"""

from django.db import migrations


def backfill(apps, schema_editor):
    AuditLog = apps.get_model("audit", "AuditLog")
    Product = apps.get_model("shop", "Product")
    products = Product.objects.filter(
        onboarded_by__isnull=True, shop__owner__onboarding__isnull=False
    ).select_related("shop__owner")
    for product in products:
        onboarder_id = product.shop.owner.created_by_id
        if onboarder_id is None:
            continue
        created = AuditLog.objects.filter(
            action="PRODUCT_CREATED", target_type="Product", target_id=str(product.pk), actor_id=onboarder_id
        ).values_list("metadata", flat=True).first()
        if created is not None and (created or {}).get("created_via") == "onboarding":
            Product.objects.filter(pk=product.pk).update(onboarded_by_id=onboarder_id)


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0013_product_onboarded_by"),
        ("audit", "0002_auditlog_actor_snapshot"),
        ("onboarding", "0001_initial"),
        ("sellers", "0004_sellerprofile_created_by"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]

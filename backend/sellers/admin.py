from django.contrib import admin
from .models import SellerProfile


@admin.register(SellerProfile)
class SellerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "business_name",
        "user",
        "seller_type",
        "status",
        "is_operational",
        "is_suspended",
        "created_at",
    )
    list_filter = ("seller_type", "status", "created_at")
    search_fields = (
        "business_name",
        "user__username",
        "user__email",
        "business_email",
        "tax_id",
    )
    readonly_fields = (
        "reviewed_by",
        "reviewed_at",
        "approved_at",
        "suspended_at",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            "Account & Type",
            {
                "fields": ("user", "seller_type", "status"),
            },
        ),
        (
            "Business Details",
            {
                "fields": (
                    "business_name",
                    "business_email",
                    "business_phone",
                    "tax_id",
                    "description",
                ),
            },
        ),
        (
            "Audit & Review",
            {
                "fields": (
                    "rejection_reason",
                    "suspension_reason",
                    "reviewed_by",
                    "reviewed_at",
                    "approved_at",
                    "suspended_at",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )

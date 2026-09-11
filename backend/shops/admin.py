from django.contrib import admin
from .models import Shop


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "owner",
        "status",
        "phone",
        "location_display",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "name",
        "slug",
        "owner__business_name",
        "owner__user__username",
        "owner__user__email",
        "phone",
        "address",
    )

    @admin.display(description="Location (Lat, Lng)")
    def location_display(self, obj):
        if obj.has_coordinates:
            return f"{obj.latitude:.5f}, {obj.longitude:.5f}"
        return "Unassigned"
    readonly_fields = (
        "slug",
        "reviewed_by",
        "reviewed_at",
        "approved_at",
        "suspended_at",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            "Core Information",
            {
                "fields": ("name", "slug", "owner", "status"),
            },
        ),
        (
            "Media & Branding",
            {
                "fields": ("logo", "cover_image", "description"),
            },
        ),
        (
            "Contact & Location",
            {
                "fields": ("phone", "address", "location"),
            },
        ),
        (
            "Review & Audit",
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

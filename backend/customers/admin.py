from django.contrib import admin
from .models import Address, CustomerProfile


@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "display_name",
        "phone",
        "gender",
        "created_at",
    )
    search_fields = (
        "user__username",
        "user__email",
        "display_name",
        "phone",
    )
    list_filter = ("gender", "created_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "label",
        "recipient_name",
        "phone",
        "city",
        "country",
        "is_default",
        "created_at",
    )
    search_fields = (
        "user__username",
        "recipient_name",
        "phone",
        "address_line_1",
        "city",
        "postal_code",
    )
    list_filter = ("is_default", "label", "city", "country")
    readonly_fields = ("default_flag", "created_at", "updated_at")

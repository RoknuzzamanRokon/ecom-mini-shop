from django.contrib import admin
from django.db.models import Count
from .models import CustomerProfile, Address, Favorite

@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'date_of_birth', 'gender', 'order_count', 'address_count')
    search_fields = ('user__username', 'user__email', 'phone')
    list_filter = ('gender',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related('user')
        qs = qs.annotate(
            order_count=Count('user__orders', distinct=True),
            address_count=Count('user__addresses', distinct=True)
        )
        return qs

    def order_count(self, obj):
        return obj.order_count
    order_count.short_description = 'Orders'
    order_count.admin_order_field = 'order_count'

    def address_count(self, obj):
        return obj.address_count
    address_count.short_description = 'Addresses'
    address_count.admin_order_field = 'address_count'

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ('user', 'label', 'recipient_name', 'phone', 'city', 'is_default')
    search_fields = ('user__username', 'recipient_name', 'phone', 'city')
    list_filter = ('is_default', 'label', 'city')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'product', 'created_at')
    search_fields = ('user__username', 'product__name')
    list_filter = ('created_at',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user', 'product')

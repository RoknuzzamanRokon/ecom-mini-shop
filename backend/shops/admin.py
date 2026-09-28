from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.utils.html import format_html

from audit.admin_mixins import ReasonRequiredActionMixin, StatusBadgeMixin
from sellers.models import SellerProfile
from .models import Shop
from .services import ShopService, ShopError

# The changelist query the seller profile's "Shops" link opens.
OWNER_FILTER = 'owner__id__exact'


@admin.register(Shop)
class ShopAdmin(ReasonRequiredActionMixin, StatusBadgeMixin, admin.ModelAdmin):
    list_display = (
        'shop_display', 'owner_display', 'status_badge', 'product_count',
        'phone', 'created_at'
    )
    list_display_links = ('shop_display',)
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'slug', 'owner__user__username', 'phone')
    readonly_fields = (
        'status', 'reviewed_by', 'reviewed_at', 'approved_at',
        'suspended_at', 'created_at', 'updated_at', 'location_display'
    )
    actions = ['approve_and_activate', 'suspend_shops', 'reject_shops', 'reactivate_shops']

    fieldsets = (
        ('Basic Information', {
            'fields': ('owner', 'name', 'slug', 'description', 'status')
        }),
        ('Media', {
            'fields': ('logo', 'cover_image')
        }),
        ('Contact & Location', {
            'fields': ('phone', 'address', 'location', 'location_display')
        }),
        ('Status & Reviews', {
            'fields': ('rejection_reason', 'suspension_reason', 'reviewed_by', 
                       'reviewed_at', 'approved_at', 'suspended_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_list_display(self, request):
        # Filtered to one seller, the owner column would repeat the seller
        # header above the list (templates/admin/shops/shop/change_list.html).
        if request.GET.get(OWNER_FILTER):
            return tuple(name for name in self.list_display if name != 'owner_display')
        return self.list_display

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), 'seller_filter': self._seller_filter(request)}
        return super().changelist_view(request, extra_context)

    def _seller_filter(self, request):
        """The seller the list is filtered to, with shop and product totals for
        the header; None when unfiltered or the id matches no seller."""
        raw = request.GET.get(OWNER_FILTER, '')
        if not raw.isdigit():
            return None
        return (
            SellerProfile.objects.select_related('user')
            .annotate(
                shop_total=Count('shops', distinct=True),
                active_shop_total=Count(
                    'shops', filter=Q(shops__status=Shop.STATUS_ACTIVE), distinct=True
                ),
                product_total=Count('shops__products', distinct=True),
            )
            .filter(pk=int(raw))
            .first()
        )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related('owner', 'owner__user', 'reviewed_by')
        qs = qs.annotate(product_count=Count('products', distinct=True))
        return qs

    def product_count(self, obj):
        return obj.product_count
    product_count.short_description = 'Products'
    product_count.admin_order_field = 'product_count'

    @admin.display(description='Shop', ordering='name')
    def shop_display(self, obj):
        # Logo (or initial), name and slug; Django wraps it in the row link.
        if obj.logo:
            mark = format_html('<img class="mp-shop-mark" src="{}" alt="">', obj.logo.url)
        else:
            mark = format_html(
                '<span class="mp-shop-mark is-initial" aria-hidden="true">{}</span>',
                obj.name[:1].upper() or '?',
            )
        return format_html(
            '{}<span class="mp-shop-id"><span class="mp-shop-name">{}</span>'
            '<span class="mp-shop-slug">{}</span></span>',
            mark, obj.name, obj.slug,
        )

    @admin.display(description='Owner', ordering='owner__business_name')
    def owner_display(self, obj):
        # Links to this same list filtered to the owner, not to the seller page,
        # so it needs no permission beyond the one already viewing shops.
        return format_html(
            '<a href="?{}={}" title="Show only this seller\'s shops">{}</a>',
            OWNER_FILTER, obj.owner_id, obj.owner.business_name,
        )

    def location_display(self, obj):
        if obj.location:
            return f"Lat: {obj.location.y}, Lng: {obj.location.x}"
        return "N/A"
    location_display.short_description = 'Location (Lat, Lng)'


    def audit_context(self, obj):
        return {'shop': obj, 'seller': obj.owner}

    def approve_and_activate(self, request, queryset):
        self.run_simple_action(
            request, queryset,
            verb='Approved and activated',
            perform=lambda shop, user: ShopService.approve_shop(shop, user),
            audit_action='ADMIN_SHOP_APPROVE',
            catch=(ValidationError, ShopError),
        )
    approve_and_activate.short_description = "Approve and activate selected shops"
    approve_and_activate.allowed_permissions = ('change',)

    def suspend_shops(self, request, queryset):
        return self.run_reason_action(
            request, queryset,
            action_name='suspend_shops',
            title='Suspend shops',
            verb='Suspended',
            reason_label='Suspension reason',
            help_text='Suspending a shop removes it and its products from the storefront.',
            perform=lambda shop, user, reason: ShopService.suspend_shop(shop, user, reason),
            audit_action='ADMIN_SHOP_SUSPEND',
            catch=(ValidationError, ShopError),
        )
    suspend_shops.short_description = "Suspend selected shops (reason required)"
    suspend_shops.allowed_permissions = ('change',)

    def reject_shops(self, request, queryset):
        return self.run_reason_action(
            request, queryset,
            action_name='reject_shops',
            title='Reject shops',
            verb='Rejected',
            reason_label='Rejection reason',
            help_text='Rejecting a shop application is visible to its owner.',
            perform=lambda shop, user, reason: ShopService.reject_shop(shop, user, reason),
            audit_action='ADMIN_SHOP_REJECT',
            catch=(ValidationError, ShopError),
        )
    reject_shops.short_description = "Reject selected shops (reason required)"
    reject_shops.allowed_permissions = ('change',)

    def reactivate_shops(self, request, queryset):
        self.run_simple_action(
            request, queryset,
            verb='Reactivated',
            perform=lambda shop, user: ShopService.reactivate_shop(shop, user),
            audit_action='ADMIN_SHOP_REACTIVATE',
            catch=(ValidationError, ShopError),
        )
    reactivate_shops.short_description = "Reactivate selected shops"
    reactivate_shops.allowed_permissions = ('change',)

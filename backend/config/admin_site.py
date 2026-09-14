"""
Custom AdminSite that injects platform metrics into the dashboard.

Overriding `AdminSite.index()` is the only supported hook for adding context
to admin/index.html. Delegating to super() keeps `app_list`, `each_context()`,
`available_apps` (which nav_sidebar.html reads) and the `admin:` URL namespace
intact. Metrics are computed on the dashboard request only -- never on a
changelist -- which is why this is not a context processor.
"""
from django.conf import settings
from django.contrib import admin
from django.db.models import Count, Q


class MiniShopAdminSite(admin.AdminSite):
    site_header = "MiniShop Administration"
    site_title = "MiniShop Admin Portal"
    index_title = "Dashboard & Store Management"

    def each_context(self, request):
        """
        Supply what the custom admin chrome needs, so the templates do not
        depend on shop.context_processors.shop_context leaking storefront
        values into every admin page.
        """
        from shop.models import Category

        context = super().each_context(request)
        context["storefront_url"] = getattr(
            settings, "STOREFRONT_URL", "http://localhost:3000"
        )
        context["nav_categories"] = Category.objects.filter(
            is_active=True
        ).annotate(
            product_count=Count("products", filter=Q(products__is_active=True))
        )
        return context

    def index(self, request, extra_context=None):
        # Imported here so the module stays importable before apps are loaded.
        from shop.metrics import get_platform_metrics

        context = {
            "metrics": get_platform_metrics(),
            **(extra_context or {}),
        }
        return super().index(request, extra_context=context)

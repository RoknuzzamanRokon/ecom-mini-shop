"""
Custom AdminSite that injects platform metrics into the dashboard and serves
the signed-in staff member's own profile page at /admin/profile/.

Overriding `AdminSite.index()` is the only supported hook for adding context
to admin/index.html. Delegating to super() keeps `app_list`, `each_context()`,
`available_apps` (which nav_sidebar.html reads) and the `admin:` URL namespace
intact. Metrics are computed on the dashboard request only -- never on a
changelist -- which is why this is not a context processor.
"""
from django.conf import settings
from django.contrib import admin
from django.core.files.storage import default_storage
from django.db.models import Count, Q
from django.urls import path


class MiniShopAdminSite(admin.AdminSite):
    site_header = "MiniShop Administration"
    site_title = "MiniShop Admin Portal"
    index_title = "Dashboard & Store Management"

    def each_context(self, request):
        """
        Supply what the custom admin chrome needs: the storefront link and
        the category rail in nav_sidebar.html.
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
        context["admin_avatar_url"] = self._avatar_url(request)
        return context

    @staticmethod
    def _avatar_url(request):
        """The header avatar's photo, if the signed-in user uploaded one."""
        from customers.models import CustomerProfile

        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return ""
        name = (
            CustomerProfile.objects.filter(user=user)
            .values_list("avatar", flat=True)
            .first()
        )
        return default_storage.url(name) if name else ""

    def get_urls(self):
        # Ahead of super()'s patterns, whose final catch-all would 404 it.
        return [
            path("profile/", self.admin_view(self.profile_view), name="profile"),
        ] + super().get_urls()

    def profile_view(self, request):
        """/admin/profile/ -- see config/admin_profile.py."""
        from .admin_profile import profile_view

        return profile_view(self, request)

    def index(self, request, extra_context=None):
        # Imported here so the module stays importable before apps are loaded.
        from shop.metrics import get_platform_metrics

        context = {
            "metrics": get_platform_metrics(),
            **(extra_context or {}),
        }
        return super().index(request, extra_context=context)

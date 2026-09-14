"""App configs for the project package."""
from django.contrib.admin.apps import AdminConfig


class MiniShopAdminConfig(AdminConfig):
    """Swaps in MiniShopAdminSite while keeping the `admin` app label."""
    default_site = "config.admin_site.MiniShopAdminSite"

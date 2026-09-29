"""
The backend serves no storefront pages: the Next.js app at
settings.STOREFRONT_URL is the storefront, and this project is its API and
the Django admin.

These three routes used to render the legacy Django-template catalogue. The
site root now opens the admin (its login page when signed out). The category
and product routes redirect to the matching Next.js page, so old links and
`Category.get_absolute_url()` / `Product.get_absolute_url()` (the admin's
"View on site") still land somewhere real. The redirects are temporary (302)
so a browser never caches them against a STOREFRONT_URL that changes.
"""
from urllib.parse import quote, urlencode

from django.conf import settings
from django.shortcuts import redirect


def _to_storefront(path, **params):
    url = settings.STOREFRONT_URL.rstrip("/") + path
    if params:
        url = f"{url}?{urlencode(params)}"
    return redirect(url)


def backend_home(request):
    return redirect("admin:index")


def category(request, category_slug):
    # The storefront's own category link (Navbar.tsx) is /?category=<slug>.
    return _to_storefront("/", category=category_slug)


def product_detail(request, slug):
    return _to_storefront(f"/product/{quote(slug)}")

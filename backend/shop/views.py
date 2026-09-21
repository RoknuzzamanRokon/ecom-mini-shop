from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

from .models import Category, Product


def product_list(request, category_slug=None):
    products = Product.objects.filter(is_active=True).select_related("category")

    category = None
    if category_slug:
        category = get_object_or_404(Category, slug=category_slug, is_active=True)
        products = products.filter(category=category)

    query = request.GET.get("q", "").strip()
    if query:
        products = products.filter(
            Q(name__icontains=query) | Q(category__name__icontains=query)
        ).distinct()

    paginator = Paginator(products, settings.PRODUCTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    hot_deal = (
        Product.objects.filter(is_active=True, old_price__isnull=False)
        .exclude(old_price__lte=0)
        .order_by("-created_at")
        .first()
    )

    context = {
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "category": category,
        "hot_deal": hot_deal,
        "search_query": query,
    }
    return render(request, "shop/product_list.html", context)


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category"), slug=slug, is_active=True
    )
    return render(request, "shop/product_detail.html", {"product": product})

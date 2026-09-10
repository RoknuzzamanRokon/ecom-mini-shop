from django.db.models import Count, Q
from .cart import cart_item_count
from .models import Category


def shop_context(request):
    return {
        "cart_item_count": cart_item_count(request),
        "nav_categories": Category.objects.filter(is_active=True).annotate(
            product_count=Count("products", filter=Q(products__is_active=True))
        ),
        "search_query": request.GET.get("q", "").strip(),
    }


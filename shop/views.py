import uuid

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import cart as cart_utils
from .forms import CheckoutForm
from .models import Category, Order, OrderItem, Product


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


@require_POST
def cart_add(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)
    try:
        quantity = int(request.POST.get("quantity", 1))
    except ValueError:
        quantity = 1
    quantity = max(quantity, 1)
    cart_utils.add_product(request, product, quantity=quantity)
    messages.success(request, f'"{product.name}" was added to your cart.')

    next_url = request.POST.get("next")
    if next_url:
        return redirect(next_url)
    return redirect("shop:cart")


@require_POST
def cart_increase(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart_utils.increase_quantity(request, product)
    return redirect("shop:cart")


@require_POST
def cart_decrease(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    cart_utils.decrease_quantity(request, product)
    return redirect("shop:cart")


@require_POST
def cart_remove(request, product_id):
    cart_utils.remove_product(request, product_id)
    messages.success(request, "Item removed from cart.")
    return redirect("shop:cart")


def cart_view(request):
    items, total = cart_utils.get_cart_items(request)
    return render(request, "shop/cart.html", {"items": items, "total": total})


def checkout(request):
    items, total = cart_utils.get_cart_items(request)
    if not items:
        messages.info(request, "Your cart is empty.")
        return redirect("shop:cart")

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            order = Order.objects.create(
                order_number=_generate_order_number(),
                customer_name=form.cleaned_data["full_name"],
                phone=form.cleaned_data["phone"],
                address=form.cleaned_data["address"],
                city=form.cleaned_data["city"],
                total_amount=total,
            )
            for item in items:
                OrderItem.objects.create(
                    order=order,
                    product=item["product"],
                    product_name=item["product"].name,
                    price=item["product"].price,
                    quantity=item["quantity"],
                    subtotal=item["subtotal"],
                )
            cart_utils.clear_cart(request)
            return redirect("shop:order_success", order_id=order.id)
    else:
        form = CheckoutForm()

    return render(
        request, "shop/checkout.html", {"form": form, "items": items, "total": total}
    )


def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    return render(request, "shop/order_success.html", {"order": order})


def _generate_order_number():
    return f"ORD{timezone.now():%Y%m%d}{uuid.uuid4().hex[:6].upper()}"

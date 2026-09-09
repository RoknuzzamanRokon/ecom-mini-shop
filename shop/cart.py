from decimal import Decimal

from .models import Product

CART_SESSION_KEY = "cart"


def get_cart(request):
    return request.session.get(CART_SESSION_KEY, {})


def save_cart(request, cart):
    request.session[CART_SESSION_KEY] = cart
    request.session.modified = True


def add_product(request, product, quantity=1):
    cart = get_cart(request)
    product_id = str(product.id)
    current = cart.get(product_id, 0)
    new_qty = current + quantity
    if product.stock:
        new_qty = min(new_qty, product.stock)
    if new_qty > 0:
        cart[product_id] = new_qty
    save_cart(request, cart)
    return cart[product_id]


def set_quantity(request, product, quantity):
    cart = get_cart(request)
    product_id = str(product.id)
    if quantity <= 0:
        cart.pop(product_id, None)
    else:
        if product.stock:
            quantity = min(quantity, product.stock)
        cart[product_id] = quantity
    save_cart(request, cart)


def increase_quantity(request, product):
    cart = get_cart(request)
    current = cart.get(str(product.id), 0)
    set_quantity(request, product, current + 1)


def decrease_quantity(request, product):
    cart = get_cart(request)
    current = cart.get(str(product.id), 0)
    set_quantity(request, product, current - 1)


def remove_product(request, product_id):
    cart = get_cart(request)
    cart.pop(str(product_id), None)
    save_cart(request, cart)


def clear_cart(request):
    save_cart(request, {})


def cart_item_count(request):
    return sum(get_cart(request).values())


def get_cart_items(request):
    cart = get_cart(request)
    items = []
    total = Decimal("0.00")
    if not cart:
        return items, total

    product_ids = [int(pid) for pid in cart.keys()]
    products = Product.objects.filter(id__in=product_ids, is_active=True).select_related(
        "category"
    )
    products_by_id = {product.id: product for product in products}

    for product_id, quantity in list(cart.items()):
        product = products_by_id.get(int(product_id))
        if not product:
            continue
        subtotal = product.price * quantity
        total += subtotal
        items.append(
            {
                "product": product,
                "quantity": quantity,
                "subtotal": subtotal,
            }
        )
    return items, total

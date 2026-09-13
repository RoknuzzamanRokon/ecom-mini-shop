# MiniShop

A simple, functional e-commerce website built with Django, converted from a static
HTML/Tailwind UI reference (`main_ui.html`) into a dynamic app backed by the Django ORM
and SQLite.

**Flow:** Products → Product Details → Add to Cart → Cart → Checkout → Order Success
(Cash on Delivery).

## Features

- Product catalog with categories, search (by product or category name), and pagination
- Product detail pages with quantity selector
- Session-based shopping cart (add / increase / decrease / remove, live cart badge)
- Checkout with form validation and Cash on Delivery orders
- Order success page with order summary
- Django admin for managing categories, products, and orders

## Tech Stack

- Django 5.2 + Django Templates + Django ORM
- SQLite (development/demo database)
- Tailwind CSS (via CDN) + vanilla JavaScript
- Pillow (for product images)

## Setup

Requires Python 3.10+.

```bash
# 1. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Apply database migrations
python manage.py migrate

# 4. Seed demo categories and products (with placeholder images)
python manage.py seed_demo_data

# 4b. Or seed the full showcase storefront: 4 demo shops, 9 categories and
#     24 products with real product photography downloaded from Unsplash.
#     Add --force to re-download images, --password to enable demo seller login.
python manage.py seed_showcase

# 5. Create an admin user
python manage.py createsuperuser

# 6. Run the development server
python manage.py runserver
```

Then open:

- **Storefront:** http://127.0.0.1:8000/
- **Admin panel:** http://127.0.0.1:8000/admin/

## Running Tests

```bash
python manage.py test shop
```

## Project Structure

```
config/                Django project settings, root URLs
shop/                  Main app: models, views, urls, cart, admin
  management/commands/  seed_demo_data, seed_showcase commands
  migrations/
templates/
  base.html            Base layout (header, footer, messages)
  shop/                Page templates (product list/detail, cart, checkout, order success)
  shop/partials/       Reusable partials (navbar, category sidebar, hot deal, product card, footer)
static/
  css/style.css        Minimal custom CSS (Tailwind utility classes handle most styling)
  js/cart.js           Quantity selector behavior
media/products/        Uploaded/generated product images (created at runtime, gitignored)
main_ui.html           Original static HTML design reference
```

## Notes

- Demo product images are generated placeholder graphics (solid color + label), not real
  product photos. Replace them anytime via the admin panel.
- `db.sqlite3` and `media/` are gitignored — re-run migrations and the seed command after
  a fresh clone.

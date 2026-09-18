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

## Settings

`config/settings/` holds three modules. Select one with `--settings=` or
`DJANGO_SETTINGS_MODULE`.

| Module | Selected by | Notes |
| --- | --- | --- |
| `config.settings.base` | neither, directly | Shared configuration only. |
| `config.settings.dev` | `manage.py`, `wsgi.py`, `asgi.py` (default) | `DEBUG = True`. Value-for-value identical to the pre-split `config/settings.py`. |
| `config.settings.test` | the test suite | Same application behaviour as `dev`; only the cost of running it differs. |

## Running Tests

```bash
python manage.py test --settings=config.settings.test --parallel --keepdb --noinput
```

- `--settings=config.settings.test` — low-iteration password hashing, and a
  default worker count for a bare `--parallel`. Without it the suite still
  passes, just far more slowly.
- `--keepdb` — reuses the test database instead of replaying 21 migrations.
- `--noinput` — required for unattended runs: a stale `test_minishop` database
  otherwise blocks on an interactive prompt and the run hangs forever.
- `--parallel` — one worker per `DJANGO_TEST_PROCESSES`, which the test settings
  default to 4x the core count because the suite is database-round-trip-bound
  rather than CPU-bound. Pass `--parallel N` to override. **Requires `tblib`**
  (in `requirements.txt`): Django returns worker-process failures to the parent
  by pickling them, and tracebacks cannot be pickled without it — so a parallel
  run without `tblib` aborts with `TypeError: cannot pickle 'traceback' object`
  the moment any test fails, rather than reporting the failure.

Single app or module, same flags:

```bash
python manage.py test shop --settings=config.settings.test --keepdb --noinput
```

### Pointing the suite at a different MySQL

The suite's wall clock is dominated by database round-trip time, so it runs
dramatically faster against a local MySQL than a remote one. `TEST_DATABASE_URL`
overrides `DATABASE_URL` for test runs only:

```bash
TEST_DATABASE_URL=mysql://user:pass@127.0.0.1:3306/minishop \
    python manage.py test --settings=config.settings.test --parallel --keepdb --noinput
```

It must be MySQL. The suite's concurrency tests rely on real
`SELECT ... FOR UPDATE` row locking, which SQLite accepts and silently ignores —
they would report green there while testing nothing.

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

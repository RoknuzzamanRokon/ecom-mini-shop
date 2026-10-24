# MiniShop

A simple, functional e-commerce website built with Django, converted from a static
HTML/Tailwind UI reference (`main_ui.html`) into a dynamic app backed by the Django ORM
and SQLite.

**Flow:** the server-rendered pages here are the catalogue only — Products → Product
Details. The cart/checkout/order-success storefront was retired on 2026-09-21
(Phase 2E); the Next.js app is the customer storefront and checkout surface, and it
talks to the DRF API under `/api/`.

## Features

- Product catalog with categories, search (by product or category name), and pagination
- Product detail pages
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

# 2b. Create backend/.env (gitignored) with the database URL and two
#     different secret keys -- see "Environment variables" below
#     DATABASE_URL=mysql://user:password@127.0.0.1:3306/minishop
#     DJANGO_SECRET_KEY=<generated>
#     DJANGO_JWT_SIGNING_KEY=<generated, not the same value>

# 3. Apply database migrations
python manage.py migrate

# 4. Seed demo categories and products (with placeholder images) into the
#    seeder's own "MiniShop Demo Store". Seed commands run only with DEBUG on
#    and --i-know-this-is-a-dev-db, and change only their own rows (accounts
#    @minishop.demo, their shops and products); a real row that shares a slug
#    or username is reported and left alone.
python manage.py seed_demo_data --i-know-this-is-a-dev-db

# 4b. Or seed the full showcase storefront: 4 demo shops, 9 categories and
#     24 products with real product photography downloaded from Unsplash.
#     Add --force to re-download images, --password to give the demo seller
#     accounts this run creates a login (existing accounts keep theirs).
python manage.py seed_showcase --i-know-this-is-a-dev-db

# 5. Create an admin user
python manage.py createsuperuser

# 6. Run the development server
python manage.py runserver
```

Then open:

- **Storefront:** http://127.0.0.1:8000/
- **Admin panel:** http://127.0.0.1:8000/admin/

## Settings

`config/settings/` holds four modules. Select one with `--settings=` or
`DJANGO_SETTINGS_MODULE`.

| Module | Selected by | Notes |
| --- | --- | --- |
| `config.settings.base` | neither, directly | Shared configuration only. |
| `config.settings.dev` | `manage.py` (default) | `DEBUG = True`. Refuses to start without both secret keys. |
| `config.settings.test` | the test suite | Same application behaviour as `dev`; only the cost of running it differs. Makes up throwaway keys when none are set. |
| `config.settings.prod` | any deployment | `DEBUG = False`, HTTPS redirect, HSTS, secure cookies; hosts and origins from the environment. |

`wsgi.py` and `asgi.py` have no default: a server started without
`DJANGO_SETTINGS_MODULE` stops with an error instead of running as `dev`.

### Environment variables

Read from the environment, or from `backend/.env` (gitignored). A real
environment variable wins over the same line in `.env`.

| Variable | Used by | Notes |
| --- | --- | --- |
| `DATABASE_URL` | all | `mysql://user:password@host:3306/name`. MySQL 8 only. |
| `DJANGO_SECRET_KEY` | all | Sessions, CSRF, password-reset links. Required by `dev` and `prod`. |
| `DJANGO_JWT_SIGNING_KEY` | all | Signs API access and refresh tokens. Must differ from `DJANGO_SECRET_KEY`. Required by `dev` and `prod`. |
| `DJANGO_ALLOWED_HOSTS` | `prod` | Comma-separated. Required. |
| `DJANGO_CORS_ALLOWED_ORIGINS` | `prod` | Comma-separated storefront origins, e.g. `https://shop.example.com`. Required. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `prod` | Comma-separated. Optional. |
| `DJANGO_BEHIND_TLS_PROXY` | `prod` | `true` when a proxy terminates HTTPS and sets `X-Forwarded-Proto`. Only when the proxy overwrites that header. |
| `DJANGO_SECURE_HSTS_SECONDS` | `prod` | Optional; one year by default. |
| `DJANGO_NUM_PROXIES` | all | Trusted proxies in front of Django that append to `X-Forwarded-For`, so rate limits, the admin sign-in lockout and audit rows see the real client address. `0` (the default) uses `REMOTE_ADDR` and ignores the header. |

Generate each key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

`prod` wants each key at least 50 characters long. The key that used to be
committed in `config/settings/base.py` is in git history: treat it as public
and never reuse it. Changing `DJANGO_JWT_SIGNING_KEY` signs every API client
out; changing `DJANGO_SECRET_KEY` ends every admin session.

Before a deployment, this must report no issues:

```bash
python manage.py check --deploy --fail-level WARNING --settings=config.settings.prod
```

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

### Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request: the backend suite
against a MySQL 8 service container, then `npm run typecheck` and `npm run build`
for the frontend. It is verification only — no deploy, publish or release step.

CI supplies `DATABASE_URL` as an environment variable (there is no `.env` in a
fresh checkout), generates throwaway secret keys for each run, and runs the suite with `--parallel 4` rather than the settings
default, because against a local database the suite is CPU-bound rather than
round-trip-bound.

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
shop/                  Main app: models, views, urls, services, API views, admin
  management/commands/  seed_demo_data, seed_showcase commands
  fixtures/seed_images/ Category images seed_demo_data copies into media/
  migrations/
templates/
  base.html            Base layout (header, footer, messages)
  shop/                Page templates (product list, product detail)
  shop/partials/       Reusable partials (navbar, category sidebar, hot deal, product card, footer)
static/
  css/style.css        Minimal custom CSS (Tailwind utility classes handle most styling)
media/                 Runtime uploads: customer photos, product and shop images (gitignored)
main_ui.html           Original static HTML design reference
```

## Notes

- Demo product images are generated placeholder graphics (solid color + label), not real
  product photos. Replace them anytime via the admin panel.
- `media/` and `*.log` are gitignored: uploads (including customers' photos) and server
  logs never belong in git, and CI fails if a file under `backend/media/` or a log is
  tracked. After a fresh clone, re-run migrations and the seed commands: `seed_demo_data`
  copies the category images from `shop/fixtures/seed_images/`, and `seed_showcase`
  downloads the product and shop photos.

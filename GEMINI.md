# MiniShop Project Rules & Guidelines

## 1. Project Architecture & Monorepo Structure
- **Decoupled Full-Stack Architecture**:
  - `backend/`: Django 5 + Django REST Framework (DRF) running with SQLite. Virtualenv is located at `backend/venv/`.
  - `frontend/`: Next.js 16 (Turbopack) + React 19 + TypeScript + Tailwind CSS v4.
- **Root Directory**: `/mnt/Project/Python/MiniShop`

---

## 2. Ports & Networking
- **Django Backend**: Must always run on port **`8001`** (`http://127.0.0.1:8001`).
  - *Reason*: Avoid port 8000 conflicts with local services.
  - Command: `backend/venv/bin/python backend/manage.py runserver 127.0.0.1:8001`
- **Next.js Frontend**: Runs on port **`3000`** (`http://localhost:3000`).
  - Command: `npm run dev` inside `frontend/`
- **API & Media Proxy**:
  - `NEXT_PUBLIC_API_URL=http://127.0.0.1:8001` in `frontend/.env.local`.
  - Next.js rewrites forward `/media/:path*` directly to `http://127.0.0.1:8001/media/:path*`.
  - All local image URLs on the frontend must use `formatImageUrl()` from `@/lib/api`.

---

## 3. Mandatory Currency Standard
- **Always use the Bangladeshi Taka symbol `৳`** across the entire application:
  - Header deals, Perks, Hot Deals widget, Product grids/cards, Detail pages, Cart drawer, Checkout, and Order receipts.
  - **Never** use `$`, `USD`, `Tk`, or `BDT` in user-facing UI text.

---

## 4. Design System & Theme Styling
- **Theme Palettes**: 5 Japanese-inspired color grading palettes supported (`ai` Kachi Indigo default, `sumi`, `matsu`, `den`, `current`) with light and dark mode.
- **Strict Token Rule**:
  - **Never** use hardcoded arbitrary colors (e.g. `bg-blue-600`, `text-gray-900`, `bg-[#21486B]`) in components.
  - **Always** use semantic CSS tokens defined in `src/app/globals.css`:
    - `bg-page`, `bg-surface`, `bg-surface-alt`, `bg-surface-sunken`
    - `text-ink`, `text-ink-body`, `text-ink-muted`
    - `bg-primary`, `bg-primary-hover`, `text-on-primary`
    - `text-accent`, `bg-accent`, `text-on-accent`
    - `border-line`, `border-line-subtle`
    - `bg-nav`, `bg-nav-strip`, `bg-nav-active`, `text-nav-text`, `text-nav-active-text`

---

## 5. Layout & UX Requirements
- **Sticky Navigation**:
  - Both `Header` and `Navbar` must stick together at `top: 0` (`sticky top-0 z-40 w-full shadow-sm`).
  - The category navigation strip must never hide on scroll.
- **Mobile View Responsiveness (`< lg`)**:
  - The left sidebar (`CategorySidebar` and `HotDealWidget`) must be **hidden** on mobile screens (`hidden lg:flex lg:col-span-3`).
  - Main catalog section takes full width (`w-full lg:col-span-9`).
  - `Navbar` must display a **Categories Toggler Button** with a collapsible 2-column touch drawer and quick-scroll pills.
- **Hero Banner Rules**:
  - **Home / All Mode (`activeCategory === 'all'`)**:
    - Animated carousel slider cycling through all categories.
    - Autoplay every 4.5s with pause-on-hover, previous/next chevron buttons, and indicator dots (`• • •`).
  - **Filtered Category Mode (e.g. `Shoes`, `Clothing`)**:
    - Slider is disabled. Display **only** that category's hero image and description with an item count badge and "All Categories" button.
- **Product Detail Page**:
  - Balanced 5:7 column split (`lg:col-span-5` for gallery, `lg:col-span-7` for product info and actions).
  - Main image container must remain compact (`aspect-[4/3] sm:aspect-square max-h-[430px] w-full`).
  - Main image must feature the **Amazon-style circular magnifying zoom loupe** (`ProductImageZoom.tsx`) on cursor hover.

---

## 6. Backend & Database Conventions
- **REST Endpoints**: All API routes live under `/api/` in `backend/shop/urls.py`.
- **Category Administration**:
  - `Category` model includes `image` (`upload_to="categories/"`) and `description`.
  - `CategoryAdmin` displays live `image_preview` thumbnails, file upload controls, and search by name/description.
  - `CategorySerializer` prioritizes `category.image.url`, falling back to the first active product image if unassigned.
- **Image Optimization**:
  - `next.config.ts` must have `images: { unoptimized: true }` to allow local Django IP media serving without 400 errors.

---

## 7. Quality Assurance & Verification
Before marking any task complete:
1. Run backend tests:
   ```bash
   backend/venv/bin/python backend/manage.py test shop
   ```
   *(Ensure all unit and API tests pass with 0 errors).*
2. Run frontend build verification:
   ```bash
   cd frontend && npm run build
   ```
   *(Ensure TypeScript and Turbopack compile with 0 errors).*
3. Verify both dev servers respond with HTTP 200:
   - Django: `http://127.0.0.1:8001/api/categories/`
   - Next.js: `http://localhost:3000/`

---

## 8. Mandatory Git Version Control & Commit Protocol
- **Always Stage & Commit Every Completed Change**:
  - For any modification, feature addition, refactoring, or bug fix, you **MUST** stage the files with `git add` and create a commit using `git commit -m "<subject line>"`.
  - The commit subject line must clearly describe the changing stage (e.g. `feat: ...`, `fix: ...`, `refactor: ...`, `style: ...`, `docs: ...`).
  - **Never** finish a task or leave modified files unstaged/uncommitted. Every working milestone must be preserved in version control.


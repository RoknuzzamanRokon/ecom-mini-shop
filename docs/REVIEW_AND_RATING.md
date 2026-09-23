# MiniShop — Review & Rating System Plan

**Created:** 2026-09-23 · **Baseline commit:** `6179759` · **Status:** Tasks 0–2 done; Tasks 3–12 not started

This is the task list for the review & rating feature. Work through it **one task at a
time, in order**. Each task is sized to be one commit. When a task is done, tick its
checkboxes, set its **Status** line, and update the table in §4.

To continue, just ask: **"do Task N"**.

---

## 1. What we are building

1. A logged-in user can give a **star rating (1–5)** and an optional **comment**.
2. They can rate **an individual product** or **a shop**.
3. Every **product page** and every **shop page** shows its average rating and its
   list of reviews at the bottom.
4. Ratings also show where a product or shop is listed (product cards, shops list).
5. A user who is not logged in can **read** reviews but not write them. They see a
   "Log in to write a review" prompt.

---

## 2. What already exists (do not rebuild)

Product reviews were added in commit `c4fb3b8` (`feat(reviews): add product reviews and ratings`).

| Part | Where |
|---|---|
| `Review` model: one review per (user, product), rating 1–5, comment, `is_verified_purchase` | `backend/customers/models.py:191` |
| Migration | `backend/customers/migrations/0003_review.py` |
| `ReviewService` create / update / delete, writes `REVIEW_*` audit logs | `backend/customers/services.py:282` |
| `CanCreateReview` (`reviews.create`, seeded to CUSTOMER only), `IsReviewOwner` | `backend/customers/permissions.py:97` |
| `POST /api/reviews/` · `GET /api/reviews/mine/?product_id=` · `PATCH`/`DELETE /api/reviews/<id>/` | `backend/customers/urls.py:23-25` |
| Public list `GET /api/products/<id>/reviews/` (404 for non-public products) | `backend/shop/api_views.py:220` |
| `average_rating` + `review_count` on every public product endpoint (one annotation) | `backend/shop/services.py:317-325` |
| Django admin `ReviewAdmin` | `backend/customers/admin.py:48` |
| 19 backend tests | `backend/shop/test_product_reviews.py` |
| `ProductReviews` component: list, pagination, submit/edit/delete form, verified badge | `frontend/src/components/product/ProductReviews.tsx` |
| Real stars and review count in the product page header | `frontend/src/app/product/[slug]/page.tsx:150-170` |
| API helpers and types | `frontend/src/lib/api.ts:1099-1171`, `frontend/src/lib/types.ts:111-131` |

**Gaps found while reading the code:**

- `ProductCard` shows **5 hardcoded filled stars** for every product
  (`frontend/src/components/home/ProductCard.tsx:174-181`).
- `GET /api/reviews/mine/?product_id=abc` returns a **500** instead of a 400
  (`backend/customers/views.py:280`, where a non-numeric id reaches the ORM).
- A shop owner who also holds the CUSTOMER role can **review their own product**.
- When a super administrator edits or deletes someone else's review, the audit log
  records the **review's author** as the actor, not the administrator
  (`backend/customers/services.py:342`, `:354`).
- The "Log In" button in the review section goes to `/login` with no `?next=`, so the
  user lands on the home page instead of back on the product
  (`ProductReviews.tsx:215`).
- There is **no shop review** at all: no model, API or UI.

---

## 3. Decisions (the rules the system follows)

These are the defaults this plan is built on. Change them here **before** starting the
task that depends on them.

| # | Rule | Why |
|---|---|---|
| D1 | Any logged-in user who holds `reviews.create` (the CUSTOMER role) can review. **A purchase is not required.** The "Verified Purchase" badge marks reviews from real buyers. | Matches the request: "if user login then user can give rating". |
| D2 | **One review per user per product, and one per user per shop.** Posting a second one returns `409`. The user edits their existing review instead. | Same as the current product rule. Stops one user from stacking ratings. |
| D3 | Rating is **required** (whole number 1–5). Comment is **optional**, max 2000 characters. | Same as the current product rule. |
| D4 | A **shop's rating comes only from shop reviews.** It is not an average of its products' ratings. | Keeps the two ratings independent and easy to explain. |
| D5 | A shop owner **cannot review their own shop or their own products** (`403`). | Prevents self-promotion. |
| D6 | Averages and counts are **calculated live** with database annotations. No stored `rating` columns. | Same approach products already use. It can't drift out of sync. Revisit only if it gets slow. |
| D7 | Shop reviews reuse the existing **`reviews.create`** permission. No new RBAC permission, except `reviews.moderate` in optional Task 12. | One permission for "can write reviews" is simpler for admins. |
| D8 | `ShopReview` lives in the **`customers`** app, next to `Review`. Its tests go in **`backend/shop/test_shop_reviews.py`**, next to `test_product_reviews.py`. | Keeps review code in one place, and AGENTS.md's `manage.py test shop` covers both. |
| D9 | The shop FK uses `related_name="customer_reviews"`, the same name `Product` uses. | `Shop` already has `reviewed_by`/`reviewed_at` for the unrelated approval workflow. |

---

## 4. Task overview

| Task | Title | Side | Status |
|---|---|---|---|
| 0 | Product reviews (model, API, product-page UI) | full-stack | ✅ Done (`c4fb3b8`) |
| 1 | Product cards show real star ratings | frontend | ✅ Done |
| 2 | Product review fixes | backend (+1 frontend line) | ✅ Done |
| 3 | Rating summary + review sorting on the product page | full-stack | ⬜ Not started |
| 4 | "Top Rated" product sort | full-stack | ⬜ Not started |
| 5 | `ShopReview` model, migration, Django admin | backend | ⬜ Not started |
| 6 | Shop review write API (create / mine / edit / delete) | backend | ⬜ Not started |
| 7 | Shop review public list + shop rating aggregates | backend | ⬜ Not started |
| 8 | Shared review UI components (refactor) | frontend | ⬜ Not started |
| 9 | Shop page: rating in header + reviews section | frontend | ⬜ Not started |
| 10 | Shops list cards show rating | frontend | ⬜ Not started |
| 11 | *(optional)* "My Reviews" page in profile | full-stack | ⬜ Not started |
| 12 | *(optional)* Review moderation for staff | full-stack | ⬜ Not started |

**The feature you asked for is complete after Task 10.** Tasks 11 and 12 are extras.

---

## 5. Tasks in detail

### Task 1 — Product cards show real star ratings

**Goal.** Every product card shows its true average rating and review count.

- [x] Create `frontend/src/components/reviews/StarRating.tsx`: read-only stars from a
      number, with full / half (`star_half`) / empty icons, and a `size` prop. Use
      the `text-star` token (no palette colours).
- [x] `ProductCard.tsx:174-181`: replace the 5 hardcoded stars with
      `<StarRating rating={product.average_rating ?? 0} />` plus `(review_count)`.
      When `review_count` is 0, show muted empty stars with no count.
- [x] Use `StarRating` in the product page header (`product/[slug]/page.tsx:152-164`)
      and in `ProductReviews.tsx` (`StarRow`), so the stars are drawn in one place.

**Done when.** A product with no reviews shows empty stars on its card. A product
rated 4 and 5 shows 4½ stars and `(2)`. `npm run build` passes.

**Status:** ✅ Done 2026-09-23

- `StarRating` rounds to the nearest half star and clamps to 0–5. A rating of 0 (or
  NaN) draws **faint outlines** (`text-ink-faint`), because 0 can only mean "no
  reviews"; any real rating uses `text-star`. It has `role="img"` plus an
  `aria-label` / `title` such as "Rated 4.5 out of 5".
- **`star_half` does not get `fill-active`.** The glyph was rendered from the real
  Material Symbols font: at FILL 0 its left half is already solid, which is the
  half-star look. Full stars use the existing `fill-active` class, not inline
  `fontVariationSettings`.
- **Wider than planned:** the card's **list view** (`ProductCard.tsx:99-103`) and
  `HotDealWidget.tsx:136-140` also had hardcoded stars (the hot deal showed a fixed
  4/5). Both now use `StarRating`. `/api/hot-deal/` already returns the rating
  fields, because it uses the annotated public queryset.
- The product page header also shows the average as a number (e.g. `4.5`) next to
  the stars when there are reviews.
- Verified: the component was rendered with `react-dom/server` for 0, 1, 3.24, 3.25,
  4.5, 5, 7 and NaN, and each gives the expected stars and colour. `npm run
  typecheck` and `npm run build` pass. Not checked in a running browser.
- Pre-existing, left alone: `npx eslint` reports `react-hooks/set-state-in-effect`
  at `HotDealWidget.tsx:21`, on the image `useEffect` this task did not touch. CI
  does not run lint.

---

### Task 2 — Product review fixes

**Goal.** Close the gaps listed in §2 before building shop reviews on the same code.

- [x] `MyProductReviewView`: return `400` when `product_id` is missing **or not a
      number** (today a non-number gives a 500).
- [x] Self-review guard (D5): add `SelfReviewError` in `customers/services.py`.
      `ReviewService.create_review` raises it when `product.shop.owner.user == user`,
      and the view returns `403` with a clear message.
- [x] Audit actor: `update_review` / `delete_review` take an `actor` argument, and the
      views pass `request.user`. The log then names the administrator when an
      administrator acts.
- [x] Public reviewer name: `ReviewSerializer.get_reviewer_name` uses
      `customer_profile.display_name`, then full name, then username. Add
      `select_related("user__customer_profile")` to the list query so there are no
      extra queries per review.
- [x] `ProductReviews.tsx:215`: send guests to `/login?next=/product/<slug>`. The
      component needs the product slug as a new prop.
- [x] Tests in `shop/test_product_reviews.py`: non-numeric id → 400; owner reviewing
      own product → 403; admin delete logs the admin as actor; display name is used.

**Done when.** All new and existing review tests pass. `npm run build` passes.

**Status:** ✅ Done 2026-09-23

- The self-review guard is one query: `Product.objects.filter(pk=product_id,
  shop__owner__user=user).exists()`. It runs before the verified-purchase check. A
  shop owner can still review **other** shops' products (tested).
- Audit entries: `REVIEW_UPDATED` / `REVIEW_DELETED` now log `actor=request.user`
  and add `author_id` to the metadata, so the author stays on record after a delete.
  All three review actions now also record `ip_address`, like `AddressService`.
  Callers that pass no actor still fall back to the review's author.
- `MyProductReviewView` parses `product_id` with `int()` (catching `TypeError` and
  `ValueError`), so both a missing id and `abc` return a 400.
- Reviewer name: blank or whitespace-only `display_name` falls through to full name,
  then username. A user with no `CustomerProfile` works, because the missing
  one-to-one raises an `AttributeError` subclass, which `getattr(..., None)` catches.
- New tests (10): missing/non-numeric id → 400 (2); owner → 403, other shop → 201
  (2); owner-edit / admin-edit / admin-delete audit actor (3); display name,
  blank-name fallback, and **query count stays flat from 1 to 3 reviews** (3).
- Verified: `shop.test_product_reviews` **29/29 OK** (19 existing + 10 new) in 516 s.
  It ran against a separate throwaway test database (`test_minishop_reviews`,
  created and then destroyed) because the Task 1 full `shop` suite was still using
  `test_minishop`. `npm run typecheck` and `npm run build` pass.
- Pre-existing, left alone: `npx eslint` flags `ProductReviews.tsx` for
  `react-hooks/set-state-in-effect` (the `loadMyReview` effect) and `no-explicit-any`
  (`catch (err: any)`), on lines this task did not change. CI does not run lint.
  Task 8 rewrites this component and should clear them.

---

### Task 3 — Rating summary + review sorting on the product page

**Goal.** Above the review list, show an Amazon-style summary: a large average, stars,
the total count, and a bar for each star level. The user can also sort the list.

- [ ] Backend: add `rating_breakdown` to `ProductDetailSerializer` only (not the list
      serializer), as `{"5": n, "4": n, "3": n, "2": n, "1": n}` with every key
      present. Use one `values("rating").annotate(Count)` query.
- [ ] Backend: `GET /api/products/<id>/reviews/?ordering=` accepts `newest` (default),
      `oldest`, `highest`, `lowest`. Unknown values fall back to `newest`. Break ties
      by `-created_at`.
- [ ] Frontend: `types.ts` adds `rating_breakdown?` to `Product`, and
      `getProductReviews()` takes an `ordering` argument.
- [ ] Frontend: create `components/reviews/RatingSummary.tsx` (average, stars, count,
      5 bars with percentages, all token colours). Show it at the top of
      `ProductReviews`, with a sort `<select>` above the list.
- [ ] Tests: breakdown counts are correct after create/update/delete; each ordering
      value sorts correctly; a bad ordering value falls back.

**Done when.** The product page shows the summary bars and the sort control works.
Tests and build pass.

**Status:** ⬜ Not started

---

### Task 4 — "Top Rated" product sort

**Goal.** Shoppers can sort the catalogue by rating.

- [ ] Backend: add `rating` → `average_rating` and `-rating` → `-average_rating`
      (tie-break `-review_count`, then `-created_at`) to `ORDERING_MAP`
      (`shop/api_views.py:162`). Products with no reviews must sort **last** for
      `-rating`.
- [ ] Frontend: add a "Top Rated" option to the shop page sort dropdown
      (`shop/[slug]/page.tsx:306-309`) and to any other catalogue sort control.
- [ ] Tests: `?ordering=-rating` returns the highest-rated product first and
      unreviewed products last.

**Done when.** "Top Rated" sorts correctly. Tests and build pass.

**Status:** ⬜ Not started

---

### Task 5 — `ShopReview` model, migration, Django admin

**Goal.** The database can store shop reviews.

- [ ] `customers/models.py`: add `ShopReview`, built like `Review`:
      - `user` FK → `AUTH_USER_MODEL`, `related_name="shop_reviews"`
      - `shop` FK → `"shops.Shop"`, `related_name="customer_reviews"` (D9)
      - `rating` 1–5 (validators + `clean()`), `comment` (blank allowed),
        `is_verified_purchase`, `created_at`, `updated_at`
      - `UniqueConstraint(user, shop)` named `unique_review_per_user_shop`
      - index `(shop, -created_at)` named `cust_shoprev_shop_created_idx`
- [ ] Migration `customers/0004_shopreview.py` via `makemigrations`. Then
      `makemigrations --check` must report nothing.
- [ ] `customers/admin.py`: `ShopReviewAdmin` (list: user, shop, rating, verified,
      created; search by username or shop name; filter by rating, verified, date;
      `select_related`).
- [ ] Tests: the unique constraint blocks a duplicate; rating outside 1–5 fails `clean()`.

**Done when.** The migration applies cleanly, `ShopReviewAdmin` appears in `/admin/`,
and the tests pass.

**Status:** ⬜ Not started

---

### Task 6 — Shop review write API

**Goal.** A logged-in customer can create, read back, edit and delete their shop review.

- [ ] `customers/services.py`: `ShopReviewService.create_review / update_review /
      delete_review`, built like `ReviewService`, including Task 2's `actor` argument.
      - Verified purchase is set once at creation: the user has a `DELIVERED` order
        with an `OrderItem` whose `shop` is this shop (`OrderItem.shop` exists,
        `shop/models.py:467`).
      - Raises `ReviewAlreadyExistsError` (409) and `SelfReviewError` when
        `shop.owner.user == user` (403).
      - Audit actions: `SHOP_REVIEW_CREATED`, `SHOP_REVIEW_UPDATED`, `SHOP_REVIEW_DELETED`.
- [ ] `customers/serializers.py`: `ShopReviewSerializer` (read, same fields as
      `ReviewSerializer`), `ShopReviewCreateSerializer` (`shop_id` must be a public
      shop: `APPROVED` or `ACTIVE`), `ShopReviewUpdateSerializer`.
- [ ] `customers/views.py` + `urls.py`:
      - `POST   /api/shop-reviews/` (`IsAuthenticated` + `CanCreateReview`)
      - `GET    /api/shop-reviews/mine/?shop_id=<id>` (404 if none, 400 on bad id)
      - `PATCH` / `DELETE /api/shop-reviews/<id>/` (`IsReviewOwner`)
- [ ] Tests in `shop/test_shop_reviews.py`, covering the same cases as
      `test_product_reviews.py`: create 201, duplicate 409, guest 401, no role 403,
      rating 0/6 → 400, non-public shop → 400, own shop → 403, verified purchase
      true/false, owner edit/delete, non-owner edit/delete → 403, mine 404/200/401.

**Done when.** All endpoints behave as listed and the tests pass.

**Status:** ⬜ Not started

---

### Task 7 — Shop review public list + shop rating aggregates

**Goal.** Anyone can read a shop's reviews and see its rating.

- [ ] `shops/views.py` + `urls.py`: `GET /api/shops/<slug>/reviews/`: `AllowAny`,
      paginated (12), 404 for non-public shops, same `?ordering=` values as Task 3.
      Place it before the catch-all `<slug:slug>/` route.
- [ ] `PublicShopListView` and `PublicShopDetailView` querysets: annotate
      `average_rating=Avg("customer_reviews__rating")` and
      `review_count=Count("customer_reviews", distinct=True)`.
- [ ] `PublicShopSerializer`: add `average_rating` (rounded to 1 decimal, `0.0` when
      none) and `review_count`. Detail responses also get `rating_breakdown`.
- [ ] If `ShopService.get_nearby_shops` can take the same annotation cheaply, add it
      to `NearbyShopSerializer` too. Otherwise note it here and skip.
- [ ] Tests: guest can list; unknown or non-public shop → 404; average/count correct
      after create/update/delete; fields present on list and detail; breakdown correct.

**Done when.** `GET /api/shops/` and `GET /api/shops/<slug>/` include rating fields,
the review list works, and the tests pass.

**Status:** ⬜ Not started

---

### Task 8 — Shared review UI components (refactor)

**Goal.** Products and shops use the same review UI, so the code isn't written twice.

- [ ] Move the stateful logic of `ProductReviews.tsx` into
      `components/reviews/ReviewSection.tsx`. It takes an adapter prop
      `{ list, getMine, create, update, remove }`, plus labels
      (e.g. "Share your experience with this shop…") and a `loginNext` path.
- [ ] Move `StarPicker` to `components/reviews/StarPicker.tsx`.
- [ ] `ProductReviews.tsx` becomes a thin wrapper that passes the product adapter.
- [ ] **No visible change** on the product page. This task only moves code.

**Done when.** The product page reviews look and work exactly as before (check
submit, edit, delete, paging, sort). `npm run build` passes.

**Status:** ⬜ Not started

---

### Task 9 — Shop page: rating in header + reviews section

**Goal.** A shop page shows its rating at the top and its reviews at the bottom, and
logged-in users can rate the shop.

- [ ] `types.ts`: `ShopReview`, `ShopReviewCreatePayload`, `ShopReviewUpdatePayload`.
      `Shop` gets `average_rating?`, `review_count?`, `rating_breakdown?`.
- [ ] `api.ts`: `getShopReviews(slug, page, ordering)`, `getMyShopReview(shopId, token)`
      (404 → `null`), `createShopReview`, `updateShopReview`, `deleteShopReview`.
      Authenticated calls go through the existing `customerRequest` wrapper.
- [ ] `components/reviews/ShopReviews.tsx`: a `ReviewSection` wrapper with the shop adapter.
- [ ] `shop/[slug]/page.tsx`:
      - In the metadata pills (`:207`), add `★ 4.3 · 12 reviews`. Clicking it scrolls to
        `#shop-reviews`. With no reviews, show "No reviews yet".
      - Below the product grid and pagination, add `<ShopReviews>` with `id="shop-reviews"`.
      - After a review changes, reload the shop so the header rating updates.
- [ ] Guests see "Log in to write a review", which links to `/login?next=/shop/<slug>`.

**Done when.** On a shop page a customer can submit, edit and delete a shop review,
and the header rating updates. A guest sees the reviews but no form. The layout works
at phone width. `npm run build` passes.

**Status:** ⬜ Not started

---

### Task 10 — Shops list cards show rating

**Goal.** `/shops` shows each shop's rating.

- [ ] `shops/page.tsx`: under the shop name on each card, add `<StarRating>` +
      `4.3 (12)`. With no reviews, show muted "No reviews yet".
- [ ] *(optional)* Backend `?ordering=-rating` on `PublicShopListView`, plus a
      "Top Rated" sort on `/shops`.

**Done when.** Shop cards show real ratings. Build passes (and tests, if the optional
sort is done).

**Status:** ⬜ Not started

---

### Task 11 — *(optional)* "My Reviews" page in profile

**Goal.** A customer can see and manage everything they've reviewed in one place.

- [ ] Backend: `GET /api/profile/reviews/` returns
      `{ product_reviews: [...], shop_reviews: [...] }` for the current user. Each item
      includes a small product or shop summary (name, slug, image or logo).
- [ ] Frontend: `/profile/reviews` page with two tabs (Products / Shops). Each row has
      edit and delete, reusing `StarPicker`.
- [ ] Add a "My Reviews" link to the profile sidebar (`profile/layout.tsx:15-19`).
- [ ] On a delivered order's detail page, add a "Rate this product" link next to each
      item, going to `/product/<slug>#reviews`. Give the product review section
      `id="reviews"`; it has no anchor today.
- [ ] Tests: only the caller's own reviews come back; guest → 401.

**Status:** ⬜ Not started

---

### Task 12 — *(optional)* Review moderation for staff

**Goal.** Staff can hide abusive reviews without deleting them.

- [ ] Add `is_hidden` (default `False`), `hidden_reason`, `hidden_by`, `hidden_at` to
      both `Review` and `ShopReview`, with a migration.
- [ ] Hidden reviews are left out of every public list and of `average_rating`,
      `review_count` and `rating_breakdown` (filter the annotations with
      `Q(customer_reviews__is_hidden=False)`). The author still sees their own review,
      marked "Hidden by moderator".
- [ ] RBAC: seed a new `reviews.moderate` permission to SUPER_ADMINISTRATOR,
      ADMINISTRATOR and SUPPORT_TEAM (`rbac/models.py:7-14`). Mirror it in `frontend/src/lib/admin-navigation.ts`
      `ADMIN_PERMISSIONS`.
- [ ] Staff API: `GET /api/admin/reviews/?type=product|shop&rating=&hidden=&q=`,
      `POST .../<id>/hide/` (reason required), `POST .../<id>/unhide/`. Each action
      writes an `AuditLog` entry.
- [ ] Admin console: `/admin/reviews` module following the existing
      `*Governance.tsx` pattern (filter bar, data table, confirm modal).
- [ ] Tests: hidden reviews leave public lists and averages; permission gating; audit logged.

**Status:** ⬜ Not started

---

## 6. How to verify every task

Run from the paths shown. AGENTS.md commandment 8 requires both before a task counts
as done.

```bash
# backend/  — always pass --noinput (a stale test DB otherwise waits forever on a prompt)
venv/Scripts/python.exe manage.py makemigrations --check --dry-run
venv/Scripts/python.exe manage.py test shop --settings=config.settings.test --keepdb --noinput
#   add `customers shops` to the test labels for tasks that touch those apps

# frontend/
npm run typecheck
npm run build
```

**Local environment notes (found in Task 1):**

- **Do not pass `--parallel` on this machine.** Django clones the MySQL test database
  for parallel workers by running `mysqldump`, which is not installed here. The run
  dies with `FileNotFoundError: [WinError 2]` before any test starts. Run serially
  (it is slower), or install the MySQL client tools.
- If `npm run build` / `typecheck` fails with `TS2307` errors in
  `.next/dev/types/validator.ts` about `src/app/account/...`, that is a stale
  `next dev` cache from before commit `9c7f621` removed those pages. Delete
  `frontend/.next/dev/types` (gitignored; `next dev` regenerates it) and rebuild.

Then commit the task by itself (AGENTS.md commandment 9), for example
`feat(reviews): show real star ratings on product cards`.

**UI rules for every frontend task** (from AGENTS.md / GEMINI.md): only token colours
(`text-star`, `text-ink`, `bg-surface`, `border-line`, …), never palette classes;
`৳` for any money; keep the sticky Header + Navbar; everything must work at phone width.

---

## 7. Not in this plan

Recorded so they aren't forgotten. Each would need its own plan.

- Seller **replies** to reviews
- **Photos** on reviews
- **"Was this helpful?"** votes
- **Requiring a purchase** before reviewing (a one-line change to D1 if wanted)
- Email or in-app **notifications** to sellers about new reviews
- **Rate limiting** review posts (DRF throttling)
- Stored `rating` columns (only if live annotations become slow; see D6)

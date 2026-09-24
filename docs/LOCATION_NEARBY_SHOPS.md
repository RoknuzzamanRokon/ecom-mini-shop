# MiniShop — Location & Nearby Shop Discovery Plan

**Created:** 2026-09-24 · **Baseline commit:** `1c64fc1` · **Brief:** [`LOCATION_NEARBY_SHOPS_TASK.md`](./LOCATION_NEARBY_SHOPS_TASK.md) · **Status:** Planned

This is the audit and task list for the location feature. Sections 1–16 follow the
report the brief asks for. Work through the tasks in §14 **one at a time, in order**.
Each task is one commit. When a task is done, tick its boxes, set its **Status** line,
and update the table in §14.

To continue, just ask: **"do Task N"**.

---

## 1. Current Architecture Findings

- **Backend.** Shops live in the `shops` app (`Shop`, `ShopService`, public / seller /
  staff views). Admin shop creation lives in the `shop` app
  (`POST /api/admin/shops/`, `shop/admin_views.py:816`), which delegates to
  `ShopService.create_shop`. Database is MySQL 8.0.46 (shared remote dev server).
- **Shop coordinates are already stored spatially.** `Shop.location` is a custom
  `MySQLPointField` (`shops/fields.py`), a native `POINT NOT NULL SRID 4326`, with a
  `SPATIAL INDEX` (`shops/migrations/0002_alter_shop_location.py`). No GeoDjango/GDAL.
- **`POINT(0 0)` means "no coordinates".** It is the column default.
  `Shop.latitude` / `longitude` return `None` for it and `has_coordinates` is `False`
  (`shops/models.py:86-103`).
- **A public nearby endpoint already exists:** `GET /api/shops/nearby/?lat=&lng=&radius=`
  (`shops/views.py:73`, `ShopService.get_nearby_shops` at `shops/services.py:237`). It
  has 4 API tests. **Nothing in the frontend calls it.**
- **Frontend.** Next.js 16 App Router, React 19, Tailwind v4 tokens. Global state is
  plain React context (`src/context/*`: Auth, Cart, Favorites, Profile, Theme), nested
  in `src/app/layout.tsx`. No state library. `package.json` has only `next`, `react`,
  `react-dom`, `clsx`: **no map library, and no code uses `navigator.geolocation`.**
- **Shop forms with coordinates:**
  - Admin create — `src/app/admin/shops/new/page.tsx:396-430`, two number inputs,
    "both or neither" check, sent to `POST /api/admin/shops/`.
  - Seller edit modal — `src/app/seller/shops/page.tsx:491-518`, sent as `FormData`
    to `PATCH /api/shops/mine/<pk>/update/`.
  - There is **no admin shop edit endpoint**; after creation only the owning seller
    edits the shop. `AdminShopSerializer` does **not** return coordinates, so the admin
    shop detail page cannot show them (`src/lib/admin-api.ts:232-239` says so).
- **Storefront.** Home is `src/app/page.tsx` (client component). Product search lives
  in `Header` and is desktop-only (`hidden md:flex`); it filters products live. The
  shop directory is `/shops` (`src/app/shops/page.tsx`), and a shop's page is
  `/shop/[slug]`.
- **Dev data:** 10 ACTIVE shops. 4 have Dhaka coordinates (from `seed_showcase`); 6
  are at `POINT(0 0)`.
- `backend/tools/my_location.py` / `my_browser_location.html` are standalone scratch
  scripts (IP geolocation via `geocoder`, a bare geolocation demo). The app does not
  use them, and nothing here reuses them.

## 2. Existing Location/Spatial Functionality

| Part | Where | Reuse? |
|---|---|---|
| `Point` value object + `MySQLPointField` (writes with `ST_GeomFromText(..., 4326, 'axis-order=long-lat')`) | `shops/fields.py` | As is |
| Spatial index `shops_shop_location_spatial_idx` | `shops/migrations/0002_alter_shop_location.py` | As is |
| `validate_coordinates()` — required, numeric, finite, lat ±90, lng ±180, rounds to 7 dp | `shops/services.py:38` | As is |
| `validate_radius()` — required, numeric, finite, `> 0`, `<= max_radius_km` (default 1000) | `shops/services.py:67` | As is, with a smaller max passed in |
| `ShopService.get_public_shops_queryset()` — APPROVED/ACTIVE + `average_rating` / `review_count` | `shops/services.py:221` | Base for nearby |
| `ShopService.get_nearby_shops()` — `ST_Distance_Sphere` via parameterised `RawSQL`, public statuses only, `distance <= radius`, nearest first | `shops/services.py:237` | Extend |
| `PublicNearbyShopListView` — AllowAny, `{count, results}` | `shops/views.py:73` | Extend |
| `NearbyShopSerializer` — shop card fields + `distance_km`, `distance_meters` | `shops/serializers.py:57` | Extend |
| Seller/admin coordinate validation on write (`SellerShopUpdateSerializer`, `AdminShopCreateSerializer` → `ShopService`) | `shops/serializers.py:137`, `shop/admin_serializers.py:487` | As is (authoritative) |
| 13 spatial/nearby tests (`ShopSpatialAndNearbyTests`) | `shops/tests.py:368` | Keep; add to them |
| `Shop` TS type already has `latitude` / `longitude` | `src/lib/types.ts:44` | Extend |
| `StarRating`, shop card markup on `/shops` | `src/components/reviews/StarRating.tsx`, `src/app/shops/page.tsx` | Reuse look |

## 3. Gap Analysis

Backend (nearby endpoint):

1. **Radius cap is 1000 km** — far too wide for "nearby". Nothing caps the result count.
2. **Unlocated shops are not excluded.** A shop at `POINT(0 0)` is only filtered out
   by being far away; a search near 0°,0° would list every unlocated shop.
3. **Error handling is wrong.** The view catches DRF's `ValidationError`, but the
   service raises Django's. So every validation error falls through to
   `except Exception` (`shops/views.py:106`) and returns `"['Latitude must be…']"`
   (a stringified list). That same catch-all turns **any** server error (for example
   a database error) into a 400 that echoes the exception text to the public.
4. **No ratings in results.** `NearbyShopSerializer` lacks `average_rating` /
   `review_count` / `status`, so nearby cards can't match the `/shops` cards.
5. Order ties are unstable (distance only).

Backend (shop forms): nothing is missing for the button. Validation already runs on
both write paths. The admin API just doesn't *return* coordinates (see §1).

Frontend: everything is missing — geolocation helper, "Use My Current Location" on
both shop forms, customer location state, API client and types for nearby, the nearby
page, the map, and the home page entry point.

## 4. Recommended Architecture

```text
Existing functionality          shops.ShopService.get_nearby_shops + GET /api/shops/nearby/
        ↓
Reusable service/API            same service, built on get_public_shops_queryset()
        ↓
Required extension              50 km cap · 50-result cap · skip POINT(0 0) · ratings ·
                                clean 400s · stable order        (Task 1, no new endpoint)
        ↓
Frontend integration            lib/geolocation.ts ──► shop forms button      (Tasks 2–3)
                                LocationContext (memory only) + getNearbyShops (Task 4)
                                /shops/nearby page: list  →  + Leaflet map    (Tasks 5–6)
                                home page "Shops near you" bar → /shops/nearby (Task 7)
```

**Decisions** (change them here before starting the task that depends on them):

| # | Rule | Why |
|---|---|---|
| D1 | **Extend `GET /api/shops/nearby/`**; keep its `lat` / `lng` / `radius` names. No new endpoint, no unified search endpoint. | It already has the right shape and tests. Normal search (`/api/products/?q=`, `/api/shops/?q=`) is a different question (text match vs distance) and stays untouched. |
| D2 | Public max radius **50 km**. UI options **1, 2, 5, 10, 20, 50 km**, default **5 km**. | Covers greater Dhaka at the top end; keeps queries and marker counts small. `validate_radius`'s own default (1000) is unchanged for other callers. |
| D3 | At most **50 results**, nearest first. `count` is the total inside the radius, so the UI can say "showing 50 of 73". | Enough for a map and list on a phone; bounds response size. |
| D4 | Shops at `POINT(0 0)` **never** appear in nearby results. | They have no real location. |
| D5 | Customer location lives **only in memory** (a React context in the root layout). Not in `localStorage`, not in the URL, not stored on the server. It is sent only as the query of the nearby request. | Privacy. Survives client navigation (home → nearby → shop → back), gone on reload. |
| D6 | The browser's permission prompt appears **only after a click**. If permission is already `granted`, the nearby page may locate automatically (no prompt appears). | "Must not be forced to grant location to browse". |
| D7 | Shop forms: the button **only fills the two inputs**. Manual entry still works; the backend still validates. **No reverse geocoding**, no map picker. | Smallest correct change. Address stays a human-typed field. |
| D8 | Map: **Leaflet 1.9 + OpenStreetMap tiles**, tile URL and attribution overridable with `NEXT_PUBLIC_MAP_TILE_URL` / `NEXT_PUBLIC_MAP_TILE_ATTRIBUTION`. | Free, no API key, BSD-2 licence, ~40 KB gz. See §7. |
| D9 | The nearby UI is its own route **`/shops/nearby?radius=`** (next to `/shops`). Home gets an entry bar, not a map. | The home page is already hero + grid. A route gives the back button and a shareable radius. Coordinates never go in the URL (D5). |
| D10 | **No database change.** | §11. |

## 5. Proposed API Contract

```text
GET /api/shops/nearby/?lat=23.7788&lng=90.4172&radius=5
Auth: none (AllowAny). Read-only.
```

| Param | Required | Rule | Error |
|---|---|---|---|
| `lat` | yes | number, finite, −90…90 | 400 |
| `lng` | yes | number, finite, −180…180 | 400 |
| `radius` | yes | km, finite, `> 0` and `<= 50` | 400 |

```jsonc
// 200
{
  "count": 3,          // public, located shops inside the radius (all of them)
  "radius_km": 5.0,    // the validated radius
  "limit": 50,         // results holds at most this many
  "results": [         // nearest first; ties by id
    {
      "id": 9, "name": "Urban Thread", "slug": "urban-thread",
      "description": "…", "logo": "…", "cover_image": null,
      "phone": "…", "address": "…",
      "latitude": 23.7936, "longitude": 90.4043,
      "status": "ACTIVE",
      "average_rating": 4.5, "review_count": 2,   // same numbers as /api/shops/
      "created_at": "…",
      "distance_km": 1.234,                       // great-circle, 3 dp
      "distance_meters": 1234.1
    }
  ]
}

// 400
{ "error": "Latitude must be between -90.0 and 90.0 degrees. Received: 95.0." }
```

Visibility: only `APPROVED` / `ACTIVE` shops with real coordinates. Fields are exactly
the public shop card fields (no owner, reasons, reviewer or timestamps beyond
`created_at`). Distance is `ST_Distance_Sphere` (spherical earth, well under 0.5%
error at city scale).

## 6. Proposed UI/UX

**Shop forms (admin create, seller edit).** Under the latitude/longitude inputs: a
secondary button **"Use My Current Location"** (`my_location` icon). While locating:
spinner + "Locating…", button disabled. On success: fill both inputs (rounded to 7 dp),
then a status line such as "Location found (±12 m). Check it before saving." When accuracy is worse than
500 m: a warning that this looks like a network estimate. Both forms get a
"Check on map" link to openstreetmap.org for the typed/filled point. Errors appear
inline, in words (§8). The admin shop detail page shows the saved coordinates.

**Home page.** A slim **"Shops near you"** bar at the top of the main column (above
the hero, visible on every breakpoint because the header search is desktop-only):

- no location: short privacy note + **Use My Current Location**
- locating: spinner, "Finding your location…"
- location on: "Location on · ±15 m" + **Update** / **Clear**
- error: the message + **Try again**
- always: radius select + **Find Nearby Shops** (asks for location first if needed,
  then goes to `/shops/nearby?radius=N`).

The `/shops` directory gets a **Find Nearby Shops** link next to its sort control.

**Nearby page `/shops/nearby`.** Sticky Header + Navbar, breadcrumb
Home › Shops › Nearby, title, then a control row: location status (with Refresh and
Clear) and radius chips (1–50 km, `aria-pressed`). Body:

| State | Shows |
|---|---|
| No location yet | Card: why location is needed, that it stays on the device, **Use My Current Location**, link to all shops |
| Locating | Spinner + "Finding your location…" |
| Denied / unsupported / insecure | Explanation + how to re-enable + **Browse all shops** (normal browsing unaffected) |
| Unavailable / timeout | Message + **Try again** |
| Loading results | Skeleton cards (and map, once added) |
| API error | Message + **Retry** |
| Empty | "No shops within 5 km." + **Search within 10 km** (next radius up) + all shops link |
| Results | "3 shops within 5 km", list of cards (logo, name, stars, address, distance badge, **View Shop**) + map |

Layout: **desktop** `lg:grid-cols-12` — list `col-span-5` (own scroll area), map
`col-span-7`, sticky under the header. **Tablet** map on top (`h-96`), list below in two
columns. **Mobile** map on top (`h-72`), single-column list; touch targets ≥ 40 px;
radius chips scroll sideways.

**Interactions** (map and list share one `selectedShopId`):

| Action | Result |
|---|---|
| Click marker | Select shop, open its popup, scroll its card into view |
| Click card | Select shop, pan map to it and open the popup |
| Popup / card **View Shop** | Client-side `router.push('/shop/<slug>')` (keeps location in memory) |
| Change radius | Update `?radius=`, refetch, refit map to the radius circle |
| Move / zoom map | Nothing is refetched |
| Refresh location | Re-locate, refetch, recentre |

## 7. Mapping Solution

| Option | Package | Key? | Licence / terms | Verdict |
|---|---|---|---|---|
| **Leaflet + OSM tiles** | `leaflet` (+ `@types/leaflet` dev) | No | Leaflet BSD-2. OSM data ODbL: attribution **required**. OSM's tile servers have a fair-use policy: fine for development and light use; heavy production traffic should switch to a commercial or self-hosted tile provider (a config change, D8). | **Recommended** |
| react-leaflet | `react-leaflet` + `leaflet` | No | Hippocratic licence | Not needed; a ~150-line imperative wrapper avoids a second dependency and its React-version coupling |
| MapLibre GL | `maplibre-gl` (~250 KB gz) | Usually (vector tile host) | BSD-3 | Heavier; vector tiles need a provider |
| Google Maps JS | loader | **Yes**, billing account | Google ToS | Cost, key management, ToS limits |

Implementation notes: import `leaflet` **dynamically inside `useEffect`** (it touches
`window` at import, which breaks prerendering); import `leaflet/dist/leaflet.css` in
the map component. Markers are `L.divIcon`s styled in `globals.css` with the theme
variables (no default image icons, which break under bundlers). Popups are built with
DOM nodes and `textContent` (shop names are user data — no `innerHTML`). Wrap the map
in `isolate` so Leaflet's internal z-indexes (up to 1000) can't cover the sticky
header. No backend map service is needed. Tiles are loaded straight from the tile host.

## 8. Location Permission Strategy

One helper, `src/lib/geolocation.ts`, wraps `navigator.geolocation.getCurrentPosition`
in a promise and maps every failure to one of five kinds with a fixed message:

| Kind | When | Message / action |
|---|---|---|
| `unsupported` | no `navigator.geolocation` | "Your browser can't share its location." → browse all shops / type coordinates |
| `insecure` | `window.isSecureContext === false` | "Location only works over HTTPS." (see below) |
| `denied` | `PERMISSION_DENIED` | "Location access is blocked. Allow it in your browser's site settings, then try again." |
| `unavailable` | `POSITION_UNAVAILABLE` | "Your location couldn't be determined." → Try again |
| `timeout` | `TIMEOUT` (15 s) | "Finding your location took too long." → Try again |

Options: `enableHighAccuracy: true`, `timeout: 15000`; `maximumAge` 60 s for customers,
`0` for shop forms (always fresh). Accuracy (metres) is kept and shown. A failed
refresh keeps the previous position, if there was one.

**HTTPS.** Browsers only expose geolocation in a secure context. `http://localhost:3000`
and `http://127.0.0.1:3000` count as secure, so desktop dev works. **A phone opening
`http://192.168.x.x:3000` does not.** Test on a phone through an HTTPS tunnel or
`next dev --experimental-https`. Production must be HTTPS.

## 9. Security Considerations

- Backend stays authoritative: coordinates and radius are validated server-side on
  every request (`validate_coordinates`, `validate_radius`, max 50 km); the frontend
  radius list is only a convenience.
- Injection: the origin is built from **validated floats** and passed as a bound
  parameter to `RawSQL` (`%s`), never string-formatted into SQL from raw input.
- Visibility: only `APPROVED`/`ACTIVE` shops (the same filter as `/api/shops/`), only
  public card fields; unlocated shops excluded.
- No catch-all `except Exception` → no internal error text in public responses.
- No new permission (public, read-only, like `/api/shops/`). No throttle exists on any
  public endpoint today; adding DRF throttling is listed in "Not in this plan".
- Privacy: customer location is never persisted (D5). Note that it does appear in the
  request query string, so it can reach web-server access logs (see §15).
- Shop forms: the button can't bypass anything — it only types into inputs the user
  could type into anyway.

## 10. Performance Considerations

- `ST_Distance_Sphere(...) <= r` **cannot use the spatial index**; MySQL evaluates it
  for every public shop. With 10 shops (and realistically thousands) that is trivial.
  If shops grow past ~10k, add an `MBRContains(<bounding box>, location)` prefilter,
  which does use the R-tree index. That is not needed now.
- Result cap 50 (D3) bounds serialisation and markers; 50 `divIcon`s are cheap. No
  clustering needed at this size.
- Requests happen only on: location obtained/refreshed, or radius changed. Map
  pan/zoom never fetches. A radius click is a discrete action, so no debounce; stale
  responses are dropped with an `AbortController`.
- Customer location is cached for the session in context, with `maximumAge` 60 s, so
  navigating back and forth doesn't re-prompt or re-locate.
- Leaflet is loaded only on `/shops/nearby` (dynamic import).
- Two queries per request (results + count).

## 11. Database/Migration Impact

**None.** `location` is already `POINT NOT NULL SRID 4326` with a spatial index, and
the `POINT(0 0)` sentinel already marks "no coordinates". No new fields, indexes or
migrations; no `seed_rbac` change.

## 12. Exact Files Likely to Change

Backend: `backend/shops/services.py`, `backend/shops/views.py`,
`backend/shops/serializers.py`, `backend/shops/tests.py`,
`backend/shop/admin_serializers.py` (`AdminShopSerializer` coordinates),
`backend/shop/test_admin_governance.py`.

Frontend (existing): `frontend/src/app/admin/shops/new/page.tsx`,
`frontend/src/app/admin/shops/[id]/page.tsx`, `frontend/src/app/seller/shops/page.tsx`,
`frontend/src/lib/admin-api.ts`, `frontend/src/lib/api.ts`, `frontend/src/lib/types.ts`,
`frontend/src/app/layout.tsx`, `frontend/src/app/page.tsx`,
`frontend/src/app/shops/page.tsx`, `frontend/src/app/globals.css`,
`frontend/package.json`, `frontend/package-lock.json`.

Frontend (new): `frontend/src/lib/geolocation.ts`,
`frontend/src/components/location/UseCurrentLocationButton.tsx`,
`frontend/src/context/LocationContext.tsx`, `frontend/src/app/shops/nearby/page.tsx`,
`frontend/src/components/shops/NearbyShopCard.tsx`,
`frontend/src/components/shops/NearbyShopsMap.tsx`,
`frontend/src/components/home/NearbyShopsBar.tsx`.

## 13. Testing Plan

**Backend** (`shops/tests.py`, extending `ShopSpatialAndNearbyTests`):

- valid request → 200 with `count`, `radius_km`, `limit`, rating fields, distance fields
- invalid lat (95, −90.5, `abc`, `nan`) / lng (181, `inf`) → 400 with a plain message
  (not `"['…']"`)
- radius `0`, `-1`, `abc`, `50.01`, `1000` → 400; exactly `50` → 200
- unlocated (`POINT(0 0)`) shop excluded, even for a search at 0.001°, 0.001°
- boundary: a shop ~1.52 km away is in at `radius=1.6`, out at `radius=1.5`
- ordering: nearest first; equal distance → lower id first
- result cap: with the limit patched to 2, `results` has 2 and `count` has all
- ratings: hidden reviews don't count; numbers match `/api/shops/`
- existing: visibility (draft/pending/suspended/rejected excluded), missing params,
  inside/outside radius — kept
- admin: `POST /api/admin/shops/` with coordinates stores them and returns them;
  out-of-range latitude → 400 and nothing created (`shop/test_admin_governance.py`)

**Frontend** (no test runner in the repo; verified by `npm run typecheck`,
`npm run build`, and small scratch harnesses run with Node, as in the review plan):

- geolocation helper: granted, denied, unavailable, timeout, unsupported, insecure
  map to the right kind/message; rounding; accuracy/distance formatting
- nearby page states: idle, locating, denied, error+retry, loading skeleton, empty
  (+ widen radius), results; radius change refetches; stale response ignored
- map: renders markers for each result + customer marker; marker click selects the
  card; card click opens the popup; View Shop navigates to `/shop/<slug>`
- responsive: 375 px, 768 px, 1280 px widths; keyboard: tab to radius chips, cards,
  markers, zoom buttons; focus rings visible; status messages in `aria-live`

**Security:** the invalid-input tests above; `radius=1000` rejected; non-public and
unlocated shops never returned; response fields limited to the public set; injection
strings in `lat` (`1 OR 1=1`, `1);DROP`) → 400.

## 14. Implementation Breakdown

| Task | Title | Side | Status |
|---|---|---|---|
| 1 | Harden and extend the nearby-shops API | backend | ✅ Done |
| 2 | Geolocation helper + "Use My Current Location" on both shop forms | frontend | ✅ Done |
| 3 | Admin API returns shop coordinates; admin shop page shows them | full-stack | ✅ Done |
| 4 | Customer location context + nearby API client and types | frontend | ✅ Done |
| 5 | `/shops/nearby` page with radius control and result list | frontend | ✅ Done |
| 6 | Interactive map (Leaflet + OSM) on the nearby page | frontend | ⬜ |
| 7 | Home page "Shops near you" bar + `/shops` entry link | frontend | ⬜ |
| 8 | Regression run and documentation close-out | docs | ⬜ |

**The requested feature is complete after Task 7.** Task 8 records the final checks.

### Task 1 — Harden and extend the nearby-shops API

**Goal.** The existing endpoint returns only what a nearby UI needs, safely.

- [x] `shops/services.py`: add `NEARBY_MAX_RADIUS_KM = 50.0` and
      `NEARBY_RESULT_LIMIT = 50`. `get_nearby_shops` defaults to the 50 km cap, starts
      from `get_public_shops_queryset()` (ratings), excludes `POINT(0 0)`, orders by
      `distance_meters, id`.
- [x] `shops/serializers.py`: `NearbyShopSerializer` extends `PublicShopSerializer`
      and adds `distance_km`, `distance_meters`.
- [x] `shops/views.py`: catch Django's `ValidationError` and return its plain message;
      remove the `except Exception` catch-all; respond with `count` (total),
      `radius_km`, `limit`, `results` (first 50).
- [x] Tests from §13 (backend part, except admin).

**Done when.** `manage.py test shops` passes, including the new tests.

**Status:** ✅ Done 2026-09-24

- Unlocated shops are dropped with a `WHERE NOT (ST_Latitude(location) = 0 AND
  ST_Longitude(location) = 0)` filter (a boolean `RawSQL` passed straight to
  `.filter()`, so it adds no column and no `GROUP BY` entry).
- The view validates the radius itself (it needs the value for `radius_km`), then the
  service validates coordinates and radius again. Radius errors are reported first.
- `count` is a second query (`COUNT(*)` over the grouped queryset); `results` is the
  same queryset sliced to `LIMIT 50`. Two queries per request.
- New tests (7): response shape + ratings ignore hidden reviews + no private fields +
  numbers match `/api/shops/<slug>/`; unlocated shop excluded next to 0,0 while a
  located one at 0.002,0.002 is returned; 50 km accepted, 50.01 and 1000 rejected;
  ~1.52 km boundary in at 1.6, out at 1.5; equal distances ordered by id; result cap
  (limit patched to 2) keeps `count` = 3; nine bad inputs (range, `inf`, `abc`,
  `1 OR 1=1`, `1);DROP TABLE …`, bad radius) → 400 with a plain string message.
- Smoke-checked against the dev database (read-only): from 23.78, 90.40 at 5 km the 4
  located seed shops come back nearest first (1.574 → 4.594 km); the 6 unlocated shops
  never appear.
- Verified: `shops` **36/36 OK** (29 existing + 7 new) in 136 s on a throwaway
  `test_minishop_loc1` database (created, then destroyed). `manage.py check` clean,
  `makemigrations --check` reports no changes.
- Left alone: `SellerShopLocationUpdateView` has the same DRF-vs-Django
  `ValidationError` mix-up, but its serializer validates first, so it can't trigger.

---

### Task 2 — Geolocation helper + "Use My Current Location" on both shop forms

**Goal.** An admin creating a shop, or a seller editing theirs, fills the coordinates
with one click.

- [x] `src/lib/geolocation.ts`: `getCurrentPosition()`, `GeolocationError` with the
      five kinds and messages from §8, `roundCoordinate()`, `formatAccuracy()`,
      `formatDistance()`, `openStreetMapUrl()`.
- [x] `src/components/location/UseCurrentLocationButton.tsx`: button + `aria-live`
      status line (locating, found ±accuracy, low-accuracy warning, each error).
- [x] Admin create page and seller edit modal: button under the lat/lng inputs; fills
      both; "Check on map" link when both inputs hold a valid point.

**Done when.** Both forms fill coordinates from the browser; denying permission shows
the message and manual entry still works; `npm run build` passes.

**Status:** ✅ Done 2026-09-24

- The helper also exports `geolocationBlocker()` (checked before asking, so an
  insecure page says "HTTPS" instead of a generic failure), `isValidCoordinatePair()`,
  `toGeolocationError()` and `LOW_ACCURACY_METERS = 500`. `GeolocationError.retryable`
  is true for `unavailable` / `timeout`; for the other kinds the button adds "You can
  still type the coordinates."
- Shop forms always ask for a fresh reading (`maximumAge: 0`); coordinates are
  rounded to 7 dp, the precision the backend stores.
- `CoordinateMapLink` (same file) opens openstreetmap.org with a marker on the typed or
  filled point, and renders nothing until both inputs hold a valid pair.
- The status line is one always-present `role="status"` region, so screen readers
  announce each result. Colours are `text-success` / `text-danger` / `text-accent`
  tokens.
- Wider than planned: the seller modal's latitude/longitude `<label>`s were not tied to
  their inputs; they now have `htmlFor` / `id`.
- Verified: a Node harness (compiled with `tsc`, `navigator` mocked) checks all five
  error kinds, `retryable`, the options passed to the browser, rounding, the accuracy
  and distance formats, the coordinate ranges and the map URL — all pass.
  `npm run typecheck`, `npm run build` and `eslint` on the two new files pass. Not
  checked in a real browser.

---

### Task 3 — Admin API returns shop coordinates; admin shop page shows them

**Goal.** After creating a shop, the admin can see the coordinates that were saved.

- [x] `AdminShopSerializer`: add read-only `latitude`, `longitude`.
- [x] `AdminShop` type (`admin-api.ts`) + its doc comment; admin shop detail
      "Contact & Location" shows the coordinates and a map link, or "Not set".
- [x] Tests: create with coordinates stores and returns them; latitude 95 → 400, no
      shop created.

**Done when.** Tests pass; `npm run build` passes.

**Status:** ✅ Done 2026-09-24

- The fields come from the `Shop.latitude` / `longitude` properties, so a shop at
  `POINT(0 0)` reports `null` and the detail page says "Not set — the shop won't
  appear in nearby-shop search."
- The admin list endpoint returns the same two fields (it shares the serializer); the
  list page doesn't show them.
- New tests (3) in `AdminShopCreationTests`: create with coordinates → stored, in the
  create response and in `GET /api/admin/shops/<id>/`; create without → both `null`;
  latitude 95, longitude −180.5, or latitude alone → 400 and no shop created.
- Verified: `shop.test_admin_governance` **86/86 OK** (83 existing + 3 new) in 360 s
  on a throwaway `test_minishop_loc3` database. `npm run typecheck` and
  `npm run build` pass. Not checked in a browser (the admin console needs a staff
  login this session doesn't have).
- Pre-existing, left alone: `eslint` flags `react-hooks/set-state-in-effect` at
  `admin/shops/[id]/page.tsx:88`, on code this task didn't touch.

---

### Task 4 — Customer location context + nearby API client and types

**Goal.** One in-memory place for the customer's location, and a typed API call.

- [x] `src/context/LocationContext.tsx`: `status` (`idle` / `locating` / `ready` /
      `error`), `position`, `error`, `permission` (from the Permissions API, if
      available), `requestLocation()`, `clearLocation()`. Memory only (D5).
- [x] Provider in `src/app/layout.tsx`.
- [x] `types.ts`: `NearbyShop`, `NearbyShopsResponse`. `api.ts`: `getNearbyShops()` —
      throws with the backend message (no demo fallback: the UI needs a real error
      state), accepts an `AbortSignal`. `NEARBY_RADIUS_OPTIONS` / default radius.

**Done when.** Typecheck and build pass. (Nothing visible yet.)

**Status:** ✅ Done 2026-09-24

- The hook is `useCustomerLocation()`. `LocationProvider` sits innermost in the root
  layout (inside `CartProvider`), around the page, `CartDrawer` and `ThemeSwitcher`.
- `requestLocation()` shares one browser request between concurrent callers, resolves
  with the position or `null`, and keeps the previous position when a refresh fails.
  A `denied` result also sets `permission` to `"denied"`; `permission` follows the
  Permissions API's `change` event where the browser has one.
- Customer readings accept a cached position up to 60 s old (`maximumAge`).
- `getNearbyShops()` sends coordinates at 6 dp, uses the backend's `error` text only
  for a 400, turns network failures into "Check your connection", and passes an abort
  through untouched. `parseNearbyRadius()` maps a `?radius=` value to one of the
  options, else the 5 km default.
- Verified: `npm run typecheck`, `npm run build` and `eslint` on the new context pass.
  Exercised in a real browser through the Task 5 page.

---

### Task 5 — `/shops/nearby` page with radius control and result list

**Goal.** A customer sees nearby shops as a list, with every state from §6.

- [x] `src/app/shops/nearby/page.tsx` (+ `Suspense` for `useSearchParams`): location
      prompt, radius chips synced to `?radius=`, auto-locate only when permission is
      already granted, fetch with abort, all states from §6.
- [x] `src/components/shops/NearbyShopCard.tsx`: logo, name, stars, address, distance
      badge, View Shop; selected state.

**Done when.** The page works end to end against the dev API without a map; build
passes.

**Status:** ✅ Done 2026-09-24

- Two more components than planned, both reused by Task 7:
  `components/location/CustomerLocationControl.tsx` (status line + Use My Current
  Location / Try again / Update location / Clear, one `role="status"` region) and
  `components/shops/NearbyRadiusPicker.tsx` (radius chips with `aria-pressed`, inside a
  `fieldset`). On this page the control hides its start buttons, because the page body
  already offers them.
- Each card has a rank number (1 = nearest), matching the map markers coming in Task 6.
  The list is an `<ol>`. "View Shop" is a `next/link`, so the in-memory location
  survives the trip; a click anywhere else on the card selects it.
- Fetching keys each response by (lat, lng, radius, retry count). Loading is derived
  from "no response for the current key", so no `setState` runs inside the effect
  body, and a late response for an old radius can't overwrite a newer one (the old
  request is also aborted).
- Auto-locate happens at most once per visit, and never after a position has been seen
  on the page. The first browser run showed that without the second rule, **Clear**
  after returning with Back located the customer again straight away.
- Empty state offers the next radius up; errors offer Retry; every no-location state
  links to `/shops`.
- Verified in headless Chrome (DevTools protocol, geolocation permission and position
  set per run) against the dev API: denied → prompt, then the blocked message with
  Try again and Browse all shops; granted at 23.78, 90.40 → located on arrival, "4 shops
  within 5 km", nearest first (Urban Thread 1.6 km … Bloom & Home 4.6 km); 1 km → empty
  state, "Search within 2 km" → `?radius=2`, 1 shop; card click selects; View Shop
  → `/shop/urban-thread` in the same document; Back → results again with the location
  kept; Clear → prompt and no re-locate; 390 px wide → no horizontal overflow, chips
  scroll. No console errors. `npm run typecheck`, `npm run build` (`/shops/nearby`
  prerenders as static) and `eslint` on the new files pass.

---

### Task 6 — Interactive map (Leaflet + OSM) on the nearby page

**Goal.** The results are also shown on a map that stays in sync with the list.

- [ ] `npm install leaflet` and `npm install -D @types/leaflet`.
- [ ] `src/components/shops/NearbyShopsMap.tsx`: dynamic import; OSM tiles
      (env-overridable); customer marker + accuracy circle; radius circle; shop
      markers; DOM-built popups; selection sync both ways; fit to radius; resize
      handling; `isolate` wrapper; `aria-label`.
- [ ] Marker and popup styles in `globals.css` with theme variables.
- [ ] Page layout from §6 (desktop split, tablet/mobile stacked).

**Done when.** Markers, popups and selection work; map never covers the header;
build passes.

**Status:** ⬜ Not started

---

### Task 7 — Home page "Shops near you" bar + `/shops` entry link

**Goal.** Customers can find the feature from the home page and the shop directory.

- [ ] `src/components/home/NearbyShopsBar.tsx` with the states from §6; placed at the
      top of the home page main column.
- [ ] `/shops`: "Find Nearby Shops" link next to the sort control.
- [ ] Product search and the hero carousel behave exactly as before.

**Done when.** Build passes; the bar works at phone width.

**Status:** ⬜ Not started

---

### Task 8 — Regression run and documentation close-out

- [ ] Full `shop` + `shops` backend suites; `npm run typecheck`, `npm run build`.
- [ ] Record results here; add the nearby contract to `docs/MINISHOP_REVIEW_STATE.md`
      §6.

**Status:** ⬜ Not started

## 15. Risks / Open Questions

1. **OSM tile policy in production.** Fine for development and small traffic; decide
   on a tile provider (or self-hosting) before real launch. Switching is an env change
   (D8).
2. **Coordinates in access logs.** GET query strings are usually logged. If that
   matters, a later change can move the request to POST or round the coordinates to
   ~100 m on the client. Not done now.
3. **Radius cap 50 km / limit 50** are judgement calls (D2, D3).
4. **Phone testing needs HTTPS** (§8).
5. **6 of 10 dev shops have no coordinates**, so they will never appear nearby until a
   seller/admin sets them — which the Task 2 button makes easy.
6. Desktop browsers without GPS often return a Wi-Fi/IP estimate hundreds of metres
   off; the accuracy display and low-accuracy warning exist for that.

## 16. Recommended Implementation Order

**1 → 2 → 3 → 4 → 5 → 6 → 7 → 8.** Backend contract first (1), so the frontend builds
on the final shape. The shop-form button (2–3) is independent of the customer flow
and gives shops real coordinates to find. Then state (4), a working list page with
no map (5, the accessible fallback), the map on top of it (6), and only then the entry
points that send customers there (7).

---

## How to verify every task

```bash
# backend/ — always --noinput; never --parallel on this machine (no mysqldump)
venv/Scripts/python.exe manage.py check
venv/Scripts/python.exe manage.py makemigrations --check --dry-run
venv/Scripts/python.exe manage.py test shops --settings=config.settings.test --noinput

# frontend/
npm run typecheck
npm run build
```

UI rules (AGENTS.md / GEMINI.md): token colours only; `৳` for money; sticky
Header + Navbar untouched; everything works at phone width.

## Not in this plan

- Map picker / draggable marker on the shop forms
- Reverse geocoding (fill the address from coordinates) or address search
- Remembering the customer's location between visits (would need explicit opt-in)
- Distance shown on product cards or the shop page
- Marker clustering, bounding-box index prefilter (only if shops reach ~10k)
- DRF throttling on public endpoints
- Dark-mode map tiles

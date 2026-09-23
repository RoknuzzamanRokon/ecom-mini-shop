# MiniShop — Location & Nearby Shop Discovery

## Architecture Audit & Implementation Planning Task

You are working on the existing MiniShop project.

This is a **PLANNING / ARCHITECTURE AUDIT task only**.

**DO NOT implement the feature yet.**

Your job is to inspect the current MiniShop backend, frontend, models, APIs, spatial/location logic, permissions, UI architecture, and existing Shop/customer flows, then produce a detailed implementation plan for a future feature.

---

# 1. First Read the Existing Project Context

Before doing anything:

1. Read the MiniShop Master Prompt.
2. Read the latest:
   `docs/MINISHOP_REVIEW_STATE.md`
3. Inspect current Git status/history.
4. Inspect the existing Shop model and location-related implementation.
5. Inspect existing spatial/nearby Shop APIs and services.
6. Inspect Shop creation/editing flows in the Management Console.
7. Inspect the public storefront/home page.
8. Inspect customer authentication/location-related frontend architecture.
9. Inspect existing API helpers and frontend state/context patterns.
10. Inspect existing map/location dependencies, if any.

Do not assume that a feature does not exist simply because it is not obvious from the UI.

The current source code and tests are authoritative.

---

# 2. Feature We Want to Plan

We want to introduce a future **Location & Nearby Shop Discovery system**.

There are TWO related but separate user experiences.

---

## A. Shop Creation — Automatic Current Location

Currently, when an authorized admin/management user creates a Shop, the Shop location requires longitude/latitude to be entered manually.

We want a better UI.

During Shop creation/editing, provide a button such as:

**"Use My Current Location"**

When clicked:

1. Browser requests the user's location permission.
2. Browser Geolocation API obtains the current coordinates.
3. Latitude and longitude are populated into the Shop location fields.
4. The user can review the coordinates.
5. The existing backend validation remains authoritative.
6. Existing manual coordinate entry should continue to work.

The feature must NOT trust frontend coordinates blindly.

The plan must determine:

* where this belongs in the current Shop form
* how latitude/longitude are currently represented
* whether the backend needs changes
* whether reverse geocoding is needed or should remain out of scope
* how browser permission denial should be handled
* how unavailable/unsupported geolocation should be handled
* whether accuracy information should be displayed
* whether a map preview should be useful during Shop creation
* whether the existing Shop spatial implementation can be reused directly

Do NOT implement yet.

---

# 3. B. Customer Current Location on Home Page

We also want a customer-facing location control on the public homepage.

The homepage should have a location area/button such as:

**"Use My Current Location"**

When the customer clicks it:

1. Browser requests location permission.
2. Current latitude/longitude is obtained.
3. The location becomes available to the storefront's nearby-shop functionality.
4. The customer can still use normal search independently.
5. The customer should not be forced to grant location permission just to browse/search.

The plan must determine the best existing frontend architecture for storing this temporary location.

Consider whether this should use:

* local component state
* React context
* existing AuthContext
* a dedicated location context/state
* URL/query parameters
* another existing project pattern

Do NOT introduce a new global state library unless clearly justified.

---

# 4. C. Nearby Shop Discovery

The existing product/shop search functionality should remain unchanged.

We want to add a separate nearby-shop discovery experience beside/near the existing search UI.

Conceptually:

```text
[ Search products / shops ............... ] [Search]

                    [ Find Nearby Shops ]
```

When the customer clicks:

**Find Nearby Shops**

the UI should allow the customer to specify a radius, for example:

```text
1 km
2 km
5 km
10 km
20 km
```

The exact radius options should be proposed after inspecting the existing system.

The user should be able to choose a radius and search using their current location.

---

# 5. Nearby Shop Results

After the customer requests nearby shops, the experience should be visually polished.

We want something similar to:

```text
--------------------------------------------------
| Nearby Shops                                   |
|                                                 |
| Radius: [ 5 km ▼ ]                              |
|                                                 |
|  [ MAP                                           |
|                                                   |
|      📍 Customer                                  |
|          • Shop A                                 |
|     • Shop B        • Shop C                     |
|                                                   |
|  ]                                                |
|                                                 |
| Nearby Shops                                     |
|                                                 |
| Shop A       1.2 km                              |
| Shop B       2.4 km                              |
| Shop C       4.1 km                              |
--------------------------------------------------
```

This is only a conceptual example.

The agent must inspect the existing project and propose the appropriate UI.

The intended experience includes:

* interactive map
* customer/current location marker
* nearby Shop markers
* selected Shop details
* distance from customer
* nearby Shop result list
* radius selection
* loading state
* empty state
* location permission state
* error state
* mobile-friendly responsive UI

---

# 6. Map Requirements

Investigate what mapping solution is already available or appropriate for the project.

Before recommending a new dependency, inspect:

* package.json
* existing frontend dependencies
* existing map/location components
* existing backend spatial support
* existing Shop coordinate data

The plan should compare reasonable options if no map library currently exists.

For example, investigate whether the project should use an existing/open map solution or another appropriate mapping provider.

Do NOT install anything during this planning task.

The plan should identify:

* map library/provider
* required frontend dependency
* API/key requirements, if any
* licensing considerations
* whether tiles can be used directly
* whether a backend map service is required
* how markers should be rendered
* how map state interacts with the nearby-shop result list

---

# 7. Backend Nearby-Shop Architecture

Audit the current backend spatial implementation carefully.

Determine:

* current Shop latitude/longitude fields
* database field types
* MySQL spatial support
* existing spatial indexes/functions
* existing nearby Shop endpoint/service
* current distance calculation
* ordering by distance
* filtering by radius
* Shop status filtering
* whether inactive/rejected/suspended Shops are excluded
* pagination behavior
* authorization/public access behavior

If an existing nearby-Shop API already exists, prefer extending/reusing it rather than creating duplicate logic.

The plan must explicitly identify:

```text
Existing functionality
        ↓
Reusable service/API
        ↓
Required extension
        ↓
Frontend integration
```

---

# 8. Search + Nearby Search Relationship

The current normal search experience must remain intact.

We need to distinguish:

### Normal Search

Customer searches by:

* product
* shop
* category
* keyword

from:

### Nearby Search

Customer searches based on:

* current latitude
* current longitude
* selected radius

The plan should explain whether these should remain separate APIs/UI flows or whether a unified search endpoint makes architectural sense.

Do NOT merge them automatically.

Avoid unnecessary refactoring.

---

# 9. Shop Result Interaction

Plan what happens when a customer:

1. clicks a Shop marker
2. clicks a Shop card/list item
3. clicks a map popup
4. clicks "View Shop"
5. changes radius
6. moves/zooms the map
7. changes location

Prefer existing Shop routes such as:

```text
/shop/[slug]
```

if appropriate.

Do not create duplicate Shop detail architecture.

---

# 10. Location Permission / Privacy UX

The feature must be privacy-conscious.

The plan must cover:

### Permission granted

Use the coordinates.

### Permission denied

Do not break normal browsing/search.

Provide a clear message explaining that location access is needed for nearby-shop discovery.

### Browser does not support geolocation

Show a graceful fallback.

### Location unavailable / timeout

Show retry behavior.

### User changes location

Allow refreshing/re-requesting current location.

### HTTPS

Investigate browser geolocation requirements for development and production.

Do not store precise location permanently unless there is an explicit business requirement.

Prefer temporary client-side location state unless the existing architecture requires otherwise.

---

# 11. Security Requirements

The frontend must never be trusted for authorization.

Nearby Shop discovery is expected to be public/read-only unless current architecture indicates otherwise.

The backend must:

* validate latitude
* validate longitude
* validate radius
* enforce sensible radius limits
* return only publicly visible/eligible Shops
* avoid exposing private/admin-only Shop information
* avoid SQL/spatial injection risks
* use existing service/query patterns

Do not introduce a new permission model for public nearby-shop discovery.

---

# 12. UI/UX Planning

The future UI should be polished and production-oriented.

Plan the following states:

### Home Page

* location button
* location active state
* permission state
* loading state
* error state

### Nearby Shop Search

* radius selector
* search button
* map
* Shop markers
* customer marker
* result list
* distance display
* empty state
* loading skeleton
* error/retry

### Shop Creation

* latitude/longitude fields
* Use My Current Location button
* success feedback
* permission denied state
* geolocation failure state
* optional map preview if justified

### Responsive Design

Explicitly plan for:

* desktop
* tablet
* mobile

Especially consider mobile because browser geolocation is likely to be used primarily on mobile devices.

---

# 13. Accessibility

The plan should include:

* keyboard-accessible location button
* clear button labels
* visible focus states
* accessible map controls
* non-map fallback result list
* screen-reader-friendly status/error messages

The map must not be the only way to understand nearby Shops.

---

# 14. Performance

Analyze:

* spatial query performance
* maximum radius
* result limits
* pagination
* map marker count
* API request frequency
* repeated location requests
* radius changes
* debouncing where appropriate

Avoid querying the backend repeatedly while the user is simply moving the map unless there is a clear requirement.

Recommend a sensible initial result limit.

---

# 15. Testing Plan

Do NOT implement tests yet.

Instead, provide a detailed future testing plan covering:

### Backend

* valid coordinates
* invalid latitude
* invalid longitude
* invalid radius
* maximum radius
* no nearby Shops
* multiple nearby Shops
* distance ordering
* Shop visibility/status filtering
* boundary distance cases
* spatial query correctness

### Frontend

* location permission granted
* location permission denied
* browser geolocation unavailable
* loading
* API error
* empty result
* radius selection
* map rendering
* marker selection
* Shop navigation
* responsive behavior

### Security

* invalid coordinates
* excessive radius
* unauthorized/private Shops
* public API exposure
* query injection attempts

---

# 16. Database / Migration Audit

Determine whether this feature requires:

* model changes
* indexes
* migrations
* spatial indexes
* new fields

Do NOT create migrations during this planning task.

If existing location fields/indexes are sufficient, explicitly say so.

---

# 17. API Design Proposal

The plan should propose the exact API contract required.

For example, conceptually:

```text
GET /api/shops/nearby/
    ?latitude=...
    &longitude=...
    &radius_km=...
```

But do NOT assume this exact endpoint.

First inspect the existing API and determine whether an existing endpoint should be extended.

Provide:

* endpoint
* HTTP method
* query parameters
* validation
* response shape
* distance representation
* ordering
* pagination/result limit
* public visibility rules

---

# 18. Frontend Architecture Proposal

Identify the exact files/components that should likely change.

For example:

```text
Home page
Location component
Nearby Shop component
Map component
Shop creation form
API client
types
hooks/context
```

But these are examples only.

Use actual project files after inspection.

Do not invent paths.

---

# 19. Dependency Analysis

Determine whether we need:

* browser Geolocation API only
* map library
* tile provider
* geocoding service
* reverse geocoding
* additional backend package
* additional frontend package

Separate:

### Required

from:

### Optional future enhancement

Do not add unnecessary dependencies.

---

# 20. Scope Boundaries

This planning task must NOT implement:

* automatic Shop location
* customer location state
* nearby Shop API
* map UI
* new database migrations
* new frontend dependencies
* geocoding
* reverse geocoding
* map provider setup
* search redesign
* payment changes
* order changes
* seller architecture changes
* RBAC redesign
* authentication redesign
* unrelated UI refactoring

This is strictly a planning/audit task.

---

# 21. Required Final Report

At the end, provide a detailed but concise report with exactly these sections:

## 1. Current Architecture Findings

What already exists.

## 2. Existing Location/Spatial Functionality

What can be reused.

## 3. Gap Analysis

What is missing for the requested feature.

## 4. Recommended Architecture

Backend + frontend architecture.

## 5. Proposed API Contract

Exact endpoint/request/response design.

## 6. Proposed UI/UX

Home page, Shop creation, nearby search, map, results, responsive behavior.

## 7. Mapping Solution

Recommended option and alternatives, with dependency/API-key/licensing considerations.

## 8. Location Permission Strategy

Browser geolocation and failure states.

## 9. Security Considerations

Validation, public Shop filtering, radius limits, privacy.

## 10. Performance Considerations

Spatial query, result limits, map markers, request frequency.

## 11. Database/Migration Impact

Whether changes are required.

## 12. Exact Files Likely to Change

Only real project paths discovered during audit.

## 13. Testing Plan

Backend + frontend + security.

## 14. Implementation Breakdown

Break the future work into small, sequential implementation tasks.

For example, potentially:

```text
Task A — Location abstraction / current-location UI
Task B — Shop creation current-location button
Task C — Nearby Shop backend API
Task D — Nearby Shop frontend
Task E — Interactive map integration
Task F — Responsive/accessibility polish
Task G — Integration/regression testing
```

Do NOT assume these exact tasks are correct.

Choose the best breakdown based on the actual codebase.

## 15. Risks / Open Questions

List anything that must be decided before implementation.

## 16. Recommended Implementation Order

Give the safest dependency-aware order.

---

# 22. IMPORTANT

Do NOT write implementation code.

Do NOT modify application source files.

Do NOT install dependencies.

Do NOT create migrations.

Do NOT change Git history.

Do NOT fix unrelated issues.

This task exists only to produce a reliable implementation plan that can later be converted into separate focused coding tasks.

At the end, clearly state:

* no source files changed
* no migrations created
* no dependencies installed
* no tests modified
* Git working tree status
* recommended next implementation task

The goal is to give the project owner a **production-quality roadmap for Location + Nearby Shop Discovery** without prematurely implementing anything.

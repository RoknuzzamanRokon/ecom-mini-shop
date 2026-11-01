# Sales Team: edits with the seller's code, token payouts, product visibility

Decided 2026-11-01, before work starts on the Sales Team Android app
(`docs/FUTURE_PLAN.md`, "Sales Team field onboarding"). The user answered the
three questions left open there:

1. **Edits.** The Sales Team can correct the sellers, shops and products it
   opened, but only inside an edit session. A code goes to the seller's account.
   The onboarder enters it in the app or the browser, and can then edit for
   30 minutes. After that, editing is refused.
2. **Tokens.** An onboarder hands tokens to an admin with a request for real
   payment. When the admin accepts it, the tokens move to that admin.
3. **Products.** The Sales Team no longer sees every product. A member sees
   only the products they added, and only while they hold the permission for
   it. An admin can turn that permission off.

On review the user added two more decisions:

4. **Starting password.** An onboarded seller must replace the password the
   onboarder set, at first sign-in. Later changes go through Settings as
   today.
5. **Token value.** 1 token = ৳1.

Branch: `feature/sales-team-edits-payouts`. The API serves the Android app
later. The Console gets the same screens now, for the browser.

## 1. Edit sessions

**Flow**

1. The onboarder asks for a code for one of their sellers:
   `POST /api/onboarding/sellers/<pk>/edit-session/`.
   - A 6-digit code goes to the seller's account as a new seller event,
     `onboarding.edit_code`. It uses the ACCOUNT category, so in-app and email
     cannot be switched off.
   - The text names the onboarder and says to share the code only if the
     seller agrees to the changes.
   - The code works for **10 minutes**. A new request replaces the old code, at
     most one per minute.
2. The seller tells the onboarder the code. The onboarder enters it:
   `POST .../edit-session/verify/ {"code": "123456"}`.
   - The right code opens the session for **30 minutes** from that moment.
   - 5 wrong tries void the code, and a new one has to be requested.
3. While the session is open, the onboarder can edit:
   - `PATCH /api/onboarding/sellers/<pk>/`: business name, business email,
     business phone, tax ID and description. Not the seller type, and not the
     login account (username, password, phone, email), which stays with the
     seller.
   - `PATCH /api/onboarding/shops/<pk>/`: name, description, phones, address,
     latitude and longitude.
   - `PATCH /api/onboarding/products/<pk>/` (multipart for the image): name,
     category, description, price, old price, stock, badge, image, active.
     The same rules apply as when the seller edits: the listing lock, and a
     stock conflict check through `expected_stock`.
4. `GET .../edit-session/` reports the session state: none, waiting for the
   code (until when), or open (until when). `DELETE` closes it early.

**Rules**

- Without an open session, each edit answers 403 with
  `code: "edit_session_required"`. The time check is made on the server at each
  edit.
- An edit is allowed while the seller awaits approval or is live. It is refused
  once the seller is rejected or suspended. An edit to a live product does not
  send it back for review, the same as a seller's own edit.
- Only the seller's own onboarder can open a session. Each seller has at most
  one session at a time.
- The code is stored hashed on the session. The notification shows it in plain
  text, as an SMS would.
- Each edit writes an audit row: `ONBOARDING_SELLER_UPDATED`,
  `ONBOARDING_SHOP_UPDATED` or `PRODUCT_UPDATED`, with the session id. Opening
  the session writes `ONBOARDING_EDIT_SESSION_OPENED`.
- The Console Rules page, Onboarding group, gets two new rules:
  - "Edit code valid for": 10 minutes, range 2–30;
  - "Edit window": 30 minutes, range 5–120.

**Starting password.** The onboarder sets the seller's first password, so
until the seller replaces it the onboarder could sign in as the seller and read
the code. Section 4 closes that.

## 2. Token payouts

**What the onboarder does**

- `POST /api/onboarding/payouts/ {"tokens": 51, "note": "bKash 01…"}` asks for
  a payout.
  - The amount must be at least 1 and no more than the onboarder's balance.
  - Only one request can be pending at a time.
  - The tokens leave the onboarder's wallet at once and are held on the
    request (ledger row `PAYOUT_HELD`).
- `GET /api/onboarding/payouts/` lists their requests.
- `POST /api/onboarding/payouts/<pk>/cancel/` cancels a pending request, and
  the held tokens come back (`PAYOUT_RELEASED`).

**What the admin does**

- Admins act through a new permission, `onboarding.payouts.manage`, which
  Administrators get.
- `GET /api/onboarding/payouts/review/?status=` lists the requests.
- `POST .../review/<pk>/accept/ {"note": "Paid by bKash, TrxID …"}` accepts a
  request. The held tokens go into **the accepting admin's** token wallet
  (`PAYOUT_RECEIVED`).
- `POST .../review/<pk>/reject/ {"reason": "…"}` rejects a request. The tokens
  go back to the onboarder.
- Nobody can accept or reject their own request.

**Notifications and audit**

- `tokens.payout_requested`: in the STAFF_QUEUE category, sent to holders of
  `onboarding.payouts.manage`, in-app and by email.
- `tokens.payout_decided`: tells the onboarder in-app whether the request was
  accepted or rejected, with the note.
- Audit rows `TOKEN_PAYOUT_REQUESTED`, `_CANCELLED`, `_ACCEPTED` and
  `_REJECTED`.

- **Value.** A new Rules page setting, "Token value", is ৳ per token: default 1,
  whole taka, range 1–1,000. A request keeps the rate and the ৳ amount from
  when it was made, so a later change does not alter it. The money itself is
  paid outside the system, and the admin's note records how.

## 3. Product visibility for the Sales Team

**Permissions**

- SALES_TEAM loses `products.view`, which opened the Console's product list
  and detail for every seller.
- It also loses `inventory.view` and `inventory.adjust`. A Sales Team account
  marked `is_staff` (in the Django admin) gets every product's stock, and the
  right to adjust it, from the inventory views. Without `is_staff`, the codes
  give nothing to an account that is not a seller.
- It also loses `products.create` and `products.update`, which no view checks.
- The removals happen in migration `rbac/0008` and in `seed_rbac`.
- New code `onboarding.products.view`: "See the products they added for the
  sellers they onboarded". SALES_TEAM gets it.
- Follow-up (2026-11-02, `rbac/0009`): ADMINISTRATOR gets `sellers.onboard`
  and `onboarding.products.view` too. Managing an account below the wildcard
  (its roles, deactivating it) needs every permission it holds, so until then
  only a Super Administrator could manage a Sales Team member. Administrators
  can now also onboard sellers and see My Sellers.

**Which products**

- New field `Product.onboarded_by`: who added the product through onboarding.
  It is empty for products the seller added. Existing onboarding products are
  filled in from their `PRODUCT_CREATED` audit rows.
- `GET /api/onboarding/products/` and `GET /api/onboarding/products/<pk>/` list
  and show only the caller's products. The detail includes description, stock,
  listing end date and status.
- In the seller detail and the seller list, `products` and `product_count` now
  cover only the caller's products.
- Without the code:
  - shops come back without their products, and the two product endpoints
    answer 403;
  - editing a product is refused;
  - adding a product still works, since it is part of `sellers.onboard`.
- The review queue for approvers is unchanged.

**Turning it off for one person**

- The whole team: Console → Roles → Sales Team, as today.
- One person: a new RBAC table, `UserPermissionBlock`.
  - A block takes one code away from one account even though its roles grant it.
  - `get_user_permissions()` and `users_with_permission()` leave blocked codes
    out.
  - It does not apply to superusers or Super Administrators.
  - The Console user detail page gets a "Turn off for this person" button on
    each permission, and a list of turned-off codes with "Turn back on".
  - It needs `users.admin.manage` and the right to manage that account. Each
    change writes `USER_PERMISSION_BLOCKED` or `USER_PERMISSION_UNBLOCKED`.
  - The block works for any code, not only this one.

## 4. Starting password

- New `rbac.StartingPassword` row (account, who set the password, when it was
  replaced). Onboarding writes one for each new seller account. A migration
  writes one for every seller account onboarded so far.
- The login (`/api/auth/token/`) puts a `starting_password` claim on the
  tokens while the row is unreplaced. The JWT authentication refuses such a
  token with 403 `password_change_required`, except on `/api/auth/me/`,
  `/api/auth/change-password/` and `/api/auth/logout/`. Changing the password
  marks the row replaced and, as today, revokes the old tokens; the new pair
  has no claim. No extra query per request.
- `/api/auth/me/` returns `must_change_password`.
- Storefront: while it is true, the whole site shows one screen: "Choose your
  own password. {onboarder} set your first one when opening your account."
  It has the change form and Sign out. Afterwards the site opens as usual, and
  Settings → Password works as before.
- Accounts made by staff in the Console are left as they are.

## 5. Console (the browser)

- **`/admin/my-sellers/<id>`**: one seller.
  - It shows the business details, shops and, with the code, the products the
    onboarder added.
  - The Edit panel asks for a code, then shows a code field. Once the code is
    accepted, it shows a countdown ("Editing open until 14:35") and Edit
    buttons on the seller, each shop and each product, plus Close.
  - When the time runs out, the buttons go away.
  - The product form can also replace the photo (JPEG, PNG or WebP, up to
    5 MB); the request is then multipart. Added 2026-11-02.
- **My Sellers**:
  - a link from each row to the seller;
  - "Request payment" on the tokens card, which asks for the amount and a note;
  - the pending request with Cancel, and earlier requests below it.
- **`/admin/token-payouts`** ("Token Payouts", for
  `onboarding.payouts.manage`): the pending queue and history, with Accept
  (note) and Reject (reason).
- **Users → one user**: turn a permission off or back on.
- The Products menu disappears for the Sales Team, because it no longer holds
  `products.view`.

## Not in this work

- The Android app itself (`mobile/`, React Native + Expo). It comes next, on
  this API.
- Sending the code by SMS: it waits for the SMS provider, as phone sign-in does.
- A starting password for accounts made by staff in the Console.
- Telling the seller afterwards what was changed during a session (the audit
  rows already record it).
- A minimum payout, or rates below ৳1 per token.
- Changing the seller type or the login account from the Sales Team side.

## Tasks

- A. Product visibility:
  - the `rbac/0007` codes and removals, and `seed_rbac`;
  - `Product.onboarded_by` with its backfill;
  - the onboarding product endpoints, and filtering the nested products;
  - `UserPermissionBlock` with its API and audit;
  - tests.
- B. Edit sessions:
  - the `EditSession` model and the two settings, plus the registry group;
  - the `onboarding.edit_code` event, template and handler;
  - the request, verify, state and close endpoints;
  - the three PATCH endpoints, with a `for_onboarding` path through the seller,
    shop and product update services;
  - tests.
- C. Token payouts:
  - the `TokenPayoutRequest` model and the new ledger types;
  - the `onboarding.payouts.manage` code;
  - the onboarder and admin endpoints, the two events and the audit rows;
  - tests.
- C2. Starting password: the model and backfill, the token claim and
  authentication, `must_change_password`, and the storefront screen.
- D. Console:
  - the seller detail page with the edit panel and forms;
  - payouts on My Sellers, and the Token Payouts page and nav item;
  - permission blocks on the user page;
  - tests, lint, build.
- E. Wrap-up:
  - the full backend suite;
  - migrate the dev DB and the 16 test clones;
  - a live check in headless Chrome, then clean up its data;
  - docs: FUTURE_PLAN, REVIEW_STATE, NOTIFICATION_SYSTEM and BUSINESS_RULES.

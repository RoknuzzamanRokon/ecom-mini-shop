# MiniShop — Customer Support Ticket System Plan

**Created:** 2026-09-24 · **Baseline commit:** `2463421` · **Status:** Not started (0 of 12 tasks done)

This is the plan and task list for the support ticket feature. Work through the tasks
in §13 **one at a time, in order**. Each task is one commit. When a task is done, tick
its boxes, set its **Status** line, and update the table in §13.

To continue, just ask: **"do Task N"**.

---

## 1. What we are building

1. A logged-in customer opens a **support ticket**. They pick a category, write a
   subject and describe the whole problem. They can link one of **their own orders** and
   attach up to 5 screenshots or PDFs.
2. The customer and the support team talk in a **conversation thread** on the ticket.
3. Support staff see every ticket in the Management Console (`/admin/support`). They
   filter tickets, assign them, set priority, reply, and write **internal notes** the
   customer never sees. They move each ticket through its statuses until it is resolved
   and closed.
4. Both sides can see when something needs their attention: an **unread** marker for the
   customer, and a **needs reply** marker for staff. There is no email.

Choices the project owner made on 2026-09-24:

| Question | Answer |
|---|---|
| Who takes part in a ticket? | **Customer + support staff only.** Sellers never see tickets. |
| Attachments? | **Images + PDF, private.** 5 files per message, 5 MB each. |
| Who can open a ticket? | **Logged-in customers only.** |
| How do people learn about a reply? | **In-app only** (unread markers and counts). No email. |

---

## 2. What already exists (reuse, do not rebuild)

There is **no support code at all** today: no model, API, permission code or UI.
`docs/MINISHOP_REVIEW_STATE.md:661` and `task/Master_Prompt.md:784-786` list it as a
backend gap. The `SUPPORT_TEAM` role is seeded with the description "Handles customer
inquiries, order issues, complaints, and returns" (`seed_rbac.py:124-128`), but it has no
ticket permissions.

These parts get reused:

| Part | Where | Used for |
|---|---|---|
| Permission codes, roles, idempotent seeding: `PERMISSIONS_DATA`, `ROLE_PERMISSIONS_MAPPING`, `FORBIDDEN_ROLE_PERMISSIONS` | `backend/rbac/management/commands/seed_rbac.py` | New `support.*` codes |
| `has_user_permission(user, code)` | `backend/rbac/services.py:67` | Permission classes, assignee check |
| One named `BasePermission` class per code, with a superuser / SUPER_ADMINISTRATOR bypass | e.g. `CanModerateReviews`, `backend/shop/admin_permissions.py:265-275` | Support permission classes |
| `AuditService.log(action, target, actor, metadata, ip_address, reason, previous_state, new_state)` and `get_client_ip(request)` | `backend/audit/services.py:17`, `backend/audit/utils.py:4` | Staff action audit |
| State machine: `VALID_TRANSITIONS` / `can_transition_to()` on the model; the service locks the row, changes it and writes the audit entry | `Order`, `backend/shop/models.py:330-418`; `OrderService.transition_order_status`, `backend/shop/services.py:618` | Ticket status |
| Server-made reference `ORD<YYYYMMDD><6-HEX>` | `OrderService.generate_order_number`, `backend/shop/services.py:372` | `TKT<YYYYMMDD><6-HEX>` |
| Lock → change → audit service, and tests built on `seed_rbac` + `assign_user_role` | `ReviewModerationService`, `backend/customers/services.py:547-605`; `backend/shop/test_review_moderation.py` | Service and test style |
| `AdminPagination` (20 per page, max 100) | `backend/shop/admin_views.py:99` | Staff list |
| App with its own staff routes under its own prefix | `backend/shops/urls.py` (`/api/shops/staff/…`) | `/api/support/staff/…` |
| `customerRequest`: 401 refresh-and-retry, and multipart works (it never sets `Content-Type`) | `frontend/src/lib/api.ts:38-64`; e.g. `uploadAvatar` `:1345` | Customer API calls |
| `adminRequest` (**JSON only**), `AdminApiError`, `PaginatedResponse` | `frontend/src/lib/admin-api.ts:58-187` | Staff API calls (needs a multipart sibling) |
| `ADMIN_PERMISSIONS`, `ADMIN_NAV_ITEMS`, `hasAnyPermission()` | `frontend/src/lib/admin-navigation.ts`, `frontend/src/lib/admin-auth.ts:82-125` | Console nav and gates |
| Console list/detail pages with a `<module>Governance.tsx` beside them | `frontend/src/app/admin/reviews/*`, `frontend/src/app/admin/orders/[id]/page.tsx` | Structure to copy |
| `AdminDataTable`, `AdminFilterBar`, `AdminSearchField`, `AdminSelectField`, `AdminStatusBadge`, `AdminConfirmModal`, `AdminStatCard` | `frontend/src/components/admin/shared/` | Console UI |
| Profile shell `NAV_ITEMS`; the "My Reviews" page | `frontend/src/app/profile/layout.tsx:14-21`, `frontend/src/app/profile/reviews/page.tsx` | Customer pages |
| Image picker with a 5 MB check and object-URL preview | `frontend/src/app/seller/shops/page.tsx:18`, `:115-149` | Attachment picker |
| Customer `Pagination` | `frontend/src/components/home/Pagination` | Customer ticket list |

**Gaps found while reading the code:**

- **No upload validation anywhere.** Existing uploads only use DRF `ImageField` plus
  `upload_to`: no size limit, no type allowlist, no shared helper.
- **No email, notifications, polling, websockets or throttling** in the project.
- **`/media` is public** whenever `DEBUG` is on (`backend/config/urls.py:37-38`), and the
  Next.js rewrite forwards it. Private files must live **outside** `MEDIA_ROOT`.
- **SUPPORT_TEAM lacks `customers.admin.view`**, so it gets 403 on
  `/api/admin/customers/`. It also lacks `users.admin.view`, so it can't use
  `getAdminUsers()` to list staff. The ticket must therefore carry the customer's
  contact details itself, and there must be a separate "assignees" endpoint.
- **`adminRequest` can't send files.** The comment at `admin-api.ts:800-802` says
  multipart would need "a second request layer".
- **The profile nav highlights exact paths only** (`profile/layout.tsx:92`,
  `pathname === item.href`), so `/profile/support/<n>` would leave "Support" unlit.
  `/profile/orders/<n>` has the same problem today.
- **The profile layout sends guests to `/login` with no `?next=`**
  (`profile/layout.tsx:31`). `/login` already supports `?next=` (`app/login/page.tsx:48`).
- **The footer "Contact Support" link goes to `#`** (`components/layout/Footer.tsx:23`).
- **`AdminStatusBadge` has no tone** for `OPEN`, `IN_PROGRESS`, `WAITING_ON_CUSTOMER`,
  `RESOLVED`, `CLOSED`, or the priorities.

---

## 3. Decisions (the rules the system follows)

These are the defaults this plan is built on. Change them here **before** starting the
task that depends on them.

| # | Rule | Why |
|---|---|---|
| D1 | **Customer + staff only.** Sellers never see tickets; staff contact a seller themselves when needed. | Owner's choice. Keeps visibility rules simple. |
| D2 | Opening a ticket needs login + **`support.create`** (seeded to CUSTOMER). Staff can't open a ticket on a customer's behalf in v1. | Owner's choice (logged-in only). Same model as orders and reviews. |
| D3 | New ticket: **category** (required), **subject** 5–150 chars, **description** 10–5000 chars (it becomes the first message), optional **`order_number`**, optional attachments. The order must belong to the customer, otherwise a generic 400 "Order not found". | Enough to understand the problem. The generic message leaks nothing about other people's orders. |
| D4 | Categories: `ORDER` (Order & delivery), `PAYMENT` (Payment & refund), `PRODUCT` (Wrong or damaged item), `RETURN` (Return & exchange), `ACCOUNT` (Account & login), `SHOP` (Shop or seller complaint), `OTHER`. | Covers what SUPPORT_TEAM is described as handling. |
| D5 | Five statuses with fixed transitions (below). **`CLOSED` is terminal.** A customer with a new problem opens a new ticket. | Same idea as `Order.VALID_TRANSITIONS`. |
| D6 | **Priority** `LOW` / `NORMAL` (default) / `HIGH` / `URGENT` is set **by staff only**. The customer never sees it. | Otherwise every customer would pick "urgent". |
| D7 | **One optional assignee**, who must hold `support.staff.reply`. Any agent can reply, whoever is assigned; nothing is locked. | A small team shouldn't be blocked by assignment. |
| D8 | **Internal notes** (`is_internal=True`) and their attachments **never** leave the staff API. The customer queryset filters them out, and tests prove it. | Staff need to talk privately about a case. |
| D9 | **Attachments:** JPG / PNG / WebP / PDF, at most 5 per message, 5 MB each. The type is checked from the **file content** (Pillow `verify()` for images, a `%PDF-` header for PDFs), never from the client's `Content-Type`. Files are stored in **private storage** at `PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"` (gitignored), under `support/<yyyy>/<mm>/<uuid>.<ext>`. The original file name is kept for display only. | Screenshots can contain payment details and addresses. They must not be reachable through public `/media`. |
| D10 | Files are served **only** through authenticated download endpoints (`X-Content-Type-Options: nosniff`, inline). The frontend fetches them with the bearer token as a blob and shows them through `URL.createObjectURL`. | The JWT lives in `localStorage`, so a plain `<img src>` can't carry it. |
| D11 | **Unread markers.** Customer: `has_unread` is true when a staff public reply is newer than `customer_last_read_at`; opening the ticket marks it read. Staff: **needs reply** is true when the last public message is from the customer and the ticket isn't `RESOLVED`/`CLOSED`. | Owner's choice (in-app only). "Needs reply" is what a support queue actually sorts by. |
| D12 | **No real-time.** Ticket detail pages refetch when the window regains focus, every 60 s while the tab is visible, and after every action. | Websockets would be new infrastructure; this is cheap and feels live enough. |
| D13 | **Spam limits without throttling:** at most **5 unresolved tickets** per customer (`OPEN` / `IN_PROGRESS` / `WAITING_ON_CUSTOMER`), messages of at most 5000 chars, the attachment caps from D9. | The project has no DRF throttling today. |
| D14 | Customers see a staff author as **"<first name> · MiniShop Support"** (or just "MiniShop Support"). Staff email, username, priority and assignee are never sent to customers. | Staff privacy. |
| D15 | New Django app **`support`**, mounted at **`/api/support/`**, with staff routes under **`/api/support/staff/`**. The URL key everywhere (API and pages) is **`ticket_number`**. Tests live in `backend/support/tests/`. | Same layout as the `shops` app. Customers quote the ticket number on the phone. |
| D16 | In Django admin, `status` and `assigned_to` are **read-only**, and tickets can't be added or deleted there. Every change goes through the service and the audit log. | Lesson from Known Issue #22 (editable `status` bypassed the lifecycle and audit). |
| D17 | *(optional Task 11)* A `RESOLVED` ticket with no customer reply for **7 days** is closed by a management command. | Without it, staff close resolved tickets by hand. |

### Status flow

```text
OPEN ──► IN_PROGRESS ──► WAITING_ON_CUSTOMER ──► RESOLVED ──► CLOSED
```

| From | Staff may move it to |
|---|---|
| `OPEN` | `IN_PROGRESS`, `WAITING_ON_CUSTOMER`, `RESOLVED`, `CLOSED` |
| `IN_PROGRESS` | `WAITING_ON_CUSTOMER`, `RESOLVED`, `CLOSED` |
| `WAITING_ON_CUSTOMER` | `IN_PROGRESS`, `RESOLVED`, `CLOSED` |
| `RESOLVED` | `IN_PROGRESS`, `CLOSED` |
| `CLOSED` | nothing (terminal) |

Automatic changes:

- A new ticket starts at `OPEN`.
- A **staff public reply** on an `OPEN` ticket moves it to `IN_PROGRESS`, unless the reply
  sets a status itself. It also sets `first_response_at` the first time.
- A **customer reply** on `WAITING_ON_CUSTOMER` or `RESOLVED` moves it back to `OPEN`. On
  `OPEN` or `IN_PROGRESS` the status doesn't change.
- **Customer "Close ticket"** works from any status except `CLOSED` and moves it to
  `CLOSED`.
- An **internal note** never changes the status.

Every status change adds a **public system message** to the thread ("Status changed to
Resolved"). Assignment, priority and category changes add an **internal** system
message. Staff actions also write an `AuditLog` row.

---

## 4. Permissions (new codes in `seed_rbac.py`)

| Code | Allows | Seeded to |
|---|---|---|
| `support.view` | List and read your own tickets and their attachments | CUSTOMER |
| `support.create` | Open a ticket, reply, close your own ticket | CUSTOMER |
| `support.staff.view` | Staff list, detail, summary, assignees, attachments | SUPPORT_TEAM, ADMINISTRATOR, OPERATION_MANAGER |
| `support.staff.reply` | Public replies and internal notes; being assignable | SUPPORT_TEAM, ADMINISTRATOR, OPERATION_MANAGER |
| `support.staff.manage` | Change status, priority, category and assignee | SUPPORT_TEAM, ADMINISTRATOR |

- SUPER_ADMINISTRATOR gets them all through the wildcard.
- All three `support.staff.*` codes go into `FORBIDDEN_ROLE_PERMISSIONS[CUSTOMER]`, so a
  bad grant heals itself on the next `seed_rbac` run.
- Staff codes end in `.staff.view`, which `isManagementUser`
  (`frontend/src/lib/admin-auth.ts:52`) already accepts for console entry.
- New codes only reach an existing database when `seed_rbac` is run (§10).

---

## 5. Data model (`backend/support/models.py`)

One migration, `support/migrations/0001_initial.py`, with three tables.

**`SupportTicket`**

| Field | Type / rule |
|---|---|
| `ticket_number` | `CharField(20)`, unique; `TKT<YYYYMMDD><6-HEX>` |
| `customer` | FK User, `SET_NULL`, null, `related_name="support_tickets"` |
| `order` | FK `shop.Order`, `SET_NULL`, null, blank, `related_name="support_tickets"` |
| `category` | choices (D4) |
| `subject` | `CharField(150)` |
| `status` | choices, default `OPEN`, indexed |
| `priority` | choices, default `NORMAL` |
| `assigned_to` | FK User, `SET_NULL`, null, `related_name="assigned_support_tickets"` |
| `created_at`, `updated_at` | auto |
| `last_activity_at` | indexed; list sort key (any public message or status change) |
| `last_customer_message_at`, `last_staff_reply_at`, `first_response_at`, `resolved_at`, `closed_at`, `customer_last_read_at` | nullable datetimes |

It also has `VALID_TRANSITIONS`, `can_transition_to()`, and an `is_closed` property.
Indexes: (`customer`, `-last_activity_at`), (`status`, `-last_activity_at`),
(`assigned_to`, `status`).

**`TicketMessage`**: `ticket` (FK, `CASCADE`, `related_name="messages"`), `author` (FK
User, `SET_NULL`), `author_type` (`CUSTOMER` / `STAFF` / `SYSTEM`), `body` (text),
`is_internal` (bool, default `False`), `created_at`. Ordered by (`created_at`, `id`).

**`TicketAttachment`**: `message` (FK, `CASCADE`, `related_name="attachments"`), `file`
(`FileField` on the private storage), `original_name`, `content_type` (the detected
type), `size`, `created_at`. The storage is passed as a **callable** that reads
`settings.PRIVATE_MEDIA_ROOT`, so tests can point it at a temp directory.

---

## 6. API contract

- Errors are `400 {"detail": "<message>"}` or DRF field errors.
- Another customer's ticket or attachment → **404** (never 403, so nothing leaks).
- Missing permission code → 403.

### Customer (`/api/support/`)

| Method | Path | Code | Notes |
|---|---|---|---|
| GET | `tickets/?status=open\|closed&page=` | `support.view` | Own tickets only, 10 per page, newest activity first. `open` = everything except `CLOSED` |
| POST | `tickets/` | `support.create` | multipart: `category`, `subject`, `description`, `order_number?`, `attachments` (repeated) → 201 + ticket detail |
| GET | `tickets/<ticket_number>/` | `support.view` | Public messages only. Marks the ticket read |
| POST | `tickets/<ticket_number>/messages/` | `support.create` | multipart: `body`, `attachments` → 201 + message and new ticket status. 400 when `CLOSED` |
| POST | `tickets/<ticket_number>/close/` | `support.create` | → ticket detail |
| GET | `tickets/unread-count/` | `support.view` | `{"unread": 2}` |
| GET | `attachments/<id>/` | `support.view` | Streams the file if the caller owns the ticket and the message isn't internal; otherwise 404 |

```jsonc
// GET /api/support/tickets/TKT20260924A1B2C3/
{
  "ticket_number": "TKT20260924A1B2C3",
  "subject": "Parcel arrived damaged",
  "category": "PRODUCT", "category_label": "Wrong or damaged item",
  "status": "WAITING_ON_CUSTOMER", "status_label": "Waiting on you",
  "order_number": "ORD20260920F00D12",           // null when not linked
  "created_at": "…", "last_activity_at": "…", "resolved_at": null, "closed_at": null,
  "has_unread": false, "can_reply": true, "can_close": true,
  "messages": [
    {
      "id": 41, "author_type": "CUSTOMER", "author_name": "You",
      "body": "The box was crushed…", "created_at": "…",
      "attachments": [
        { "id": 7, "name": "box.jpg", "content_type": "image/jpeg", "size": 482113,
          "url": "/api/support/attachments/7/" }
      ]
    },
    { "id": 42, "author_type": "SYSTEM", "author_name": "MiniShop Support",
      "body": "Status changed to In progress", "created_at": "…", "attachments": [] },
    { "id": 43, "author_type": "STAFF", "author_name": "Rina · MiniShop Support",
      "body": "Sorry about that! Could you send a photo of the label?", "created_at": "…",
      "attachments": [] }
  ]
}
```

The customer shape never contains `priority`, `assigned_to`, internal messages or staff
email addresses.

### Staff (`/api/support/staff/`)

| Method | Path | Code | Notes |
|---|---|---|---|
| GET | `tickets/` | `support.staff.view` | 20 per page. Filters: `status`, `priority`, `category`, `assigned=me\|unassigned\|<user_id>`, `needs_reply=true`, `search` (ticket no, subject, customer email, order no), `ordering` (`-last_activity_at` default, `created_at`, `-priority`) |
| GET | `tickets/<ticket_number>/` | `support.staff.view` | All messages, including internal ones and internal attachments. Also `customer {id, name, username, email, phone, customer_profile_id}`, `order {id, order_number, status, total_amount, created_at}`, `priority`, `assigned_to {id, name}`, `allowed_transitions`, `needs_reply`, every timestamp |
| POST | `tickets/<ticket_number>/messages/` | `support.staff.reply` | multipart: `body`, `is_internal`, `set_status?`, `attachments` |
| PATCH | `tickets/<ticket_number>/` | `support.staff.manage` | `{status?, priority?, category?, reason?}` |
| POST | `tickets/<ticket_number>/assign/` | `support.staff.manage` | `{"assignee_id": 12}` or `{"assignee_id": null}`. 400 if the user doesn't hold `support.staff.reply` |
| GET | `assignees/` | `support.staff.view` | `[{id, name, email}]`: active users holding `support.staff.reply` through a role or a direct grant |
| GET | `summary/` | `support.staff.view` | `{by_status: {OPEN: 4, …}, needs_reply: 3, unassigned: 2, assigned_to_me: 1}` |
| GET | `attachments/<id>/` | `support.staff.view` | Any attachment |

---

## 7. UI / UX

### Customer (inside the `/profile` shell; Header + Navbar stay sticky)

- **Profile nav:** a new **Support** item (`support_agent` icon, hint "Get help with a
  problem") with an unread count badge. The active check becomes a prefix match, so
  detail pages stay highlighted (this also fixes `/profile/orders/<n>`).
- **`/profile/support`: My Support Tickets.**
  - **Open / Closed** tabs and a **New ticket** button.
  - One card per ticket: ticket number, subject, category, status badge, last activity
    ("2 h ago"), and an unread dot.
  - Loading, error + Retry, and an empty state ("No tickets yet. Having a problem? Open a
    ticket.").
- **`/profile/support/new`: New ticket.**
  - **Category chips.**
  - **Subject**, and **description** with a character counter.
  - **Related order** select, filled with recent orders. `?order=<n>` preselects one;
    "Not about an order" is also an option.
  - **Attachment picker:** thumbnails for images, a file chip for PDFs, a remove button,
    inline errors for type, size and count.
  - Submit goes to the new ticket's page.
- **`/profile/support/[ticketNumber]`: the conversation.**
  - Header: ticket number, subject, status badge, category, a link to the linked order,
    and a **Close ticket** button (with a confirm step).
  - Thread: customer messages on the right, staff on the left, system lines small and
    centred. Attachments open through the secure loader.
  - Reply box with attachments. When the ticket is `CLOSED`, the box is replaced by "This
    ticket is closed" + **Open a new ticket**. When it is `RESOLVED`, a note says that
    replying reopens it.
- **Entry points:**
  - **"Get help with this order"** in the order detail header, next to Cancel Order
    (`profile/orders/[orderNumber]/page.tsx:177-186`). It goes to
    `/profile/support/new?order=<n>`.
  - **"Help & Support"** in the header account dropdown, after Favorites
    (`components/layout/Header.tsx`, around `:197`).
  - The footer **"Contact Support"** link goes to `/profile/support/new`.
  - The profile layout redirect becomes `/login?next=<current path>`, so a guest who
    clicks a support link comes back after logging in.

### Staff (`/admin/support`, nav section Operations, gated by `support.staff.view`)

- **List page:**
  - Four **`AdminStatCard`s**: Needs reply, Open, Unassigned, Assigned to me. Clicking one
    applies it as a filter.
  - **Status tabs:** Active (not closed), Open, In progress, Waiting on customer,
    Resolved, Closed, All.
  - **`AdminFilterBar`:** search, priority, category, assignee (Anyone / Me / Unassigned
    / each agent).
  - **`AdminDataTable`** columns: ticket number, subject + customer name, category,
    priority badge, status badge, assignee, last activity, needs-reply dot.
  - Filters live in the URL, and search is debounced (same pattern as
    `admin/reviews/page.tsx`).
- **Detail page** (`lg:grid-cols-12`):
  - **Thread** (`lg:col-span-8`): internal notes sit on a different token background with
    an "Internal note" label.
  - **Composer:** **Reply to customer / Internal note** tabs, attachments, and an optional
    "…and set status to" select.
  - **Side panel** (`lg:col-span-4`):
    - **Status** (the allowed transitions only, optional reason, `AdminConfirmModal`)
    - **Priority** and **Category**
    - **Assignee** select + **Assign to me**
    - **Customer** card: name, email, phone. It links to `/admin/customers/<id>` only
      when the viewer holds `customers.admin.view`.
    - **Order** card: order number, status, total in ৳, link to `/admin/orders/<id>`
    - **Timeline:** created, first response, resolved, closed
  - Controls the viewer can't use are hidden (reply needs `support.staff.reply`; status,
    priority, category and assignee need `support.staff.manage`).
- `AdminStatusBadge` gets tones for the five statuses and four priorities.
- Customer pages use theme tokens only (`bg-surface`, `text-ink`, `text-accent`, …). No
  palette colours.

---

## 8. Security

- Every customer query starts with `filter(customer=request.user)` and excludes internal
  messages. Another customer's ticket or attachment returns a safe **404**.
- A linked order is checked with `order.user == customer`. A wrong or foreign order number
  gets the same generic 400.
- Every staff endpoint has its own permission class. The frontend only hides and shows
  controls; the backend decides.
- CUSTOMER is denylisted from `support.staff.*` in `seed_rbac`.
- **Files:**
  - Private storage outside `MEDIA_ROOT`, random UUID names.
  - The type is detected from the content; SVG, HTML and anything else is rejected.
  - Size and count limits.
  - `X-Content-Type-Options: nosniff`.
  - A cleaned file name in `Content-Disposition`.
- Message text is shown as plain text (`whitespace-pre-wrap`), **never**
  `dangerouslySetInnerHTML`.
- Status, assignee and timestamps change **only** in `SupportTicketService`, inside
  `transaction.atomic()` with `select_for_update()` on the ticket. Two agents acting at
  once can't lose each other's change.
- **Audit actions:** `SUPPORT_TICKET_CREATED`, `SUPPORT_TICKET_STATUS_CHANGED`,
  `SUPPORT_TICKET_ASSIGNED`, `SUPPORT_TICKET_UPDATED` (priority / category). Each records
  the actor, reason, previous and new state, and IP. Plain messages aren't audited,
  because each message is already a permanent record.

## 9. Performance

- The staff list uses `select_related("customer__customer_profile", "assigned_to",
  "order")`, and "needs reply" comes from stored timestamps, so there are no per-row
  queries.
- The detail page uses `prefetch_related("messages__attachments", "messages__author")`.
- The §5 indexes cover the default sort and the status / assignee filters.
- 10 tickets per page for customers, 20 for staff.
- Polling is limited: 60 s, detail pages only, only while the tab is visible.

## 10. Database / migration impact

- New app `support` with **3 tables** (`support/0001_initial`) and **5 new permission
  codes**. No change to existing tables.
- The shared dev MySQL needs `manage.py migrate` and `manage.py seed_rbac` once Tasks 1–4
  are in. Until then the new endpoints fail (missing tables) or return 403 (missing
  codes). **Offer to run these; don't run them unasked.**
- `backend/.gitignore` gets `private_media/`.

## 11. Files likely to change

**Backend (new):** `backend/support/` with `__init__.py`, `apps.py`, `models.py`,
`services.py`, `validators.py`, `storage.py`, `permissions.py`, `serializers.py`,
`views.py`, `urls.py`, `admin.py`, `migrations/0001_initial.py` and `tests/`.

**Backend (existing):** `backend/config/settings/base.py` (`INSTALLED_APPS`,
`PRIVATE_MEDIA_ROOT`), `backend/config/urls.py`,
`backend/rbac/management/commands/seed_rbac.py`, `backend/.gitignore`.

**Frontend (new):**
- `frontend/src/lib/support.ts`
- `frontend/src/components/support/` with `TicketStatusBadge.tsx`,
  `AttachmentPicker.tsx`, `SecureAttachment.tsx`, `TicketThread.tsx`
- `frontend/src/app/profile/support/page.tsx`, `new/page.tsx`,
  `[ticketNumber]/page.tsx`
- `frontend/src/app/admin/support/page.tsx`, `[ticketNumber]/page.tsx`,
  `supportGovernance.tsx`

**Frontend (existing):**
- `frontend/src/lib/types.ts`, `api.ts`, `admin-api.ts`, `admin-navigation.ts`
- `frontend/src/components/admin/shared/AdminStatusBadge.tsx`
- `frontend/src/app/profile/layout.tsx`
- `frontend/src/app/profile/orders/[orderNumber]/page.tsx`
- `frontend/src/components/layout/Header.tsx`, `Footer.tsx`

## 12. Testing plan

**Backend** (`backend/support/tests/`, in the style of `shop/test_review_moderation.py`:
`setUpTestData` + `call_command("seed_rbac")` + `assign_user_role`):

- **Transitions:** every allowed and every blocked pair from §3; `CLOSED` goes nowhere.
- **Creating a ticket:** the first message, timestamps, and the `TKT…` number are set; the
  6th unresolved ticket is refused; someone else's order number → 400; an unknown order
  number → the same 400.
- **Replies:**
  - Customer: a reply reopens `WAITING_ON_CUSTOMER` and `RESOLVED`; a reply on `CLOSED`
    → 400.
  - Staff: the first public reply moves the ticket to `IN_PROGRESS` and sets
    `first_response_at`; `set_status` works; an internal note changes nothing the customer
    can see.
- **Audit:** a row is written for create, status change, assignment and priority /
  category change, with the right actor.
- **Attachments:**
  - Each allowed type is accepted.
  - Rejected: 5 MB + 1 byte, 6 files, a `.png` that is really text, an SVG, a PDF renamed
    `.jpg` (it is stored as PDF or rejected, never trusted by its name).
  - Files land under the private root (a temp dir in tests), not `MEDIA_ROOT`.
  - Downloads: the owner gets 200 with `nosniff`; another customer gets 404; an
    internal-note attachment through the customer endpoint gets 404.
- **Customer API:**
  - Two customers never see each other's tickets (list, detail, reply, close, download).
  - The detail has no internal notes and no priority or assignee.
  - Unread count and mark-read work; close works.
  - A user without `support.view` / `support.create` gets 403.
- **Staff API:**
  - Permissions: CUSTOMER → 403, SUPPORT_TEAM → full access, OPERATION_MANAGER can
    view and reply but not manage.
  - Every filter, `search` and `needs_reply` work.
  - Assign accepts only a `support.staff.reply` holder.
  - `summary` counts are right.
  - `assignees` lists role grants and direct grants.
- **Seeding:** `seed_rbac` grants the codes as in §4; a CUSTOMER that somehow holds
  `support.staff.view` loses it on the next run.

**Frontend** (no test runner in the repo): `npm run typecheck`, `npm run build`, `eslint`
on the new files, and headless-Chrome walkthroughs against the dev API, as in earlier
plans:

- **Customer opens a ticket:** from an order page, with 2 images.
- **Staff handle it:** filter, assign to themselves, write an internal note (the customer
  never sees it), reply, set "Waiting on customer".
- **Customer answers:** sees the unread badge, replies, and the ticket reopens. Staff
  resolve it; the customer closes it.
- **Every page:** 390 px wide with no horizontal scroll, keyboard focus visible, no
  console errors.

---

## 13. Implementation breakdown

| Task | Title | Side | Status |
|---|---|---|---|
| 1 | `support` app: models, migration, private storage, read-only Django admin, permission codes | backend | ☐ Not started |
| 2 | `SupportTicketService` + attachment validator | backend | ☐ Not started |
| 3 | Customer API | backend | ☐ Not started |
| 4 | Staff API | backend | ☐ Not started |
| 5 | Frontend foundation: types, API clients, shared support components | frontend | ☐ Not started |
| 6 | Customer ticket list + new ticket form + profile nav item | frontend | ☐ Not started |
| 7 | Customer ticket conversation page | frontend | ☐ Not started |
| 8 | Customer entry points: order page, header menu, footer | frontend | ☐ Not started |
| 9 | Admin `/admin/support` ticket list | frontend | ☐ Not started |
| 10 | Admin ticket detail: thread, reply / internal note, status, priority, assignee | frontend | ☐ Not started |
| 11 | *(optional)* Auto-close resolved tickets after 7 days | backend | ☐ Not started |
| 12 | Regression run and documentation close-out | docs | ☐ Not started |

**The feature is usable end to end after Task 10.** Task 11 is an extra; Task 12 records
the final checks.

### Task 1 — `support` app: models, migration, private storage, Django admin, permission codes

**Goal.** The database and permissions for tickets exist. Nothing is reachable through
the API yet.

- [ ] Create the `support` app (`apps.py`, `__init__.py`) and add it to
      `INSTALLED_APPS` (`config/settings/base.py`).
- [ ] `PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"` in `base.py`;
      `private_media/` in `backend/.gitignore`.
- [ ] `support/storage.py`: a callable returning a `FileSystemStorage` on
      `settings.PRIVATE_MEDIA_ROOT` (no `base_url`), plus the
      `support/<yyyy>/<mm>/<uuid>.<ext>` `upload_to` function.
- [ ] `support/models.py`: `SupportTicket`, `TicketMessage`, `TicketAttachment` exactly
      as §5, with choices, `VALID_TRANSITIONS`, `can_transition_to()`, `is_closed`,
      indexes and `__str__`.
- [ ] Migration `support/migrations/0001_initial.py`.
- [ ] `support/admin.py`: ticket admin with list filters (status, priority, category),
      search (ticket number, subject, customer email), read-only message and attachment
      inlines; `status` / `assigned_to` read-only; no add, no delete (D16).
- [ ] `seed_rbac.py`: the five codes in `PERMISSIONS_DATA`, the role grants from §4, and
      the three `support.staff.*` codes in `FORBIDDEN_ROLE_PERMISSIONS[CUSTOMER]`.
- [ ] Tests: the transition table; `seed_rbac` grants per role; the CUSTOMER denylist
      heals a bad grant; the upload path is a UUID under `support/`.

**Done when.** `manage.py test support` passes; `manage.py check` is clean;
`makemigrations --check` reports no changes.

**Status:** ☐ Not started

---

### Task 2 — `SupportTicketService` + attachment validator

**Goal.** All ticket rules live in one tested service, with no views yet.

- [ ] `support/validators.py`: `validate_attachments(files)`. It enforces at most 5 files
      and 5 MB each; detects the type from the content (Pillow `open()` + `verify()` for
      JPG / PNG / WebP, `%PDF-` header for PDF); rejects everything else; returns the
      detected content type and a cleaned original name for each file.
- [ ] `support/services.py`: `SupportTicketError` (message → 400) and
      `SupportTicketService` with:
  - [ ] `generate_ticket_number()` (`TKT<YYYYMMDD><6-HEX>`, retry on collision, like
        `generate_order_number`)
  - [ ] `create_ticket(customer, category, subject, description, order_number=None,
        files=(), ip_address=None)`: order ownership, 5-unresolved cap (D13), ticket +
        first message + attachments, timestamps, `SUPPORT_TICKET_CREATED` audit
  - [ ] `add_customer_reply(ticket, customer, body, files=())`: locks the ticket;
        refuses `CLOSED`; reopens `WAITING_ON_CUSTOMER` / `RESOLVED` with a system
        message; updates `last_customer_message_at` and `last_activity_at`
  - [ ] `close_by_customer(ticket, customer)`
  - [ ] `add_staff_message(ticket, staff, body, files=(), is_internal=False,
        set_status=None, ip_address=None)`: the automatic `OPEN → IN_PROGRESS` move,
        `first_response_at`, `last_staff_reply_at` (public only); an internal note
        leaves all customer-visible fields alone
  - [ ] `change_status(ticket, staff, new_status, reason="", ip_address=None)`:
        transition check, `resolved_at` / `closed_at`, public system message, audit
  - [ ] `update_details(ticket, staff, priority=None, category=None, reason="",
        ip_address=None)`: internal system message, audit
  - [ ] `assign(ticket, staff, assignee, ip_address=None)`: the assignee must be active
        and hold `support.staff.reply`; `None` unassigns; internal system message, audit
  - [ ] `mark_read_by_customer(ticket)` and `get_assignable_staff()` (active users
        holding `support.staff.reply` through an active role or an active direct grant,
        plus SUPER_ADMINISTRATOR / superusers)
- [ ] Every write runs in `transaction.atomic()` with `select_for_update()` on the ticket.
- [ ] Tests: the service and attachment cases from §12.

**Done when.** `manage.py test support` passes, including the new tests.

**Status:** ☐ Not started

---

### Task 3 — Customer API

**Goal.** A customer can open, read, answer and close their own tickets over the API.

- [ ] `support/permissions.py`: `CanViewOwnSupportTickets` (`support.view`) and
      `CanCreateSupportTickets` (`support.create`), in the `CanModerateReviews` style.
- [ ] `support/serializers.py`: create (multipart, field validation from D3), customer
      ticket list, customer ticket detail with public messages only and staff names per
      D14, reply.
- [ ] `support/views.py` + `support/urls.py` (`app_name = "support"`): every customer
      route in §6. Querysets are scoped to `request.user`; `ticket_number` lookups give
      404 off-scope; the detail GET marks the ticket read; the attachment view returns a
      `FileResponse` with `nosniff`, the detected content type and a cleaned file name.
- [ ] Mount it with `path("api/support/", include("support.urls"))` in `config/urls.py`
      (**before** the `api/` customers include).
- [ ] Tests: the customer API cases from §12.

**Done when.** Tests pass; the §6 example shape comes back from the detail endpoint.

**Status:** ☐ Not started

---

### Task 4 — Staff API

**Goal.** Support staff can find, read, answer and manage every ticket over the API.

- [ ] Permission classes `CanViewSupportTickets`, `CanReplySupportTickets`,
      `CanManageSupportTickets`.
- [ ] Staff serializers: list row (with `needs_reply`, customer name and email,
      assignee, priority), detail (every message including internal ones; customer,
      order and `allowed_transitions` blocks from §6), staff message, update, assign.
- [ ] Views under `support/urls.py` at `staff/…`: list with every filter, `search` and
      `ordering` (`AdminPagination` style, 20 per page), detail, messages, PATCH, assign,
      assignees, summary, attachment download.
- [ ] Tests: the staff API cases from §12, including OPERATION_MANAGER reply-but-not-manage.

**Done when.** `manage.py test support` passes; `manage.py check` is clean.

**Status:** ☐ Not started

> After Task 4, the shared dev database needs `migrate` + `seed_rbac` before the
> frontend tasks can be checked against it (§10).

---

### Task 5 — Frontend foundation: types, API clients, shared support components

**Goal.** Everything the support pages need exists and compiles. Nothing is visible yet.

- [ ] `lib/types.ts`: `SupportCategory`, `SupportStatus`, `SupportTicketSummary`,
      `SupportTicket`, `SupportMessage`, `SupportAttachment`. Use names that don't clash
      with the old `Admin*` types there.
- [ ] `lib/support.ts`: category and status labels, limits (5 files, 5 MB, allowed
      types, subject/description lengths), `validateSupportFiles()`, `formatFileSize()`.
- [ ] `lib/api.ts` (customer, token last, like `createReview`): `getMySupportTickets`,
      `getMySupportTicket`, `createSupportTicket(FormData)`, `replyToSupportTicket`,
      `closeSupportTicket`, `getSupportUnreadCount`, `fetchSupportAttachment` (→ `Blob`).
- [ ] `lib/admin-api.ts`: a private `adminMultipartRequest` (same 401 refresh-and-retry
      as `adminRequest`, but no JSON `Content-Type`); staff types with "Mirrors …"
      comments; `getAdminSupportTickets`, `getAdminSupportTicket`,
      `postAdminSupportMessage(FormData)`, `updateAdminSupportTicket`,
      `assignAdminSupportTicket`, `getAdminSupportAssignees`, `getAdminSupportSummary`,
      `fetchAdminSupportAttachment`.
- [ ] `components/support/TicketStatusBadge.tsx` (token colours),
      `AttachmentPicker.tsx` (pick, validate, previews, remove; revokes object URLs),
      `SecureAttachment.tsx` (takes a `load(): Promise<Blob>` prop, renders a thumbnail
      or a file chip, opens in a new tab, revokes on unmount),
      `TicketThread.tsx` (customer / staff / system / internal bubbles, `variant`
      prop, plain text with `whitespace-pre-wrap`).

**Done when.** `npm run typecheck`, `npm run build` and `eslint` on the new files pass.

**Status:** ☐ Not started

---

### Task 6 — Customer ticket list + new ticket form + profile nav item

**Goal.** A customer can see their tickets and open a new one.

- [ ] `profile/layout.tsx`: a **Support** nav item with an unread badge
      (`getSupportUnreadCount`); prefix active match; redirect to
      `/login?next=<current path>`.
- [ ] `app/profile/support/page.tsx`: Open / Closed tabs, ticket cards, pagination,
      loading / error / empty states (the "My Reviews" page pattern).
- [ ] `app/profile/support/new/page.tsx` (with `Suspense` for `useSearchParams`):
      category chips, subject, description + counter, related-order select prefilled
      from `?order=`, `AttachmentPicker`, submit → `/profile/support/<ticket_number>`,
      backend errors shown inline.

**Done when.** A ticket with attachments can be created in the browser and appears in
the list; `npm run build` passes; it works at 390 px.

**Status:** ☐ Not started

---

### Task 7 — Customer ticket conversation page

**Goal.** A customer can read the conversation, reply and close the ticket.

- [ ] `app/profile/support/[ticketNumber]/page.tsx`: header (status, category, order
      link), `TicketThread`, reply box with `AttachmentPicker`, **Close ticket** with a
      confirm step, the closed and resolved notes from §7.
- [ ] Refetch on window focus, every 60 s while visible, and after every action (D12).
- [ ] Attachments through `SecureAttachment` + `fetchSupportAttachment`.
- [ ] Not found (someone else's ticket or a bad number) → a friendly "Ticket not found"
      with a link back to the list.

**Done when.** Reply, reopen-by-reply and close work in the browser; the unread badge
clears after opening; `npm run build` passes.

**Status:** ☐ Not started

---

### Task 8 — Customer entry points: order page, header menu, footer

**Goal.** Customers can find support where they need it.

- [ ] Order detail header: **Get help with this order** →
      `/profile/support/new?order=<order_number>`.
- [ ] Header account dropdown: **Help & Support** → `/profile/support` (after
      Favorites, same classes).
- [ ] Footer **Contact Support** → `/profile/support/new`.

**Done when.** All three links work, including for a logged-out visitor (login, then
back); `npm run build` passes.

**Status:** ☐ Not started

---

### Task 9 — Admin `/admin/support` ticket list

**Goal.** Staff see and filter the ticket queue.

- [ ] `lib/admin-navigation.ts`: `ADMIN_PERMISSIONS.supportView / supportReply /
      supportManage` and a **Support Tickets** nav item (`support_agent`, section
      Operations, `requiredPermissions: supportView`).
- [ ] `app/admin/support/supportGovernance.tsx`: `canViewSupport`, `canReplySupport`,
      `canManageSupport`, `SupportAccessNotice`.
- [ ] `AdminStatusBadge`: tones for the 5 statuses and 4 priorities.
- [ ] `app/admin/support/page.tsx`: stat cards from `summary`, status tabs,
      `AdminFilterBar` (search, priority, category, assignee), `AdminDataTable` with the
      §7 columns, URL-synced filters, debounced search, 20 per page.

**Done when.** A SUPPORT_TEAM user sees the queue and every filter works; a user without
`support.staff.view` sees the access notice; `npm run build` passes.

**Status:** ☐ Not started

---

### Task 10 — Admin ticket detail: thread, reply / internal note, status, priority, assignee

**Goal.** Staff handle a ticket from start to finish in the console.

- [ ] `app/admin/support/[ticketNumber]/page.tsx`: back link, identity header,
      `lg:grid-cols-12` layout from §7.
- [ ] Thread (`TicketThread variant="staff"`, internal notes marked), composer with
      **Reply to customer / Internal note** tabs, attachments via
      `adminMultipartRequest`, optional "…and set status to".
- [ ] Side panel: status (allowed transitions + reason, `AdminConfirmModal`), priority,
      category, assignee + **Assign to me**, customer card, order card (৳ total),
      timeline.
- [ ] Controls hidden per `support.staff.reply` / `support.staff.manage`; the same
      refetch rules as D12.

**Done when.** The full §12 walkthrough passes in the browser (the customer never sees
the internal note); `npm run build` passes.

**Status:** ☐ Not started

---

### Task 11 — *(optional)* Auto-close resolved tickets after 7 days

**Goal.** Resolved tickets don't stay open for ever.

- [ ] `support/management/commands/close_resolved_tickets.py` with `--days` (default 7)
      and `--dry-run`. It closes `RESOLVED` tickets whose `resolved_at` is older than the
      cut-off and that have no newer customer message, through the service (system
      message + audit, actor `None`).
- [ ] Tests: old → closed; recent → untouched; customer replied → untouched; dry run
      changes nothing.
- [ ] Document how to schedule it (Windows Task Scheduler / cron). There is no scheduler
      in the project.

**Done when.** Tests pass.

**Status:** ☐ Not started

---

### Task 12 — Regression run and documentation close-out

- [ ] Backend: `manage.py test support shop --settings=config.settings.test --noinput`
      (serial; `shop` alone takes about an hour).
- [ ] Frontend: `npm run typecheck`, `npm run build`.
- [ ] `docs/MINISHOP_REVIEW_STATE.md`: header line; §2 (new `support` app and
      `/api/support/` mount); §4 (new codes); §11 (console module); §12 (new routes);
      §17 (support ticketing no longer missing); §21 history entry with the commits.
- [ ] Record the results and the dev-database step (`migrate` + `seed_rbac`) here.

**Status:** ☐ Not started

---

## 14. Risks / open questions

1. **Files on one server's disk.** Fine for now. Moving to S3 or similar later is a
   storage-class swap, because every file goes through the one storage callable.
2. **"Needs reply" is per team, not per agent.** There is no per-agent read tracking.
3. **No email,** so a customer only sees a reply when they next visit the site.
4. **A staff member who also holds CUSTOMER** could handle their own ticket. It is not
   blocked in v1.
5. **Judgement calls:** the 5-ticket cap, 5 MB limit, 60 s refresh and 7-day auto-close
   (D9, D12, D13, D17).
6. **Dev database:** nothing works against the shared MySQL until `migrate` and
   `seed_rbac` have run (§10).

## 15. Not in this plan

- Sellers taking part in tickets
- A guest contact form
- Email or push notifications
- Websockets / real-time chat
- SLA timers and escalation rules
- Canned replies / templates
- A customer satisfaction rating
- A return / RMA workflow (refunds stay in `/admin/payments`)
- Merging or splitting tickets
- DRF throttling
- Staff opening tickets for customers

---

## How to verify every task

```bash
# backend/ — always --noinput; never --parallel on this machine (no mysqldump)
venv/Scripts/python.exe manage.py check
venv/Scripts/python.exe manage.py makemigrations --check --dry-run
venv/Scripts/python.exe manage.py test support --settings=config.settings.test --noinput

# frontend/
npm run typecheck
npm run build
```

The full `shop` suite (AGENTS.md rule 8) takes about an hour when run serially, so it
runs once, in Task 12. Every earlier task is committed as soon as its own checks pass.

UI rules (AGENTS.md / GEMINI.md): theme tokens only, no palette colours; `৳` for money;
sticky Header + Navbar untouched; everything works at phone width.

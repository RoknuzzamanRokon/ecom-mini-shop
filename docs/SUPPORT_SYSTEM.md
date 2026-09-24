# MiniShop — Customer Support Ticket System Plan

**Created:** 2026-09-24 · **Baseline commit:** `2463421` · **Status:** In progress (Tasks 1–9 of 12 done; backend complete, customer side complete)

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
- **Dev database: done 2026-09-24** (after Task 2, at the owner's request).
  - `migrate` applied `support.0001_initial`, the only pending migration.
  - `seed_rbac` reported "5 permissions created (total 71) … 15 new role-permission links
    created, 0 forbidden grant(s) revoked".
  - The grants on the dev database match §4.
  - Any later migration or new permission code is run there as part of its own task.
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
| 1 | `support` app: models, migration, private storage, read-only Django admin, permission codes | backend | ✅ Done |
| 2 | `SupportTicketService` + attachment validator | backend | ✅ Done |
| 3 | Customer API | backend | ✅ Done |
| 4 | Staff API | backend | ✅ Done |
| 5 | Frontend foundation: types, API clients, shared support components | frontend | ✅ Done |
| 6 | Customer ticket list + new ticket form + profile nav item | frontend | ✅ Done |
| 7 | Customer ticket conversation page | frontend | ✅ Done |
| 8 | Customer entry points: order page, header menu, footer | frontend | ✅ Done |
| 9 | Admin `/admin/support` ticket list | frontend | ✅ Done |
| 10 | Admin ticket detail: thread, reply / internal note, status, priority, assignee | frontend | ☐ Not started |
| 11 | *(optional)* Auto-close resolved tickets after 7 days | backend | ☐ Not started |
| 12 | Regression run and documentation close-out | docs | ☐ Not started |

**The feature is usable end to end after Task 10.** Task 11 is an extra; Task 12 records
the final checks.

### Task 1 — `support` app: models, migration, private storage, Django admin, permission codes

**Goal.** The database and permissions for tickets exist. Nothing is reachable through
the API yet.

- [x] Create the `support` app (`apps.py`, `__init__.py`) and add it to
      `INSTALLED_APPS` (`config/settings/base.py`).
- [x] `PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"` in `base.py`;
      `private_media/` in `backend/.gitignore`.
- [x] `support/storage.py`: a callable returning a `FileSystemStorage` on
      `settings.PRIVATE_MEDIA_ROOT` (no `base_url`), plus the
      `support/<yyyy>/<mm>/<uuid>.<ext>` `upload_to` function.
- [x] `support/models.py`: `SupportTicket`, `TicketMessage`, `TicketAttachment` exactly
      as §5, with choices, `VALID_TRANSITIONS`, `can_transition_to()`, `is_closed`,
      indexes and `__str__`.
- [x] Migration `support/migrations/0001_initial.py`.
- [x] `support/admin.py`: ticket admin with list filters (status, priority, category),
      search (ticket number, subject, customer email), read-only message and attachment
      inlines; `status` / `assigned_to` read-only; no add, no delete (D16).
- [x] `seed_rbac.py`: the five codes in `PERMISSIONS_DATA`, the role grants from §4, and
      the three `support.staff.*` codes in `FORBIDDEN_ROLE_PERMISSIONS[CUSTOMER]`.
- [x] Tests: the transition table; `seed_rbac` grants per role; the CUSTOMER denylist
      heals a bad grant; the upload path is a UUID under `support/`.

**Done when.** `manage.py test support` passes; `manage.py check` is clean;
`makemigrations --check` reports no changes.

**Status:** ✅ Done 2026-09-24

- **Storage.** `PrivateMediaStorage` reads `PRIVATE_MEDIA_ROOT` on every access instead
  of caching it, so `override_settings` works in tests. Its `url()` raises
  `ValueError`, so nothing can accidentally hand out a public link. The upload path
  keeps only a known extension (`jpg`, `png`, `webp`, `pdf`; `jpeg` becomes `jpg`).
  Anything else is stored as an inert `.bin`, and the client's file name never reaches
  the disk.
- **Model constants for later tasks:** `CUSTOMER_REOPEN_STATUSES` (WAITING / RESOLVED)
  and `UNRESOLVED_STATUSES` (the D13 cap). `can_transition_to()` is the staff table only;
  the service applies the customer moves.
- **Wider than planned:**
  - A database `CHECK` constraint, `support_msg_customer_not_internal`: a customer's
    message can never be internal.
  - The Django admin is fully **view-only**, stricter than "status/assignee read-only":
    no field is editable, and add/change/delete all return 403. Attachments appear in
    the message inline by name and size only, because they have no URL.
  - `rbac/widgets.py` `RESOURCE_META` gets a "Support tickets" group
    (`support_agent`, weight 170) for the Django-admin permission board.
- **Indexes.** Names are shortened to fit Django's 30-character limit
  (`support_tkt_cust_act_idx`, `support_tkt_status_act_idx`, `support_tkt_assignee_idx`,
  `support_msg_tkt_created_idx`). `status` has no index of its own, because the
  (`status`, `-last_activity_at`) index covers it.
- **Roles.** OPERATION_MANAGER gets `support.staff.view` + `support.staff.reply` (no
  `manage`), with a comment in `seed_rbac.py` saying why.
- **Verified:** `manage.py test support` **34/34 OK** in 87 s on a throwaway
  `test_minishop_sup1` database (created, then destroyed). The 34 cover: every
  transition pair; the check constraint; ticket-number uniqueness; the ticket surviving
  its customer's deletion; files landing under the private root and not `MEDIA_ROOT`;
  no public URL; path sanitising; per-role grants; the CUSTOMER denylist healing a bad
  grant; the admin refusing add/change/delete. `manage.py check` is clean and
  `makemigrations --check` reports no changes.
- **Regression:** the `rbac` suite, which covers `seed_rbac` and the permission board,
  passed **69/69 OK** in 671 s on a throwaway `test_minishop_sup1r` database.
- **Dev database:** migrated and seeded on 2026-09-24, after Task 2 (§10).

---

### Task 2 — `SupportTicketService` + attachment validator

**Goal.** All ticket rules live in one tested service, with no views yet.

- [x] `support/validators.py`: `validate_attachments(files)`. It enforces at most 5 files
      and 5 MB each; detects the type from the content (Pillow `open()` + `verify()` for
      JPG / PNG / WebP, `%PDF-` header for PDF); rejects everything else; returns the
      detected content type and a cleaned original name for each file.
- [x] `support/services.py`: `SupportTicketError` (message → 400) and
      `SupportTicketService` with:
  - [x] `generate_ticket_number()` (`TKT<YYYYMMDD><6-HEX>`, retry on collision, like
        `generate_order_number`)
  - [x] `create_ticket(customer, category, subject, description, order_number=None,
        files=(), ip_address=None)`: order ownership, 5-unresolved cap (D13), ticket +
        first message + attachments, timestamps, `SUPPORT_TICKET_CREATED` audit
  - [x] `add_customer_reply(ticket, customer, body, files=())`: locks the ticket;
        refuses `CLOSED`; reopens `WAITING_ON_CUSTOMER` / `RESOLVED` with a system
        message; updates `last_customer_message_at` and `last_activity_at`
  - [x] `close_by_customer(ticket, customer)`
  - [x] `add_staff_message(ticket, staff, body, files=(), is_internal=False,
        set_status=None, ip_address=None)`: the automatic `OPEN → IN_PROGRESS` move,
        `first_response_at`, `last_staff_reply_at` (public only); an internal note
        leaves all customer-visible fields alone
  - [x] `change_status(ticket, staff, new_status, reason="", ip_address=None)`:
        transition check, `resolved_at` / `closed_at`, public system message, audit
  - [x] `update_details(ticket, staff, priority=None, category=None, reason="",
        ip_address=None)`: internal system message, audit
  - [x] `assign(ticket, staff, assignee, ip_address=None)`: the assignee must be active
        and hold `support.staff.reply`; `None` unassigns; internal system message, audit
  - [x] `mark_read_by_customer(ticket)` and `get_assignable_staff()` (active users
        holding `support.staff.reply` through an active role or an active direct grant,
        plus SUPER_ADMINISTRATOR / superusers)
- [x] Every write runs in `transaction.atomic()` with `select_for_update()` on the ticket.
- [x] Tests: the service and attachment cases from §12.

**Done when.** `manage.py test support` passes, including the new tests.

**Status:** ✅ Done 2026-09-24

- **Signatures take a ticket number, not a ticket.** The customer methods are
  `add_customer_reply(customer, ticket_number, body, files=(), ip_address=None)` and
  `close_by_customer(customer, ticket_number, ip_address=None)`. The staff methods are
  `add_staff_message / change_status / update_details / assign(staff, ticket_number,
  …)`.
  - The row lock and the ownership scope are one query:
    `select_for_update().get(ticket_number=…, customer=customer)`.
  - Another customer's ticket raises `SupportTicket.DoesNotExist`.
  - **Task 3/4 views map** `DoesNotExist` → 404, `SupportTicketError` → 400
    `{"detail": str(exc)}`, and Django `PermissionDenied` → 403 (DRF does that last one
    by itself).
- **The service checks permissions itself** (wider than planned):
  - Customer methods need `support.create`.
  - `add_staff_message` needs `support.staff.reply`, plus `support.staff.manage` when
    `set_status` is given.
  - `change_status`, `update_details` and `assign` need `support.staff.manage`.
  - So no future caller can skip the check, which is the gap
    `OrderService.transition_order_status` has.
- **Errors:** `support/exceptions.py` holds `SupportTicketError` and its subclass
  `AttachmentError`, so views catch one type.
- **Rules settled while building:**
  - A message may have an **empty body if it has at least one attachment**.
  - An internal note **can't set a status**, but it **can** be added to a `CLOSED`
    ticket. Public replies to a closed ticket are refused.
  - A `set_status` equal to the current status is ignored.
  - Leaving `RESOLVED` for an active status clears `resolved_at`; a reopen by the
    customer does the same.
  - A status-change `reason` goes to the audit log and into an **internal** system note
    ("Status change reason: …"). The public line only says "Status changed to …".
  - Every status change is audited, including the customer's reopen and close
    (`metadata.changed_by`: `customer` / `staff`).
  - Messages sent by the customer mark the ticket read for them.
  - A blank or whitespace-only `order_number` means "no order".
- **Ticket creation** takes a `select_for_update()` on the customer's user row first,
  so two simultaneous requests can't both slip under the 5-ticket cap.
- **Files:** they are written inside the transaction through
  `_discard_files_on_error()`; if anything later in the transaction fails (tested by
  making the audit write raise), the files written so far are deleted.
- **Attachment names:** the stored name comes from the detected type ("receipt.jpg"
  holding a PDF is stored and shown as "receipt.pdf"). Display names lose directories
  and control characters (including the right-to-left override `U+202E`) and are cut
  to 255 characters keeping the extension.
- **Refused on purpose:** SVG, HTML, GIF, BMP, a ZIP renamed `.pdf`, text renamed
  `.png`, and a truncated PNG.
- **Constants** for serializers live in `support/services.py` (`SUBJECT_MIN_LENGTH`,
  `MESSAGE_MAX_LENGTH`, `MAX_UNRESOLVED_TICKETS`, …) and `support/validators.py`
  (`MAX_ATTACHMENTS_PER_MESSAGE`, `MAX_ATTACHMENT_BYTES`).
- **Verified:** `manage.py test support` **82/82 OK** (34 from Task 1 + 15 validator +
  33 service) in 372 s on a throwaway `test_minishop_sup2` database (created, then
  destroyed). Temporary private-media directories are removed after each class.
  `manage.py check` is clean; `makemigrations --check` reports no changes.
- **Not tested:** real concurrent requests. The row lock is in place, but a threaded
  race test against the remote MySQL wasn't attempted.

---

### Task 3 — Customer API

**Goal.** A customer can open, read, answer and close their own tickets over the API.

- [x] `support/permissions.py`: `CanViewOwnSupportTickets` (`support.view`) and
      `CanCreateSupportTickets` (`support.create`), in the `CanModerateReviews` style.
- [x] `support/serializers.py`: create (multipart, field validation from D3), customer
      ticket list, customer ticket detail with public messages only and staff names per
      D14, reply.
- [x] `support/views.py` + `support/urls.py` (`app_name = "support"`): every customer
      route in §6. Querysets are scoped to `request.user`; `ticket_number` lookups give
      404 off-scope; the detail GET marks the ticket read; the attachment view returns a
      `FileResponse` with `nosniff`, the detected content type and a cleaned file name.
- [x] Mount it with `path("api/support/", include("support.urls"))` in `config/urls.py`
      (**before** the `api/` customers include).
- [x] Tests: the customer API cases from §12.

**Done when.** Tests pass; the §6 example shape comes back from the detail endpoint.

**Status:** ✅ Done 2026-09-24

- **Contract as built** (the frontend in Tasks 5–7 relies on it):
  - `POST tickets/`, `POST tickets/<n>/messages/` and `POST tickets/<n>/close/` all
    return the **full customer ticket detail**: 201, 201 and 200. The plan said reply
    would return "message + status"; returning the whole ticket lets the page swap its
    state in one step.
  - Files go in a repeated `attachments` multipart field.
  - `GET tickets/?status=` accepts `open` (everything except CLOSED), `closed`, `all`
    (the default). Anything else → 400.
  - The list is `{count, next, previous, results}`, 10 per page, newest activity first.
  - Customer status labels: `OPEN` "Open", `IN_PROGRESS` "In progress",
    `WAITING_ON_CUSTOMER` **"Waiting on you"**, `RESOLVED` "Resolved", `CLOSED` "Closed".
  - Author names: the customer's own messages read **"You"**. Staff messages read
    "<first name> · MiniShop Support", or just "MiniShop Support" when the staff user
    has no first name. System lines read "MiniShop Support".
  - Attachment `url` is a relative `/api/support/attachments/<id>/`.
- **Errors:**
  - Field errors come back per field with plain wording
    (`{"subject": ["Subject must be at least 5 characters."]}`).
  - Service rules come back as `{"detail": …}`.
  - Missing or foreign tickets → 404 `{"detail": "Ticket not found."}`.
  - A file missing from disk → 404 `{"detail": "This file is no longer available."}`.
- **Read tracking:** `SupportTicket.has_unread_for_customer` (a model property) drives
  both `has_unread` and the detail view's mark-read. The detail GET only writes when
  something is actually unread, so the page's 60-second refresh doesn't write every
  time.
- **Private data:**
  - Messages are prefetched as `public_messages` with `is_internal=False`.
  - The serializer never falls back to `ticket.messages.all()`.
  - A test checks that the raw response contains no internal-note text, no
    internal-attachment name, no priority value and no assignment note.
- **Downloads** send `Content-Disposition: inline; filename="…"` (Django escapes it),
  the detected `Content-Type`, `X-Content-Type-Options: nosniff` and
  `Cache-Control: private, no-store`.
- **Verified:**
  - `manage.py test support.tests.test_customer_api` **17/17 OK** in 327 s on a
    throwaway `test_minishop_sup3` database.
  - `manage.py check` is clean; `makemigrations --check` reports no changes.
  - **Live check on the dev database**, run through the Django shell in a transaction
    that was rolled back, with the attachment file deleted afterwards (ticket count 0
    before and after):
    - A real CUSTOMER (`smoke_customer_user`) created a ticket with a PNG (201).
    - The ticket showed in the list and the PNG downloaded (200, `image/png`,
      `nosniff`).
    - A staff reply raised `unread` to 1. Opening the ticket cleared it.
    - An internal note did **not** appear.
    - Reply returned 201, close returned 200 with `can_reply: false`, and another
      user's request got 404.
- **Regression:** the whole `support` suite, **99/99 OK** in 680 s on the committed
  Task 3 code (throwaway `test_minishop_sup3f`).
- **Test pitfall found and fixed:** after reading a `FileResponse`'s
  `streaming_content`, calling `response.close()` again fires `request_finished` a
  second time. Django then closes the database connection in the middle of the
  transaction. The download test no longer does this, and a comment says why.

---

### Task 4 — Staff API

**Goal.** Support staff can find, read, answer and manage every ticket over the API.

- [x] Permission classes `CanViewSupportTickets`, `CanReplySupportTickets`,
      `CanManageSupportTickets`.
- [x] Staff serializers: list row (with `needs_reply`, customer name and email,
      assignee, priority), detail (every message including internal ones; customer,
      order and `allowed_transitions` blocks from §6), staff message, update, assign.
- [x] Views under `support/urls.py` at `staff/…`: list with every filter, `search` and
      `ordering` (`AdminPagination` style, 20 per page), detail, messages, PATCH, assign,
      assignees, summary, attachment download.
- [x] Tests: the staff API cases from §12, including OPERATION_MANAGER reply-but-not-manage.

**Done when.** `manage.py test support` passes; `manage.py check` is clean.

**Status:** ✅ Done 2026-09-24

- **Contract as built** (Tasks 9–10 rely on it):
  - `POST staff/tickets/<n>/messages/` (201), `PATCH staff/tickets/<n>/` (200) and
    `POST staff/tickets/<n>/assign/` (200) all return the **full staff ticket detail**.
  - Staff status labels are the model's own ("Waiting on customer").
  - `allowed_transitions` is a list of status codes.
  - `order.total_amount` is a string (for example `"1250.00"`).
  - Author names are real: customers by display name, else full name, else username;
    staff by full name, else username; system lines read "System".
  - Internal-note attachments use `/api/support/staff/attachments/<id>/`.
- **List filters:**
  - `status` takes a status code, `active` (everything except CLOSED) or `all`.
  - `priority`, `category`.
  - `assigned` takes `me`, `unassigned` or a user id.
  - `needs_reply=true`.
  - `search` matches ticket number, subject, customer username / email / first name /
    last name, and order number.
  - `ordering`: `±last_activity_at` (default newest), `±created_at`, `±priority`
    (Low < Normal < High < Urgent).
  - `page_size` up to 100.
  - Any unknown filter value → 400, not silently ignored.
- **`needs_reply`** lives on the model in one place. The `needs_reply` property and
  `needs_reply_condition()` (a `Q`, used by the `SupportTicket.objects.needs_reply()`
  queryset method and the summary count) implement the same D11 rule. The new manager
  needed no migration.
- **PATCH is all-or-nothing.** Priority/category and status changes run in one outer
  transaction, so a refused status change also undoes a priority change sent with it
  (tested). A body with none of the three fields → 400 `{"detail": "Nothing to
  change."}`.
- **Summary** returns `{by_status: {all 5 statuses}, active, needs_reply, unassigned,
  assigned_to_me}`. The last four count only tickets that aren't closed. The grouped
  query calls `order_by()` so `Meta.ordering` can't split the `GROUP BY`.
- **Assign:** an unknown user id gets the same 400 as a user who can't be assigned, so
  the endpoint doesn't reveal which ids exist.
- **Permissions:** each staff view also requires `support.staff.view`, so a direct
  grant of only `reply` or `manage` isn't enough to use the API.
- **Verified:**
  - `manage.py test support.tests.test_staff_api` **22/22 OK** in 214 s on a throwaway
    `test_minishop_sup4` database.
  - The whole `support` suite (Tasks 1–4) passed **121/121 OK** in 903 s on a
    throwaway `test_minishop_sup4f` database. This is the "Done when" criterion.
  - `manage.py check` is clean; `makemigrations --check` reports no changes.
  - **Live check on the dev database**, in a rolled-back transaction with the file
    deleted afterwards (0 tickets before and after):
    - Summary and the `needs_reply` + search list found the new ticket.
    - The assignees list returned 4 people.
    - An internal note with a PNG was added; staff could download it, the customer got
      404.
    - A reply with `set_status=WAITING_ON_CUSTOMER` cleared `needs_reply`.
    - The priority change and assignment each added an internal system line.
    - The customer's view showed 3 messages and "Waiting on you", with no internal
      text, priority or assignment.
    - Resolving via PATCH worked, and the RESOLVED filter found the ticket.

---

### Task 5 — Frontend foundation: types, API clients, shared support components

**Goal.** Everything the support pages need exists and compiles. Nothing is visible yet.

- [x] `lib/types.ts`: `SupportCategory`, `SupportStatus`, `SupportTicketSummary`,
      `SupportTicket`, `SupportMessage`, `SupportAttachment`. Use names that don't clash
      with the old `Admin*` types there.
- [x] `lib/support.ts`: category and status labels, limits (5 files, 5 MB, allowed
      types, subject/description lengths), `validateSupportFiles()`, `formatFileSize()`.
- [x] `lib/api.ts` (customer, token last, like `createReview`): `getMySupportTickets`,
      `getMySupportTicket`, `createSupportTicket(FormData)`, `replyToSupportTicket`,
      `closeSupportTicket`, `getSupportUnreadCount`, `fetchSupportAttachment` (→ `Blob`).
- [x] `lib/admin-api.ts`: a private `adminMultipartRequest` (same 401 refresh-and-retry
      as `adminRequest`, but no JSON `Content-Type`); staff types with "Mirrors …"
      comments; `getAdminSupportTickets`, `getAdminSupportTicket`,
      `postAdminSupportMessage(FormData)`, `updateAdminSupportTicket`,
      `assignAdminSupportTicket`, `getAdminSupportAssignees`, `getAdminSupportSummary`,
      `fetchAdminSupportAttachment`.
- [x] `components/support/TicketStatusBadge.tsx` (token colours),
      `AttachmentPicker.tsx` (pick, validate, previews, remove; revokes object URLs),
      `SecureAttachment.tsx` (takes a `load(): Promise<Blob>` prop, renders a thumbnail
      or a file chip, opens in a new tab, revokes on unmount),
      `TicketThread.tsx` (customer / staff / system / internal bubbles, `variant`
      prop, plain text with `whitespace-pre-wrap`).

**Done when.** `npm run typecheck`, `npm run build` and `eslint` on the new files pass.

**Status:** ✅ Done 2026-09-24

- **Signatures as built** (they differ a little from the checklist):
  - Customer (token last):
    - `createSupportTicket(input, token)` takes a typed `SupportTicketCreateInput` and
      builds the `FormData` itself.
    - `replyToSupportTicket(ticketNumber, body, files, token)`.
    - `getMySupportTicket` returns **`null` on 404** (missing or not yours), like
      `getMyProductReview`.
    - Every write returns the whole `SupportTicket`.
    - Errors carry the backend's own words: `detail`, else the first field error.
    - A network failure reads "Couldn't reach MiniShop. Check your connection and try
      again."
  - Staff (token first):
    - `postAdminSupportMessage(token, n, {body, isInternal, setStatus?, files})`. It
      never sends `set_status` with an internal note, because the backend refuses the
      pair.
    - `assignAdminSupportTicket(token, n, assigneeId | null)`.
    - `getAdminSupportTickets(token, filters)` takes every filter from Task 4, typed.
- **Staff transport:** `admin-api.ts` gets `adminRawRequest`, which returns the raw
  `Response` and handles 401 refresh-and-retry and `AdminApiError` like
  `adminRequest`.
  - `adminMultipartRequest` and `fetchAdminSupportAttachment` are both built on it.
  - This is the "second request layer" the `AdminCategoryWritePayload` comment
    anticipated.
- **Attachment fetchers** refuse any URL outside `/api/support/`
  (`/api/support/staff/` for the staff one), so the token is never sent anywhere
  else.
- **Types:** customer types (plus `SupportPriority`, `SupportAuthorType`,
  `SupportTicketCreateInput`, `SupportTicketListStatus`) are in `types.ts`. Staff
  types (`AdminSupportTicket`, `AdminSupportTicketDetail`, `AdminSupportMessage`,
  `AdminSupportSummary`, `AdminSupportAssignee`, …) are next to their fetchers in
  `admin-api.ts`, each with a "Mirrors …Serializer" comment.
- **`lib/support.ts` extras:**
  - Both label sets: `CUSTOMER_STATUS_LABELS` ("Waiting on you") and
    `STAFF_STATUS_LABELS` ("Waiting on customer").
  - Categories with Material icons, plus `SUPPORT_STATUSES` and `SUPPORT_PRIORITIES`.
  - `SUPPORT_FILE_ACCEPT` and `SUPPORT_FILE_HINT`.
  - `formatSupportDateTime()`.
  - `formatRelativeTime(iso, now)`. It takes `now` as an argument so pages can keep
    render pure.
  - `validateSupportFiles` falls back to the file extension when the browser sends an
    empty MIME type.
- **Object URLs never go into React state.** `AttachmentPicker`'s previews and
  `SecureAttachment`'s thumbnails create the URL inside an effect, write it to the
  `<img>` / `<a>` through a ref, and revoke it in the effect's cleanup. React's
  development double-mount therefore can't leave a revoked URL on screen, which a
  `useMemo` + cleanup version would.
  - These are the only two `<img>` elements in the app, each with an
    `@next/next/no-img-element` exception, because `next/image` can't load a
    `blob:` URL.
- **Attachment behaviour:**
  - Images are fetched right away and shown as 96 px thumbnails that open full size in
    a new tab.
  - PDFs are fetched only when clicked, then open in a new tab. If a pop-up blocker
    stops that, they download instead. The URL is revoked 60 s later.
  - A failed load shows "Couldn't load" / "Couldn't open — try again".
- **`TicketThread`** takes `viewer: "customer" | "staff"` (the checklist called it
  `variant`); the viewer's own messages sit on the right.
  - Internal notes get a dashed accent border and the label "Internal note · staff
    only".
  - Internal system lines get a lock icon and a screen-reader-only "Staff only:".
  - Times use `<time dateTime>`.
  - The list is an `<ol aria-label="Conversation">`.
- **`TicketStatusBadge`** uses theme tokens. `WAITING_ON_CUSTOMER` is the one solid
  (accent) badge, because it is the only status that asks the customer to act.
- **Verified:**
  - `npm run typecheck` passes, and `npm run build` compiles (42 pages).
  - `eslint` on `components/support/*`, `lib/support.ts` and `lib/admin-api.ts` is
    clean.
  - A Node harness (`lib/support.ts` compiled with `tsc`, real `File` objects) passes
    7 checks: the four allowed types; the extension fallback; SVG / empty / 5 MB + 1
    byte refused while good files are kept; the 5-file cap counting files already
    chosen; file sizes; relative times; every label present.
  - Found while testing: `en-GB` month names come out as "Sept" in Node and current
    browsers; the console's existing `formatDateTime` does the same.
  - Not rendered in a browser yet: the components get their first real use in
    Task 6.
- **Pre-existing, left alone:** `eslint` reports `no-explicit-any` at `types.ts:307`
  (`Payment.metadata`, from 2026-09-12) and at `api.ts:1435` / `:1485`, plus three
  unused-variable warnings in `api.ts`. All are in code this task didn't touch.

---

### Task 6 — Customer ticket list + new ticket form + profile nav item

**Goal.** A customer can see their tickets and open a new one.

- [x] `profile/layout.tsx`: a **Support** nav item with an unread badge
      (`getSupportUnreadCount`); prefix active match; redirect to
      `/login?next=<current path>`.
- [x] `app/profile/support/page.tsx`: Open / Closed tabs, ticket cards, pagination,
      loading / error / empty states (the "My Reviews" page pattern).
- [x] `app/profile/support/new/page.tsx` (with `Suspense` for `useSearchParams`):
      category chips, subject, description + counter, related-order select prefilled
      from `?order=`, `AttachmentPicker`, submit → `/profile/support/<ticket_number>`,
      backend errors shown inline.

**Done when.** A ticket with attachments can be created in the browser and appears in
the list; `npm run build` passes; it works at 390 px.

**Status:** ✅ Done 2026-09-24

- **Profile layout:**
  - The **Support** item (last in the nav, `support_agent` icon) appears only for a
    user holding `support.view` (or `*`, or a superuser), so a staff account without
    the CUSTOMER role doesn't get a link that would 403.
  - The unread badge is re-fetched on every profile navigation, so opening a ticket
    clears it. It has a screen-reader text ("1 ticket with a new reply").
  - The active check is now `pathname === href || pathname.startsWith(href + "/")`,
    and the active link has `aria-current="page"`.
  - The login redirect reads `window.location` inside the effect, so the layout doesn't
    need `useSearchParams` and a `Suspense` boundary. It sends
    `/login?next=<path + query, encoded>`.
- **Wider than planned: the active item scrolls into view on phones.** Below `lg` the
  nav is one sideways-scrolling row, and Support, being last, was off-screen while
  active.
  - The layout now sets the row's own `scrollLeft` to centre the current item. It
    never calls `scrollIntoView`, so the page itself can't jump.
  - This helps every profile page, not only Support.
- **List page:**
  - Uses the My Reviews request-key loading pattern, so no `setState` runs in the
    effect body.
  - Relative times ("just now", "3 h ago") are measured from when the page loaded,
    which keeps render pure.
  - A ticket with a staff reply gets an accent border and a "New reply" marker.
  - Each tab has its own empty state; Open offers "Open a ticket".
  - 10 per page, with the existing `Pagination`.
- **New-ticket form:**
  - Category is a real radio group: `fieldset` / `legend`, visually hidden radios, and
    the focus ring drawn on the chip via `has-focus-visible:`.
  - `?order=<n>` preselects that order **and** the "Order & delivery" category.
  - The order select lists the customer's 10 most recent orders as
    "number · date · ৳total". A linked order that isn't among them still gets its own
    option; the backend decides whether it is theirs.
  - Subject and description have live counters and a note not to include passwords or
    card numbers.
  - Client-side checks mirror the backend's minimums (`aria-invalid` +
    `aria-describedby`).
  - Backend errors (for example the 5-open-ticket cap) show in a `role="alert"` box at
    the top of the form.
  - On success it goes to `/profile/support/<ticket_number>`. **That page arrives in
    Task 7**; until then the link lands on the not-found page.
- **Verified:**
  - `npm run typecheck` passes, and `npm run build` compiles with `/profile/support` and
    `/profile/support/new` both static.
  - `eslint` on the layout and both pages is clean.
  - **Browser:** headless Chrome driven over the DevTools protocol, logged in as
    `smoke_cust_1` (3 orders) on the dev database.
  - Setup note: port 3000 was already taken by the owner's own `next dev` (running
    since 11:53), so the checks ran against it; it was left running. Django ran on
    8001, started for the test and stopped afterwards.
  - All of these passed with no console errors:
    - Logged out, `/profile/support/new?order=…` → `/login?next=%2Fprofile%2Fsupport%2Fnew%3Forder%3D…`.
    - The Support item is marked current on the list **and** on `/new`.
    - `?order=` preselected the order and category; all 3 recent orders were listed
      with ৳ totals.
    - An empty submit showed both field errors.
    - A PNG and a PDF showed as chips, and the PNG preview used a `blob:` URL.
    - An SVG was refused by the picker while the two good files stayed.
    - Submit created `TKT20260924601BF9` and navigated to its page.
    - The Open list grew from 0 to 1, with subject, "Open", order number, category and
      "just now". The backend stored the two files as `image/png` and
      `application/pdf` under `private_media/support/…`.
    - After a staff reply (added from the Django shell) the nav showed "1" from another
      profile page, and the card showed "New reply" and "In progress".
    - At 390 px: no horizontal overflow on the list or the form (two files chosen),
      and the active Support item sits inside the nav row with `scrollX` 0.
  - **Cleanup:** the test ticket (1 ticket, 3 messages, 2 attachments) and both files
    were deleted afterwards; the dev database has 0 tickets again. Its 2 audit-log rows
    (created, status change) remain, because the log is append-only.

---

### Task 7 — Customer ticket conversation page

**Goal.** A customer can read the conversation, reply and close the ticket.

- [x] `app/profile/support/[ticketNumber]/page.tsx`: header (status, category, order
      link), `TicketThread`, reply box with `AttachmentPicker`, **Close ticket** with a
      confirm step, the closed and resolved notes from §7.
- [x] Refetch on window focus, every 60 s while visible, and after every action (D12).
- [x] Attachments through `SecureAttachment` + `fetchSupportAttachment`.
- [x] Not found (someone else's ticket or a bad number) → a friendly "Ticket not found"
      with a link back to the list.

**Done when.** Reply, reopen-by-reply and close work in the browser; the unread badge
clears after opening; `npm run build` passes.

**Status:** ✅ Done 2026-09-24

- **Header:**
  - Status badge, ticket number, subject, category, a link to the linked order
    (`/profile/orders/<n>`), and the opening date.
  - A **Close ticket** button while the ticket can be closed.
- **Status notes:**
  - RESOLVED: "We've marked this as resolved", saying that a reply reopens the ticket,
    plus an "All sorted, close it" button.
  - WAITING_ON_CUSTOMER: "We're waiting for your reply". This goes slightly beyond §7,
    because it is the one status that asks the customer to act.
- **Thread:** `TicketThread` with `viewer="customer"`. Attachments go through a
  module-level loader that reads the token on every call, so `SecureAttachment` gets a
  stable function, as it needs.
- **Reply box:**
  - Message counter (5000); files through `AttachmentPicker`; Ctrl/⌘ + Enter sends.
  - Sending with no text and no file shows the backend's own rule inline ("Write a
    message or attach a file.").
  - Backend errors show in a `role="alert"` box and trigger a refetch, in case the team
    closed the ticket meanwhile.
  - When the ticket is CLOSED, the box is replaced by "This ticket is closed" and **Open
    a new ticket**. That link carries the order over (`?order=<n>`) when the ticket had
    one.
- **Close:** reuses `AdminConfirmModal`, a generic dialog that calls no API, in its
  non-destructive primary style. It gives role="dialog", focus trap, Escape and focus
  restore. The dialog warns when an unsent reply would be discarded and shows a failed
  close inline.
- **Refreshing (D11):**
  - The ticket is re-read every 60 s while the tab is visible, and on window focus or a
    return to the tab (at most one read per 5 s).
  - Every write answers with the whole ticket, and the page shows that directly.
  - A generation counter drops any read that answers after a newer read or write, so a
    slow poll can't undo a reply.
  - Background refreshes keep the page as it is (no spinner). A failed background read
    keeps the last good copy.
- **Screen-reader announcements** (a polite live region): "Reply sent." (or "… The
  ticket is open again." when the reply reopened it), "Ticket closed.", and "New reply
  from MiniShop Support." when a refresh brings a staff message.
- **Unread badge (`profile/layout.tsx`, `lib/support.ts`):**
  - The page fires `SUPPORT_UNREAD_EVENT` after each successful read (`notifySupportUnreadChanged()`).
    Opening a ticket marks it read, and the layout re-counts on that event.
  - The re-count's effect cleanup drops the count started on navigation. That count
    could otherwise answer after the mark-read and leave a stale "1" on screen.
- **Ticket not found:** "Ticket not found" with **Back to my tickets**. This covers both
  a made-up number and another customer's ticket (the API's 404, D8).
- **Verified:**
  - `npm run typecheck` passes. `npm run build` passes, with `/profile/support/[ticketNumber]`
    dynamic (ƒ). `eslint` on the page, the layout and `lib/support.ts` is clean.
  - **Browser:** headless Chrome over the DevTools protocol, logged in as `smoke_cust_1`,
    against the dev database. The test data came from the Django shell: one ticket with
    a PNG + PDF, a staff reply with an image that set "Waiting on customer", an internal
    note with a PDF, and one ticket owned by another customer.
  - Setup note: the owner's own `next dev` on 3000 (running since 11:53) answered 500
    for the new route. Its worker had crashed ("Jest worker encountered 2 child process
    exceptions"), while existing routes still returned 200. It was left untouched.
    - Instead, the production build was served with `next start -p 3001`, next to
      Django on 8001.
    - The test Chrome ran with `--disable-web-security`, because CORS allows only port
      3000.
    - Both servers were stopped afterwards. Restarting `next dev` should make the route
      work there too.
  - All 20 checks passed, with no console errors:
    - Before opening, the nav badge showed "1". After opening, it cleared on the ticket
      page itself, with no navigation.
    - The header showed "Waiting on you", the ticket number, the category, the order
      link, the Close button and the waiting note.
    - Thread layout: the customer on the right, staff on the left, system lines centred.
    - Neither the internal note text nor its PDF appeared.
    - Both images loaded as `blob:` thumbnails. The PDF button fetched an
      `application/pdf` blob and opened it.
    - An empty reply showed the inline error.
    - A text + PNG reply turned the status to **Open** (reopened by reply) and added
      the message and the "Reopened" line. The draft and files were cleared, and "Reply
      sent. The ticket is open again." was announced. The new image showed as a
      thumbnail.
    - At 390 px there was no horizontal overflow.
    - A staff reply posted from the shell appeared **on its own 54 s later** (60 s
      refresh). The status became In progress, "New reply from MiniShop Support." was
      announced, and no badge came back.
    - The staff then resolved the ticket. A window focus refetched it, showing Resolved,
      the resolved note, and the reply box still there.
    - **Close ticket** opened the dialog with focus inside, and Escape dismissed it
      (still Resolved). "All sorted, close it" followed by the confirm closed the
      ticket:
      - the status became Closed;
      - the closed note appeared, with the `?order=` link;
      - there was no reply box or Close button;
      - "Ticket closed." was announced.
    - A made-up number and the other customer's ticket both showed "Ticket not found"
      with the link back.
  - **Cleanup:** the test tickets and their private files were deleted after each run;
    the dev database has 0 tickets. Their audit rows remain, because the log is
    append-only.
- **Noticed, not changed:** the public system line reads "Status changed to Waiting on
  customer." (staff wording) while the customer's badge says "Waiting on you". That
  text is written by `SupportTicketService` (Task 2). It could use the customer wording
  for public lines if wanted.

---

### Task 8 — Customer entry points: order page, header menu, footer

**Goal.** Customers can find support where they need it.

- [x] Order detail header: **Get help with this order** →
      `/profile/support/new?order=<order_number>`.
- [x] Header account dropdown: **Help & Support** → `/profile/support` (after
      Favorites, same classes).
- [x] Footer **Contact Support** → `/profile/support/new`.

**Done when.** All three links work, including for a logged-out visitor (login, then
back); `npm run build` passes.

**Status:** ✅ Done 2026-09-24

- **Order detail** (`profile/orders/[orderNumber]/page.tsx`):
  - **Get help with this order** is an outlined button (`support_agent` icon) next to
    Cancel Order. The two sit in one wrapping group, so they share a row on desktop and
    stack neatly under the title on phones.
  - It shows on every order, cancelled and delivered ones included (refund questions).
- **Header menu** (`components/layout/Header.tsx`): **Help & Support** right after
  Favorites, with the same classes and the `support_agent` icon; clicking it closes the
  menu.
- **Footer** (`components/layout/Footer.tsx`): **Contact Support** now goes to
  `/profile/support/new`; the other footer links are still `#`. A logged-out visitor is
  sent to `/login?next=…` by the profile layout (Task 6) and comes back after logging
  in.
- **One rule for who sees the links:** `canUseSupport(user)` in `lib/support.ts`
  (`support.view`, `*`, or superuser).
  - The profile layout now uses it too, instead of its own inline copy.
  - The header item and the order button only show for those users, so a staff account
    without the CUSTOMER role isn't offered pages that would answer 403.
  - The footer link stays for everyone, logged out included.
- **Wider than planned: `?next=` can no longer leave the site.**
  - `/login` and `/register` passed `?next=` straight to `router.replace()`. Next's
    router makes a full page load to any other origin (`isExternalURL` →
    `completeHardNavigation`), so `/login?next=https://evil.example` sent a user
    off-site after login. For an already-logged-in visitor it did so at once.
  - This task sends every logged-out support visitor through that redirect.
  - `safeNextPath()` in `lib/auth.ts` fixes it. It keeps `next` only if it starts with
    `/` and still has this site's origin once parsed the way the browser parses it;
    anything else goes to `/`. This also catches `//host`, `/\host` and a tab or
    newline between the slashes.
  - Both pages use it: both login redirects, and the register redirect.
- **Verified:**
  - `npm run typecheck` passes, and `npm run build` compiles.
  - eslint is clean on every changed file except the order page. Its 2 errors (the
    `loadOrder()` effect and an `err: any`) are already in `HEAD`, 4 lines earlier; this
    task didn't touch those lines.
  - `safeNextPath` was compiled and run under Node against 17 inputs, all correct:
    - kept: normal paths with query and hash, `/%2F%2F…` (a plain path), and
      `/../../profile` (becomes `/profile`);
    - sent to `/`: `https://…`, `//…`, `/\…`, `\\…`, `/\\…`, `/<tab>/…`, `/<LF>/…`,
      `/<CR>/…`, `javascript:…`, a leading space, empty and null.
  - **Browser:** headless Chrome over the DevTools protocol, against the production
    build on `next start -p 3001` with Django on 8001. The owner's `next dev` on 3000
    was still answering 500 for new routes (see Task 7). The test Chrome used
    `--disable-web-security`, because CORS allows only port 3000.
  - Throwaway users were created for the run and deleted afterwards:
    `t8_login_check` (CUSTOMER, known password, for the real login form) and
    `t8_staff_check` (SUPPORT_TEAM only). `smoke_cust_1`, who owns orders, logged in by
    token.
  - All 16 checks passed, with no console errors:
    - Logged out, the footer link went to `/login?next=%2Fprofile%2Fsupport%2Fnew`.
      Submitting the real login form landed on the new-ticket form.
    - The header menu read …Favorites → **Help & Support** → Seller Center. Clicking it
      opened `/profile/support` and closed the menu.
    - Logged in, `/login?next=` with `https://evil.invalid/`, `//evil.invalid` or
      `/\evil.invalid`, and `/register?next=https://evil.invalid/`, all stayed on
      MiniShop's home page. A normal `next=/profile/support` still went there.
    - Logged out, the order page went to `/login?next=%2Fprofile%2Forders%2F<n>`. After
      logging in, it came back to the order. **Get help with this order** linked to
      `/profile/support/new?order=<n>`, and the form opened with that order and "Order
      & delivery" chosen.
    - The order page had no horizontal overflow at 390 px.
    - The staff-only account's header menu had no Help & Support, and still had
      Management Portal.
  - Both servers were stopped afterwards.

---

### Task 9 — Admin `/admin/support` ticket list

**Goal.** Staff see and filter the ticket queue.

- [x] `lib/admin-navigation.ts`: `ADMIN_PERMISSIONS.supportView / supportReply /
      supportManage` and a **Support Tickets** nav item (`support_agent`, section
      Operations, `requiredPermissions: supportView`).
- [x] `app/admin/support/supportGovernance.tsx`: `canViewSupport`, `canReplySupport`,
      `canManageSupport`, `SupportAccessNotice`.
- [x] `AdminStatusBadge`: tones for the 5 statuses and 4 priorities.
- [x] `app/admin/support/page.tsx`: stat cards from `summary`, status tabs,
      `AdminFilterBar` (search, priority, category, assignee), `AdminDataTable` with the
      §7 columns, URL-synced filters, debounced search, 20 per page.

**Done when.** A SUPPORT_TEAM user sees the queue and every filter works; a user without
`support.staff.view` sees the access notice; `npm run build` passes.

**Status:** ✅ Done 2026-09-24

- **Navigation:**
  - `ADMIN_PERMISSIONS.supportView / supportReply / supportManage` map to the three
    `support.staff.*` codes, commented with their backend classes.
  - **Support Tickets** sits under Operations after Payments. It appears in the sidebar
    and, through the same list, in the dashboard's Operational Shortcuts. The sidebar's
    prefix match keeps it lit on ticket pages.
- **`AdminStatusBadge` tones:**
  - Statuses: OPEN warning, IN_PROGRESS info, WAITING_ON_CUSTOMER accent, RESOLVED
    success, CLOSED neutral.
  - Priorities: LOW neutral, NORMAL info, HIGH warning, URGENT danger.
  - None of these tokens was already in use, so no other module's badges change.
- **`AdminStatCard`** gets an optional `active` prop, for a card used as a quick filter:
  it adds a primary outline and `aria-current="true"`. Existing cards are unaffected.
- **`supportGovernance.tsx`:**
  - The three gates and the access notice (names `support.staff.view`).
  - The status tabs, priority options (highest first), category options and sort
    options.
  - URL parsers, so an unknown value in a link (the backend would answer 400) falls
    back to the default instead of breaking the list.
  - The four queue-card definitions.
- **The page:**
  - **Queue cards:** Needs reply, Open, Unassigned, Assigned to me, from `summary`.
    - Each is a link to exactly its own view on the Active tab, so the list shows the
      number the card promised. The current sort is kept.
    - The matching card is outlined.
  - **Status tabs:** Active (the default; not in the URL), Open, In progress, Waiting
    on customer, Resolved, Closed, All. Each shows its count from `summary`.
  - **Filter bar:**
    - Search, debounced 350 ms: ticket number, subject, customer, order number.
    - Priority and Category.
    - Assignee: Anyone / Me / Unassigned / each agent from `assignees`, with the
      viewer marked "(you)". A link to someone no longer assignable still shows
      "User #id".
    - **Sort by** (added; the API already supported it): latest activity, oldest
      activity, highest priority, newest tickets, oldest tickets.
    - A **Needs reply only** checkbox, so the Needs reply card's filter stays visible
      and removable.
    - **Clear** resets the filters and sort, keeping the tab.
  - **Everything lives in the URL.** Choosing a tab or filter resets the page number,
    and the default tab and sort are left out.
  - **Table:** needs-reply dot (accent), Ticket, Category, Priority, Status, Assignee,
    Last activity ("27 min ago", with the full date on hover), 20 per page.
  - **Refresh** reloads the list and counts; there is no polling here (D11).
- **Layout change after the first browser pass:**
  - At 1280 px the planned separate "Ticket no." column pushed Last activity off
    screen. The ticket number now sits under the subject ("TKT… · customer"), and
    category and assignee names wrap, so all columns fit at 1280.
  - At phone width, priority, status and last activity move onto a line under the
    subject, and those columns are hidden, so the table doesn't scroll sideways.
  - Subjects are clamped to two lines. The first version paired `block` with
    `line-clamp-1`; `block` wins the `display` property, so the clamp did nothing.
- **Linking:** each subject links to `/admin/support/<ticket_number>`. **That page
  arrives in Task 10**; until then the link opens the console's generic module
  placeholder.
- **Verified:**
  - `npm run typecheck` passes. `npm run build` compiles, with `/admin/support` static.
    `eslint` is clean on every changed file.
  - **Browser:** headless Chrome over the DevTools protocol, against the production
    build on `next start -p 3001` with Django on 8001. The owner's `next dev` on 3000
    still answered 500 for new routes. The test Chrome used `--disable-web-security`,
    because CORS allows only 3000.
  - **Test data:** 22 tickets written straight through the ORM with fixed timestamps.
    The list reads only ticket fields, the sort order is then predictable, and the
    append-only audit log stayed at 22 support rows. The 22 tickets were: every status,
    priority and category, 3 needing a reply, 2 unassigned, 3 assigned to the agent, 1
    linked order, and 15 old closed ones for a second page.
  - **Users:** throwaway `t9_agent` and `t9_agent2` (SUPPORT_TEAM), `t9_ops`
    (OPERATION_MANAGER) and `t9_sales` (SALES_TEAM), logged in by token.
  - **All 46 checks passed** with no console errors. Every list shown was compared,
    row for row and in order, with the API's own answer for the same filters:
    - **Sidebar:** entry under Operations, marked current on the page.
    - **Default Active tab:** 6 rows. The needs-reply dots, the "(you)" / "Unassigned"
      assignee labels and newest-first relative times all matched.
    - **Cards and tabs:** the cards showed 3 / 2 / 2 / 3, and the tabs 6 / 2 / 2 / 1 /
      1 / 16 / 22, all matching `summary`.
    - **Each tab** showed only its status. All held 20 rows, page 2 the other 2, with
      `page=2` in the URL. Changing tab dropped the page and `status=active` from the
      URL.
    - **Each card** opened exactly its list, and that card was marked current. The
      filter bar showed the card's filter.
    - **Each filter:** priority, category and a named assignee on their own, then High
      + Me together (both in the URL). Clear reset them all.
    - **The checkbox**, and **search** by subject word, ticket number, order number and
      customer email, each reaching the URL after the debounce.
    - **Both sorts:** highest priority (Urgent > … > Low) and oldest activity. Choosing
      the default sort removed it from the URL.
    - **Links in:** a shared link restored its filters. Clicking a card after a search
      cleared the search box, and Back restored both the box and the list. Junk values
      (`status=BOGUS&priority=NOPE&assigned=xyz&ordering=bad&page=abc`) fell back to the
      defaults with no error.
    - **Refresh** showed a priority changed in the database.
    - **Layout:**
      - At 1280 px no column is scrolled away.
      - At 390 px there is no page or table overflow, and each row carries its
        priority, status and time.
      - A 150-character subject rendered as 2 lines at both widths, with the customer
        line whole.
    - **Roles:** OPERATION_MANAGER opened the queue. SALES_TEAM had no sidebar entry,
      and the page showed the access notice naming `support.staff.view`.
  - **Cleanup:** the 22 tickets and 4 users were deleted; the dev database has 0
    tickets. Both servers were stopped.

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
6. ~~**Dev database:** nothing works against the shared MySQL until `migrate` and
   `seed_rbac` have run.~~ Done 2026-09-24 (§10).

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

# Phase 2D — One Authorization System

## Objective

Replace the remaining hand-rolled role-code authorization checks with the existing MiniShop RBAC permission system, and prevent `total_revenue` from being exposed to management users who do not hold the required existing permission.

---

## Before Coding — Mandatory

1. Read the MiniShop Master Prompt completely.
2. Read:

   * `docs/MINISHOP_REVIEW_STATE.md`
   * `docs/FUTURE_PLAN.md`
3. Inspect current Git status, recent commits, and working-tree diff.
4. Inspect the actual current source before relying on the line references below.
5. Inspect the existing RBAC permission classes/services and current permission assignments.
6. Inspect the affected authorization tests before changing code.

Current baseline includes completed:

* Phase 2A
* Phase 2B
* Phase 2C
* Extra RBAC Role Permission Matrix work

Do not assume the documented line numbers are still exact if the source has moved.

---

# Scope

## 1. Remove hand-rolled `is_staff_override` role checks

`shop/api_views.py` currently contains six inline `is_staff_override` role-code checks at approximately:

* `:422`
* `:778`
* `:822`
* `:874`
* `:912`
* `:958`

They manually repeat combinations of:

* `user.is_staff`
* `ROLE_SUPER_ADMINISTRATOR`
* `ROLE_ADMINISTRATOR`
* `ROLE_OPERATION_MANAGER`

Replace these checks with the appropriate **existing MiniShop RBAC permission classes/services**.

### Important

Do NOT invent a new permission system.

Do NOT use Django `auth.Permission` / `user_permissions`.

Do NOT create another role-check helper that merely hides the same hard-coded role tuples.

The existing MiniShop RBAC system remains the single authorization source of truth.

Before choosing the replacement permission, inspect the actual existing permission definitions and mappings. Do not guess which permission should be used.

---

# 2. Admin Metrics Authorization

Inspect:

`shop/admin_views.py`

particularly `AdminMetricsAPIView`.

It currently:

* uses `permission_classes = [IsAuthenticated]`
* performs management authorization inline in `get()`
* uses the same hard-coded role-code pattern.

Replace the inline authorization with the existing RBAC authorization mechanism.

### Important distinction

There are TWO separate decisions here:

### A. Management metrics access

The endpoint must continue enforcing the existing management-console access requirement.

This is not currently an open authorization vulnerability. Do not describe it as one.

### B. `total_revenue` visibility

The endpoint currently returns the complete metrics payload, including `total_revenue`, to management users even when they do not have the appropriate finance/revenue permission.

Fix this **server-side**.

A management user who is otherwise allowed to access metrics but does NOT hold the existing permission required for revenue visibility must receive the metrics payload **without the `total_revenue` key**.

Do not rely on frontend hiding.

---

# 3. Preserve the Existing API Contract

Do not rename or remove any existing metrics keys.

The existing metrics response has seven keys.

For users authorized to see revenue:

* all seven keys remain unchanged.

For users without the revenue permission:

* only `total_revenue` is omitted.
* the remaining six keys remain unchanged.

Do not change metric calculations in this phase.

Do not change the frontend API client.

Do not change the dashboard UI.

Do not change the frontend console-access heuristic.

---

# Explicit Scope Boundaries

DO NOT:

* build a second authorization/permission system
* use Django `auth.Permission`
* use `user_permissions`
* change MiniShop role grants
* change which roles currently hold which permissions
* change the RBAC permission model
* modify `frontend/src/lib/admin-auth.ts:70`
* redesign the management console
* modify dashboard UI
* modify revenue calculation logic from Phase 2C
* modify payment/refund lifecycle
* fix unrelated issues
* fix known Issue #26
* start Phase 2E or any later phase

This phase changes **how authorization is expressed** plus the **server-side revenue field gate**.

---

# Required Tests

Add or update focused tests as necessary.

## Authorization regression

Verify all affected endpoints preserve their existing authorized/unauthorized behavior.

## Revenue visibility

At minimum prove:

### Authorized management user

A management user with the existing permission required for revenue visibility receives:

```text
total_revenue
```

in the metrics response.

### Finance-less management user

A management user who can access management metrics but does NOT hold the revenue/finance permission receives:

```text
NO total_revenue key
```

The response must still contain the other six existing metrics keys.

### Important

The test must verify the actual HTTP/API response, not merely frontend behavior.

Do not make the test depend on hiding a dashboard card.

---

# Additional Verification

Run:

1. Focused affected authorization tests.
2. Admin metrics tests.
3. Full backend test suite.
4. `python manage.py makemigrations --check`
5. `npx tsc --noEmit`
6. `npm run build`

Do not fix unrelated failures discovered during these checks unless they are directly caused by this phase.

---

# Review-State / Roadmap

Update:

* `docs/MINISHOP_REVIEW_STATE.md`
* `docs/FUTURE_PLAN.md`

only as appropriate for completing Phase 2D.

Record any newly discovered unrelated issue separately rather than fixing it inside this phase.

---

# Git

Create exactly one focused commit:

```text
refactor(auth): unify management authorization
```

Stage files explicitly.

Do NOT use:

```text
git add .
git add -A
```

Do NOT push.

Leave the working tree clean.

---

# Final Report

Report:

1. Exact files changed.
2. All six `is_staff_override` sites replaced.
3. Existing RBAC permission(s) used.
4. How management metrics authorization now works.
5. How `total_revenue` server-side visibility now works.
6. Confirmation that the other six metrics keys are unchanged.
7. Confirmation that role grants were not changed.
8. Tests and exact results.
9. `tsc` result.
10. Build result.
11. `makemigrations --check` result.
12. Commit hash/message.
13. Git working-tree status.
14. Confirmation that nothing was pushed.
15. Any newly discovered unrelated issue, if applicable.

Implement ONLY Phase 2D.
Do not begin any later phase.

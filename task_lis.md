# Django Superuser Admin — Task Tracker

## Phase 1: Register Missing Models + Enhance All ModelAdmin Classes
- [ ] shop/admin.py — Register `ProductInventory`, `InventoryTransaction`, `Payment`, `Refund`
- [ ] shop/admin.py — Enhance `CategoryAdmin`, `ProductAdmin`, `OrderAdmin`, `OrderItemAdmin`
- [ ] sellers/admin.py — Add status badges, select_related, annotated counts
- [ ] shops/admin.py — Add status badges, select_related, annotated counts
- [ ] customers/admin.py — Add order count, select_related, register `Favorite`
- [ ] cart/admin.py — Add select_related optimizations
- [ ] audit/admin.py — Add select_related, IP in list_display
- [ ] points/admin.py — Add select_related optimizations
- [ ] rbac/admin.py — Add select_related, annotated counts

## Phase 2: Enhanced Dashboard + Navigation
- [ ] Create `shop/admin_dashboard.py` — Custom dashboard view with metrics
- [ ] Modify `config/urls.py` — Register dashboard view
- [ ] Enhance `templates/admin/index.html` — Real platform metrics
- [ ] Enhance `templates/admin/nav_sidebar.html` — Organized sections
- [ ] Enhance `static/css/japanese_admin.css` — Status badges, dashboard grid, indicators

## Phase 3: Admin Actions with Service Integration
- [ ] Seller lifecycle actions (approve, suspend, reject) via `sellers.services`
- [ ] Shop lifecycle actions (approve, suspend, reject, reactivate) via `ShopService`
- [ ] Order lifecycle actions (confirm, process, ship, deliver, cancel) via `OrderService`
- [ ] Create `templates/admin/admin_actions.html` — Intermediate confirmation form
- [ ] AuditService integration for all admin actions

## Phase 4: User Admin Enhancement
- [ ] Customize User admin with UserRole inline, search, filters

## Verification
- [ ] `python manage.py check`
- [ ] Run test suite
- [ ] Frontend build verification
- [ ] Git commit

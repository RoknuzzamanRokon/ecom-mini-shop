import type { AuthUser } from "./types";
import { hasAnyPermission } from "./admin-auth";

/**
 * ==============================================================================
 * CANONICAL ADMIN PERMISSION MAP
 * ==============================================================================
 *
 * Every code below was verified against the backend, in this order:
 *   1. rbac/management/commands/seed_rbac.py  -> PERMISSIONS_DATA (the catalogue)
 *   2. shop/admin_permissions.py              -> the DRF permission classes
 *   3. shop/permissions.py                    -> the staff order/payment classes
 *
 * Nothing here is invented. Codes absent from PERMISSIONS_DATA are NOT used,
 * because a permission that is never seeded can never be held by any user and
 * would silently hide the menu entry from everyone but superusers.
 *
 * These sets are for UI visibility only. The backend remains the final
 * authorization authority on every request.
 */
export const ADMIN_PERMISSIONS = {
  /** GET /api/admin/shops/ -> CanViewAdminShops */
  shopsView: ["shops.admin.manage", "shops.view"],
  /** POST /api/admin/shops/<pk>/status/ -> CanChangeAdminShopStatus */
  shopsApprove: ["shops.admin.manage", "shops.approve"],
  /** Reject / suspend / reactivate -> CanManageAdminShops */
  shopsManage: ["shops.admin.manage"],

  /** GET /api/admin/sellers/ -> CanViewAdminSellers */
  sellersView: ["sellers.admin.manage", "sellers.view"],
  /** POST /api/admin/sellers/<pk>/status/ -> CanManageAdminSellers */
  sellersManage: ["sellers.admin.manage"],

  /**
   * GET /api/admin/products/ and /api/admin/products/<pk>/ -> CanViewAdminProducts.
   * Phase 1A.1 widened the admin product read endpoints from the manage-only
   * gate to 'products.admin.manage' OR 'products.view', so a read-only holder
   * (SALES_MANAGER, SALES_TEAM) can legitimately open the module.
   */
  productsView: ["products.admin.manage", "products.view"],
  /**
   * POST /api/admin/products/<pk>/status/ -> CanChangeAdminProductStatus gates
   * entry to the endpoint, then AdminProductStatusAPIView._update_status
   * enforces one permission per action. These four sets mirror that mapping
   * exactly; 'unpublish' deliberately has no narrow permission of its own.
   */
  productsApprove: ["products.admin.manage", "products.approve"],
  productsReject: ["products.admin.manage", "products.reject"],
  productsPublish: ["products.admin.manage", "products.publish"],
  productsManage: ["products.admin.manage"],

  /** GET /api/staff/orders/ -> CanViewStaffOrders */
  ordersView: ["orders.staff.view"],
  /** POST /api/staff/orders/<pk>/status/ -> CanUpdateStaffOrders */
  ordersUpdate: ["orders.staff.update"],

  /** GET /api/staff/payments/ -> CanViewStaffPayments */
  paymentsView: ["payments.view"],
  /** POST /api/staff/payments/<pk>/verify/ -> CanVerifyStaffPayments */
  paymentsVerify: ["payments.verify", "payments.process"],
  /** POST /api/staff/payments/<pk>/refund/ -> CanRefundStaffPayments */
  paymentsRefund: ["payments.refund", "orders.refund"],

  /**
   * /api/support/staff/ (support/permissions.py). View opens the queue, a
   * ticket, the summary, the assignee list and attachments -> CanViewSupportTickets.
   * Seeded to SUPPORT_TEAM, ADMINISTRATOR and OPERATION_MANAGER.
   */
  supportView: ["support.staff.view"],
  /** Public replies and internal notes; also makes a user assignable -> CanReplySupportTickets. */
  supportReply: ["support.staff.reply"],
  /**
   * Status, priority, category and assignee -> CanManageSupportTickets.
   * SUPPORT_TEAM and ADMINISTRATOR only; OPERATION_MANAGER can view and reply.
   */
  supportManage: ["support.staff.manage"],

  /**
   * GET /api/admin/categories/ -> CanManageAdminCategories.
   * There is no seeded read-only category permission. See KNOWN CONTRACT GAPS.
   */
  categoriesManage: ["categories.admin.manage"],

  /** GET /api/admin/customers/ -> CanViewAdminCustomers */
  customersView: ["customers.admin.view"],

  /**
   * /api/admin/reviews/<product|shop>/ (list, hide, unhide) -> CanModerateReviews.
   * One permission covers reading and moderating; seeded to ADMINISTRATOR and
   * SUPPORT_TEAM (SUPER_ADMINISTRATOR holds every code).
   */
  reviewsModerate: ["reviews.moderate"],

  /** GET /api/admin/users/ -> CanViewAdminUsers */
  usersView: ["users.admin.view"],
  /** Mutations on /api/admin/users/ -> CanManageAdminUsers */
  usersManage: ["users.admin.manage"],

  /** GET /api/admin/roles/ -> CanViewAdminRoles */
  rolesView: ["roles.admin.view"],
  /** Mutations on /api/admin/roles/ -> CanManageAdminRoles */
  rolesManage: ["roles.admin.manage"],

  /**
   * GET /api/admin/audit-logs/ -> CanViewAdminAuditLogs.
   * That class also accepts "audit.view" / "audit.admin.view", but NEITHER is
   * present in PERMISSIONS_DATA, so the only codes any real user can actually
   * hold are the two governance permissions below.
   */
  auditView: ["users.admin.view", "roles.admin.view"],

  /** Analytical/sales reporting permission (held by ADMIN, OPS, SALES, FINANCE, SUPPORT). */
  reportsView: ["reports.view"],

  /**
   * GET /api/points/sellers/<id>/ and /history/ -> CanViewPoints ('points.view').
   * Phase 1G-C. No wildcard-only entry here: rbac.services.has_user_permission
   * already treats a resolved '*' as pass-all, and hasAnyPermission separately
   * bypasses for is_superuser / permissions.includes('*').
   */
  pointsView: ["points.view"],
  /**
   * POST /api/points/sellers/<id>/adjust/ with action=CREDIT.
   * Mirrors points.permissions.POINT_ACTION_PERMISSIONS["CREDIT"] exactly:
   * 'points.add' OR 'points.adjust'. 'points.deduct' alone must NOT satisfy
   * this — see points.permissions.can_perform_point_action.
   */
  pointsCredit: ["points.add", "points.adjust"],
  /**
   * POST /api/points/sellers/<id>/adjust/ with action=DEBIT.
   * Mirrors POINT_ACTION_PERMISSIONS["DEBIT"]: 'points.deduct' OR
   * 'points.adjust'. 'points.add' alone must NOT satisfy this.
   */
  pointsDebit: ["points.deduct", "points.adjust"],

  // ---------------------------------------------------------------------------
  // DASHBOARD KPI GATES
  // ---------------------------------------------------------------------------
  // Metric visibility is deliberately broader than module visibility: a user may
  // legitimately read an aggregate without holding the module's management
  // permission. Each set below still names only seeded permission codes.

  /** Platform revenue is financial data — never shown on /admin access alone. */
  metricRevenue: ["payments.view", "reports.view"],
  /** Order volume aggregate. */
  metricOrders: ["orders.staff.view", "orders.view"],
  /** Shop counts and pending-approval backlog. */
  metricShops: ["shops.admin.manage", "shops.view"],
  /** Seller counts and pending-KYC backlog. */
  metricSellers: ["sellers.admin.manage", "sellers.view"],
  /** Catalog size aggregate. */
  metricProducts: ["products.admin.manage", "products.view"],
} satisfies Record<string, string[]>;

export type AdminPermissionKey = keyof typeof ADMIN_PERMISSIONS;

/**
 * Sidebar grouping. Order here is the render order.
 */
export const ADMIN_NAV_SECTIONS = [
  "Overview",
  "Marketplace",
  "Operations",
  "Administration",
] as const;

export type AdminNavSection = (typeof ADMIN_NAV_SECTIONS)[number];

export interface AdminNavItem {
  href: string;
  label: string;
  icon: string;
  section: AdminNavSection;
  /** Exact pathname match (used only by the dashboard root). */
  exact?: boolean;
  /**
   * OR-semantics: the item is visible when the user holds ANY of these.
   * Omitted entirely for items every management user may open.
   */
  requiredPermissions?: string[];
  /** Short description reused by the module placeholder and quick actions. */
  description?: string;
  badge?: string;
}

/**
 * The single source of truth for management navigation.
 * AdminSidebar renders it; the dashboard derives its quick actions from it, so
 * a permission is declared exactly once for both surfaces.
 */
export const ADMIN_NAV_ITEMS: AdminNavItem[] = [
  {
    href: "/admin",
    label: "Dashboard",
    icon: "dashboard",
    section: "Overview",
    exact: true,
    description: "Platform-wide operational overview.",
  },
  {
    href: "/admin/shops",
    label: "Shops",
    icon: "storefront",
    section: "Marketplace",
    requiredPermissions: ADMIN_PERMISSIONS.shopsView,
    description: "Approve and inspect multi-vendor storefronts.",
  },
  {
    href: "/admin/sellers",
    label: "Sellers",
    icon: "badge",
    section: "Marketplace",
    requiredPermissions: ADMIN_PERMISSIONS.sellersView,
    description: "Verify merchant accounts and KYC applications.",
  },
  {
    href: "/admin/products",
    label: "Products",
    icon: "inventory_2",
    section: "Marketplace",
    requiredPermissions: ADMIN_PERMISSIONS.productsView,
    description: "Review, approve, and publish catalog listings.",
  },
  {
    href: "/admin/categories",
    label: "Categories",
    icon: "category",
    section: "Marketplace",
    requiredPermissions: ADMIN_PERMISSIONS.categoriesManage,
    description: "Maintain catalog taxonomy and hero banners.",
  },
  {
    href: "/admin/reviews",
    label: "Reviews",
    icon: "reviews",
    section: "Marketplace",
    requiredPermissions: ADMIN_PERMISSIONS.reviewsModerate,
    description: "Hide or restore abusive product and shop reviews.",
  },
  {
    href: "/admin/orders",
    label: "Orders",
    icon: "receipt_long",
    section: "Operations",
    requiredPermissions: ADMIN_PERMISSIONS.ordersView,
    description: "Track fulfillment and order state transitions.",
  },
  {
    href: "/admin/payments",
    label: "Payments",
    icon: "payments",
    section: "Operations",
    requiredPermissions: ADMIN_PERMISSIONS.paymentsView,
    description: "Verify transactions and process refunds.",
  },
  {
    href: "/admin/support",
    label: "Support Tickets",
    icon: "support_agent",
    section: "Operations",
    requiredPermissions: ADMIN_PERMISSIONS.supportView,
    description: "Work the customer ticket queue: reply, assign and resolve.",
  },
  {
    href: "/admin/customers",
    label: "Customers",
    icon: "group",
    section: "Administration",
    requiredPermissions: ADMIN_PERMISSIONS.customersView,
    description: "Read-only customer profile directory.",
  },
  {
    href: "/admin/users",
    label: "Users",
    icon: "manage_accounts",
    section: "Administration",
    requiredPermissions: ADMIN_PERMISSIONS.usersView,
    description: "Manage management accounts and role assignments.",
  },
  {
    href: "/admin/roles",
    label: "Roles & Permissions",
    icon: "shield_person",
    section: "Administration",
    requiredPermissions: ADMIN_PERMISSIONS.rolesView,
    description: "Inspect RBAC role definitions and permission grants.",
  },
  {
    href: "/admin/audit-logs",
    label: "Audit Logs",
    icon: "history",
    section: "Administration",
    requiredPermissions: ADMIN_PERMISSIONS.auditView,
    description: "Immutable governance and state-transition history.",
  },
];

/**
 * Menu visibility rule: an item is shown only when the user holds at least one
 * of its required permissions. Items without requiredPermissions are visible to
 * every authenticated management user (AdminGuard already gated the console).
 */
export function canAccessNavItem(
  user: AuthUser | null | undefined,
  item: AdminNavItem
): boolean {
  if (!item.requiredPermissions || item.requiredPermissions.length === 0) return true;
  return hasAnyPermission(user, item.requiredPermissions);
}

export function getAccessibleNavItems(user: AuthUser | null | undefined): AdminNavItem[] {
  return ADMIN_NAV_ITEMS.filter((item) => canAccessNavItem(user, item));
}

/**
 * Accessible items bucketed into their sections, preserving ADMIN_NAV_SECTIONS
 * order and dropping any section left empty by the permission filter.
 */
export function getAccessibleNavSections(
  user: AuthUser | null | undefined
): Array<{ section: AdminNavSection; items: AdminNavItem[] }> {
  const accessible = getAccessibleNavItems(user);
  return ADMIN_NAV_SECTIONS.map((section) => ({
    section,
    items: accessible.filter((item) => item.section === section),
  })).filter((group) => group.items.length > 0);
}

/** Resolves the nav entry backing a route, used by the module placeholder page. */
export function findNavItemByHref(href: string): AdminNavItem | undefined {
  return ADMIN_NAV_ITEMS.find((item) => item.href === href);
}

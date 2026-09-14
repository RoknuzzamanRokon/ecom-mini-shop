/**
 * Shared Management UI foundation.
 *
 * Reusable, domain-agnostic building blocks for every admin module
 * (shops, sellers, products, orders, payments, categories, customers,
 * users, roles, audit logs). No business logic or API calls live here.
 */

export { default as AdminDataTable } from "./AdminDataTable";
export type {
  AdminDataTableProps,
  AdminTableColumn,
  AdminRowAction,
} from "./AdminDataTable";

export { default as AdminPagination } from "./AdminPagination";
export type { AdminPaginationProps } from "./AdminPagination";

export {
  default as AdminFilterBar,
  AdminSearchField,
  AdminSelectField,
  AdminDateField,
} from "./AdminFilterBar";
export type {
  AdminFilterBarProps,
  AdminSearchFieldProps,
  AdminSelectFieldProps,
  AdminDateFieldProps,
  AdminSelectOption,
} from "./AdminFilterBar";

export { default as AdminStatusBadge, getStatusTone } from "./AdminStatusBadge";
export type { AdminStatusBadgeProps, AdminStatusTone } from "./AdminStatusBadge";

export { default as AdminConfirmModal } from "./AdminConfirmModal";
export type { AdminConfirmModalProps } from "./AdminConfirmModal";

export { default as AdminStatCard } from "./AdminStatCard";
export type { AdminStatCardProps, AdminStatTone, AdminStatTrend } from "./AdminStatCard";

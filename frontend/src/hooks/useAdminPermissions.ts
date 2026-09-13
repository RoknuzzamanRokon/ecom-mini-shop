"use client";

import { useAuth } from "@/context/AuthContext";
import {
  hasManagementPermission,
  hasAnyPermission,
  hasAllPermissions,
  canViewShops,
  canManageShops,
  canApproveShops,
  canViewSellers,
  canManageSellers,
  canViewOrders,
  canUpdateOrders,
  canViewPayments,
  canVerifyPayments,
  canRefundPayments,
  canManageCategories,
  canViewAuditLogs,
  isManagementUser,
  getManagementRoleLabel,
} from "@/lib/admin-auth";

/**
 * Reusable React hook for permission checks and role labels in Management Console UI.
 * NOTE: Frontend checks are strictly for UX/UI visibility. The backend always enforces authorization.
 */
export function useAdminPermissions() {
  const { user } = useAuth();

  return {
    user,
    isManagementUser: isManagementUser(user),
    roleLabel: getManagementRoleLabel(user),
    hasPermission: (perm: string | string[]) => hasManagementPermission(user, perm),
    hasAnyPermission: (perms: string[]) => hasAnyPermission(user, perms),
    hasAllPermissions: (perms: string[]) => hasAllPermissions(user, perms),
    // Domain-specific UI guards
    canViewShops: canViewShops(user),
    canManageShops: canManageShops(user),
    canApproveShops: canApproveShops(user),
    canViewSellers: canViewSellers(user),
    canManageSellers: canManageSellers(user),
    canViewOrders: canViewOrders(user),
    canUpdateOrders: canUpdateOrders(user),
    canViewPayments: canViewPayments(user),
    canVerifyPayments: canVerifyPayments(user),
    canRefundPayments: canRefundPayments(user),
    canManageCategories: canManageCategories(user),
    canViewAuditLogs: canViewAuditLogs(user),
  };
}

import { AuthUser } from "./types";

export const MANAGEMENT_ROLES = [
  "SUPER_ADMINISTRATOR",
  "ADMINISTRATOR",
  "OPERATION_MANAGER",
  "SALES_MANAGER",
  "SALES_TEAM",
  "FINANCE",
  "SUPPORT_TEAM",
] as const;

export type ManagementRole = (typeof MANAGEMENT_ROLES)[number];

/**
 * Checks whether an authenticated user is eligible for management console access.
 * Must possess at least one management role, have is_superuser/is_staff,
 * or possess the 'admin:access' / '*' permission.
 */
export function isManagementUser(user: AuthUser | null | undefined): boolean {
  if (!user) return false;

  // Superuser or Django staff
  if (user.is_superuser || user.is_staff) return true;

  // Management RBAC role
  const userRoles = user.roles || [];
  const hasManagementRole = userRoles.some((role) =>
    MANAGEMENT_ROLES.includes(role as ManagementRole)
  );
  if (hasManagementRole) return true;

  // Direct management permission
  const permissions = user.permissions || [];
  if (
    permissions.includes("admin:access") ||
    permissions.includes("*") ||
    permissions.some((p) => p.endsWith(".admin.manage") || p.endsWith(".staff.view"))
  ) {
    return true;
  }

  return false;
}

/**
 * Checks whether a management user has a specific granular permission code.
 * Supports wildcards (*) and both dot-notation and colon-notation matching.
 */
export function hasManagementPermission(
  user: AuthUser | null | undefined,
  requiredPermission: string | string[]
): boolean {
  if (!user) return false;

  if (user.is_superuser) return true;

  const userPerms = user.permissions || [];
  if (userPerms.includes("*")) return true;

  const targets = Array.isArray(requiredPermission)
    ? requiredPermission
    : [requiredPermission];

  return targets.some((target) => {
    if (userPerms.includes(target)) return true;

    // Normalizing between dot and colon (e.g. shops.view <=> shop:read)
    const normalizedTarget = target.replace(/:/g, ".").toLowerCase();
    return userPerms.some((perm) => {
      const normalizedPerm = perm.replace(/:/g, ".").toLowerCase();
      return normalizedPerm === normalizedTarget;
    });
  });
}

/**
 * Formats user's primary management role for display in the admin header / badge.
 */
export function getManagementRoleLabel(user: AuthUser | null | undefined): string {
  if (!user) return "Guest";

  if (user.is_superuser) return "Super Administrator";

  const userRoles = user.roles || [];
  const matched = userRoles.find((r) =>
    MANAGEMENT_ROLES.includes(r as ManagementRole)
  );

  if (matched) {
    return matched
      .split("_")
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(" ");
  }

  if (user.is_staff) return "Staff Member";

  return "Management User";
}

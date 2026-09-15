/**
 * Admin Profile helpers.
 *
 * Pure functions over the ALREADY-authenticated user from /api/auth/me/.
 * Nothing here fetches, and nothing here is a security boundary: this module
 * only formats what the backend already told us about the current session.
 */

import type { AuthUser } from "@/lib/types";

/**
 * The wildcard token the backend actually emits.
 *
 * rbac/services.get_user_permissions() gives a superuser (or a holder of the
 * SUPER_ADMINISTRATOR role) EVERY seeded permission code AND adds "*" on top,
 * so a full-access user's array is the whole catalogue plus this token — not a
 * lone "*". "__ALL__" appears only inside seed_rbac.py's ROLE_PERMISSIONS_MAPPING
 * as an internal marker and is never serialized, so it is deliberately not
 * matched here.
 */
export const WILDCARD_PERMISSION = "*";

/** True when the session genuinely carries platform-wide access. */
export function hasFullPlatformAccess(user: AuthUser | null | undefined): boolean {
  if (!user) return false;
  return user.is_superuser || (user.permissions || []).includes(WILDCARD_PERMISSION);
}

export interface PermissionGroup {
  /** The raw domain segment, e.g. "products". */
  key: string;
  /** Display label derived from the segment, e.g. "Products". */
  label: string;
  /** The permission codes, verbatim and sorted. */
  codes: string[];
}

/**
 * Splits a permission code into its domain segment.
 *
 * Every code seeded in PERMISSIONS_DATA is dot-notation ("products.approve",
 * "orders.staff.view"), so the first segment is the domain. Colon-notation is
 * handled too because admin-auth.ts normalizes between the two forms, and a
 * code with neither separator falls into "other" rather than being dropped —
 * this must never silently hide a permission the user actually holds.
 */
function domainOf(code: string): string {
  const dot = code.indexOf(".");
  const colon = code.indexOf(":");
  const separators = [dot, colon].filter((index) => index > 0);
  if (separators.length === 0) return "other";
  return code.slice(0, Math.min(...separators)).toLowerCase();
}

function labelOf(domain: string): string {
  if (domain === "other") return "Other";
  return domain
    .split(/[_-]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

/**
 * Groups the user's real permission codes by domain for display.
 *
 * The wildcard is excluded: it is surfaced separately as "Full Platform
 * Access" rather than being listed as if it were an ordinary grant. Codes are
 * preserved exactly as the backend sent them — never renamed or prettified,
 * because the operator needs the literal string to reason about access.
 */
export function groupPermissions(permissions: string[]): PermissionGroup[] {
  const buckets = new Map<string, string[]>();

  for (const code of permissions) {
    if (code === WILDCARD_PERMISSION) continue;
    const domain = domainOf(code);
    const bucket = buckets.get(domain);
    if (bucket) bucket.push(code);
    else buckets.set(domain, [code]);
  }

  return Array.from(buckets.entries())
    .map(([key, codes]) => ({
      key,
      label: labelOf(key),
      codes: [...codes].sort((a, b) => a.localeCompare(b)),
    }))
    .sort((a, b) => {
      // "Other" last; everything else alphabetically.
      if (a.key === "other") return 1;
      if (b.key === "other") return -1;
      return a.label.localeCompare(b.label);
    });
}

/** The concrete grants, i.e. the permission count excluding the wildcard token. */
export function countConcretePermissions(permissions: string[]): number {
  return permissions.filter((code) => code !== WILDCARD_PERMISSION).length;
}

/**
 * Humanizes an RBAC role code for display: "OPERATION_MANAGER" -> "Operation
 * Manager". The raw code is always shown alongside it so the operator can still
 * see exactly what the backend assigned.
 */
export function formatRoleLabel(role: string): string {
  return role
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(" ");
}

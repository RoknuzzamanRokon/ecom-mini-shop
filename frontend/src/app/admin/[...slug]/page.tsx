"use client";

import React, { use } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { getManagementRoleLabel } from "@/lib/admin-auth";
import { canAccessNavItem, findNavItemByHref } from "@/lib/admin-navigation";
import { humanizeToken } from "@/lib/admin-format";

/**
 * Placeholder for management modules that are navigable but not yet implemented.
 *
 * Module titles, icons, descriptions, and required permissions are read from the
 * shared navigation model rather than duplicated here, so adding a nav entry
 * automatically gives that route a coherent placeholder and cannot drift out of
 * sync with the sidebar.
 */
export default function AdminModulePlaceholderPage({
  params,
}: {
  params: Promise<{ slug: string[] }>;
}) {
  const resolvedParams = use(params);
  const { user } = useAuth();

  const slugSegments = resolvedParams.slug ?? [];
  const rootSegment = slugSegments[0] ?? "";
  const navItem = findNavItemByHref(`/admin/${rootSegment}`);

  const roleLabel = getManagementRoleLabel(user);

  const title = navItem?.label ?? humanizeToken(rootSegment);
  const icon = navItem?.icon ?? "admin_panel_settings";
  const description = navItem?.description ?? "Platform management module.";

  /**
   * Page authorization is a separate concern from menu visibility: hiding a menu
   * entry does not stop someone typing the URL. This check keeps the two
   * consistent for known modules. The backend remains the final authority — no
   * data is fetched here, so nothing is exposed either way.
   */
  const isKnownModule = Boolean(navItem);
  const isAuthorized = navItem ? canAccessNavItem(user, navItem) : true;

  if (isKnownModule && !isAuthorized) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
        <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center">
          <div className="w-14 h-14 rounded-2xl bg-red-500/10 text-red-600 flex items-center justify-center mb-4">
            <span aria-hidden="true" className="material-symbols-outlined text-[32px]">
              shield_lock
            </span>
          </div>
          <h1 className="text-xl font-black text-ink tracking-tight mb-2">
            Insufficient Permissions
          </h1>
          <p className="text-xs text-ink-muted leading-relaxed mb-6">
            Your account does not hold the permissions required to open{" "}
            <strong className="text-ink">{title}</strong>. Contact a Super Administrator
            if you believe this is incorrect.
          </p>
          <Link
            href="/admin"
            className="w-full py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
          >
            Return to Overview
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
      <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center">
        <div className="w-14 h-14 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-4">
          <span aria-hidden="true" className="material-symbols-outlined text-[32px]">
            {icon}
          </span>
        </div>

        <span className="text-[10px] uppercase font-extrabold px-2 py-0.5 rounded-md bg-accent/15 text-accent border border-accent/20 mb-2">
          Foundation Ready
        </span>

        <h1 className="text-xl font-black text-ink tracking-tight mb-2">{title}</h1>

        <p className="text-xs text-ink-muted leading-relaxed mb-6">{description}</p>

        <dl className="w-full p-3 rounded-xl bg-surface-alt border border-line text-left text-xs space-y-1 mb-6">
          <div className="flex justify-between gap-3 text-[11px]">
            <dt className="text-ink-muted">Authenticated Operator:</dt>
            <dd className="font-bold text-ink truncate">{user?.username}</dd>
          </div>
          <div className="flex justify-between gap-3 text-[11px]">
            <dt className="text-ink-muted">Assigned Role:</dt>
            <dd className="font-bold text-primary truncate">{roleLabel}</dd>
          </div>
          <div className="flex justify-between gap-3 text-[11px]">
            <dt className="text-ink-muted">Module Status:</dt>
            <dd className="font-semibold text-emerald-600">Awaiting Implementation</dd>
          </div>
        </dl>

        <Link
          href="/admin"
          className="w-full py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-xs focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
        >
          Return to Overview
        </Link>
      </div>
    </div>
  );
}

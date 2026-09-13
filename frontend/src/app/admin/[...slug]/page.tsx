"use client";

import React, { use } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { getManagementRoleLabel } from "@/lib/admin-auth";

const MODULE_INFO: Record<
  string,
  { title: string; icon: string; description: string; permissions: string[] }
> = {
  shops: {
    title: "Shop Governance",
    icon: "storefront",
    description: "Approve, review, suspend, and monitor multi-vendor storefronts across the platform.",
    permissions: ["shops.admin.manage", "shops.view", "shop:read"],
  },
  sellers: {
    title: "Seller Management & KYC",
    icon: "badge",
    description: "Verify seller applications, inspect business documentation, and manage merchant accounts.",
    permissions: ["sellers.admin.manage", "sellers.view", "seller:read"],
  },
  orders: {
    title: "Platform Order Operations",
    icon: "receipt_long",
    description: "Inspect platform-wide customer orders, manage state transitions, tracking numbers, and fulfillment.",
    permissions: ["orders.staff.view", "orders.view", "order:read"],
  },
  payments: {
    title: "Financial Clearance & Payments",
    icon: "payments",
    description: "Verify offline transactions, reconcile customer payments, and process administrative refunds.",
    permissions: ["payments.view", "payments.verify", "payment:read"],
  },
  categories: {
    title: "Category Administration",
    icon: "category",
    description: "Create, reorder, update, and manage catalog taxonomy and hero banners.",
    permissions: ["categories.admin.manage", "category:read"],
  },
  "audit-logs": {
    title: "System Audit Logs",
    icon: "history",
    description: "Inspect immutable security logs, administrative decisions, and state transition histories.",
    permissions: ["audit:read", "audit.view"],
  },
};

export default function AdminModulePlaceholderPage({
  params,
}: {
  params: Promise<{ slug: string[] }>;
}) {
  const resolvedParams = use(params);
  const slugKey = resolvedParams.slug?.[0] || "";
  const info = MODULE_INFO[slugKey] || {
    title: slugKey
      .split("-")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" "),
    icon: "admin_panel_settings",
    description: "Platform management module.",
    permissions: [],
  };

  const { user } = useAuth();
  const roleLabel = getManagementRoleLabel(user);

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6">
      <div className="max-w-md w-full bg-surface rounded-2xl border border-line p-8 shadow-xs flex flex-col items-center">
        <div className="w-14 h-14 rounded-2xl bg-primary/10 text-primary flex items-center justify-center mb-4">
          <span className="material-symbols-outlined text-[32px]">{info.icon}</span>
        </div>

        <span className="text-[10px] uppercase font-extrabold px-2 py-0.5 rounded-md bg-accent/15 text-accent border border-accent/20 mb-2">
          Master Prompt Section 13 Milestone
        </span>

        <h1 className="text-xl font-black text-ink tracking-tight mb-2">
          {info.title}
        </h1>

        <p className="text-xs text-ink-muted leading-relaxed mb-6">
          {info.description}
        </p>

        <div className="w-full p-3 rounded-xl bg-surface-alt border border-line text-left text-xs space-y-1 mb-6">
          <div className="flex justify-between text-[11px]">
            <span className="text-ink-muted">Authenticated Operator:</span>
            <span className="font-bold text-ink">{user?.username}</span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-ink-muted">Assigned Role:</span>
            <span className="font-bold text-primary">{roleLabel}</span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-ink-muted">Module Status:</span>
            <span className="font-semibold text-emerald-600">Foundation Ready</span>
          </div>
        </div>

        <Link
          href="/admin"
          className="w-full py-2.5 px-4 rounded-xl bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-xs"
        >
          Return to Overview
        </Link>
      </div>
    </div>
  );
}

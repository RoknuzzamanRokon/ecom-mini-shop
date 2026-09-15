"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { getAuthToken } from "@/lib/auth";
import { AdminApiError, AdminCustomerDetail, getAdminCustomerDetail } from "@/lib/admin-api";
import { formatDate, formatDateTime, formatTaka, humanizeToken } from "@/lib/admin-format";
import { AdminStatusBadge } from "@/components/admin/shared";
import {
  CustomerAccessNotice,
  canViewAdminCustomers,
  customerDisplayName,
  genderLabel,
} from "../customerDirectory";

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-baseline gap-1 sm:gap-3 py-2 border-b border-line last:border-0 text-xs">
      <dt className="w-40 shrink-0 text-ink-muted font-semibold">{label}</dt>
      <dd className="text-ink break-words">{value}</dd>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading customer detail">
      <div className="h-6 w-40 bg-surface-alt animate-pulse rounded-md" />
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-3">
        <div className="h-6 w-64 bg-surface-alt animate-pulse rounded-md" />
        <div className="h-4 w-40 bg-surface-alt animate-pulse rounded-md" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {[0, 1].map((i) => (
          <div key={i} className="bg-surface rounded-2xl border border-line shadow-xs p-6 space-y-3">
            <div className="h-4 w-32 bg-surface-alt animate-pulse rounded-md" />
            <div className="h-3 w-full bg-surface-alt animate-pulse rounded-md" />
            <div className="h-3 w-3/4 bg-surface-alt animate-pulse rounded-md" />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AdminCustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const customerId = params.id;
  const { user } = useAuth();

  const canView = canViewAdminCustomers(user);

  const [customer, setCustomer] = useState<AdminCustomerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<AdminApiError | Error | null>(null);

  const fetchCustomer = useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      setLoading(false);
      setError(new AdminApiError("No active session token was found. Please sign in again.", 401));
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const data = await getAdminCustomerDetail(token, customerId);
      setCustomer(data);
    } catch (err) {
      setCustomer(null);
      setError(err instanceof Error ? err : new Error("Failed to load customer."));
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    if (!canView) return;
    fetchCustomer();
  }, [canView, fetchCustomer]);

  const backLink = (
    <Link
      href="/admin/customers"
      className="inline-flex items-center gap-1.5 text-xs font-bold text-ink-muted hover:text-ink transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary rounded-sm"
    >
      <span aria-hidden="true" className="material-symbols-outlined text-[18px]">
        arrow_back
      </span>
      Back to Customers
    </Link>
  );

  if (!canView) {
    return <CustomerAccessNotice />;
  }

  if (loading) {
    return (
      <div className="space-y-6">
        {backLink}
        <DetailSkeleton />
      </div>
    );
  }

  if (error || !customer) {
    const isNotFound = error instanceof AdminApiError && error.isNotFound;
    return (
      <div className="space-y-6">
        {backLink}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-8 flex flex-col items-center text-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-red-500/10 text-red-600 flex items-center justify-center">
            <span aria-hidden="true" className="material-symbols-outlined text-[26px]">
              {isNotFound ? "search_off" : "error"}
            </span>
          </div>
          <div>
            <p className="text-sm font-bold text-ink">
              {isNotFound ? "Customer not found" : "Unable to load customer"}
            </p>
            <p className="text-xs text-ink-muted mt-1 max-w-md">
              {isNotFound
                ? "This customer profile does not exist or may have been removed."
                : error?.message || "An unexpected error occurred."}
            </p>
          </div>
          {!isNotFound && (
            <button
              type="button"
              onClick={fetchCustomer}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary hover:bg-primary-hover text-on-primary text-xs font-bold transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                refresh
              </span>
              Try Again
            </button>
          )}
        </div>
      </div>
    );
  }

  const fullName = `${customer.first_name} ${customer.last_name}`.trim();

  return (
    <div className="space-y-6">
      {backLink}

      {/* Identity header */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl font-black text-ink tracking-tight break-words">
                {customerDisplayName(customer)}
              </h1>
              <AdminStatusBadge
                status={null}
                label={customer.is_active ? "Active" : "Inactive"}
                tone={customer.is_active ? "success" : "neutral"}
              />
            </div>
            <p className="text-xs text-ink-muted mt-1">
              @{customer.username}
              {customer.email ? ` · ${customer.email}` : ""}
            </p>
            <p className="text-[11px] text-ink-muted mt-2 flex items-center gap-1.5">
              <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
                receipt_long
              </span>
              {customer.orders_count} order{customer.orders_count === 1 ? "" : "s"}
            </p>
          </div>

          {/* No action buttons: this module is read-only by design and the
              backend exposes no customer mutation endpoint. */}
          <p className="text-[11px] font-bold uppercase tracking-wider text-ink-faint shrink-0">
            Read-only
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Identity */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Identity
          </h2>
          <dl>
            <InfoRow label="Display Name" value={customer.display_name || "—"} />
            <InfoRow label="Full Name" value={fullName || "—"} />
            <InfoRow label="Username" value={customer.username} />
            <InfoRow label="Gender" value={genderLabel(customer.gender)} />
            <InfoRow label="Date of Birth" value={formatDate(customer.date_of_birth)} />
          </dl>
        </div>

        {/* Contact */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Contact
          </h2>
          <dl>
            <InfoRow label="Email" value={customer.email || "—"} />
            <InfoRow label="Phone" value={customer.phone || "—"} />
          </dl>
        </div>

        {/* Account metadata */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Account
          </h2>
          <dl>
            <InfoRow label="Profile ID" value={`#${customer.id}`} />
            <InfoRow label="User ID" value={`#${customer.user_id}`} />
            <InfoRow
              label="Account Status"
              value={customer.is_active ? "Active" : "Inactive"}
            />
            <InfoRow label="Registered" value={formatDateTime(customer.date_joined)} />
            <InfoRow label="Profile Created" value={formatDateTime(customer.created_at)} />
            <InfoRow label="Profile Updated" value={formatDateTime(customer.updated_at)} />
          </dl>
          <p className="text-[11px] text-ink-faint mt-3">
            The customer admin serializers expose no password, hash, token or other credential,
            and no last-login timestamp.
          </p>
        </div>

        {/* Addresses */}
        <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
          <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
            Addresses ({customer.addresses.length})
          </h2>
          {customer.addresses.length === 0 ? (
            <p className="text-xs text-ink-muted">This customer has no saved addresses.</p>
          ) : (
            <ul className="space-y-3">
              {customer.addresses.map((address) => (
                <li
                  key={address.id}
                  className="rounded-xl border border-line p-3 text-xs bg-surface-alt/40"
                >
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="font-bold text-ink">{address.label || "Address"}</span>
                    {address.is_default && (
                      <AdminStatusBadge status={null} label="Default" tone="info" size="sm" />
                    )}
                  </div>
                  <p className="text-ink">{address.recipient_name}</p>
                  <p className="text-ink-muted">
                    {address.address_line_1}
                    {address.city ? `, ${address.city}` : ""}
                  </p>
                  {address.phone && <p className="text-ink-muted">{address.phone}</p>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Recent orders — the five the detail serializer already embeds. */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs p-6">
        <h2 className="text-sm font-extrabold text-ink uppercase tracking-wider mb-3">
          Recent Orders
        </h2>
        {customer.recent_orders.length === 0 ? (
          <p className="text-xs text-ink-muted">This customer has not placed any orders.</p>
        ) : (
          <>
            <div className="overflow-x-auto -mx-6 px-6">
              <table className="w-full min-w-[32rem] text-xs">
                <caption className="sr-only">
                  The five most recent orders placed by this customer
                </caption>
                <thead>
                  <tr className="text-left text-ink-muted border-b border-line">
                    <th scope="col" className="font-extrabold uppercase tracking-wider text-[10px] py-2 pr-3">
                      Order
                    </th>
                    <th scope="col" className="font-extrabold uppercase tracking-wider text-[10px] py-2 pr-3">
                      Status
                    </th>
                    <th scope="col" className="font-extrabold uppercase tracking-wider text-[10px] py-2 pr-3 text-right">
                      Total
                    </th>
                    <th scope="col" className="font-extrabold uppercase tracking-wider text-[10px] py-2 text-right">
                      Placed
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {customer.recent_orders.map((order) => (
                    <tr key={order.id} className="border-b border-line last:border-0">
                      <td className="py-2.5 pr-3 font-mono font-bold text-ink">
                        {order.order_number}
                      </td>
                      <td className="py-2.5 pr-3">
                        <AdminStatusBadge
                          status={order.status}
                          label={humanizeToken(order.status)}
                          size="sm"
                        />
                      </td>
                      <td className="py-2.5 pr-3 text-right text-ink">
                        {formatTaka(order.total_amount)}
                      </td>
                      <td className="py-2.5 text-right text-ink-muted">
                        {formatDate(order.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {customer.orders_count > customer.recent_orders.length && (
              <p className="text-[11px] text-ink-faint mt-3">
                Showing the {customer.recent_orders.length} most recent of{" "}
                {customer.orders_count} orders — the detail endpoint returns no more than five.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

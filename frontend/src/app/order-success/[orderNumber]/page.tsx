"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import StorefrontChrome from "@/components/layout/StorefrontChrome";
import Footer from "@/components/layout/Footer";
import { RouteErrorState, RouteSpinner } from "@/components/feedback";
import { useAuth } from "@/context/AuthContext";
import { Order } from "@/lib/types";
import { getOrderDetail } from "@/lib/api";
import { getAuthToken } from "@/lib/auth";

/** What the order lookup found, for one orderNumber and attempt. */
type Lookup =
  | { key: string; kind: "found"; order: Order }
  | { key: string; kind: "missing" }
  | { key: string; kind: "failed" };

/**
 * Confirms an order only once the order has been read back from this
 * customer's account. An unknown number, someone else's order or a failed
 * read used to show "Order Confirmed" all the same (BUG-089).
 */
export default function OrderSuccessPage() {
  const params = useParams();
  const orderNumber = params?.orderNumber as string;
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const [attempt, setAttempt] = useState(0);
  const [lookup, setLookup] = useState<Lookup | null>(null);
  const key = `${orderNumber}|${attempt}`;

  useEffect(() => {
    if (!orderNumber || authLoading || !isAuthenticated) return;
    let cancelled = false;
    getOrderDetail(orderNumber, getAuthToken())
      .then((order) => {
        if (!cancelled) setLookup(order ? { key, kind: "found", order } : { key, kind: "missing" });
      })
      .catch(() => {
        if (!cancelled) setLookup({ key, kind: "failed" });
      });
    return () => {
      cancelled = true;
    };
  }, [orderNumber, authLoading, isAuthenticated, key]);

  // An answer for an earlier number or attempt is no answer for this one.
  const current = lookup?.key === key ? lookup : null;

  let body: React.ReactNode;
  if (authLoading || (isAuthenticated && !current)) {
    body = <RouteSpinner label="Loading your order…" />;
  } else if (!isAuthenticated) {
    body = (
      <Notice
        icon="lock"
        title="Sign in to see this order"
        text="Order details are shown only to the account that placed the order."
        href={`/login?next=${encodeURIComponent(`/order-success/${orderNumber}`)}`}
        label="Sign In"
      />
    );
  } else if (current?.kind === "missing") {
    body = (
      <Notice
        icon="search_off"
        title="Order not found"
        text={`There is no order ${orderNumber} in your account. Check the number, or find the order in your order history.`}
        href="/profile/orders"
        label="Order History"
      />
    );
  } else if (current?.kind === "failed") {
    body = (
      <RouteErrorState
        title="We couldn't load this order"
        description="This is usually temporary. Please try again, or find the order in your order history."
        onRetry={() => setAttempt((n) => n + 1)}
        fallbackHref="/profile/orders"
        fallbackLabel="Order History"
      />
    );
  } else if (current?.kind === "found") {
    body = <Confirmation order={current.order} />;
  }

  return (
    <div className="min-h-screen flex flex-col bg-page transition-colors duration-200">
      <StorefrontChrome />
      <main className="max-w-[720px] w-full mx-auto px-4 sm:px-6 py-12 flex-1 flex flex-col items-center justify-center text-center">
        {body}
      </main>
      <Footer />
    </div>
  );
}

function Notice({
  icon,
  title,
  text,
  href,
  label,
}: {
  icon: string;
  title: string;
  text: string;
  href: string;
  label: string;
}) {
  return (
    <>
      <div className="w-16 h-16 rounded-full bg-surface-alt border border-line flex items-center justify-center text-ink-muted mb-5">
        <span aria-hidden="true" className="material-symbols-outlined text-[32px]">
          {icon}
        </span>
      </div>
      <h1 className="text-2xl font-extrabold text-ink tracking-tight mb-2">{title}</h1>
      <p className="text-sm text-ink-body max-w-md mb-8">{text}</p>
      <div className="flex flex-col sm:flex-row gap-3">
        <Link
          href={href}
          className="inline-flex items-center justify-center bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-6 py-3 rounded-lg shadow-sm transition-colors"
        >
          {label}
        </Link>
        <Link
          href="/"
          className="inline-flex items-center justify-center border border-line text-ink hover:bg-surface-alt font-bold text-xs uppercase tracking-wider px-6 py-3 rounded-lg transition-colors"
        >
          Continue Shopping
        </Link>
      </div>
    </>
  );
}

function Confirmation({ order }: { order: Order }) {
  return (
    <>
      {/* Animated Checkmark Circle */}
      <div className="w-16 h-16 rounded-full bg-success/15 border-2 border-success flex items-center justify-center text-success mb-5 animate-in zoom-in-50 duration-300">
        <span aria-hidden="true" className="material-symbols-outlined text-[36px]">
          check
        </span>
      </div>

      <span className="text-xs uppercase font-bold tracking-widest text-primary">
        Order Confirmed
      </span>
      <h1 className="text-2xl sm:text-3xl font-extrabold text-ink tracking-tight mt-1 mb-2">
        Thank you for your order!
      </h1>
      <p className="text-sm text-ink-body max-w-md mb-8">
        We have received your order and are currently preparing it for delivery.
      </p>

      {/* Order Details Card */}
      <div className="w-full bg-surface rounded-xl border border-line p-6 shadow-sm text-left space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-line gap-2">
          <div>
            <span className="text-xs text-ink-muted">Order Number</span>
            <p className="text-base font-bold text-ink tracking-wide font-mono">{order.order_number}</p>
          </div>
          <span className="self-start sm:self-auto bg-primary/10 text-primary text-xs font-semibold px-3 py-1 rounded-full uppercase">
            {order.status}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs text-ink-body">
          <div>
            <span className="text-ink-muted block">Payment Method</span>
            <span className="font-semibold text-ink">Cash on Delivery</span>
          </div>
          <div>
            <span className="text-ink-muted block">Estimated Delivery</span>
            <span className="font-semibold text-ink">2 — 4 Business Days</span>
          </div>
          <div>
            <span className="text-ink-muted block">Recipient</span>
            <span className="font-semibold text-ink">{order.shipping_recipient_name || order.customer_name}</span>
          </div>
          <div>
            <span className="text-ink-muted block">Total Amount</span>
            <span className="font-bold text-primary">৳{order.total_amount}</span>
          </div>
        </div>
      </div>

      {/* Navigation Action */}
      <div className="mt-8 flex flex-col sm:flex-row gap-4">
        <Link
          href="/"
          className="inline-flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-8 py-3 rounded-lg shadow-sm transition-all cursor-pointer"
        >
          <span>Continue Shopping</span>
          <span aria-hidden="true" className="material-symbols-outlined text-[16px]">
            arrow_forward
          </span>
        </Link>
      </div>
    </>
  );
}

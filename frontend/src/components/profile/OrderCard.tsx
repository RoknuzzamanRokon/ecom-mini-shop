"use client";

import React from "react";
import Link from "next/link";
import { Order } from "@/lib/types";

export const ACTIVE_STATUSES = ["PENDING", "CONFIRMED", "PROCESSING", "SHIPPED"];
const TRACK_STEPS = ["PENDING", "CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED"];

const STATUS_STYLES: Record<string, string> = {
  PENDING: "bg-warning/15 text-warning",
  CONFIRMED: "bg-primary/10 text-primary",
  PROCESSING: "bg-primary/10 text-primary",
  SHIPPED: "bg-primary/10 text-primary",
  DELIVERED: "bg-success/15 text-success",
  CANCELLED: "bg-accent/10 text-accent",
};

function formatDate(value: string) {
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function OrderCard({
  order,
  showTracker = false,
}: {
  order: Order;
  showTracker?: boolean;
}) {
  const status = (order.status || "").toUpperCase();
  const currentStep = TRACK_STEPS.indexOf(status);
  const isCancelled = status === "CANCELLED";

  return (
    <div className="bg-surface rounded-2xl border border-line shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-line">
        <div className="min-w-0">
          <p className="text-sm font-bold text-ink font-mono truncate">
            {order.order_number}
          </p>
          <p className="text-xs text-ink-muted">
            Placed {formatDate(order.created_at)}
            {order.total_items_count ? ` · ${order.total_items_count} item(s)` : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm font-bold text-primary">৳{order.total_amount}</span>
          <span
            className={`text-[11px] font-bold uppercase tracking-wide px-3 py-1 rounded-full ${
              STATUS_STYLES[status] || "bg-surface-alt text-ink-body"
            }`}
          >
            {status || "UNKNOWN"}
          </span>
        </div>
      </div>

      {/* Tracker */}
      {showTracker && !isCancelled && (
        <div className="px-5 py-4 border-b border-line">
          <div className="flex items-center">
            {TRACK_STEPS.map((step, index) => {
              const reached = currentStep >= index;
              return (
                <React.Fragment key={step}>
                  <div className="flex flex-col items-center gap-1 shrink-0">
                    <div
                      className={`w-7 h-7 rounded-full flex items-center justify-center border-2 transition-colors ${
                        reached
                          ? "bg-primary border-primary text-on-primary"
                          : "bg-surface border-line text-ink-muted"
                      }`}
                    >
                      <span className="material-symbols-outlined text-[15px]">
                        {reached ? "check" : "radio_button_unchecked"}
                      </span>
                    </div>
                    <span
                      className={`text-[10px] font-semibold uppercase tracking-wide ${
                        reached ? "text-primary" : "text-ink-muted"
                      }`}
                    >
                      {step}
                    </span>
                  </div>
                  {index < TRACK_STEPS.length - 1 && (
                    <div
                      className={`flex-1 h-0.5 mx-1 mb-4 rounded ${
                        currentStep > index ? "bg-primary" : "bg-line"
                      }`}
                    />
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>
      )}

      {/* Items */}
      <div className="px-5 py-4 flex flex-col gap-3">
        {order.items?.map((item) => (
          <div key={item.id} className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-lg bg-surface-alt border border-line shrink-0 flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px] text-ink-muted">
                inventory_2
              </span>
            </div>
            <div className="flex-1 min-w-0">
              {item.product_slug ? (
                <Link
                  href={`/product/${item.product_slug}`}
                  className="text-sm font-medium text-ink hover:text-primary transition-colors truncate block"
                >
                  {item.product_name}
                </Link>
              ) : (
                <span className="text-sm font-medium text-ink truncate block">
                  {item.product_name}
                </span>
              )}
              <p className="text-xs text-ink-muted">
                {item.shop_name ? `${item.shop_name} · ` : ""}Qty {item.quantity}
              </p>
            </div>
            <span className="text-sm font-semibold text-ink shrink-0">
              ৳{item.line_total ?? item.subtotal}
            </span>
          </div>
        ))}
      </div>

      {/* Shipping */}
      {(order.shipping_address_line_1 || order.address) && (
        <div className="px-5 py-3 bg-surface-alt/50 border-t border-line">
          <p className="flex items-start gap-1.5 text-xs text-ink-muted">
            <span className="material-symbols-outlined text-[14px] shrink-0 mt-px">
              location_on
            </span>
            <span className="truncate">
              {order.shipping_address_line_1 || order.address}
              {order.shipping_city || order.city
                ? `, ${order.shipping_city || order.city}`
                : ""}
            </span>
          </p>
        </div>
      )}
    </div>
  );
}

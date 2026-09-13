"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import { Order } from "@/lib/types";
import { getOrderDetail } from "@/lib/api";

export default function OrderSuccessPage() {
  const params = useParams();
  const orderNumber = params?.orderNumber as string;
  const [order, setOrder] = useState<Order | null>(null);

  useEffect(() => {
    async function load() {
      if (orderNumber) {
        const token =
          typeof window !== "undefined"
            ? localStorage.getItem("minishop_token") ||
              localStorage.getItem("token") ||
              localStorage.getItem("access_token")
            : null;
        const data = await getOrderDetail(orderNumber, token);
        if (data) setOrder(data);
      }
    }
    load();
  }, [orderNumber]);

  return (
    <div className="min-h-screen flex flex-col bg-page transition-colors duration-200">
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header />
        <Navbar />
      </div>

      <main className="max-w-[720px] mx-auto px-4 sm:px-6 py-12 flex-1 flex flex-col items-center justify-center text-center">
        {/* Animated Checkmark Circle */}
        <div className="w-16 h-16 rounded-full bg-success/15 border-2 border-success flex items-center justify-center text-success mb-5 animate-in zoom-in-50 duration-300">
          <span className="material-symbols-outlined text-[36px]">check</span>
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
              <p className="text-base font-bold text-ink tracking-wide font-mono">
                {orderNumber}
              </p>
            </div>
            <span className="self-start sm:self-auto bg-primary/10 text-primary text-xs font-semibold px-3 py-1 rounded-full uppercase">
              {order ? order.status : "Pending Delivery"}
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
            {order && (
              <>
                <div>
                  <span className="text-ink-muted block">Recipient</span>
                  <span className="font-semibold text-ink">{order.customer_name}</span>
                </div>
                <div>
                  <span className="text-ink-muted block">Total Amount</span>
                  <span className="font-bold text-primary">৳{order.total_amount}</span>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Navigation Action */}
        <div className="mt-8 flex flex-col sm:flex-row gap-4">
          <Link
            href="/"
            className="inline-flex items-center justify-center gap-2 bg-primary hover:bg-primary-hover text-on-primary font-bold text-xs uppercase tracking-wider px-8 py-3 rounded-lg shadow-sm transition-all cursor-pointer"
          >
            <span>Continue Shopping</span>
            <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
          </Link>
        </div>
      </main>

      <Footer />
    </div>
  );
}

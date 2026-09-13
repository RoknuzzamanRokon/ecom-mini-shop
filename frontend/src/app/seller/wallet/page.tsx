"use client";

import React, { useState, useEffect, useCallback } from "react";
import { getSellerWallet, getSellerPointHistory } from "@/lib/api";
import { SellerWallet, PointTransaction } from "@/lib/types";

const TXN_TYPES = [
  "ALL",
  "PRODUCT_CREATION",
  "ADMIN_CREDIT",
  "ADMIN_DEBIT",
  "BONUS",
  "REFUND",
  "ADJUSTMENT",
];

export default function SellerWalletPage() {
  const [wallet, setWallet] = useState<SellerWallet | null>(null);
  const [transactions, setTransactions] = useState<PointTransaction[]>([]);
  const [selectedType, setSelectedType] = useState<string>("ALL");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchWalletData = useCallback(async () => {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token") ||
          localStorage.getItem("token") ||
          localStorage.getItem("access_token")
        : null;
    if (!token) return;

    try {
      setLoading(true);
      setError(null);
      const [walletRes, historyRes] = await Promise.all([
        getSellerWallet(token),
        getSellerPointHistory(token, selectedType !== "ALL" ? selectedType : undefined),
      ]);
      setWallet(walletRes);
      setTransactions(historyRes);
    } catch (err: any) {
      setError(err.message || "Failed to load wallet data.");
    } finally {
      setLoading(false);
    }
  }, [selectedType]);

  useEffect(() => {
    fetchWalletData();
  }, [fetchWalletData]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">
          Wallet &amp; Points
        </h1>
        <p className="text-xs text-ink-muted mt-1">
          Review your points balance and itemized deduction ledger for product listings.
        </p>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-accent/10 border border-accent/30 text-accent text-xs font-semibold flex items-center gap-2">
          <span className="material-symbols-outlined text-[20px]">error</span>
          <span>{error}</span>
        </div>
      )}

      {/* Wallet Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-surface rounded-2xl border border-line p-6 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-ink-muted">
              Available Balance
            </p>
            <p className="text-3xl font-black text-ink mt-1">
              {loading ? "..." : `${wallet?.balance ?? 0}`}
            </p>
            <p className="text-[11px] text-ink-muted mt-0.5">Points currently active</p>
          </div>
          <div className="w-14 h-14 rounded-2xl bg-primary/10 text-primary flex items-center justify-center">
            <span className="material-symbols-outlined text-[32px]">
              account_balance_wallet
            </span>
          </div>
        </div>

        <div className="bg-surface rounded-2xl border border-line p-6 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-ink-muted">
              Total Points Credited
            </p>
            <p className="text-3xl font-black text-success mt-1">
              {loading ? "..." : `+${wallet?.total_earned ?? 0}`}
            </p>
            <p className="text-[11px] text-ink-muted mt-0.5">Lifetime bonus and allocations</p>
          </div>
          <div className="w-14 h-14 rounded-2xl bg-success/10 text-success flex items-center justify-center">
            <span className="material-symbols-outlined text-[32px]">trending_up</span>
          </div>
        </div>

        <div className="bg-surface rounded-2xl border border-line p-6 shadow-xs flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-ink-muted">
              Total Points Spent
            </p>
            <p className="text-3xl font-black text-ink mt-1">
              {loading ? "..." : `-${wallet?.total_spent ?? 0}`}
            </p>
            <p className="text-[11px] text-ink-muted mt-0.5">Consumed on product listings</p>
          </div>
          <div className="w-14 h-14 rounded-2xl bg-accent/10 text-accent flex items-center justify-center">
            <span className="material-symbols-outlined text-[32px]">shopping_cart_checkout</span>
          </div>
        </div>
      </div>

      {/* Platform Policy Notice */}
      <div className="p-4 rounded-xl bg-surface-alt/70 border border-line flex items-start gap-3 text-xs">
        <span className="material-symbols-outlined text-primary text-[22px] shrink-0">
          info
        </span>
        <div className="space-y-1 text-ink-body">
          <p className="font-bold text-ink">About MiniShop Seller Points</p>
          <p className="leading-relaxed">
            Points are required to list new products on the platform. Points are granted or adjusted by platform administrators. If you run out of points, contact the MiniShop support or administrator team to request an allocation top-up.
          </p>
        </div>
      </div>

      {/* Transaction History Section */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs overflow-hidden">
        <div className="p-4 sm:p-5 border-b border-line flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-bold text-ink">Transaction History</h2>
            <p className="text-xs text-ink-muted">Itemized audit ledger of point additions and deductions</p>
          </div>

          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
            {TXN_TYPES.map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => setSelectedType(type)}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors whitespace-nowrap cursor-pointer ${
                  selectedType === type
                    ? "bg-primary text-on-primary shadow-xs"
                    : "bg-surface-alt hover:bg-surface-sunken text-ink-body"
                }`}
              >
                {type}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="py-12 text-center text-xs text-ink-muted">Loading transaction history...</div>
        ) : transactions.length === 0 ? (
          <div className="py-12 text-center text-xs text-ink-muted">
            <span className="material-symbols-outlined text-[48px] opacity-40 mb-2 block">
              receipt
            </span>
            No point transactions found.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-ink">
              <thead className="bg-surface-alt/70 text-ink-muted uppercase tracking-wider font-bold border-b border-line text-[10px]">
                <tr>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">Amount</th>
                  <th className="py-3 px-4">Description</th>
                  <th className="py-3 px-4 text-right">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {transactions.map((txn) => {
                  const isDebit = txn.amount < 0 || txn.transaction_type === "PRODUCT_CREATION" || txn.transaction_type === "ADMIN_DEBIT";
                  return (
                    <tr key={txn.id} className="hover:bg-surface-alt/40 transition-colors">
                      <td className="py-3 px-4">
                        <span
                          className={`text-[10px] font-extrabold uppercase px-2 py-0.5 rounded ${
                            isDebit
                              ? "bg-accent/15 text-accent"
                              : "bg-success/15 text-success"
                          }`}
                        >
                          {txn.transaction_type}
                        </span>
                      </td>

                      <td className="py-3 px-4 font-black">
                        <span className={isDebit ? "text-accent" : "text-success"}>
                          {txn.amount > 0 ? `+${txn.amount}` : txn.amount} Points
                        </span>
                      </td>

                      <td className="py-3 px-4 text-ink-body">
                        {txn.description || "Point transaction"}
                      </td>

                      <td className="py-3 px-4 text-right text-ink-muted font-mono">
                        {new Date(txn.created_at).toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

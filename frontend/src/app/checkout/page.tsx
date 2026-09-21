"use client";

import React, { useState, useEffect } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Header from "@/components/layout/Header";
import Navbar from "@/components/layout/Navbar";
import Footer from "@/components/layout/Footer";
import { useCart } from "@/context/CartContext";
import { useAuth } from "@/context/AuthContext";
import {
  createOrder,
  formatImageUrl,
  getCustomerAddresses,
  createCustomerAddress,
} from "@/lib/api";
import { Address } from "@/lib/types";
import { getAuthToken } from "@/lib/auth";

export default function CheckoutPage() {
  const router = useRouter();
  const { items, totalAmount, clearCart } = useCart();
  const { user, isAuthenticated } = useAuth();

  const [addresses, setAddresses] = useState<Address[]>([]);
  const [loadingAddresses, setLoadingAddresses] = useState(false);
  const [selectedAddressId, setSelectedAddressId] = useState<number | null>(null);
  const [useManualAddress, setUseManualAddress] = useState(false);
  const [saveToProfile, setSaveToProfile] = useState(false);

  const [formData, setFormData] = useState({
    fullName: "",
    phone: "",
    address: "",
    city: "",
    postalCode: "",
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load customer's saved addresses when authenticated
  useEffect(() => {
    if (!isAuthenticated) {
      setAddresses([]);
      setSelectedAddressId(null);
      setUseManualAddress(true);
      return;
    }

    const token = getAuthToken();

    if (!token) return;

    setLoadingAddresses(true);
    getCustomerAddresses(token)
      .then((data) => {
        setAddresses(data);
        if (data.length > 0) {
          const defaultAddr = data.find((a) => a.is_default) || data[0];
          setSelectedAddressId(defaultAddr.id);
          setUseManualAddress(false);
        } else {
          setUseManualAddress(true);
        }
      })
      .catch((err) => {
        console.warn("Could not load saved addresses:", err);
        setUseManualAddress(true);
      })
      .finally(() => {
        setLoadingAddresses(false);
      });
  }, [isAuthenticated]);

  // Pre-fill user name if authenticated and manual form is blank
  useEffect(() => {
    if (isAuthenticated && user && !formData.fullName) {
      const userFullName =
        [user.first_name, user.last_name].filter(Boolean).join(" ") ||
        user.username ||
        "";
      setFormData((prev) => ({
        ...prev,
        fullName: userFullName,
      }));
    }
  }, [isAuthenticated, user, formData.fullName]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (items.length === 0) {
      setError("Your cart is empty.");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const token = getAuthToken();

      let orderPayload: Parameters<typeof createOrder>[0];

      // If user chose a saved address
      if (isAuthenticated && !useManualAddress && selectedAddressId) {
        const chosen = addresses.find((a) => a.id === selectedAddressId);
        const userFullName = user
          ? [user.first_name, user.last_name].filter(Boolean).join(" ") ||
            user.username
          : "Customer";
        orderPayload = {
          address_id: selectedAddressId,
          customer_name: chosen?.recipient_name || userFullName || "Customer",
          phone: chosen?.phone || "",
          address: chosen?.address_line_1 || "",
          city: chosen?.city || "",
          shipping_recipient_name: chosen?.recipient_name || userFullName || "",
          shipping_phone: chosen?.phone || "",
          shipping_address_line_1: chosen?.address_line_1 || "",
          shipping_city: chosen?.city || "",
          items: items
            .filter((i) => i.is_available !== false)
            .map((i) => ({
              product_id: i.product.id,
              quantity: i.quantity,
            })),
        };
      } else {
        // Manual shipping address validation
        if (!formData.fullName.trim()) {
          setError("Full name is required.");
          setSubmitting(false);
          return;
        }
        if (!formData.phone.trim()) {
          setError("Phone number is required.");
          setSubmitting(false);
          return;
        }
        if (!formData.city.trim()) {
          setError("City is required.");
          setSubmitting(false);
          return;
        }
        if (!formData.address.trim()) {
          setError("Delivery address is required.");
          setSubmitting(false);
          return;
        }

        // If authenticated and user opted into saving to profile
        if (isAuthenticated && token && saveToProfile) {
          try {
            await createCustomerAddress(
              {
                label: "Home",
                recipient_name: formData.fullName,
                phone: formData.phone,
                address_line_1: formData.address,
                city: formData.city,
                postal_code: formData.postalCode || "1000",
                country: "Bangladesh",
                is_default: addresses.length === 0,
              },
              token
            );
          } catch (addrErr) {
            console.warn("Could not save address to profile:", addrErr);
          }
        }

        orderPayload = {
          customer_name: formData.fullName,
          phone: formData.phone,
          address: formData.address,
          city: formData.city,
          shipping_recipient_name: formData.fullName,
          shipping_phone: formData.phone,
          shipping_address_line_1: formData.address,
          shipping_city: formData.city,
          items: items
            .filter((i) => i.is_available !== false)
            .map((i) => ({
              product_id: i.product.id,
              quantity: i.quantity,
            })),
        };
      }

      const order = await createOrder(orderPayload, token);

      clearCart();
      router.push(`/order-success/${order.order_number}`);
    } catch (err: any) {
      console.error("Order submission failed:", err);
      setError(
        err?.message ||
          "Failed to submit order. Please verify your details and try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  if (items.length === 0) {
    return (
      <div className="min-h-screen flex flex-col bg-page">
        <div className="sticky top-0 z-40 w-full shadow-sm">
          <Header />
          <Navbar />
        </div>
        <main className="max-w-[1360px] mx-auto px-4 sm:px-6 py-12 flex-1 flex flex-col items-center justify-center text-center">
          <span className="material-symbols-outlined text-[64px] text-ink-muted/40 mb-3">
            shopping_cart
          </span>
          <h2 className="text-xl font-bold text-ink">Your cart is empty</h2>
          <p className="text-sm text-ink-body mt-1">Please add some items before checking out.</p>
          <Link
            href="/"
            className="mt-4 bg-primary hover:bg-primary-hover text-on-primary px-6 py-2.5 rounded font-bold text-xs uppercase"
          >
            Start Shopping
          </Link>
        </main>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col bg-page transition-colors duration-200">
      <div className="sticky top-0 z-40 w-full shadow-sm">
        <Header />
        <Navbar />
      </div>

      <main className="max-w-[1360px] mx-auto px-4 sm:px-6 py-8 flex-1 w-full">
        <h1 className="text-2xl font-extrabold text-ink tracking-tight mb-6">
          Checkout
        </h1>

        {error && (
          <div className="mb-6 p-4 rounded-lg bg-danger/10 border border-danger/30 text-danger text-sm">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Left: Shipping Form */}
          <div className="lg:col-span-7 bg-surface rounded-xl border border-line p-6 shadow-sm">
            <h2 className="text-base font-bold uppercase tracking-wider text-ink mb-4 pb-2 border-b border-line">
              Shipping &amp; Delivery Details
            </h2>

            {/* Guest / Auth awareness banner */}
            {!isAuthenticated ? (
              <div className="mb-5 p-3.5 rounded-lg bg-surface-alt border border-line flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2 text-ink-body">
                  <span className="material-symbols-outlined text-[18px] text-accent">
                    account_circle
                  </span>
                  <span>
                    Already have an account?{" "}
                    <Link
                      href="/login?next=/checkout"
                      className="text-primary font-semibold hover:underline"
                    >
                      Sign in
                    </Link>{" "}
                    for saved addresses and faster checkout.
                  </span>
                </div>
                <span className="text-[11px] text-ink-muted">Guest checkout below</span>
              </div>
            ) : (
              <div className="mb-5 flex items-center justify-between p-3 rounded-lg bg-surface-alt border border-line text-xs">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[18px] text-success">
                    verified_user
                  </span>
                  <span className="text-ink-muted">
                    Logged in as <strong className="text-ink">{user?.email || user?.username}</strong>
                  </span>
                </div>
                <Link
                  href="/profile/addresses"
                  className="text-primary hover:underline font-semibold flex items-center gap-1"
                >
                  <span>Manage Address Book</span>
                  <span className="material-symbols-outlined text-[14px]">
                    arrow_forward
                  </span>
                </Link>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Authenticated User Saved Address Selector */}
              {isAuthenticated && addresses.length > 0 && (
                <div className="mb-6 pb-6 border-b border-line">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-ink">
                      Saved Delivery Addresses
                    </h3>
                    <button
                      type="button"
                      onClick={() => setUseManualAddress(!useManualAddress)}
                      className="text-xs font-semibold text-primary hover:underline cursor-pointer flex items-center gap-1"
                    >
                      <span className="material-symbols-outlined text-[16px]">
                        {useManualAddress ? "bookmark" : "edit_location_alt"}
                      </span>
                      <span>
                        {useManualAddress
                          ? "Use Saved Address"
                          : "+ Enter Different Address"}
                      </span>
                    </button>
                  </div>

                  {!useManualAddress && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {addresses.map((addr) => {
                        const isSelected = selectedAddressId === addr.id;
                        return (
                          <label
                            key={addr.id}
                            className={`p-3.5 rounded-lg border-2 cursor-pointer transition-all flex flex-col justify-between ${
                              isSelected
                                ? "border-primary bg-primary/5 shadow-xs"
                                : "border-line bg-surface hover:border-line-subtle"
                            }`}
                          >
                            <div>
                              <div className="flex items-center justify-between mb-1.5">
                                <div className="flex items-center gap-2">
                                  <input
                                    type="radio"
                                    name="selectedSavedAddress"
                                    checked={isSelected}
                                    onChange={() => setSelectedAddressId(addr.id)}
                                    className="text-primary focus:ring-primary h-4 w-4"
                                  />
                                  <span className="text-xs font-bold text-ink uppercase tracking-wide">
                                    {addr.label || "Address"}
                                  </span>
                                </div>
                                {addr.is_default && (
                                  <span className="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded bg-accent/15 text-accent">
                                    Default
                                  </span>
                                )}
                              </div>
                              <p className="text-xs font-bold text-ink">
                                {addr.recipient_name}
                              </p>
                              <p className="text-xs text-ink-muted mt-0.5">
                                {addr.phone}
                              </p>
                              <p className="text-xs text-ink-body mt-1.5 line-clamp-2">
                                {addr.address_line_1}
                                {addr.address_line_2 ? `, ${addr.address_line_2}` : ""}, {addr.city}
                                {addr.postal_code ? ` - ${addr.postal_code}` : ""}
                              </p>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Manual Shipping Fields */}
              {(!isAuthenticated || useManualAddress || addresses.length === 0) && (
                <div className="space-y-4">
                  {isAuthenticated && addresses.length === 0 && !loadingAddresses && (
                    <p className="text-xs text-ink-muted italic">
                      No saved addresses found. Enter your delivery details below:
                    </p>
                  )}

                  <div>
                    <label className="block text-xs font-semibold text-ink mb-1.5">
                      Full Name <span className="text-danger">*</span>
                    </label>
                    <input
                      type="text"
                      name="fullName"
                      required
                      value={formData.fullName}
                      onChange={handleChange}
                      placeholder="e.g. Rokon Uz Zaman"
                      className="w-full bg-surface border border-line rounded-md px-3.5 py-2 text-sm text-ink focus:outline-none focus:border-primary"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-ink mb-1.5">
                      Phone Number <span className="text-danger">*</span>
                    </label>
                    <input
                      type="tel"
                      name="phone"
                      required
                      value={formData.phone}
                      onChange={handleChange}
                      placeholder="e.g. +880 1712 345678"
                      className="w-full bg-surface border border-line rounded-md px-3.5 py-2 text-sm text-ink focus:outline-none focus:border-primary"
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-semibold text-ink mb-1.5">
                        City <span className="text-danger">*</span>
                      </label>
                      <input
                        type="text"
                        name="city"
                        required
                        value={formData.city}
                        onChange={handleChange}
                        placeholder="e.g. Dhaka"
                        className="w-full bg-surface border border-line rounded-md px-3.5 py-2 text-sm text-ink focus:outline-none focus:border-primary"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-semibold text-ink mb-1.5">
                        Postal Code
                      </label>
                      <input
                        type="text"
                        name="postalCode"
                        value={formData.postalCode}
                        onChange={handleChange}
                        placeholder="e.g. 1205"
                        className="w-full bg-surface border border-line rounded-md px-3.5 py-2 text-sm text-ink focus:outline-none focus:border-primary"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-ink mb-1.5">
                      Delivery Street Address <span className="text-danger">*</span>
                    </label>
                    <textarea
                      name="address"
                      rows={3}
                      required
                      value={formData.address}
                      onChange={handleChange}
                      placeholder="Street name, house/flat number, landmarks..."
                      className="w-full bg-surface border border-line rounded-md px-3.5 py-2 text-sm text-ink focus:outline-none focus:border-primary"
                    />
                  </div>

                  {isAuthenticated && (
                    <div className="flex items-center gap-2 pt-1">
                      <input
                        type="checkbox"
                        id="saveToProfile"
                        checked={saveToProfile}
                        onChange={(e) => setSaveToProfile(e.target.checked)}
                        className="rounded text-primary focus:ring-primary h-4 w-4"
                      />
                      <label
                        htmlFor="saveToProfile"
                        className="text-xs text-ink-body cursor-pointer select-none"
                      >
                        Save this address to my profile address book
                      </label>
                    </div>
                  )}
                </div>
              )}

              {/* Payment Method */}
              <div className="pt-4 border-t border-line">
                <h3 className="text-xs font-bold uppercase tracking-wider text-ink mb-3">
                  Payment Method
                </h3>
                <div className="flex items-center gap-3 p-3.5 rounded-lg border-2 border-primary bg-surface-alt/60">
                  <input
                    type="radio"
                    id="cod"
                    name="payment"
                    defaultChecked
                    className="text-primary focus:ring-primary h-4 w-4"
                  />
                  <label htmlFor="cod" className="flex-1 cursor-pointer">
                    <span className="text-sm font-bold text-ink block">
                      Cash on Delivery (COD)
                    </span>
                    <span className="text-xs text-ink-muted">
                      Pay with cash when your package arrives at your doorstep.
                    </span>
                  </label>
                </div>
              </div>

              <button
                type="submit"
                disabled={submitting}
                className="w-full mt-6 bg-primary hover:bg-primary-hover disabled:opacity-50 text-on-primary font-bold text-sm uppercase tracking-wider py-3.5 rounded-lg shadow-sm transition-all flex items-center justify-center gap-2 cursor-pointer"
              >
                {submitting ? (
                  <span>Placing Order...</span>
                ) : (
                  <>
                    <span>Place Order (৳{totalAmount.toFixed(2)})</span>
                    <span className="material-symbols-outlined text-[18px]">
                      check_circle
                    </span>
                  </>
                )}
              </button>
            </form>
          </div>

          {/* Right: Order Summary */}
          <div className="lg:col-span-5 bg-surface rounded-xl border border-line p-6 shadow-sm flex flex-col justify-between">
            <div>
              <h2 className="text-base font-bold uppercase tracking-wider text-ink mb-4 pb-2 border-b border-line">
                Order Summary ({items.length} items)
              </h2>

              <div className="divide-y divide-line-subtle max-h-96 overflow-y-auto pr-1">
                {items.map(({ product, quantity, subtotal }) => {
                  const imgUrl = formatImageUrl(
                    product.image_url ||
                    (product.image ? product.image : "/placeholder.svg")
                  );

                  return (
                    <div key={product.id} className="py-3 flex gap-3 items-center">
                      <div className="relative w-14 h-14 rounded-md overflow-hidden bg-surface-alt shrink-0 border border-line">
                        <Image
                          src={imgUrl}
                          alt={product.name}
                          fill
                          className="object-cover"
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <h4 className="text-xs font-semibold text-ink truncate">
                          {product.name}
                        </h4>
                        <span className="text-[11px] text-ink-muted">
                          Qty: {quantity} × ৳{product.price}
                        </span>
                      </div>
                      <span className="text-xs font-bold text-ink">
                        ৳{subtotal.toFixed(2)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="pt-4 border-t border-line space-y-2 mt-6">
              <div className="flex justify-between text-xs text-ink-body">
                <span>Subtotal</span>
                <span>৳{totalAmount.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-xs text-ink-body">
                <span>Estimated Shipping</span>
                <span className="text-success font-semibold">FREE</span>
              </div>
              <div className="flex justify-between text-sm font-extrabold text-ink pt-2 border-t border-line">
                <span>Total Amount</span>
                <span className="text-primary text-base">
                  ৳{totalAmount.toFixed(2)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}

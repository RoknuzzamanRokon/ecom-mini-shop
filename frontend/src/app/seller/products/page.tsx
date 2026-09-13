"use client";

import React, { useState, useEffect, useCallback } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  getSellerProducts,
  getSellerShops,
  getCategories,
  createSellerProduct,
  updateSellerProduct,
  deleteSellerProduct,
  formatImageUrl,
} from "@/lib/api";
import { Product, SellerShop, Category } from "@/lib/types";

export default function SellerProductsPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [loading, setLoading] = useState<boolean>(true);

  // Filters
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [selectedShopId, setSelectedShopId] = useState<string>("");
  const [selectedCategory, setSelectedCategory] = useState<string>("");

  // Metadata for dropdowns
  const [shops, setShops] = useState<SellerShop[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);

  // Modals
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [deletingProduct, setDeletingProduct] = useState<Product | null>(null);
  const [submittingModal, setSubmittingModal] = useState(false);

  // Feedback notifications
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Form State
  const [formData, setFormData] = useState({
    name: "",
    shop_id: "",
    category_id: "",
    price: "",
    old_price: "",
    stock: "10",
    badge: "",
    description: "",
    is_active: true,
  });

  const fetchProductsList = useCallback(async () => {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token") ||
          localStorage.getItem("token") ||
          localStorage.getItem("access_token")
        : null;
    if (!token) return;

    try {
      setLoading(true);
      const params: Parameters<typeof getSellerProducts>[1] = {
        page,
        q: searchQuery || undefined,
        shop_id: selectedShopId ? parseInt(selectedShopId) : undefined,
        category: selectedCategory || undefined,
      };
      const res = await getSellerProducts(token, params);
      setProducts(res.results);
      setTotalCount(res.count);
      setTotalPages(Math.ceil(res.count / 10) || 1);
    } catch (err: any) {
      setActionError(err.message || "Failed to load products.");
    } finally {
      setLoading(false);
    }
  }, [page, searchQuery, selectedShopId, selectedCategory]);

  useEffect(() => {
    fetchProductsList();
  }, [fetchProductsList]);

  // Load available shops and categories for form select menus
  useEffect(() => {
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token") ||
          localStorage.getItem("token") ||
          localStorage.getItem("access_token")
        : null;
    if (!token) return;

    getSellerShops(token).then((res) => setShops(res)).catch(() => {});
    getCategories().then((res) => setCategories(res)).catch(() => {});
  }, []);

  const handleOpenAdd = () => {
    setFormData({
      name: "",
      shop_id: shops.length > 0 ? shops[0].id.toString() : "",
      category_id: categories.length > 0 ? categories[0].id.toString() : "",
      price: "",
      old_price: "",
      stock: "10",
      badge: "",
      description: "",
      is_active: true,
    });
    setActionError(null);
    setActionSuccess(null);
    setIsAddOpen(true);
  };

  const handleOpenEdit = (p: Product) => {
    setEditingProduct(p);
    setFormData({
      name: p.name,
      shop_id: p.shop ? p.shop.id.toString() : "",
      category_id: p.category ? p.category.id.toString() : "",
      price: p.price.toString(),
      old_price: p.old_price ? p.old_price.toString() : "",
      stock: (p.stock ?? 0).toString(),
      badge: p.badge || "",
      description: p.description || "",
      is_active: p.is_active !== false,
    });
    setActionError(null);
    setActionSuccess(null);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token") ||
          localStorage.getItem("token") ||
          localStorage.getItem("access_token")
        : null;
    if (!token) return;

    if (!formData.shop_id) {
      setActionError("Please select a shop to associate with this product.");
      return;
    }
    if (!formData.category_id) {
      setActionError("Please select a category.");
      return;
    }

    setSubmittingModal(true);
    setActionError(null);

    try {
      await createSellerProduct(token, {
        name: formData.name,
        shop_id: parseInt(formData.shop_id),
        category_id: parseInt(formData.category_id),
        price: parseFloat(formData.price),
        old_price: formData.old_price ? parseFloat(formData.old_price) : null,
        stock: parseInt(formData.stock) || 0,
        badge: formData.badge || undefined,
        description: formData.description,
      });

      setActionSuccess(`Product "${formData.name}" created successfully.`);
      setIsAddOpen(false);
      await fetchProductsList();
    } catch (err: any) {
      setActionError(
        err.message || "Failed to create product. Check point balance and permissions."
      );
    } finally {
      setSubmittingModal(false);
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingProduct) return;
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token") ||
          localStorage.getItem("token") ||
          localStorage.getItem("access_token")
        : null;
    if (!token) return;

    setSubmittingModal(true);
    setActionError(null);

    try {
      await updateSellerProduct(token, editingProduct.id, {
        name: formData.name,
        price: parseFloat(formData.price),
        old_price: formData.old_price ? parseFloat(formData.old_price) : null,
        stock: parseInt(formData.stock) || 0,
        badge: formData.badge,
        description: formData.description,
        is_active: formData.is_active,
      });

      setActionSuccess(`Product "${formData.name}" updated successfully.`);
      setEditingProduct(null);
      await fetchProductsList();
    } catch (err: any) {
      setActionError(err.message || "Failed to update product.");
    } finally {
      setSubmittingModal(false);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deletingProduct) return;
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("minishop_token") ||
          localStorage.getItem("token") ||
          localStorage.getItem("access_token")
        : null;
    if (!token) return;

    setSubmittingModal(true);
    try {
      await deleteSellerProduct(token, deletingProduct.id);
      setActionSuccess(`Product "${deletingProduct.name}" deleted.`);
      setDeletingProduct(null);
      await fetchProductsList();
    } catch (err: any) {
      setActionError(err.message || "Failed to delete product.");
    } finally {
      setSubmittingModal(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-black text-ink tracking-tight">
            Product Catalog
          </h1>
          <p className="text-xs text-ink-muted mt-1">
            Manage your listings, prices, stock levels, and store visibility.
          </p>
        </div>

        <div>
          <button
            type="button"
            onClick={handleOpenAdd}
            disabled={shops.length === 0}
            className="px-4 py-2.5 rounded-lg bg-primary hover:bg-primary-hover disabled:opacity-50 text-on-primary font-bold text-xs uppercase tracking-wider transition-colors shadow-sm flex items-center gap-2 cursor-pointer disabled:cursor-not-allowed"
          >
            <span className="material-symbols-outlined text-[18px]">add_box</span>
            <span>Add New Product</span>
          </button>
        </div>
      </div>

      {shops.length === 0 && (
        <div className="p-3.5 rounded-xl bg-accent/10 border border-accent/20 text-accent text-xs flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px] shrink-0">warning</span>
          <span>
            You must have at least one registered shop before creating products.{" "}
            <Link href="/seller/shops" className="underline font-bold">
              Register a shop here
            </Link>
            .
          </span>
        </div>
      )}

      {actionSuccess && (
        <div className="p-4 rounded-xl bg-success/10 border border-success/30 text-success text-xs font-semibold flex items-center gap-2">
          <span className="material-symbols-outlined text-[20px]">check_circle</span>
          <span>{actionSuccess}</span>
        </div>
      )}

      {actionError && (
        <div className="p-4 rounded-xl bg-accent/10 border border-accent/30 text-accent text-xs font-semibold flex items-center gap-2">
          <span className="material-symbols-outlined text-[20px]">error</span>
          <span>{actionError}</span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="bg-surface rounded-xl border border-line p-4 shadow-xs grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            placeholder="Search by product name..."
            className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
          />
        </div>

        <div>
          <select
            value={selectedShopId}
            onChange={(e) => {
              setSelectedShopId(e.target.value);
              setPage(1);
            }}
            className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
          >
            <option value="">All My Shops</option>
            {shops.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <select
            value={selectedCategory}
            onChange={(e) => {
              setSelectedCategory(e.target.value);
              setPage(1);
            }}
            className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
          >
            <option value="">All Categories</option>
            {categories.map((c) => (
              <option key={c.id} value={c.slug}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Products Table */}
      <div className="bg-surface rounded-2xl border border-line shadow-xs overflow-hidden">
        {loading ? (
          <div className="py-12 text-center text-xs text-ink-muted">Loading products...</div>
        ) : products.length === 0 ? (
          <div className="py-12 text-center text-xs text-ink-muted">
            <span className="material-symbols-outlined text-[48px] opacity-40 mb-2 block">
              inventory_2
            </span>
            No products found matching your criteria.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-ink">
              <thead className="bg-surface-alt/70 text-ink-muted uppercase tracking-wider font-bold border-b border-line text-[10px]">
                <tr>
                  <th className="py-3 px-4">Product</th>
                  <th className="py-3 px-4">Shop</th>
                  <th className="py-3 px-4">Category</th>
                  <th className="py-3 px-4">Price</th>
                  <th className="py-3 px-4">Stock</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {products.map((p) => {
                  const imgUrl = formatImageUrl(
                    p.image_url || (p.image ? p.image : "/placeholder.svg")
                  );
                  return (
                    <tr key={p.id} className="hover:bg-surface-alt/40 transition-colors">
                      <td className="py-3 px-4 flex items-center gap-3">
                        <div className="w-10 h-10 rounded-lg overflow-hidden bg-surface-alt border border-line shrink-0 relative">
                          <Image
                            src={imgUrl}
                            alt={p.name}
                            fill
                            className="object-cover"
                          />
                        </div>
                        <div className="min-w-0">
                          <p className="font-bold text-ink truncate max-w-[200px] sm:max-w-xs">
                            {p.name}
                          </p>
                          {p.badge && (
                            <span className="inline-block text-[9px] uppercase font-extrabold px-1.5 py-0.2 rounded bg-accent/15 text-accent mt-0.5">
                              {p.badge}
                            </span>
                          )}
                        </div>
                      </td>

                      <td className="py-3 px-4 text-ink-body truncate max-w-[150px]">
                        {p.shop?.name || "Unassigned"}
                      </td>

                      <td className="py-3 px-4 text-ink-muted">
                        {p.category?.name || "General"}
                      </td>

                      <td className="py-3 px-4 font-bold text-ink">
                        ৳{p.price}
                        {p.old_price && (
                          <span className="line-through text-ink-muted text-[10px] ml-1">
                            ৳{p.old_price}
                          </span>
                        )}
                      </td>

                      <td className="py-3 px-4">
                        <span
                          className={`font-semibold ${
                            (p.stock ?? 0) > 0 ? "text-success" : "text-accent"
                          }`}
                        >
                          {p.stock ?? 0} units
                        </span>
                      </td>

                      <td className="py-3 px-4">
                        <span
                          className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded ${
                            p.is_active !== false
                              ? "bg-success/15 text-success"
                              : "bg-surface-alt text-ink-muted"
                          }`}
                        >
                          {p.is_active !== false ? "Active" : "Draft"}
                        </span>
                      </td>

                      <td className="py-3 px-4 text-right">
                        <div className="inline-flex items-center gap-1.5">
                          <button
                            type="button"
                            onClick={() => handleOpenEdit(p)}
                            className="p-1 text-ink-muted hover:text-primary rounded"
                            title="Edit"
                          >
                            <span className="material-symbols-outlined text-[18px]">edit</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeletingProduct(p)}
                            className="p-1 text-ink-muted hover:text-accent rounded"
                            title="Delete"
                          >
                            <span className="material-symbols-outlined text-[18px]">delete</span>
                          </button>
                          <Link
                            href={`/product/${p.slug}`}
                            target="_blank"
                            className="p-1 text-ink-muted hover:text-ink rounded"
                            title="View Public Page"
                          >
                            <span className="material-symbols-outlined text-[18px]">
                              open_in_new
                            </span>
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="p-4 border-t border-line flex items-center justify-between text-xs">
            <span className="text-ink-muted">
              Showing page {page} of {totalPages} ({totalCount} items)
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
                className="px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt disabled:opacity-40 text-ink font-semibold"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage(page + 1)}
                className="px-3 py-1.5 rounded-lg border border-line hover:bg-surface-alt disabled:opacity-40 text-ink font-semibold"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Add / Edit Product Modal */}
      {(isAddOpen || editingProduct) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <div className="bg-surface rounded-2xl border border-line shadow-2xl max-w-lg w-full p-6 space-y-4 animate-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between pb-3 border-b border-line">
              <h3 className="text-base font-bold text-ink">
                {isAddOpen ? "Add New Product" : `Edit: ${editingProduct?.name}`}
              </h3>
              <button
                type="button"
                onClick={() => {
                  setIsAddOpen(false);
                  setEditingProduct(null);
                }}
                className="text-ink-muted hover:text-ink p-1 rounded-md"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>

            {isAddOpen && (
              <div className="p-3 rounded-xl bg-primary/10 border border-primary/20 text-primary text-xs flex items-center gap-2">
                <span className="material-symbols-outlined text-[18px] shrink-0">
                  paid
                </span>
                <span>
                  <strong>Point Cost Notice:</strong> Listing a product will automatically deduct points from your seller wallet balance according to platform rules.
                </span>
              </div>
            )}

            <form
              onSubmit={isAddOpen ? handleCreateSubmit : handleEditSubmit}
              className="space-y-4"
            >
              <div>
                <label className="block text-xs font-semibold text-ink mb-1.5">
                  Product Name <span className="text-accent">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g. Wireless Noise-Cancelling Headphones"
                  className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                />
              </div>

              {isAddOpen && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-ink mb-1.5">
                      Shop <span className="text-accent">*</span>
                    </label>
                    <select
                      required
                      value={formData.shop_id}
                      onChange={(e) =>
                        setFormData({ ...formData, shop_id: e.target.value })
                      }
                      className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                    >
                      <option value="">Select Shop</option>
                      {shops.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-ink mb-1.5">
                      Category <span className="text-accent">*</span>
                    </label>
                    <select
                      required
                      value={formData.category_id}
                      onChange={(e) =>
                        setFormData({ ...formData, category_id: e.target.value })
                      }
                      className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                    >
                      <option value="">Select Category</option>
                      {categories.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-ink mb-1.5">
                    Price (৳) <span className="text-accent">*</span>
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={formData.price}
                    onChange={(e) => setFormData({ ...formData, price: e.target.value })}
                    placeholder="999.00"
                    className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1.5">
                    Old Price (৳)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={formData.old_price}
                    onChange={(e) => setFormData({ ...formData, old_price: e.target.value })}
                    placeholder="1299.00"
                    className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-ink mb-1.5">
                    Initial Stock <span className="text-accent">*</span>
                  </label>
                  <input
                    type="number"
                    required
                    min="0"
                    value={formData.stock}
                    onChange={(e) => setFormData({ ...formData, stock: e.target.value })}
                    placeholder="25"
                    className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink mb-1.5">
                  Promotional Badge
                </label>
                <input
                  type="text"
                  value={formData.badge}
                  onChange={(e) => setFormData({ ...formData, badge: e.target.value })}
                  placeholder="e.g. HOT DEAL, 20% OFF, NEW"
                  className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-ink mb-1.5">
                  Description <span className="text-accent">*</span>
                </label>
                <textarea
                  rows={3}
                  required
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Detailed product specifications..."
                  className="w-full px-3.5 py-2 rounded-lg border border-line bg-surface text-ink text-xs focus:outline-none focus:border-primary"
                />
              </div>

              {!isAddOpen && (
                <div className="flex items-center gap-2 pt-1">
                  <input
                    type="checkbox"
                    id="is_active"
                    checked={formData.is_active}
                    onChange={(e) =>
                      setFormData({ ...formData, is_active: e.target.checked })
                    }
                    className="rounded text-primary focus:ring-primary h-4 w-4"
                  />
                  <label htmlFor="is_active" className="text-xs text-ink cursor-pointer select-none">
                    Product is active and visible on store
                  </label>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-3 border-t border-line">
                <button
                  type="button"
                  onClick={() => {
                    setIsAddOpen(false);
                    setEditingProduct(null);
                  }}
                  className="px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-ink transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingModal}
                  className="px-5 py-2 rounded-lg bg-primary hover:bg-primary-hover disabled:opacity-50 text-on-primary font-bold text-xs uppercase tracking-wider shadow-sm transition-all flex items-center gap-2 cursor-pointer"
                >
                  {submittingModal
                    ? "Saving..."
                    : isAddOpen
                    ? "Create Product"
                    : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingProduct && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <div className="bg-surface rounded-2xl border border-line shadow-2xl max-w-sm w-full p-6 space-y-4 animate-in zoom-in-95 duration-150">
            <div className="flex items-center gap-3 text-accent">
              <span className="material-symbols-outlined text-[28px]">warning</span>
              <h3 className="text-base font-bold text-ink">Delete Product</h3>
            </div>
            <p className="text-xs text-ink-muted">
              Are you sure you want to delete <strong className="text-ink">{deletingProduct.name}</strong>? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2 pt-3 border-t border-line">
              <button
                type="button"
                onClick={() => setDeletingProduct(null)}
                className="px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-wider text-ink-muted hover:text-ink transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteConfirm}
                disabled={submittingModal}
                className="px-4 py-2 rounded-lg bg-accent hover:bg-accent/90 text-white font-bold text-xs uppercase tracking-wider transition-colors cursor-pointer"
              >
                {submittingModal ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

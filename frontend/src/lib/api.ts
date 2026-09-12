import { Category, PaginatedResponse, Product, ProductFilterParams, Order, CustomerProfile, Address, AddressInput, BackendCart, BackendCartItem, SellerOrder, ProductInventory, InventoryAdjustmentPayload, OrderCancelPayload, Payment, Refund, PaymentInitiatePayload, PaymentVerifyPayload, RefundCreatePayload, StaffOrderListItem, StaffOrderDetail, StaffOrderStatusUpdatePayload, StaffOrderFilterParams, Shop, AuthUser, RegisterPayload, RegisterResponse } from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001";

export function formatImageUrl(url?: string | null): string {
  if (!url) return "/placeholder.svg";

  // If it's a full URL
  if (url.startsWith("http://") || url.startsWith("https://")) {
    try {
      const parsed = new URL(url);
      // If it's a local Django media URL, convert to relative /media/ path so it proxies cleanly
      if (
        (parsed.hostname === "127.0.0.1" || parsed.hostname === "localhost") &&
        parsed.pathname.startsWith("/media/")
      ) {
        return parsed.pathname;
      }
    } catch {}
    return url;
  }

  // If it's already a relative /media path
  if (url.startsWith("/media/")) {
    return url;
  }
  if (url.startsWith("media/")) {
    return `/${url}`;
  }

  return url;
}

// Fallback demo data from main_ui.html for seamless dev/offline mode
export const DEMO_CATEGORIES: Category[] = [
  { id: 1, name: "Clothing", slug: "clothing", icon: "checkroom", is_active: true, products_count: 6 },
  { id: 2, name: "Electronics", slug: "electronics", icon: "devices", is_active: true, products_count: 5 },
  { id: 3, name: "Shoes", slug: "shoes", icon: "roller_skating", is_active: true, products_count: 3 },
  { id: 4, name: "Watches", slug: "watches", icon: "watch", is_active: true, products_count: 2 },
  { id: 5, name: "Jewellery", slug: "jewellery", icon: "diamond", is_active: true, products_count: 2 },
  { id: 6, name: "Health and Beauty", slug: "health-and-beauty", icon: "spa", is_active: true, products_count: 3 },
  { id: 7, name: "Kids and Babies", slug: "kids-and-babies", icon: "child_friendly", is_active: true, products_count: 1 },
  { id: 8, name: "Sports", slug: "sports", icon: "sports_soccer", is_active: true, products_count: 1 },
  { id: 9, name: "Home and Garden", slug: "home-and-garden", icon: "yard", is_active: true, products_count: 1 },
];

export const DEMO_PRODUCTS: Product[] = [
  {
    id: 1,
    name: "Custom Mechanical Keyboard",
    slug: "custom-mechanical-keyboard",
    category: DEMO_CATEGORIES[1],
    description: "Compact mechanical keyboard with hot-swappable switches and RGB backlighting.",
    price: "148.00",
    old_price: "180.00",
    image_url: "https://lh3.googleusercontent.com/aida-public/AB6AXuCS6sypzndN_SgiO4iIg0BMA6tbwvyxKryvnom3evr2SbTGUheIdO0LkdClavdRt4UC-5ts-io4yhKksBPexn3Sc479zwe8I8TKaacjyI-grGmeXlNUiHv0ABT92TR-pmTU6bza_cNXnuxNhveOkUiYwsH-ZjrnyExiL8_UcP8Bz8UioBysE6WU9Pz2EBRzKLpnGkc5A49mClPw0liVVRDYowaaLGyTZhn4fOqqhKyiJj8NWoca4cbauw",
    stock: 12,
    badge: "NEW",
    is_active: true,
    discount_percent: 18,
    savings_amount: "32.00",
    in_stock: true,
    created_at: "2025-01-01T00:00:00Z",
  },
  {
    id: 2,
    name: "Insulated Flask 750ml",
    slug: "insulated-flask-750ml",
    category: DEMO_CATEGORIES[8],
    description: "Double-walled vacuum insulated stainless steel water bottle keeps beverages cold for 24h.",
    price: "34.00",
    old_price: "45.00",
    image_url: "https://lh3.googleusercontent.com/aida-public/AB6AXuBJCdTq3ylJtUfYWOdZhrcKHWkNJ8DvWrSLzy3V1QzhwMetiCcNN7UNOaRkotdhqHzYQImmYKAVzWLBY-4xWJkDGVhM89MjV1DXbCaEb-SOvTU69ByLVRKsrzLFy36YeLjg8ti7GdNZTspBXWzYFdm5Ai8VC78qMxSRKQ1BYZ_2u6aktHNFgMOuHsyWN3EdcyqGGOwWxid1jLjHaCp0nRf7i6nqe8d6gNocJarz-dwRERUys0qtKlnV7Q",
    stock: 25,
    badge: "HOT",
    is_active: true,
    discount_percent: 24,
    savings_amount: "11.00",
    in_stock: true,
    created_at: "2025-01-02T00:00:00Z",
  },
  {
    id: 3,
    name: "Wireless Studio Headphones",
    slug: "wireless-studio-headphones",
    category: DEMO_CATEGORIES[1],
    description: "High-fidelity active noise-cancelling over-ear headphones with 40-hour battery life.",
    price: "220.00",
    old_price: "280.00",
    image_url: "https://lh3.googleusercontent.com/aida-public/AB6AXuD43564gcsa-DVPOlXi8rSh6pJZfr4jzVDyoymyBJGgrlHlh_yiGjJgNBfbb8wMoVwVCMqp13i8PnY_BqIlR9dhzMcYm2lijA4XDyNL_ymgTsIg1zMMTJrLhRb2p_-NDKNUfSUo8hllb_0QWdLYbFxuGTMMFRpgs85k2M1ZV-nB1HV0FdDcZHz3h4ahcsNAlWxr5pFqoDeNanPjqCZ8a8Y2-wdPG4NWnMQeAugN4KAqeMS9xWiM0qMIwQ",
    stock: 8,
    badge: "SALE",
    is_active: true,
    discount_percent: 21,
    savings_amount: "60.00",
    in_stock: true,
    created_at: "2025-01-03T00:00:00Z",
  },
  {
    id: 4,
    name: "Heavy Canvas Tote Bag",
    slug: "heavy-canvas-tote-bag",
    category: DEMO_CATEGORIES[0],
    description: "Durable 16oz cotton canvas tote with interior zipped pocket and reinforced handles.",
    price: "38.00",
    old_price: "50.00",
    image_url: "https://lh3.googleusercontent.com/aida-public/AB6AXuBbX5hWfItjxF759_1cLGpsW2phqfec7mVCz3Ic7t5-eTRD3THah4uOx05-aDWthMwFROgfp9-1VqMHJv9tQpmPTqwdl7yF1x6nn6y4CLLfNAh8uZzNSntJuqG2RzddGP5uWLjvxtSwpWbP4d50lt2Ri8lRH1hudYmwK5M3uQsjE9lOlx_6-iBPI9mdO-3gNrlR4rWKd53bOnSaEVNPkpmd9pGC7aSVt9l0UvmY6zz4vEAmwgIUjBfRDA",
    stock: 30,
    badge: "SALE",
    is_active: true,
    discount_percent: 24,
    savings_amount: "12.00",
    in_stock: true,
    created_at: "2025-01-04T00:00:00Z",
  },
  {
    id: 5,
    name: "Artisan Ceramic Mug",
    slug: "artisan-ceramic-mug",
    category: DEMO_CATEGORIES[8],
    description: "Wheel-thrown ceramic mug finished with a reactive stoneware glaze.",
    price: "26.00",
    old_price: "32.00",
    image_url: "https://lh3.googleusercontent.com/aida-public/AB6AXuCNBZDu8naCghbQgJYWtLFYrFvsII4DO8kpQ6jxvnuIFjKl2ywCY7p5h9oLOCZSLKPpTYT3yYycRP84xvsk0CubP7JRBFDQWYCy_9WJSBcFCIgmn8rvAh_PUu_53nB_Hc1I0wtk_gvbz8pIGAEvGHe8_jbaaqC-FYJFwx3HIY7HsDPWwkDmRzcxzY9MjWOY6bVQE_CQKyWuwpmR-hCso9lLpVmihrZorj1rm0W5su-RU8AlVCc9CaPZTQ",
    stock: 15,
    badge: "",
    is_active: true,
    discount_percent: 19,
    savings_amount: "6.00",
    in_stock: true,
    created_at: "2025-01-05T00:00:00Z",
  },
  {
    id: 6,
    name: "Task Desk Lamp",
    slug: "task-desk-lamp",
    category: DEMO_CATEGORIES[1],
    description: "Minimalist aluminum task lamp with touch dimmer and adjustable arm.",
    price: "89.00",
    old_price: "110.00",
    image_url: "https://lh3.googleusercontent.com/aida-public/AB6AXuCSVwxG52Hz7vhpEWeXPi5UJm20e7TlgZtWZbHszLI4cifI7F5uPYFbxEy59NIlYWIUigqpNJ2egy32cewdQGxDTxh8kV6bZ4Nf3w3s4jW6RW8lR0YCkvt9InRkL9IWpB-tIKgwd5-gZ27tVGExSWYVzPjmxSQkjJsfrPKBicGIs9IV5ytAnf5usn6PU6lCg0h8tocx1ADCxwNN9AUQJhhhCJ3zCib2ZZadlDXWecBkEWqBrt2ESFdvQQ",
    stock: 6,
    badge: "NEW",
    is_active: true,
    discount_percent: 19,
    savings_amount: "21.00",
    in_stock: true,
    created_at: "2025-01-06T00:00:00Z",
  },
  {
    id: 7,
    name: "Minimalist Cardholder",
    slug: "minimalist-cardholder",
    category: DEMO_CATEGORIES[0],
    description: "Full-grain vegetable-tanned leather cardholder with 4 card slots and central compartment.",
    price: "48.00",
    old_price: "60.00",
    image_url: "https://lh3.googleusercontent.com/aida-public/AB6AXuAEnFF8b8fZhwGjv9tsHeILb1K3cZr2rOm7PbLISfudcvD22tUhS35wxJEZvJldvsxrF--Nb_71ivUqag_7k2WSby8fUn3pVjJNG4MQL1d5hDM5KQFpt0IeKhMcM--YRcN0Ml95oqVpLBKziSceTMdpgNQhvJKMz0IoWP8exWUapdjFL2p2wBsLz5bqZQoVCFD2lyVE7CLQACvDa8MCjdPrY3mmZSwvJTz6cHVEkhwR7Vsq99P9hNNs-g",
    stock: 18,
    badge: "TOP",
    is_active: true,
    discount_percent: 20,
    savings_amount: "12.00",
    in_stock: true,
    created_at: "2025-01-07T00:00:00Z",
  },
  {
    id: 8,
    name: "Organic Heavyweight Tee",
    slug: "organic-heavyweight-tee",
    category: DEMO_CATEGORIES[0],
    description: "280gsm heavyweight combed organic cotton boxy fit tee.",
    price: "42.00",
    old_price: "55.00",
    image_url: "https://lh3.googleusercontent.com/aida-public/AB6AXuCuEZkhQLBvJUd2tKiM1YXdA3qHGqfoC1gOJ_5TqdJRzg7iRIg-0h3LZ4jopXxdRwV5H1_yryNObHo7djUIO6S0_42grlXucu8hJTcyp5f6kLXKCpKUjKQ6tOnNKNS5VwI5tTae84KBLGKSh7CqivtV3NBTcEuGPbaYT-2_QAScX9W6AxQ0O2MRjN8linJ33YO9g15jPy5se-Daf1ffgopzI-wyzmlJotp_Z75g1RUP_IeoZf0XJtiL6g",
    stock: 40,
    badge: "SALE",
    is_active: true,
    discount_percent: 24,
    savings_amount: "13.00",
    in_stock: true,
    created_at: "2025-01-08T00:00:00Z",
  },
];

export async function getCategories(): Promise<Category[]> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/categories/`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error("Failed to fetch categories");
    return await res.json();
  } catch (err) {
    console.warn("Using fallback demo categories:", err);
    return DEMO_CATEGORIES;
  }
}

export async function getProducts(params?: ProductFilterParams): Promise<PaginatedResponse<Product>> {
  const query = new URLSearchParams();
  if (params?.category && params.category !== "all") query.set("category", params.category);
  const searchQuery = params?.q || params?.search;
  if (searchQuery) query.set("q", searchQuery);
  if (params?.badge) query.set("badge", params.badge);
  if (params?.shop !== undefined && params?.shop !== null) query.set("shop", params.shop.toString());
  if (params?.min_price !== undefined && params?.min_price !== null) query.set("min_price", params.min_price.toString());
  if (params?.max_price !== undefined && params?.max_price !== null) query.set("max_price", params.max_price.toString());
  if (params?.ordering) query.set("ordering", params.ordering);
  if (params?.page) query.set("page", params.page.toString());
  if (params?.page_size) query.set("page_size", params.page_size.toString());

  try {
    const res = await fetch(`${API_BASE_URL}/api/products/?${query.toString()}`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error("Failed to fetch products");
    return await res.json();
  } catch (err) {
    console.warn("Using fallback demo products:", err);
    let filtered = [...DEMO_PRODUCTS];
    if (params?.category && params.category !== "all") {
      filtered = filtered.filter((p) => p.category?.slug === params.category);
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.description.toLowerCase().includes(q) ||
          p.category?.name.toLowerCase().includes(q)
      );
    }
    if (params?.badge) {
      filtered = filtered.filter((p) => p.badge?.toLowerCase() === params.badge?.toLowerCase());
    }
    return {
      count: filtered.length,
      next: null,
      previous: null,
      results: filtered,
    };
  }
}

export async function getProductDetail(slug: string): Promise<Product | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/products/${slug}/`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error("Product not found");
    return await res.json();
  } catch (err) {
    console.warn("Using fallback demo product for slug:", slug, err);
    const found = DEMO_PRODUCTS.find((p) => p.slug === slug);
    if (!found) return null;
    return {
      ...found,
      related_products: DEMO_PRODUCTS.filter((p) => p.slug !== slug).slice(0, 4),
    };
  }
}

export async function getProductById(id: number): Promise<Product | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/products/${id}/`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error("Product not found");
    return await res.json();
  } catch (err) {
    console.warn("Using fallback demo product for id:", id, err);
    const found = DEMO_PRODUCTS.find((p) => p.id === id);
    if (!found) return null;
    return {
      ...found,
      related_products: DEMO_PRODUCTS.filter((p) => p.id !== id).slice(0, 4),
    };
  }
}

export async function getShopDetail(slug: string): Promise<Shop | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/shops/${slug}/`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error("Shop not found");
    return await res.json();
  } catch (err) {
    console.warn("Failed to fetch shop detail for slug:", slug, err);
    return null;
  }
}

export async function getShops(params?: {
  page?: number;
  page_size?: number;
  search?: string;
}): Promise<PaginatedResponse<Shop>> {
  const query = new URLSearchParams();
  if (params?.search) query.set("search", params.search);
  if (params?.page) query.set("page", params.page.toString());
  if (params?.page_size) query.set("page_size", params.page_size.toString());

  try {
    const res = await fetch(`${API_BASE_URL}/api/shops/?${query.toString()}`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error("Failed to fetch shops");
    return await res.json();
  } catch (err) {
    console.warn("Failed to fetch shops list:", err);
    return { count: 0, next: null, previous: null, results: [] };
  }
}

export async function getHotDeal(): Promise<Product | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/hot-deals/`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error("Failed to fetch hot deal");
    return await res.json();
  } catch (err) {
    console.warn("Using fallback demo hot deal:", err);
    return DEMO_PRODUCTS[7]; // Organic Heavyweight Tee (49% off)
  }
}

export async function createOrder(
  data: {
    customer_name?: string;
    phone?: string;
    address?: string;
    city?: string;
    address_id?: number | null;
    shipping_recipient_name?: string;
    shipping_phone?: string;
    shipping_address_line_1?: string;
    shipping_city?: string;
    items?: { product_id: number; quantity: number }[];
  },
  token?: string | null
): Promise<Order> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE_URL}/api/orders/`, {
    method: "POST",
    headers,
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: "Error creating order" }));
    const msg = errorData.detail || errorData.cart || "Failed to submit order";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }

  return await res.json();
}

export async function getUserOrders(
  token: string,
  page: number = 1
): Promise<PaginatedResponse<Order>> {
  const res = await fetch(`${API_BASE_URL}/api/orders/?page=${page}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to fetch orders");
  }

  return await res.json();
}

export async function getOrderDetail(
  orderNumber: string,
  token?: string | null
): Promise<Order | null> {
  try {
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const res = await fetch(`${API_BASE_URL}/api/orders/${orderNumber}/`, {
      headers,
      cache: "no-store",
    });
    if (!res.ok) throw new Error("Order not found");
    return await res.json();
  } catch (err) {
    console.error("Failed to fetch order detail:", err);
    return null;
  }
}

export async function getSellerProducts(
  token: string,
  params?: { shop_id?: number; status?: string; category?: string; q?: string; page?: number }
): Promise<PaginatedResponse<Product>> {
  const query = new URLSearchParams();
  if (params?.shop_id) query.set("shop_id", params.shop_id.toString());
  if (params?.status) query.set("status", params.status);
  if (params?.category) query.set("category", params.category);
  if (params?.q) query.set("q", params.q);
  if (params?.page) query.set("page", params.page.toString());

  const res = await fetch(`${API_BASE_URL}/api/products/mine/?${query.toString()}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.error || "Failed to fetch seller products");
  }

  return await res.json();
}

export async function createSellerProduct(
  token: string,
  data: {
    name: string;
    category_id: number;
    shop_id: number;
    description: string;
    price: string | number;
    old_price?: string | number | null;
    stock?: number;
    badge?: string;
  }
): Promise<Product> {
  const res = await fetch(`${API_BASE_URL}/api/products/mine/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    if (res.status === 400 && errorData.required_points) {
      throw new Error(
        `Insufficient points: required ${errorData.required_points}, available ${errorData.available_points}`
      );
    }
    throw new Error(errorData.error || "Failed to create product");
  }

  return await res.json();
}

/**
 * Customer Profile & Address API Methods (Task 8)
 */
export async function getCustomerProfile(token: string): Promise<CustomerProfile> {
  const res = await fetch(`${API_BASE_URL}/api/profile/me/`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to fetch customer profile");
  }
  return await res.json();
}

export async function updateCustomerProfile(
  data: Partial<CustomerProfile>,
  token: string
): Promise<CustomerProfile> {
  const res = await fetch(`${API_BASE_URL}/api/profile/me/`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to update customer profile");
  }
  return await res.json();
}

export async function getCustomerAddresses(token: string): Promise<Address[]> {
  const res = await fetch(`${API_BASE_URL}/api/addresses/`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to fetch addresses");
  }
  return await res.json();
}

export async function createCustomerAddress(
  data: AddressInput,
  token: string
): Promise<Address> {
  const res = await fetch(`${API_BASE_URL}/api/addresses/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to create address");
  }
  return await res.json();
}

export async function updateCustomerAddress(
  id: number,
  data: Partial<AddressInput>,
  token: string
): Promise<Address> {
  const res = await fetch(`${API_BASE_URL}/api/addresses/${id}/`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to update address");
  }
  return await res.json();
}

export async function deleteCustomerAddress(id: number, token: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/addresses/${id}/`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to delete address");
  }
}

export async function setDefaultCustomerAddress(id: number, token: string): Promise<Address> {
  const res = await fetch(`${API_BASE_URL}/api/addresses/${id}/set-default/`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to set default address");
  }
  return await res.json();
}

export async function getCart(token: string): Promise<BackendCart> {
  const res = await fetch(`${API_BASE_URL}/api/cart/`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to fetch cart");
  }
  return await res.json();
}

export async function addToCartApi(
  productId: number,
  quantity: number,
  token: string
): Promise<BackendCart> {
  const res = await fetch(`${API_BASE_URL}/api/cart/items/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ product_id: productId, quantity }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.product_id || "Failed to add item to cart");
  }
  return await res.json();
}

export async function updateCartItemApi(
  itemId: number,
  quantity: number,
  token: string
): Promise<BackendCart> {
  const res = await fetch(`${API_BASE_URL}/api/cart/items/${itemId}/`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ quantity }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || errorData.quantity || "Failed to update cart item");
  }
  return await res.json();
}

export async function removeCartItemApi(
  itemId: number,
  token: string
): Promise<BackendCart> {
  const res = await fetch(`${API_BASE_URL}/api/cart/items/${itemId}/`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to remove item from cart");
  }
  return await res.json();
}

export async function clearCartApi(token: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/cart/`, {
    method: "DELETE",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to clear cart");
  }
}

export async function getSellerOrders(
  token: string,
  status?: string,
  page: number = 1
): Promise<PaginatedResponse<SellerOrder>> {
  const query = new URLSearchParams({ page: page.toString() });
  if (status) query.set("status", status);

  const res = await fetch(`${API_BASE_URL}/api/seller/orders/?${query.toString()}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to fetch seller orders");
  }

  return await res.json();
}

export async function getSellerOrderDetail(
  orderNumber: string,
  token: string
): Promise<SellerOrder> {
  const res = await fetch(`${API_BASE_URL}/api/seller/orders/${orderNumber}/`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to fetch seller order detail");
  }

  return await res.json();
}

export async function updateSellerOrderStatus(
  orderNumber: string,
  status: string,
  token: string,
  note?: string
): Promise<SellerOrder> {
  const res = await fetch(`${API_BASE_URL}/api/seller/orders/${orderNumber}/status/`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ status, note }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const msg = errorData.detail || errorData.order || errorData.status || "Failed to update order status";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }

  return await res.json();
}

export async function getSellerProductInventory(
  productId: number,
  token: string
): Promise<ProductInventory> {
  const res = await fetch(`${API_BASE_URL}/api/seller/inventory/${productId}/`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to fetch inventory record");
  }

  return await res.json();
}

export async function adjustSellerProductStock(
  productId: number,
  payload: InventoryAdjustmentPayload,
  token: string
): Promise<ProductInventory> {
  const res = await fetch(`${API_BASE_URL}/api/seller/inventory/${productId}/adjust/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const msg = errorData.detail || errorData.quantity || "Failed to adjust inventory stock";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }

  return await res.json();
}

export async function cancelCustomerOrder(
  orderNumber: string,
  token: string,
  reason?: string
): Promise<Order> {
  const res = await fetch(`${API_BASE_URL}/api/orders/${orderNumber}/cancel/`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ reason }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const msg = errorData.detail || errorData.order || "Failed to cancel order";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }

  return await res.json();
}

export async function getOrderPayment(orderNumber: string, token: string): Promise<Payment> {
  const res = await fetch(`${API_BASE_URL}/api/orders/${orderNumber}/payment/`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to fetch order payment");
  }
  return await res.json();
}

export async function initiateOrderPayment(
  orderNumber: string,
  payload: PaymentInitiatePayload,
  token: string
): Promise<Payment> {
  const res = await fetch(`${API_BASE_URL}/api/orders/${orderNumber}/payment/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const msg = errorData.detail || errorData.payment || "Failed to initiate payment";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return await res.json();
}

export async function getStaffPayments(
  token: string,
  params?: { status?: string; order_number?: string; page?: number }
): Promise<PaginatedResponse<Payment>> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.order_number) query.set("order_number", params.order_number);
  if (params?.page) query.set("page", params.page.toString());

  const res = await fetch(`${API_BASE_URL}/api/staff/payments/?${query.toString()}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) throw new Error("Failed to fetch staff payments");
  return await res.json();
}

export async function verifyStaffPayment(
  paymentId: number,
  payload: PaymentVerifyPayload,
  token: string
): Promise<Payment> {
  const res = await fetch(`${API_BASE_URL}/api/staff/payments/${paymentId}/verify/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to verify payment");
  }
  return await res.json();
}

export async function refundStaffPayment(
  paymentId: number,
  payload: RefundCreatePayload,
  token: string
): Promise<Refund> {
  const res = await fetch(`${API_BASE_URL}/api/staff/payments/${paymentId}/refund/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const msg = errorData.detail || errorData.amount || errorData.refund || "Failed to process refund";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return await res.json();
}

export async function getStaffOrders(
  token: string,
  params?: StaffOrderFilterParams
): Promise<PaginatedResponse<StaffOrderListItem>> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.payment_status) query.set("payment_status", params.payment_status);
  if (params?.seller_id) query.set("seller_id", params.seller_id.toString());
  if (params?.shop_id) query.set("shop_id", params.shop_id.toString());
  if (params?.search) query.set("search", params.search);
  if (params?.order_number) query.set("order_number", params.order_number);
  if (params?.start_date) query.set("start_date", params.start_date);
  if (params?.end_date) query.set("end_date", params.end_date);
  if (params?.created_after) query.set("created_after", params.created_after);
  if (params?.created_before) query.set("created_before", params.created_before);
  if (params?.page) query.set("page", params.page.toString());
  if (params?.page_size) query.set("page_size", params.page_size.toString());

  const res = await fetch(`${API_BASE_URL}/api/staff/orders/?${query.toString()}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to fetch staff orders");
  }
  return await res.json();
}

export async function getStaffOrderDetail(
  orderNumberOrId: string | number,
  token: string
): Promise<StaffOrderDetail> {
  const res = await fetch(`${API_BASE_URL}/api/staff/orders/${orderNumberOrId}/`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to fetch staff order details");
  }
  return await res.json();
}

export async function updateStaffOrderStatus(
  orderNumberOrId: string | number,
  payload: StaffOrderStatusUpdatePayload,
  token: string
): Promise<StaffOrderDetail> {
  const res = await fetch(`${API_BASE_URL}/api/staff/orders/${orderNumberOrId}/status/`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    const msg = errorData.detail || errorData.status || errorData.order || "Failed to update order status";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return await res.json();
}

/**
 * Authentication API Methods (Task 19)
 */

export async function loginUser(
  username: string,
  password: string
): Promise<{ access: string; refresh: string }> {
  const res = await fetch(`${API_BASE_URL}/api/auth/token/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ username, password }),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(
      errorData.detail || "Invalid credentials. Please try again."
    );
  }

  return await res.json();
}

export async function refreshAccessToken(
  refreshToken: string
): Promise<{ access: string; refresh: string }> {
  const res = await fetch(`${API_BASE_URL}/api/auth/token/refresh/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ refresh: refreshToken }),
  });

  if (!res.ok) {
    throw new Error("Token refresh failed");
  }

  return await res.json();
}

export async function getCurrentUser(token: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE_URL}/api/auth/me/`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(
      errorData.detail || "Failed to fetch current user"
    );
  }

  return await res.json();
}

export async function registerCustomer(
  payload: RegisterPayload
): Promise<RegisterResponse> {
  const res = await fetch(`${API_BASE_URL}/api/auth/register/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    if (typeof errorData === "object" && errorData !== null) {
      // Gather all field errors into a clean string
      const messages: string[] = [];
      for (const [key, value] of Object.entries(errorData)) {
        if (Array.isArray(value)) {
          messages.push(`${value.join(" ")}`);
        } else if (typeof value === "string") {
          messages.push(value);
        }
      }
      if (messages.length > 0) {
        throw new Error(messages.join(" "));
      }
    }
    throw new Error("Registration failed. Please check your information and try again.");
  }

  return await res.json();
}



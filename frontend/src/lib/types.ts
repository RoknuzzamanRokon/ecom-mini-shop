export interface Category {
  id: number;
  name: string;
  slug: string;
  icon?: string;
  is_active: boolean;
  products_count?: number;
  image_url?: string | null;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ProductFilterParams {
  category?: string;
  q?: string;
  search?: string;
  badge?: string;
  shop?: number | string;
  min_price?: number | string;
  max_price?: number | string;
  ordering?: string;
  page?: number;
  page_size?: number;
}

export interface ProductImage {
  id: number;
  image: string;
  image_url: string;
  order: number;
}

export interface Product {
  id: number;
  name: string;
  slug: string;
  category?: Category;
  description: string;
  price: string | number;
  old_price?: string | number | null;
  image?: string;
  image_url?: string | null;
  stock: number;
  badge?: string;
  is_active: boolean;
  status?: string;
  rejection_reason?: string;
  shop?: {
    id: number;
    name: string;
    slug: string;
    status?: string;
  } | null;
  discount_percent?: number;
  savings_amount?: string | number | null;
  in_stock: boolean;
  created_at: string;
  images?: ProductImage[];
  all_image_urls?: string[];
  related_products?: Product[];
}

export interface CartItem {
  id?: number;
  product: Product;
  quantity: number;
  subtotal: number;
  is_available?: boolean;
  unavailable_reason?: string;
}

export interface OrderItem {
  id: number;
  product?: number | null;
  product_name: string;
  product_slug?: string;
  shop?: number | null;
  shop_name?: string;
  seller?: number | null;
  seller_name?: string;
  unit_price?: string | number;
  price: string | number;
  quantity: number;
  line_total?: string | number;
  subtotal: string | number;
  created_at?: string;
}

export interface Order {
  id: number;
  order_number: string;
  customer_name?: string;
  phone?: string;
  address?: string;
  city?: string;
  shipping_recipient_name?: string;
  shipping_phone?: string;
  shipping_address_line_1?: string;
  shipping_address_line_2?: string;
  shipping_area?: string;
  shipping_city?: string;
  shipping_state?: string;
  shipping_postal_code?: string;
  shipping_country?: string;
  subtotal?: string | number;
  discount_total?: string | number;
  shipping_fee?: string | number;
  total_amount: string | number;
  total_items_count?: number;
  status: string;
  created_at: string;
  updated_at?: string;
  items: OrderItem[];
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface CustomerProfile {
  id: number;
  user_id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  display_name: string;
  phone: string;
  avatar?: string | null;
  date_of_birth?: string | null;
  gender?: "MALE" | "FEMALE" | "OTHER" | "PREFER_NOT_TO_SAY" | "";
  created_at: string;
  updated_at: string;
}

export interface Address {
  id: number;
  label: "Home" | "Work" | "Office" | "Other" | string;
  recipient_name: string;
  phone: string;
  address_line_1: string;
  address_line_2?: string;
  area?: string;
  city: string;
  state?: string;
  postal_code: string;
  country: string;
  latitude?: string | number | null;
  longitude?: string | number | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export type AddressInput = Omit<Address, "id" | "created_at" | "updated_at">;

export interface BackendCartItem {
  id: number;
  product: Product;
  quantity: number;
  unit_price: string;
  line_total: string;
  is_available: boolean;
  unavailable_reason: string;
  created_at: string;
  updated_at: string;
}

export interface BackendCart {
  id: number;
  items: BackendCartItem[];
  total_items_count: number;
  total_amount: string;
  has_unavailable_items: boolean;
  created_at: string;
  updated_at: string;
}


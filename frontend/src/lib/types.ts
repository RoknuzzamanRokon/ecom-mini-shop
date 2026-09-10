export interface Category {
  id: number;
  name: string;
  slug: string;
  icon?: string;
  is_active: boolean;
  products_count?: number;
  image_url?: string | null;
  description?: string;
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
  discount_percent?: number;
  savings_amount?: string | number | null;
  in_stock: boolean;
  created_at: string;
  images?: ProductImage[];
  all_image_urls?: string[];
  related_products?: Product[];
}

export interface CartItem {
  product: Product;
  quantity: number;
  subtotal: number;
}

export interface OrderItem {
  id: number;
  product?: number | null;
  product_name: string;
  price: string | number;
  quantity: number;
  subtotal: string | number;
}

export interface Order {
  id: number;
  order_number: string;
  customer_name: string;
  phone: string;
  address: string;
  city: string;
  total_amount: string | number;
  status: string;
  created_at: string;
  items: OrderItem[];
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

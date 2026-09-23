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

export interface AuthUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_staff: boolean;
  is_superuser: boolean;
  roles: string[];
  permissions: string[];
}

export interface RegisterPayload {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
  first_name?: string;
  last_name?: string;
}

export interface RegisterResponse {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  message?: string;
}

export interface Shop {
  id: number;
  name: string;
  slug: string;
  description?: string;
  logo?: string | null;
  cover_image?: string | null;
  phone?: string;
  address?: string;
  latitude?: number | null;
  longitude?: number | null;
  status: string;
  /** From shop reviews only (not product reviews); 0 when unrated. */
  average_rating?: number;
  review_count?: number;
  /** Detail endpoint only. */
  rating_breakdown?: RatingBreakdown;
  created_at: string;
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
  average_rating?: number;
  review_count?: number;
  /** Detail endpoint only. */
  rating_breakdown?: RatingBreakdown;
  created_at: string;
  images?: ProductImage[];
  all_image_urls?: string[];
  related_products?: Product[];
}

/** Review count per star level; the API always sends all five keys. */
export type RatingBreakdown = Record<"5" | "4" | "3" | "2" | "1", number>;

/** `?ordering=` values accepted by the public review lists. */
export type ReviewOrdering = "newest" | "oldest" | "highest" | "lowest";

export interface Review {
  id: number;
  user_id: number;
  reviewer_name: string;
  rating: number;
  comment: string;
  is_verified_purchase: boolean;
  created_at: string;
  updated_at: string;
}

export interface ReviewCreatePayload {
  product_id: number;
  rating: number;
  comment?: string;
}

export interface ReviewUpdatePayload {
  rating?: number;
  comment?: string;
}

/** A shop review has exactly the same public shape as a product review. */
export type ShopReview = Review;

export interface ShopReviewCreatePayload {
  shop_id: number;
  rating: number;
  comment?: string;
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
  product_image?: string | null;
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
  can_cancel?: boolean;
  payment?: PaymentSummary | null;
  created_at: string;
  updated_at?: string;
  items: OrderItem[];
}

export interface OrderCancelPayload {
  reason?: string;
}

export type PaymentStatus =
  | "PENDING"
  | "PROCESSING"
  | "PAID"
  | "FAILED"
  | "CANCELLED"
  | "REFUNDED"
  | "PARTIALLY_REFUNDED";

export type PaymentMethod =
  | "CASH_ON_DELIVERY"
  | "BKASH"
  | "NAGAD"
  | "ROCKET"
  | "CARD"
  | "ONLINE";

export interface Refund {
  id: number;
  refund_number: string;
  order_id: number;
  order_number: string;
  payment_id: number;
  payment_number: string;
  amount: string | number;
  currency: string;
  reason: string;
  status: string;
  processed_by_name?: string;
  transaction_id?: string;
  created_at: string;
  updated_at?: string;
}

export interface PaymentSummary {
  payment_number: string;
  payment_method: PaymentMethod | string;
  status: PaymentStatus;
  amount: string | number;
  currency: string;
  paid_at?: string | null;
  is_paid: boolean;
}

export interface Payment {
  id: number;
  payment_number: string;
  order_id: number;
  order_number: string;
  payment_method: PaymentMethod | string;
  status: PaymentStatus;
  amount: string | number;
  currency: string;
  transaction_id?: string;
  provider?: string;
  failure_reason?: string;
  metadata?: Record<string, any>;
  is_paid: boolean;
  refundable_amount: string | number;
  refunds: Refund[];
  paid_at?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface PaymentInitiatePayload {
  payment_method: PaymentMethod | string;
}

export interface PaymentVerifyPayload {
  status: "PAID" | "FAILED";
  transaction_id?: string;
  reason?: string;
}

export interface RefundCreatePayload {
  amount?: string | number;
  reason?: string;
}

export interface StaffOrderCustomer {
  id: number | null;
  username: string;
  email: string;
  name: string;
  phone: string;
}

export interface StaffOrderShipping {
  recipient_name: string;
  phone: string;
  address_line_1: string;
  address_line_2?: string;
  area?: string;
  city: string;
  state?: string;
  postal_code?: string;
  country: string;
}

export interface StaffOrderItem {
  id: number;
  product_id?: number | null;
  product_name: string;
  product_slug?: string;
  shop_id?: number | null;
  shop_name?: string;
  seller_id?: number | null;
  seller_name?: string;
  unit_price: string | number;
  price?: string | number;
  quantity: number;
  line_total: string | number;
  subtotal?: string | number;
  created_at: string;
}

export interface StaffOrderListItem {
  id: number;
  order_number: string;
  status: string;
  customer: StaffOrderCustomer;
  subtotal: string | number;
  discount_total: string | number;
  shipping_fee: string | number;
  total_amount: string | number;
  total_items_count: number;
  payment_status?: string | null;
  payment_method?: string | null;
  shipping_city?: string;
  created_at: string;
  updated_at?: string;
}

export interface StaffOrderDetail {
  id: number;
  order_number: string;
  status: string;
  allowed_transitions: string[];
  customer: StaffOrderCustomer;
  shipping_address: StaffOrderShipping;
  items: StaffOrderItem[];
  subtotal: string | number;
  discount_total: string | number;
  shipping_fee: string | number;
  total_amount: string | number;
  total_items_count: number;
  payment?: PaymentSummary | null;
  refunds?: Refund[];
  created_at: string;
  updated_at?: string;
}

export interface StaffOrderStatusUpdatePayload {
  status: string;
  note?: string;
  reason?: string;
}

export interface StaffOrderFilterParams {
  status?: string;
  payment_status?: string;
  seller_id?: number;
  shop_id?: number;
  search?: string;
  order_number?: string;
  start_date?: string;
  end_date?: string;
  created_after?: string;
  created_before?: string;
  page?: number;
  page_size?: number;
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

export interface SellerOrderItem {
  id: number;
  product?: number | null;
  product_name: string;
  product_slug?: string;
  shop?: number | null;
  shop_name?: string;
  seller?: number | null;
  seller_name?: string;
  unit_price: string | number;
  quantity: number;
  line_total: string | number;
  created_at?: string;
}

export interface SellerOrder {
  id: number;
  order_number: string;
  status: string;
  seller_subtotal: string;
  seller_item_count: number;
  total_amount: string | number;
  created_at: string;
  updated_at?: string;
  items: SellerOrderItem[];
  shipping_recipient_name?: string;
  shipping_phone?: string;
  shipping_address_line_1?: string;
  shipping_address_line_2?: string;
  shipping_area?: string;
  shipping_city?: string;
  shipping_state?: string;
  shipping_postal_code?: string;
  shipping_country?: string;
  customer_name?: string;
  phone?: string;
  address?: string;
  city?: string;
}

export interface SellerOrderStatusUpdatePayload {
  status: "PENDING" | "CONFIRMED" | "PROCESSING" | "SHIPPED" | "DELIVERED" | "CANCELLED" | string;
  note?: string;
}

export interface ProductInventory {
  id: number;
  product_id: number;
  product_name: string;
  product_slug: string;
  available_quantity: number;
  reserved_quantity: number;
  sold_quantity: number;
  total_quantity: number;
  created_at: string;
  updated_at: string;
}

export interface InventoryAdjustmentPayload {
  quantity: number;
  reason?: string;
}

export interface InventoryTransaction {
  id: number;
  product_id: number;
  product_name: string;
  transaction_type:
    | "INITIAL_STOCK"
    | "STOCK_IN"
    | "STOCK_OUT"
    | "RESERVATION"
    | "RELEASE"
    | "SALE"
    | "ADJUSTMENT"
    | string;
  quantity: number;
  before_available: number;
  after_available: number;
  before_reserved: number;
  after_reserved: number;
  before_sold: number;
  after_sold: number;
  actor_name: string;
  reason: string;
  created_at: string;
}

// ==============================================================================
// TASK 17: ADMIN & PLATFORM GOVERNANCE TYPES
// ==============================================================================

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  roles: string[];
  customer_profile_id?: number | null;
  seller_profile_id?: number | null;
  date_joined: string;
  last_login?: string | null;
}

export interface AdminRole {
  id: number;
  code: string;
  name: string;
  description: string;
  is_active: boolean;
  is_protected: boolean;
  permissions: string[];
  user_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdminSeller {
  id: number;
  username: string;
  email: string;
  business_name: string;
  business_email: string;
  business_phone: string;
  seller_type: string;
  status: string;
  tax_id: string;
  description: string;
  rejection_reason?: string;
  suspension_reason?: string;
  is_operational: boolean;
  shops_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdminShop {
  id: number;
  owner_id: number;
  owner_business_name: string;
  name: string;
  slug: string;
  description: string;
  phone: string;
  address: string;
  status: string;
  rejection_reason?: string;
  suspension_reason?: string;
  products_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdminProduct {
  id: number;
  name: string;
  slug: string;
  category_id: number;
  category_name: string;
  shop_id: number;
  shop_name: string;
  seller_business_name?: string;
  price: string;
  old_price?: string;
  stock: number;
  badge?: string;
  is_active: boolean;
  status: string;
  rejection_reason?: string;
  is_publicly_visible: boolean;
  created_at: string;
  updated_at: string;
}

export interface AdminCategory {
  id: number;
  name: string;
  slug: string;
  icon?: string;
  image?: string;
  description?: string;
  is_active: boolean;
  products_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdminCustomer {
  id: number;
  user_id: number;
  username: string;
  email: string;
  display_name: string;
  phone: string;
  gender: string;
  is_active: boolean;
  orders_count: number;
  created_at: string;
}

export interface Favorite {
  id: number;
  product: Product;
  created_at: string;
}

export interface PasswordChangePayload {
  current_password: string;
  new_password: string;
  new_password_confirm: string;
}

export interface SellerProfile {
  id: number;
  user: number;
  username: string;
  user_email: string;
  seller_type: "FULL_SHOP_OWNER" | "LIMITED_SHOP_OWNER" | "PRODUCT_OWNER" | string;
  seller_type_display: string;
  status: "PENDING" | "UNDER_REVIEW" | "APPROVED" | "REJECTED" | "SUSPENDED" | string;
  status_display: string;
  business_name: string;
  business_email: string;
  business_phone: string;
  tax_id: string;
  description: string;
  is_operational: boolean;
  is_suspended: boolean;
  rejection_reason?: string;
  suspension_reason?: string;
  reviewed_at?: string | null;
  approved_at?: string | null;
  suspended_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SellerCapabilities {
  can_create_shops: boolean;
  max_shops: number | null;
  can_create_products: boolean;
  can_manage_inventory: boolean;
  can_manage_orders: boolean;
}

export interface SellerDashboardData {
  has_seller_profile: boolean;
  seller: SellerProfile;
  capabilities: SellerCapabilities;
  status: string;
  is_operational: boolean;
  is_suspended: boolean;
  warning?: string;
  info?: string;
}

export interface SellerShop {
  id: number;
  owner_id: number;
  owner_name: string;
  name: string;
  slug: string;
  description: string;
  logo?: string | null;
  cover_image?: string | null;
  phone: string;
  address: string;
  latitude?: number | null;
  longitude?: number | null;
  status: "DRAFT" | "PENDING" | "APPROVED" | "ACTIVE" | "SUSPENDED" | "REJECTED" | string;
  status_display: string;
  rejection_reason?: string;
  suspension_reason?: string;
  is_publicly_visible: boolean;
  created_at: string;
  updated_at: string;
}

// Mirrors points/serializers.py::SellerWalletSerializer field-for-field.
// It previously declared `seller_name` (the serializer returns `business_name`)
// and `total_earned`/`total_spent`, which the serializer did not return at all --
// so the wallet tiles read undefined and rendered +0/-0 forever while `tsc`
// stayed silent. Keep this in step with the serializer; a field here that the
// backend does not send is invisible to the type checker.
export interface SellerWallet {
  id: number;
  seller_id: number;
  business_name: string;
  balance: number;
  total_earned: number;
  total_spent: number;
  product_creation_cost: number;
  created_at: string;
  updated_at: string;
}

// Mirrors points/serializers.py::PointTransactionSerializer field-for-field.
// It previously declared `description`; the serializer exposes `reason`, so every
// ledger row fell back to the literal "Point transaction".
export type PointTransactionType =
  | "BONUS"
  | "ADMIN_CREDIT"
  | "ADMIN_DEBIT"
  | "PRODUCT_CREATION"
  | "REFUND"
  | "ADJUSTMENT";

export interface PointTransaction {
  id: number;
  wallet_id: number;
  seller_id: number;
  business_name: string;
  transaction_type: PointTransactionType | string;
  transaction_type_display: string;
  amount: number;
  balance_before: number;
  balance_after: number;
  reason: string;
  reference_type: string;
  reference_id: string;
  actor_id: number | null;
  actor_username: string | null;
  created_at: string;
}


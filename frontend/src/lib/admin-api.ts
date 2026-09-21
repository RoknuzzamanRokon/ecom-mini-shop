import { PaginatedResponse } from "./types";
import { refreshTokenOnce } from "./auth";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001";

export interface AdminMetrics {
  total_orders: number;
  total_revenue: number;
  pending_shops: number;
  pending_sellers: number;
  total_shops: number;
  total_sellers: number;
  total_products: number;
}

export interface AuditActor {
  id: number;
  username: string;
  email: string;
  first_name?: string;
  last_name?: string;
  full_name?: string;
}

export interface AdminAuditLog {
  id: number;
  actor: AuditActor | null;
  action: string;
  target_type: string;
  resource_type: string;
  target_id: string;
  resource_id: string;
  target_repr: string;
  shop: number | null;
  seller: number | null;
  metadata: Record<string, unknown>;
  changes: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
}

export interface AuditLogFilterParams {
  page?: number;
  page_size?: number;
  action?: string;
  resource_type?: string;
  target_type?: string;
  resource_id?: string;
  target_id?: string;
  actor?: string;
  search?: string;
  start_date?: string;
  end_date?: string;
  shop_id?: number;
  seller_id?: number;
}

export class AdminApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = "AdminApiError";
    this.status = status;
    this.data = data;
  }

  get isUnauthenticated(): boolean {
    return this.status === 401;
  }

  get isUnauthorized(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isValidationError(): boolean {
    return this.status === 400;
  }
}

/**
 * The single interception point for every management-console request.
 *
 * Phase 2J added the 401 recovery here: a console module that has been open
 * past the 60-minute access-token lifetime used to show a generic error panel
 * and need a page reload.
 *
 *   401 -> refreshTokenOnce() -> retry once with the new token
 *
 * `refreshTokenOnce` is the same coordinator `api.ts` uses, deliberately — one
 * shared single-flight refresh, not one per API layer, so a dashboard firing
 * several requests at once still produces a single refresh. It reaches
 * `/api/auth/token/refresh/` through `api.ts`'s plain `fetch`, never through
 * this function, so the refresh cannot re-enter the interceptor.
 *
 * `retried` is internal and the retry recurses exactly once with it set, so a
 * second 401 becomes an `AdminApiError` immediately — there is no third
 * request. Everything else here (network-error wrapping, `extractErrorMessage`,
 * `AdminApiError` status/body, JSON parsing) is unchanged.
 */
async function adminRequest<T>(
  endpoint: string,
  token: string,
  options: RequestInit = {},
  retried = false
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };

  let res: Response;
  try {
    res = await fetch(url, {
      ...options,
      headers,
      cache: "no-store",
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "Network error";
    throw new AdminApiError(`Network request failed: ${msg}`, 0);
  }

  if (res.status === 401 && !retried) {
    const refreshed = await refreshTokenOnce();
    if (refreshed) {
      return adminRequest<T>(endpoint, refreshed, options, true);
    }
    // Refresh failed: tokens are already cleared and AuthProvider already
    // notified. Fall through so the caller sees the original 401 as the
    // AdminApiError it has always received.
  }

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    const message = extractErrorMessage(errorBody, `Request failed with status ${res.status}`);
    throw new AdminApiError(message, res.status, errorBody);
  }

  return (await res.json()) as T;
}

/**
 * Resolves a human-readable message from a DRF error response body.
 *
 * Handles the shapes the admin API actually returns: a top-level `detail`
 * (permission/not-found errors, e.g. CanChangeAdminShopStatus's message), or
 * plain field-level validation errors from `serializer.is_valid(raise_exception=True)`
 * — e.g. `{"reason": ["A reason is required when rejecting a shop."]}` — which
 * previously fell through to a generic "Request failed with status 400".
 */
function extractErrorMessage(errorBody: unknown, fallback: string): string {
  // DRF renders `ValidationError("a message")` raised with a plain string as a
  // BARE JSON ARRAY — e.g. the category delete safeguard ("Cannot delete
  // category 'X' because it is referenced by N product(s)...") and the product
  // publish precondition. Arrays are typeof "object", but none of the
  // field-level handling below matches them, so without this branch the most
  // useful backend messages in the console fell through to the generic
  // "Request failed with status 400".
  if (Array.isArray(errorBody)) {
    const messages = errorBody.filter((item): item is string => typeof item === "string");
    if (messages.length > 0) return messages.join(" ");
  }

  if (errorBody && typeof errorBody === "object") {
    const body = errorBody as Record<string, unknown>;
    if (typeof body.detail === "string") return body.detail;
    if (typeof body.message === "string") return body.message;
    if (typeof body.error === "string") return body.error;

    const fieldMessages = Object.entries(body)
      .filter((entry): entry is [string, string[]] => {
        const value = entry[1];
        return Array.isArray(value) && value.every((item) => typeof item === "string");
      })
      .map(([field, messages]) => `${field}: ${messages.join(" ")}`);
    if (fieldMessages.length > 0) return fieldMessages.join(" ");
  }
  return fallback;
}

/**
 * Fetches platform-wide operational metrics for the Next.js Management Console.
 * Returns real backend aggregates for orders, revenue (in ৳), pending shops, and pending sellers.
 */
export async function getAdminMetrics(token: string): Promise<AdminMetrics> {
  return adminRequest<AdminMetrics>("/api/admin/metrics/", token);
}

/**
 * Fetches paginated platform governance audit logs with optional filtering.
 */
export async function getAdminAuditLogs(
  token: string,
  params?: AuditLogFilterParams
): Promise<PaginatedResponse<AdminAuditLog>> {
  const searchParams = new URLSearchParams();

  if (params) {
    if (params.page) searchParams.set("page", String(params.page));
    if (params.page_size) searchParams.set("page_size", String(params.page_size));
    if (params.action) searchParams.set("action", params.action);
    if (params.resource_type) searchParams.set("resource_type", params.resource_type);
    if (params.target_type) searchParams.set("target_type", params.target_type);
    if (params.resource_id) searchParams.set("resource_id", params.resource_id);
    if (params.target_id) searchParams.set("target_id", params.target_id);
    if (params.actor) searchParams.set("actor", params.actor);
    if (params.search) searchParams.set("search", params.search);
    if (params.start_date) searchParams.set("start_date", params.start_date);
    if (params.end_date) searchParams.set("end_date", params.end_date);
    if (params.shop_id) searchParams.set("shop_id", String(params.shop_id));
    if (params.seller_id) searchParams.set("seller_id", String(params.seller_id));
  }

  const queryString = searchParams.toString();
  const endpoint = `/api/admin/audit-logs/${queryString ? `?${queryString}` : ""}`;

  return adminRequest<PaginatedResponse<AdminAuditLog>>(endpoint, token);
}

// ==============================================================================
// SHOP GOVERNANCE (Phase 1B)
// ==============================================================================

/**
 * Mirrors AdminShopSerializer in shop/admin_serializers.py field-for-field.
 * That serializer is entirely read_only — every field below is exactly what
 * GET /api/admin/shops/ and /api/admin/shops/<id>/ return, nothing more.
 * Notably absent (and therefore NOT rendered anywhere in the admin UI):
 * logo, cover_image, location/coordinates, reviewed_by. The serializer does
 * not expose them, so the admin console cannot either.
 */
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
  rejection_reason: string;
  suspension_reason: string;
  products_count: number;
  reviewed_at: string | null;
  approved_at: string | null;
  suspended_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminShopListParams {
  page?: number;
  page_size?: number;
  /** Matches name/slug/owner business name, case-insensitive (see AdminShopListAPIView). */
  search?: string;
  /** Exact Shop.STATUS_CHOICES value (DRAFT/PENDING/APPROVED/ACTIVE/SUSPENDED/REJECTED). */
  status?: string;
}

/** Exactly the `action` choices accepted by AdminShopStatusUpdateSerializer. */
export type AdminShopStatusAction = "approve" | "reject" | "suspend" | "reactivate";

export interface AdminShopStatusPayload {
  action: AdminShopStatusAction;
  /** Required by the backend for 'reject' and 'suspend'; ignored for the others. */
  reason?: string;
}

/**
 * GET /api/admin/shops/
 * Requires 'shops.admin.manage' or 'shops.view' (CanViewAdminShops).
 */
export async function getAdminShops(
  token: string,
  params?: AdminShopListParams
): Promise<PaginatedResponse<AdminShop>> {
  const searchParams = new URLSearchParams();
  if (params) {
    if (params.page) searchParams.set("page", String(params.page));
    if (params.page_size) searchParams.set("page_size", String(params.page_size));
    if (params.search) searchParams.set("search", params.search);
    if (params.status) searchParams.set("status", params.status);
  }
  const queryString = searchParams.toString();
  return adminRequest<PaginatedResponse<AdminShop>>(
    `/api/admin/shops/${queryString ? `?${queryString}` : ""}`,
    token
  );
}

/**
 * GET /api/admin/shops/<id>/
 * Requires 'shops.admin.manage' or 'shops.view' (CanViewAdminShops).
 */
export async function getAdminShopDetail(token: string, id: number | string): Promise<AdminShop> {
  return adminRequest<AdminShop>(`/api/admin/shops/${id}/`, token);
}

/**
 * POST /api/admin/shops/<id>/status/
 * Entry requires CanChangeAdminShopStatus (shops.admin.manage OR shops.approve).
 * The view then enforces per-action: only 'approve' is permitted on
 * shops.approve alone — reject/suspend/reactivate require shops.admin.manage.
 */
export async function updateAdminShopStatus(
  token: string,
  id: number | string,
  payload: AdminShopStatusPayload
): Promise<AdminShop> {
  return adminRequest<AdminShop>(`/api/admin/shops/${id}/status/`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * The writable surface of AdminShopCreateSerializer, in full (Phase 1H).
 *
 * Targets an EXISTING SellerProfile by id — there is no way to create a
 * seller and a shop in one call, and none is added here. The created shop
 * always starts DRAFT (ShopService.create_shop hardcodes it when
 * submit_for_review is omitted) — this payload cannot set an initial status
 * because the serializer has no such field. `seller_id` eligibility (must be
 * operational, not PRODUCT_OWNER, and under the LIMITED_SHOP_OWNER 1-shop
 * cap) is enforced server-side by the same ShopService rule the removed
 * seller self-service endpoint used to enforce.
 */
export interface AdminShopCreatePayload {
  /** Primary key of the existing SellerProfile to assign as owner. */
  seller_id: number;
  name: string;
  description?: string;
  phone?: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  reason: string;
}

/**
 * POST /api/admin/shops/ -> 201 with the created AdminShop (status DRAFT).
 * Requires 'shops.admin.manage' (CanManageAdminShops).
 *
 * The backend rejects a seller_id that does not exist, or one that is
 * ineligible (ineligible status, PRODUCT_OWNER, or LIMITED_SHOP_OWNER already
 * at its 1-shop cap), with a 400 field/validation error — this client does
 * not pre-check any of that, it only surfaces what the backend decides.
 */
export async function createAdminShop(
  token: string,
  payload: AdminShopCreatePayload
): Promise<AdminShop> {
  return adminRequest<AdminShop>("/api/admin/shops/", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}


// ==============================================================================
// SELLER GOVERNANCE (Phase 1C)
// ==============================================================================

/**
 * Mirrors AdminSellerSerializer in shop/admin_serializers.py field-for-field.
 * That serializer declares `read_only_fields = fields`, so this is exactly what
 * GET /api/admin/sellers/ and /api/admin/sellers/<id>/ return, nothing more.
 *
 * Notably absent from the admin serializer (and therefore NOT rendered anywhere
 * in the admin UI): the SellerProfile.user id, `reviewed_by`, and any KYC
 * document/identity fields — SellerProfile has none. `tax_id`, `business_email`
 * and `business_phone` are the only verification-style attributes the backend
 * actually stores.
 */
export interface AdminSeller {
  id: number;
  /** Account username of the SellerProfile owner (source="user.username"). */
  username: string;
  /** Account email of the SellerProfile owner (source="user.email"). */
  email: string;
  business_name: string;
  business_email: string;
  business_phone: string;
  /** Exact SellerProfile.SELLER_TYPE_CHOICES value. */
  seller_type: string;
  /** Exact SellerProfile.STATUS_CHOICES value. */
  status: string;
  tax_id: string;
  description: string;
  rejection_reason: string;
  suspension_reason: string;
  /** SellerProfile.is_operational property: status is APPROVED or ACTIVE. */
  is_operational: boolean;
  shops_count: number;
  reviewed_at: string | null;
  approved_at: string | null;
  suspended_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminSellerListParams {
  page?: number;
  page_size?: number;
  /**
   * Matches business_name / business_email / business_phone / account username,
   * case-insensitive (see AdminSellerListAPIView).
   */
  search?: string;
  /** Exact SellerProfile.STATUS_CHOICES value (the backend upper-cases it). */
  status?: string;
  /** Exact SellerProfile.SELLER_TYPE_CHOICES value (the backend upper-cases it). */
  seller_type?: string;
}

/** Exactly the `action` choices accepted by AdminSellerStatusUpdateSerializer. */
export type AdminSellerStatusAction = "approve" | "reject" | "suspend" | "reactivate";

export interface AdminSellerStatusPayload {
  action: AdminSellerStatusAction;
  /** Required by the backend for 'reject' and 'suspend'; ignored for the others. */
  reason?: string;
}

/**
 * GET /api/admin/sellers/
 * Requires 'sellers.admin.manage' or 'sellers.view' (CanViewAdminSellers).
 */
export async function getAdminSellers(
  token: string,
  params?: AdminSellerListParams
): Promise<PaginatedResponse<AdminSeller>> {
  const searchParams = new URLSearchParams();
  if (params) {
    if (params.page) searchParams.set("page", String(params.page));
    if (params.page_size) searchParams.set("page_size", String(params.page_size));
    if (params.search) searchParams.set("search", params.search);
    if (params.status) searchParams.set("status", params.status);
    if (params.seller_type) searchParams.set("seller_type", params.seller_type);
  }
  const queryString = searchParams.toString();
  return adminRequest<PaginatedResponse<AdminSeller>>(
    `/api/admin/sellers/${queryString ? `?${queryString}` : ""}`,
    token
  );
}

/**
 * GET /api/admin/sellers/<id>/
 * Requires 'sellers.admin.manage' or 'sellers.view' (CanViewAdminSellers).
 */
export async function getAdminSellerDetail(
  token: string,
  id: number | string
): Promise<AdminSeller> {
  return adminRequest<AdminSeller>(`/api/admin/sellers/${id}/`, token);
}

/**
 * POST /api/admin/sellers/<id>/status/
 * Requires CanManageAdminSellers — i.e. 'sellers.admin.manage' (or superuser /
 * SUPER_ADMINISTRATOR). Unlike the shop status endpoint there is NO granular
 * approve-only path here: 'sellers.approve' and 'sellers.suspend' gate the
 * legacy /api/sellers/<id>/approve|suspend/ endpoints, not this one.
 *
 * The response body is the updated AdminSellerSerializer payload, which the
 * caller should treat as authoritative rather than optimistically guessing the
 * resulting status.
 */
export async function updateAdminSellerStatus(
  token: string,
  id: number | string,
  payload: AdminSellerStatusPayload
): Promise<AdminSeller> {
  return adminRequest<AdminSeller>(`/api/admin/sellers/${id}/status/`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * The writable surface of AdminSellerCreateSerializer, in full.
 *
 * Targets an EXISTING user by id — there is no way to create a user and a
 * seller profile in one call, and none is added here. `seller_type` defaults
 * to FULL_SHOP_OWNER server-side when omitted, matching
 * SellerProfile.TYPE_FULL_SHOP_OWNER. The created profile always starts
 * PENDING (sellers.services.create_seller_profile hardcodes it) — this
 * payload cannot set an initial status because the serializer has no such
 * field.
 */
export interface AdminSellerCreatePayload {
  /** Primary key of the existing user to attach the seller profile to. */
  user_id: number;
  business_name: string;
  /** Exact SellerProfile.SELLER_TYPE_CHOICES value; defaults server-side to FULL_SHOP_OWNER. */
  seller_type?: string;
  business_email?: string;
  business_phone?: string;
  tax_id?: string;
  description?: string;
  reason: string;
}

/**
 * POST /api/admin/sellers/ -> 201 with the created AdminSeller (status PENDING).
 * Requires 'sellers.admin.manage' (CanManageAdminSellers).
 *
 * The backend rejects a user_id that does not exist, or one that already has a
 * SellerProfile, with a 400 field/validation error — this client does not
 * pre-check either condition, it only surfaces what the backend decides.
 */
export async function createAdminSeller(
  token: string,
  payload: AdminSellerCreatePayload
): Promise<AdminSeller> {
  return adminRequest<AdminSeller>("/api/admin/sellers/", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ==============================================================================
// PRODUCT GOVERNANCE (Phase 1D)
// ==============================================================================

/**
 * Mirrors AdminProductSerializer in shop/admin_serializers.py field-for-field.
 * That serializer declares `read_only_fields = fields`, so this is exactly what
 * GET /api/admin/products/ and /api/admin/products/<id>/ return, nothing more.
 *
 * Deliberately absent, because the admin serializer does not expose them:
 * `description`, `image`, and — importantly for governance — `reviewed_by` and
 * the owning shop's / seller's own status. The console therefore cannot
 * pre-validate the publish preconditions and relies on the backend's 400.
 */
export interface AdminProduct {
  id: number;
  name: string;
  slug: string;
  /** Null only if the relation is missing; the model requires a category. */
  category_id: number | null;
  category_name: string | null;
  /** Product.shop is nullable (on_delete=SET_NULL), so these can be null. */
  shop_id: number | null;
  shop_name: string | null;
  /** SerializerMethodField: shop.owner.business_name, or null when unowned. */
  seller_business_name: string | null;
  /** DecimalField -> DRF returns these as strings. */
  price: string;
  old_price: string | null;
  stock: number;
  badge: string;
  is_active: boolean;
  /** Exact Product.STATUS_CHOICES value. */
  status: string;
  rejection_reason: string;
  /** Product.is_publicly_visible property — the full public-catalog predicate. */
  is_publicly_visible: boolean;
  submitted_at: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminProductListParams {
  page?: number;
  page_size?: number;
  /** Matches name / slug / shop name, case-insensitive (AdminProductListAPIView). */
  search?: string;
  /** Exact Product.STATUS_CHOICES value (the backend upper-cases it). */
  status?: string;
  /** Category primary key — the backend filters `category_id`, not a slug. */
  category?: number | string;
  /** Shop primary key — the backend filters `shop_id`, not a slug. */
  shop?: number | string;
}

/** Exactly the `action` choices accepted by AdminProductStatusUpdateSerializer. */
export type AdminProductStatusAction = "approve" | "reject" | "publish" | "unpublish";

export interface AdminProductStatusPayload {
  action: AdminProductStatusAction;
  /** Required by the backend for 'reject' only; ignored for the others. */
  reason?: string;
}

/**
 * GET /api/admin/products/
 * Requires 'products.admin.manage' or 'products.view' (CanViewAdminProducts).
 */
export async function getAdminProducts(
  token: string,
  params?: AdminProductListParams
): Promise<PaginatedResponse<AdminProduct>> {
  const searchParams = new URLSearchParams();
  if (params) {
    if (params.page) searchParams.set("page", String(params.page));
    if (params.page_size) searchParams.set("page_size", String(params.page_size));
    if (params.search) searchParams.set("search", params.search);
    if (params.status) searchParams.set("status", params.status);
    if (params.category) searchParams.set("category", String(params.category));
    if (params.shop) searchParams.set("shop", String(params.shop));
  }
  const queryString = searchParams.toString();
  return adminRequest<PaginatedResponse<AdminProduct>>(
    `/api/admin/products/${queryString ? `?${queryString}` : ""}`,
    token
  );
}

/**
 * GET /api/admin/products/<id>/
 * Requires 'products.admin.manage' or 'products.view' (CanViewAdminProducts).
 */
export async function getAdminProductDetail(
  token: string,
  id: number | string
): Promise<AdminProduct> {
  return adminRequest<AdminProduct>(`/api/admin/products/${id}/`, token);
}

/**
 * POST /api/admin/products/<id>/status/
 *
 * CanChangeAdminProductStatus only gates ENTRY to the endpoint (holding any one
 * of products.admin.manage / .approve / .reject / .publish is enough to reach
 * it). AdminProductStatusAPIView._update_status then enforces the real per-action
 * mapping and raises PermissionDenied for an action the caller cannot perform —
 * so a 403 here is action-specific, not module-wide.
 *
 * 'publish' additionally validates that the owning shop is APPROVED/ACTIVE and
 * the seller is operational, returning 400 when it is not. Those fields are not
 * in AdminProductSerializer, so that error can only be surfaced, never predicted.
 *
 * The response body is the updated AdminProductSerializer payload, which the
 * caller should treat as authoritative rather than optimistically guessing the
 * resulting status.
 */
export async function updateAdminProductStatus(
  token: string,
  id: number | string,
  payload: AdminProductStatusPayload
): Promise<AdminProduct> {
  return adminRequest<AdminProduct>(`/api/admin/products/${id}/status/`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ==============================================================================
// CATEGORY GOVERNANCE (Phase 1E)
// ==============================================================================

/**
 * Mirrors AdminCategorySerializer in shop/admin_serializers.py field-for-field.
 *
 * Category is FLAT: shop/models.py defines no `parent` relation, so there is no
 * hierarchy, no children, and no tree endpoint to model here.
 * Its only lifecycle state is the `is_active` boolean — there is no status
 * enum, and none is invented.
 */
export interface AdminCategory {
  id: number;
  name: string;
  slug: string;
  /** Material Symbols ligature name, e.g. "checkroom". Blank when unset. */
  icon: string;
  /** ImageField URL, or null. Read-only here — see updateAdminCategory. */
  image: string | null;
  description: string;
  is_active: boolean;
  /** SerializerMethodField: obj.products.count(). */
  products_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdminCategoryListParams {
  page?: number;
  page_size?: number;
  /** Matches name / slug, case-insensitive (AdminCategoryListCreateAPIView). */
  search?: string;
  /** The backend parses "true"/"1" and "false"/"0"; anything else is ignored. */
  is_active?: boolean;
}

/**
 * The writable subset of AdminCategorySerializer.
 *
 * `name` and `slug` are BOTH required by the serializer. Category.save()
 * auto-slugifies a blank slug, but that never runs through the API: the model's
 * SlugField is not blank=True, so DRF marks it required and rejects the payload
 * before save() is reached. The create form therefore always sends a slug.
 *
 * `image` is deliberately absent. It is an ImageField, which needs a multipart
 * upload, and adminRequest is a JSON transport — adding multipart here would
 * mean a second request layer. Existing images are displayed but not edited.
 */
export interface AdminCategoryWritePayload {
  name: string;
  slug: string;
  icon?: string;
  description?: string;
  is_active?: boolean;
}

/**
 * GET /api/admin/categories/
 * Requires 'categories.admin.manage' (CanManageAdminCategories) — there is no
 * read-only category permission in seed_rbac.py, so viewing and managing the
 * taxonomy are the same privilege.
 */
export async function getAdminCategories(
  token: string,
  params?: AdminCategoryListParams
): Promise<PaginatedResponse<AdminCategory>> {
  const searchParams = new URLSearchParams();
  if (params) {
    if (params.page) searchParams.set("page", String(params.page));
    if (params.page_size) searchParams.set("page_size", String(params.page_size));
    if (params.search) searchParams.set("search", params.search);
    if (params.is_active !== undefined) searchParams.set("is_active", String(params.is_active));
  }
  const queryString = searchParams.toString();
  return adminRequest<PaginatedResponse<AdminCategory>>(
    `/api/admin/categories/${queryString ? `?${queryString}` : ""}`,
    token
  );
}

/** GET /api/admin/categories/<id>/ -> CanManageAdminCategories. */
export async function getAdminCategoryDetail(
  token: string,
  id: number | string
): Promise<AdminCategory> {
  return adminRequest<AdminCategory>(`/api/admin/categories/${id}/`, token);
}

/** POST /api/admin/categories/ -> 201 with the created AdminCategorySerializer body. */
export async function createAdminCategory(
  token: string,
  payload: AdminCategoryWritePayload
): Promise<AdminCategory> {
  return adminRequest<AdminCategory>("/api/admin/categories/", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * PATCH /api/admin/categories/<id>/ (partial=True) -> the updated category.
 * Also the documented way to retire a category that cannot be deleted:
 * PATCH { is_active: false }.
 */
export async function updateAdminCategory(
  token: string,
  id: number | string,
  payload: Partial<AdminCategoryWritePayload>
): Promise<AdminCategory> {
  return adminRequest<AdminCategory>(`/api/admin/categories/${id}/`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/**
 * DELETE /api/admin/categories/<id>/ — a HARD delete, not a soft one.
 *
 * AdminCategoryDetailAPIView.delete refuses with 400 when the category is still
 * referenced by any product, telling the operator to deactivate it instead.
 * That safeguard is the backend's to enforce; this client never tries to work
 * around it. Success is 200 with {"detail": "..."} (not 204).
 */
export async function deleteAdminCategory(
  token: string,
  id: number | string
): Promise<{ detail: string }> {
  return adminRequest<{ detail: string }>(`/api/admin/categories/${id}/`, token, {
    method: "DELETE",
  });
}

// ==============================================================================
// CUSTOMER DIRECTORY (Phase 1F) — STRICTLY READ-ONLY
// ==============================================================================
//
// The backend exposes GET only: AdminCustomerListAPIView and
// AdminCustomerDetailAPIView define no post/patch/delete handler, so there is
// no customer mutation endpoint to call and none is modelled here.
//
// Both serializers declare `read_only_fields = fields` and neither includes a
// password, hash, token or any other credential — verified by enumerating
// their bound fields, and covered by the existing backend test
// `test_user_and_customer_apis_exclude_passwords_and_tokens`.

/** Mirrors AdminCustomerListSerializer field-for-field. */
export interface AdminCustomerListItem {
  /** CustomerProfile primary key — the id the detail route takes. */
  id: number;
  /** The underlying auth user's id (source="user.id"). */
  user_id: number;
  username: string;
  email: string;
  /** CustomerProfile.display_name; blank when the customer never set one. */
  display_name: string;
  phone: string;
  /** Exact CustomerProfile.GENDER_CHOICES value, or "" (the field is blank=True). */
  gender: string;
  /** source="user.is_active" — the auth account flag, not a profile field. */
  is_active: boolean;
  /** SerializerMethodField: Order.objects.filter(user=...).count(). */
  orders_count: number;
  created_at: string;
}

/** One entry of AdminCustomerDetailSerializer.get_addresses (a hand-built dict). */
export interface AdminCustomerAddress {
  id: number;
  label: string;
  recipient_name: string;
  phone: string;
  address_line_1: string;
  city: string;
  is_default: boolean;
}

/**
 * One entry of AdminCustomerDetailSerializer.get_recent_orders — the five most
 * recent orders, already trimmed by the backend. Deliberately not a full order
 * model: these five fields are everything that method returns.
 */
export interface AdminCustomerRecentOrder {
  id: number;
  order_number: string;
  /** Exact Order.STATUS_CHOICES value. */
  status: string;
  /** DecimalField serialized with str() by the backend. */
  total_amount: string;
  created_at: string;
}

/** Mirrors AdminCustomerDetailSerializer field-for-field. */
export interface AdminCustomerDetail {
  id: number;
  user_id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  display_name: string;
  phone: string;
  gender: string;
  date_of_birth: string | null;
  is_active: boolean;
  date_joined: string;
  addresses: AdminCustomerAddress[];
  orders_count: number;
  recent_orders: AdminCustomerRecentOrder[];
  created_at: string;
  updated_at: string;
}

export interface AdminCustomerListParams {
  page?: number;
  page_size?: number;
  /**
   * Matches username / email / display_name / phone, case-insensitive
   * (AdminCustomerListAPIView). It is the ONLY filter the endpoint supports —
   * there is no status or date filter to expose.
   */
  search?: string;
}

/**
 * GET /api/admin/customers/
 * Requires 'customers.admin.view' (CanViewAdminCustomers).
 */
export async function getAdminCustomers(
  token: string,
  params?: AdminCustomerListParams
): Promise<PaginatedResponse<AdminCustomerListItem>> {
  const searchParams = new URLSearchParams();
  if (params) {
    if (params.page) searchParams.set("page", String(params.page));
    if (params.page_size) searchParams.set("page_size", String(params.page_size));
    if (params.search) searchParams.set("search", params.search);
  }
  const queryString = searchParams.toString();
  return adminRequest<PaginatedResponse<AdminCustomerListItem>>(
    `/api/admin/customers/${queryString ? `?${queryString}` : ""}`,
    token
  );
}

/**
 * GET /api/admin/customers/<id>/
 * Requires 'customers.admin.view' (CanViewAdminCustomers).
 * `id` is the CustomerProfile pk, not the auth user id.
 */
export async function getAdminCustomerDetail(
  token: string,
  id: number | string
): Promise<AdminCustomerDetail> {
  return adminRequest<AdminCustomerDetail>(`/api/admin/customers/${id}/`, token);
}

// ==============================================================================
// USER & ROLE GOVERNANCE (Phase 1G-A)
// ==============================================================================
//
// MiniShop RBAC resolves authorization as:
//     User -> UserRole -> Role -> RolePermission -> Permission
// Every type below models that chain as the backend already exposes it. There
// is no direct user->permission write path in this console: the admin user
// endpoint accepts `is_active` and `roles` only, so role assignment is the only
// way this UI can change what a user may do.
//
// Django's own auth.Permission / user_permissions system is a SEPARATE
// mechanism that gates Django Admin. It is not modelled here and is never used
// as the authority for MiniShop permissions.

/** Mirrors AdminUserListSerializer field-for-field (`read_only_fields = fields`). */
export interface AdminUserListItem {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  /** Django Admin access flag — NOT a MiniShop RBAC permission. */
  is_staff: boolean;
  /** Django superuser flag; resolves to full MiniShop access in rbac.services. */
  is_superuser: boolean;
  /** Active MiniShop role codes, e.g. ["OPERATION_MANAGER"]. */
  roles: string[];
  /** CustomerProfile pk when the account has one, else null. */
  customer_profile_id: number | null;
  /** SellerProfile pk when the account has one, else null. */
  seller_profile_id: number | null;
  date_joined: string;
  last_login: string | null;
}

/** AdminUserDetailSerializer.get_customer_profile — exactly these four keys. */
export interface AdminUserCustomerProfileSummary {
  id: number;
  display_name: string;
  phone: string;
  gender: string;
}

/** AdminUserDetailSerializer.get_seller_profile — exactly these seven keys. */
export interface AdminUserSellerProfileSummary {
  id: number;
  business_name: string;
  business_email: string;
  business_phone: string;
  /** SellerProfile.SELLER_TYPE_CHOICES — a business attribute, not an RBAC role. */
  seller_type: string;
  status: string;
  is_operational: boolean;
}

/**
 * Mirrors AdminUserDetailSerializer. Like every admin serializer it declares
 * `read_only_fields = fields` and exposes no password, hash, token or other
 * credential — asserted by the backend tests
 * `test_user_and_customer_apis_exclude_passwords_and_tokens` and
 * `test_user_detail_exposes_effective_permissions_without_credentials`.
 */
export interface AdminUserDetail {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  roles: string[];
  /**
   * EFFECTIVE MiniShop permissions, resolved server-side by
   * rbac.services.get_user_permissions — the same resolver every DRF permission
   * class calls. The console displays this; it never recomputes it from roles.
   * The "*" wildcard is stripped by the serializer and reported separately.
   */
  permissions: string[];
  /** True when the account resolves to "*" (superuser / SUPER_ADMINISTRATOR). */
  has_full_platform_access: boolean;
  customer_profile: AdminUserCustomerProfileSummary | null;
  seller_profile: AdminUserSellerProfileSummary | null;
  date_joined: string;
  last_login: string | null;
}

export interface AdminUserListParams {
  page?: number;
  page_size?: number;
  /** Matches username / email / first_name / last_name, case-insensitive. */
  search?: string;
  /** The backend parses "true"/"1" and "false"/"0"; anything else is ignored. */
  is_active?: boolean;
  /** Exact Role.code — filters on an ACTIVE UserRole for that role. */
  role?: string;
}

/**
 * The writable surface of AdminUserUpdateSerializer, in full.
 *
 * `reason` is REQUIRED by the serializer on every call and is written to the
 * AuditLog entry for the change. There is deliberately nothing else here:
 * username, email and name are not editable through this endpoint, and no
 * password field exists on it at all.
 */
export interface AdminUserUpdatePayload {
  is_active?: boolean;
  /**
   * The COMPLETE desired set of role codes — the backend diffs it against the
   * user's current roles and assigns/removes accordingly. Omit the key entirely
   * to leave role assignments untouched.
   */
  roles?: string[];
  reason: string;
}

/**
 * GET /api/admin/users/
 * Requires 'users.admin.view' (CanViewAdminUsers).
 */
export async function getAdminUsers(
  token: string,
  params?: AdminUserListParams
): Promise<PaginatedResponse<AdminUserListItem>> {
  const searchParams = new URLSearchParams();
  if (params) {
    if (params.page) searchParams.set("page", String(params.page));
    if (params.page_size) searchParams.set("page_size", String(params.page_size));
    if (params.search) searchParams.set("search", params.search);
    if (params.is_active !== undefined) searchParams.set("is_active", String(params.is_active));
    if (params.role) searchParams.set("role", params.role);
  }
  const queryString = searchParams.toString();
  return adminRequest<PaginatedResponse<AdminUserListItem>>(
    `/api/admin/users/${queryString ? `?${queryString}` : ""}`,
    token
  );
}

/**
 * GET /api/admin/users/<id>/
 * Requires 'users.admin.view' (CanViewAdminUsers). `id` is the auth user pk.
 */
export async function getAdminUserDetail(
  token: string,
  id: number | string
): Promise<AdminUserDetail> {
  return adminRequest<AdminUserDetail>(`/api/admin/users/${id}/`, token);
}

/**
 * PATCH /api/admin/users/<id>/
 * Requires 'users.admin.manage' (CanManageAdminUsers).
 *
 * AdminUserDetailAPIView.patch enforces, in order and independently of this
 * client: only a Super Administrator may modify a Super Administrator account
 * or grant/revoke SUPER_ADMINISTRATOR or any protected role; nobody may change
 * their OWN roles; and the last active Super Administrator cannot be
 * deactivated. Each refusal is a 403 (or 400 for the last-superadmin rule) that
 * the console surfaces verbatim rather than pre-empting.
 *
 * Returns the full updated AdminUserDetail, which the caller should treat as
 * authoritative instead of optimistically guessing the resulting state.
 */
export async function updateAdminUser(
  token: string,
  id: number | string,
  payload: AdminUserUpdatePayload
): Promise<AdminUserDetail> {
  return adminRequest<AdminUserDetail>(`/api/admin/users/${id}/`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/**
 * The writable surface of AdminUserCreateSerializer, in full.
 *
 * `password_confirm` is required by the backend purely as a client-input
 * safeguard — it is never persisted. `reason` is required and written to the
 * AuditLog entry, exactly like AdminUserUpdatePayload.
 */
export interface AdminUserCreatePayload {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
  first_name?: string;
  last_name?: string;
  /** Defaults to true server-side when omitted. */
  is_active?: boolean;
  /** Role codes to assign atomically with creation. */
  roles?: string[];
  reason: string;
}

/**
 * POST /api/admin/users/ -> 201 with the created AdminUserDetail.
 * Requires 'users.admin.manage' (CanManageAdminUsers).
 *
 * AdminUserListAPIView.post enforces the same anti-escalation rules as
 * updateAdminUser's PATCH path, evaluated against an empty starting role set:
 * only a Super Administrator may include SUPER_ADMINISTRATOR or any protected
 * role code in `roles`. This client does not pre-empt that decision — a 403
 * here is the backend's, surfaced verbatim.
 */
export async function createAdminUser(
  token: string,
  payload: AdminUserCreatePayload
): Promise<AdminUserDetail> {
  return adminRequest<AdminUserDetail>("/api/admin/users/", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * Mirrors AdminRoleSerializer field-for-field.
 *
 * `permissions` is a flat list of Permission.code strings — the role's grants
 * via RolePermission, which is the only permission-bearing relation MiniShop
 * RBAC uses for roles.
 */
export interface AdminRole {
  id: number;
  /** Machine-readable unique code, e.g. "OPERATION_MANAGER". Immutable after creation. */
  code: string;
  name: string;
  description: string;
  is_active: boolean;
  /**
   * True for the codes in PROTECTED_ROLE_CODES (SUPER_ADMINISTRATOR,
   * ADMINISTRATOR). The backend refuses to update or delete these for ANY
   * caller, superuser included, so the console offers no such control.
   */
  is_protected: boolean;
  permissions: string[];
  /** Count of ACTIVE UserRole rows — the role's current holders. */
  user_count: number;
  created_at: string;
  updated_at: string;
}

/** The writable surface of AdminRoleCreateSerializer, in full. */
export interface AdminRoleCreatePayload {
  /** Upper-cased by the backend; must be unique and not a protected code. */
  code: string;
  name: string;
  description?: string;
  /** Permission codes. Every one is re-validated against the actor's delegation boundary. */
  permissions?: string[];
  reason: string;
}

/**
 * The writable surface of AdminRoleUpdateSerializer, in full.
 *
 * `code` is absent because the serializer has no such field — a role's code is
 * fixed once created. Supplying `permissions` REPLACES the role's entire grant
 * set (the view deletes every RolePermission row and recreates it), so omit the
 * key unless the permission set is genuinely being changed.
 */
export interface AdminRoleUpdatePayload {
  name?: string;
  description?: string;
  is_active?: boolean;
  permissions?: string[];
  reason: string;
}

/**
 * GET /api/admin/roles/
 * Requires 'roles.admin.view' (CanViewAdminRoles).
 *
 * Returns a PLAIN ARRAY of every role, not a paginated envelope:
 * AdminRoleListCreateAPIView.get applies no paginator, and no search or filter
 * query parameter is read. The response is therefore always the complete role
 * set, which is what lets the roles page filter it client-side without
 * misrepresenting a single server page as the whole result.
 */
export async function getAdminRoles(token: string): Promise<AdminRole[]> {
  return adminRequest<AdminRole[]>("/api/admin/roles/", token);
}

/** GET /api/admin/roles/<id>/ -> CanViewAdminRoles. */
export async function getAdminRoleDetail(
  token: string,
  id: number | string
): Promise<AdminRole> {
  return adminRequest<AdminRole>(`/api/admin/roles/${id}/`, token);
}

/**
 * POST /api/admin/roles/ -> 201 with the created AdminRole.
 * Requires 'roles.admin.manage' (CanManageAdminRoles).
 *
 * The view rejects with 403 any requested permission outside the caller's
 * delegation boundary (rbac.services.get_undelegatable_permission_codes), and
 * the serializer rejects a protected code with 400. Both are backend-side and
 * are not reimplemented here.
 */
export async function createAdminRole(
  token: string,
  payload: AdminRoleCreatePayload
): Promise<AdminRole> {
  return adminRequest<AdminRole>("/api/admin/roles/", token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/**
 * PATCH /api/admin/roles/<id>/ -> the updated AdminRole.
 * Requires 'roles.admin.manage'; refuses protected roles outright with 403.
 */
export async function updateAdminRole(
  token: string,
  id: number | string,
  payload: AdminRoleUpdatePayload
): Promise<AdminRole> {
  return adminRequest<AdminRole>(`/api/admin/roles/${id}/`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

/**
 * DELETE /api/admin/roles/<id>/ — a HARD delete, not a deactivation.
 *
 * The backend refuses with 403 for a protected role and with 400 when the role
 * is still assigned to any active user. Success is 200 with {"detail": "..."}
 * (not 204). Deactivating via PATCH { is_active: false } is the reversible
 * alternative for a role that is still in use.
 */
export async function deleteAdminRole(
  token: string,
  id: number | string
): Promise<{ detail: string }> {
  return adminRequest<{ detail: string }>(`/api/admin/roles/${id}/`, token, {
    method: "DELETE",
  });
}

/**
 * One row of the permission catalogue. Mirrors AdminPermissionSerializer.
 *
 * `is_delegatable` is a property of the (REQUESTING USER, permission) pair, not
 * of the permission — it answers "may the caller grant this to a role?" and is
 * computed by rbac.services.get_delegatable_permission_codes, the same boundary
 * the role create/update endpoints enforce.
 */
export interface AdminPermission {
  id: number;
  /** "<resource>.<action>", e.g. "sellers.create". */
  code: string;
  name: string;
  /** Grouping key for the selector, e.g. "sellers". */
  resource: string;
  action: string;
  description: string;
  is_delegatable: boolean;
}

export interface AdminPermissionCatalog {
  count: number;
  /** True when the caller holds "*" and may delegate the whole catalogue. */
  has_full_platform_access: boolean;
  delegatable_count: number;
  /** Ordered by (resource, action) — Permission.Meta.ordering. */
  results: AdminPermission[];
}

/**
 * GET /api/admin/permissions/
 * Requires 'roles.admin.view' (CanViewAdminRoles).
 *
 * The source of truth for the permission selector. The catalogue is read from
 * the database, so the console never hardcodes a permission list that could
 * drift from the seeded one, and the delegation flags come from the backend, so
 * a locked checkbox always corresponds to a real 403.
 */
export async function getAdminPermissionCatalog(
  token: string
): Promise<AdminPermissionCatalog> {
  return adminRequest<AdminPermissionCatalog>("/api/admin/permissions/", token);
}

// ==============================================================================
// SELLER POINTS / WALLET (Phase 1G-C)
// ==============================================================================
//
// These are STAFF endpoints under points/urls.py, mounted at /api/points/ —
// NOT /api/admin/points/, which does not exist and is not created here. The
// `seller_id` path segment is the SellerProfile primary key (the same id
// AdminSeller.id already carries), not the auth User id: StaffSellerWalletView,
// StaffSellerHistoryView and StaffPointAdjustmentView all resolve it with
// get_object_or_404(SellerProfile, pk=seller_id).

/** Mirrors SellerWalletSerializer field-for-field. */
export interface AdminSellerWallet {
  id: number;
  seller_id: number;
  business_name: string;
  balance: number;
  created_at: string;
  updated_at: string;
}

/** Exact PointTransaction.TRANSACTION_TYPE_CHOICES values. */
export type AdminPointTransactionType =
  | "BONUS"
  | "ADMIN_CREDIT"
  | "ADMIN_DEBIT"
  | "PRODUCT_CREATION"
  | "REFUND"
  | "ADJUSTMENT";

/** Mirrors PointTransactionSerializer field-for-field. */
export interface AdminPointTransaction {
  id: number;
  wallet_id: number;
  seller_id: number;
  business_name: string;
  transaction_type: AdminPointTransactionType | string;
  transaction_type_display: string;
  /** Always a positive magnitude (PointTransaction.amount is a PositiveIntegerField); direction is balance_after vs balance_before. */
  amount: number;
  balance_before: number;
  balance_after: number;
  reason: string;
  reference_type: string;
  reference_id: string;
  /** Null when the actor account was later deleted (actor is SET_NULL). */
  actor_id: number | null;
  actor_username: string | null;
  created_at: string;
}

/**
 * GET /api/points/sellers/<seller_id>/
 * Requires 'points.view' (CanViewPoints). Creates the wallet on first read if
 * one does not exist yet (PointService.get_or_create_wallet), so this never
 * 404s for a valid seller — a brand-new seller simply has a zero balance.
 */
export async function getAdminSellerWallet(
  token: string,
  sellerId: number | string
): Promise<AdminSellerWallet> {
  return adminRequest<AdminSellerWallet>(`/api/points/sellers/${sellerId}/`, token);
}

export interface AdminSellerPointHistoryParams {
  page?: number;
  /** Exact PointTransaction.TRANSACTION_TYPE_CHOICES value. */
  type?: AdminPointTransactionType | string;
}

/**
 * GET /api/points/sellers/<seller_id>/history/
 * Requires 'points.view' (CanViewPoints).
 *
 * Paginated by DRF's default PageNumberPagination (PAGE_SIZE = 12 in
 * settings.py), not AdminPagination — the envelope shape is the same
 * {count, next, previous, results}, but the page size differs from the
 * /api/admin/* modules' 20.
 */
export async function getAdminSellerPointHistory(
  token: string,
  sellerId: number | string,
  params?: AdminSellerPointHistoryParams
): Promise<PaginatedResponse<AdminPointTransaction>> {
  const searchParams = new URLSearchParams();
  if (params?.page) searchParams.set("page", String(params.page));
  if (params?.type) searchParams.set("type", params.type);
  const queryString = searchParams.toString();
  return adminRequest<PaginatedResponse<AdminPointTransaction>>(
    `/api/points/sellers/${sellerId}/history/${queryString ? `?${queryString}` : ""}`,
    token
  );
}

/** Exactly the `action` choices accepted by PointAdjustmentRequestSerializer. */
export type AdminPointAdjustmentAction = "CREDIT" | "DEBIT";

export interface AdminPointAdjustmentPayload {
  action: AdminPointAdjustmentAction;
  /** Positive integer; the backend rejects amount <= 0 with a 400 field error. */
  amount: number;
  /** Minimum 3 characters — mandatory business justification. */
  reason: string;
  reference_type?: string;
  reference_id?: string;
}

export interface AdminPointAdjustmentResult {
  message: string;
  transaction: AdminPointTransaction;
  current_balance: number;
}

/**
 * POST /api/points/sellers/<seller_id>/adjust/
 *
 * Entry is gated by CanAdjustPoints (any one of points.add / points.deduct /
 * points.adjust, or the superuser / SUPER_ADMINISTRATOR wildcard bypass), but
 * that is NOT sufficient on its own: the view then checks the specific
 * direction via can_perform_point_action, so a caller holding only
 * 'points.add' reaches this endpoint but still gets 403 on a DEBIT request.
 * ADMIN_PERMISSIONS.pointsCredit / pointsDebit in admin-navigation.ts mirror
 * that per-direction map for the UI gate — this function performs no
 * client-side authorization decision of its own.
 *
 * On insufficient balance the backend returns 400 with a distinct shape (see
 * getInsufficientPointsInfo) rather than the generic validation-error format.
 */
export async function adjustAdminSellerPoints(
  token: string,
  sellerId: number | string,
  payload: AdminPointAdjustmentPayload
): Promise<AdminPointAdjustmentResult> {
  return adminRequest<AdminPointAdjustmentResult>(`/api/points/sellers/${sellerId}/adjust/`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** The distinct 400 body StaffPointAdjustmentView returns for InsufficientPointsError. */
export interface AdminInsufficientPointsInfo {
  /** e.g. "Insufficient points. Required: 500, available: 120." */
  error: string;
  detail: string;
  available_balance: number;
}

/**
 * Recognises the insufficient-balance 400 specifically, so the UI can show the
 * seller's real available balance instead of a generic validation message.
 *
 * extractErrorMessage (used to build AdminApiError.message for every endpoint)
 * prefers `detail` over `error`, but for THIS endpoint `detail` is the generic
 * "Seller does not have enough points for this deduction." while `error`
 * carries the actual required/available numbers — so callers that care about
 * the numbers should read err.data via this helper rather than err.message.
 * Returns null for every other error shape, including the other PointError
 * subclasses, which share the endpoint's plain {"error": "..."} 400 body but
 * carry no `available_balance`.
 */
export function getInsufficientPointsInfo(err: unknown): AdminInsufficientPointsInfo | null {
  if (!(err instanceof AdminApiError) || !err.isValidationError) return null;
  if (!err.data || typeof err.data !== "object") return null;
  const data = err.data as Record<string, unknown>;
  if (typeof data.available_balance !== "number" || typeof data.error !== "string") return null;
  return {
    error: data.error,
    detail: typeof data.detail === "string" ? data.detail : "",
    available_balance: data.available_balance,
  };
}

// ==============================================================================
// STAFF ORDER OPERATIONS (Phase 1J)
// ==============================================================================
//
// Backed entirely by the existing shop/urls.py "api/staff/orders/..." routes
// (StaffOrderListAPIView / StaffOrderDetailAPIView / StaffOrderStatusAPIView),
// mirroring StaffOrderListSerializer / StaffOrderDetailSerializer /
// StaffOrderStatusUpdateSerializer in shop/serializers.py field-for-field. No
// endpoint is invented and nothing here talks to Order/OrderItem directly —
// every mutation still goes through OrderService.transition_order_status()
// server-side.

/** Mirrors StaffOrderListSerializer.get_customer / StaffOrderDetailSerializer.get_customer. */
export interface AdminOrderCustomer {
  id: number | null;
  username: string;
  email: string;
  name: string;
  phone: string;
}

/** Mirrors StaffOrderListSerializer exactly — the concise listing shape. */
export interface AdminOrderListItem {
  id: number;
  order_number: string;
  status: string;
  customer: AdminOrderCustomer;
  subtotal: string;
  discount_total: string;
  shipping_fee: string;
  total_amount: string;
  total_items_count: number;
  /** Current payment's status, or null when the order has no payment record. */
  payment_status: string | null;
  payment_method: string | null;
  shipping_city: string;
  created_at: string;
  updated_at: string;
}

/** Mirrors StaffOrderItemSerializer exactly. */
export interface AdminOrderItem {
  id: number;
  product_id: number | null;
  product_name: string;
  product_slug: string;
  shop_id: number | null;
  shop_name: string;
  seller_id: number | null;
  seller_name: string;
  unit_price: string;
  price: string;
  quantity: number;
  line_total: string;
  subtotal: string;
  created_at: string;
}

/** Mirrors StaffOrderDetailSerializer.get_shipping_address exactly. */
export interface AdminOrderShippingAddress {
  recipient_name: string;
  phone: string;
  address_line_1: string;
  address_line_2: string;
  area: string;
  city: string;
  state: string;
  postal_code: string;
  country: string;
}

/** Mirrors StaffOrderPaymentSummarySerializer exactly. */
export interface AdminOrderPaymentSummary {
  id: number;
  payment_number: string;
  payment_method: string;
  status: string;
  amount: string;
  currency: string;
  transaction_id: string;
  provider: string;
  failure_reason: string;
  paid_at: string | null;
  is_paid: boolean;
  created_at: string;
}

/** Mirrors StaffOrderRefundSummarySerializer exactly. */
export interface AdminOrderRefundSummary {
  id: number;
  refund_number: string;
  amount: string;
  currency: string;
  status: string;
  reason: string;
  transaction_id: string;
  /** username of the staff member who processed it, or null. */
  processed_by: string | null;
  created_at: string;
}

/** Mirrors StaffOrderDetailSerializer exactly — the full operational view. */
export interface AdminOrderDetail {
  id: number;
  order_number: string;
  status: string;
  /**
   * Order.VALID_TRANSITIONS[status], computed server-side. Authoritative for
   * which status buttons the detail page may offer — prefer this over the
   * client-side mirror in orderGovernance.tsx wherever both are available,
   * since this reflects the exact instant the order was fetched.
   */
  allowed_transitions: string[];
  customer: AdminOrderCustomer;
  shipping_address: AdminOrderShippingAddress;
  items: AdminOrderItem[];
  subtotal: string;
  discount_total: string;
  shipping_fee: string;
  total_amount: string;
  total_items_count: number;
  payment: AdminOrderPaymentSummary | null;
  refunds: AdminOrderRefundSummary[];
  created_at: string;
  updated_at: string;
}

export interface AdminOrderListParams {
  page?: number;
  page_size?: number;
  /** Exact Order.STATUS_CHOICES value (PENDING/CONFIRMED/PROCESSING/SHIPPED/DELIVERED/CANCELLED). */
  status?: string;
  /** Exact Payment.STATUS_CHOICES value. */
  payment_status?: string;
  /** Matches order_number, case-insensitive (StaffOrderListAPIView). */
  search?: string;
  seller_id?: number;
  shop_id?: number;
  /** ISO yyyy-mm-dd, inclusive. */
  start_date?: string;
  /** ISO yyyy-mm-dd, inclusive. */
  end_date?: string;
}

/**
 * GET /api/staff/orders/
 * Requires 'orders.staff.view' (CanViewStaffOrders; superuser / SUPER_ADMINISTRATOR bypass).
 */
export async function getAdminOrders(
  token: string,
  params?: AdminOrderListParams
): Promise<PaginatedResponse<AdminOrderListItem>> {
  const searchParams = new URLSearchParams();
  if (params) {
    if (params.page) searchParams.set("page", String(params.page));
    if (params.page_size) searchParams.set("page_size", String(params.page_size));
    if (params.status) searchParams.set("status", params.status);
    if (params.payment_status) searchParams.set("payment_status", params.payment_status);
    if (params.search) searchParams.set("search", params.search);
    if (params.seller_id) searchParams.set("seller_id", String(params.seller_id));
    if (params.shop_id) searchParams.set("shop_id", String(params.shop_id));
    if (params.start_date) searchParams.set("start_date", params.start_date);
    if (params.end_date) searchParams.set("end_date", params.end_date);
  }
  const queryString = searchParams.toString();
  return adminRequest<PaginatedResponse<AdminOrderListItem>>(
    `/api/staff/orders/${queryString ? `?${queryString}` : ""}`,
    token
  );
}

/**
 * GET /api/staff/orders/<id>/
 * Requires 'orders.staff.view'. StaffOrderDetailAPIView accepts either the
 * numeric pk or the order_number as the lookup; the console always uses the
 * numeric id, matching every other module's `[id]` route convention.
 */
export async function getAdminOrderDetail(
  token: string,
  id: number | string
): Promise<AdminOrderDetail> {
  return adminRequest<AdminOrderDetail>(`/api/staff/orders/${id}/`, token);
}

/** Exactly the `status` choices StaffOrderStatusUpdateSerializer accepts — never PENDING, which is create-only. */
export type AdminOrderStatusValue =
  | "CONFIRMED"
  | "PROCESSING"
  | "SHIPPED"
  | "DELIVERED"
  | "CANCELLED";

export interface AdminOrderStatusPayload {
  status: AdminOrderStatusValue;
  /** Optional operational note; StaffOrderStatusUpdateSerializer also accepts an equivalent 'reason' alias, unused here. */
  note?: string;
}

/**
 * POST /api/staff/orders/<id>/status/
 * Requires 'orders.staff.update' (CanUpdateStaffOrders). The backend validates
 * the transition against Order.VALID_TRANSITIONS via order.can_transition_to()
 * independently of anything the client believes is allowed, and executes it
 * through OrderService.transition_order_status() (atomic inventory
 * release/finalization + payment refund/cancellation where applicable).
 * Returns the full StaffOrderDetailSerializer representation of the updated order.
 */
export async function updateAdminOrderStatus(
  token: string,
  id: number | string,
  payload: AdminOrderStatusPayload
): Promise<AdminOrderDetail> {
  return adminRequest<AdminOrderDetail>(`/api/staff/orders/${id}/status/`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ==============================================================================
// STAFF PAYMENT OPERATIONS (Phase 1K)
// ==============================================================================
//
// Backed entirely by the existing shop/urls.py "api/staff/payments/..." routes
// (StaffPaymentListAPIView / StaffPaymentDetailAPIView / StaffPaymentVerifyAPIView
// / StaffPaymentRefundAPIView), mirroring PaymentSerializer / RefundSerializer /
// PaymentVerifySerializer / RefundCreateSerializer in shop/serializers.py
// field-for-field. No endpoint is invented; every mutation still goes through
// PaymentService (process_payment_success / process_payment_failure /
// process_refund) server-side, which remains the sole authority on payment
// state transitions and refund eligibility/amount validation.

/** Mirrors RefundSerializer exactly. */
export interface AdminRefund {
  id: number;
  refund_number: string;
  order_id: number;
  order_number: string;
  payment_id: number;
  payment_number: string;
  amount: string;
  currency: string;
  reason: string;
  /** Refund.STATUS_CHOICES: PENDING | COMPLETED | FAILED. */
  status: string;
  processed_by_name: string;
  transaction_id: string;
  created_at: string;
  updated_at: string;
}

/**
 * Mirrors PaymentSerializer exactly — used for BOTH the list and detail staff
 * endpoints (unlike Orders, there is no separate concise/detail pair). Notably
 * carries no customer name/email/phone: the serializer only exposes
 * `order_id`/`order_number`, so the console cannot show customer identity on
 * a payment without a second request to the Orders API.
 */
export interface AdminPayment {
  id: number;
  payment_number: string;
  order_id: number;
  order_number: string;
  /** Payment.METHOD_CHOICES: CASH_ON_DELIVERY | BKASH | NAGAD | ROCKET | CARD | ONLINE. */
  payment_method: string;
  /** Payment.STATUS_CHOICES: PENDING | PROCESSING | PAID | FAILED | CANCELLED | REFUNDED | PARTIALLY_REFUNDED. */
  status: string;
  amount: string;
  currency: string;
  transaction_id: string;
  provider: string;
  failure_reason: string;
  /** Non-sensitive transaction metadata (model field docstring); never a card number, CVV, or gateway secret. */
  metadata: Record<string, unknown>;
  is_paid: boolean;
  /** Server-computed: amount minus completed refunds, floored at 0. Authoritative — never recomputed client-side. */
  refundable_amount: string;
  refunds: AdminRefund[];
  paid_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminPaymentListParams {
  page?: number;
  page_size?: number;
  /** Exact Payment.STATUS_CHOICES value. */
  status?: string;
  /** Exact Payment.METHOD_CHOICES value. */
  payment_method?: string;
  /** Matches order_number, case-insensitive (StaffPaymentListAPIView) — the only search the backend supports. */
  order_number?: string;
}

/**
 * GET /api/staff/payments/
 * Requires 'payments.view' (CanViewPayment; superuser / SUPER_ADMINISTRATOR bypass).
 */
export async function getAdminPayments(
  token: string,
  params?: AdminPaymentListParams
): Promise<PaginatedResponse<AdminPayment>> {
  const searchParams = new URLSearchParams();
  if (params) {
    if (params.page) searchParams.set("page", String(params.page));
    if (params.page_size) searchParams.set("page_size", String(params.page_size));
    if (params.status) searchParams.set("status", params.status);
    if (params.payment_method) searchParams.set("payment_method", params.payment_method);
    if (params.order_number) searchParams.set("order_number", params.order_number);
  }
  const queryString = searchParams.toString();
  return adminRequest<PaginatedResponse<AdminPayment>>(
    `/api/staff/payments/${queryString ? `?${queryString}` : ""}`,
    token
  );
}

/**
 * GET /api/staff/payments/<id>/
 * Requires 'payments.view'.
 */
export async function getAdminPaymentDetail(token: string, id: number | string): Promise<AdminPayment> {
  return adminRequest<AdminPayment>(`/api/staff/payments/${id}/`, token);
}

/** Exactly the `status` choices PaymentVerifySerializer accepts — never PENDING/PROCESSING/CANCELLED, which this endpoint cannot set. */
export type AdminPaymentVerifyStatus = "PAID" | "FAILED";

export interface AdminPaymentVerifyPayload {
  status: AdminPaymentVerifyStatus;
  /** Only meaningful (and only stored) when status is PAID — PaymentService.process_payment_success writes it, process_payment_failure does not read it. */
  transaction_id?: string;
  /** Only meaningful when status is FAILED — becomes Payment.failure_reason. */
  reason?: string;
}

/**
 * POST /api/staff/payments/<id>/verify/
 * Requires 'payments.verify' or 'payments.process' (CanVerifyPayment). The
 * backend independently validates the transition via
 * payment.can_transition_to() and rejects verifying a payment on a cancelled
 * order — nothing here decides eligibility. Returns the full updated payment
 * (PaymentSerializer), so callers can replace their local copy wholesale
 * rather than merging individual fields.
 */
export async function verifyAdminPayment(
  token: string,
  id: number | string,
  payload: AdminPaymentVerifyPayload
): Promise<AdminPayment> {
  return adminRequest<AdminPayment>(`/api/staff/payments/${id}/verify/`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export interface AdminRefundCreatePayload {
  /** Omit for a full refund of the remaining refundable amount — RefundCreateSerializer / PaymentService.process_refund default to that when absent. */
  amount?: number;
  reason?: string;
}

/**
 * POST /api/staff/payments/<id>/refund/
 * Requires 'payments.refund' or 'orders.refund' (CanRefundPayment).
 * PaymentService.process_refund is the sole authority on refund eligibility
 * (payment must be PAID or PARTIALLY_REFUNDED) and amount validation (> 0,
 * <= the server-computed remaining refundable amount) — this call never
 * pre-validates either. Returns only the created Refund (201), NOT the
 * updated Payment — callers must re-fetch the payment (getAdminPaymentDetail)
 * to observe its new status/refundable_amount, exactly as the rest of this
 * module already does wherever a mutation's response is a different resource
 * than the one displayed.
 */
export async function refundAdminPayment(
  token: string,
  id: number | string,
  payload: AdminRefundCreatePayload
): Promise<AdminRefund> {
  return adminRequest<AdminRefund>(`/api/staff/payments/${id}/refund/`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

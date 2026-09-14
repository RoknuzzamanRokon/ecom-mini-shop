import { PaginatedResponse } from "./types";

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

async function adminRequest<T>(
  endpoint: string,
  token: string,
  options: RequestInit = {}
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

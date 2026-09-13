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
    const message =
      errorBody.detail ||
      errorBody.message ||
      errorBody.error ||
      `Request failed with status ${res.status}`;
    throw new AdminApiError(message, res.status, errorBody);
  }

  return (await res.json()) as T;
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


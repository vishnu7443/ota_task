export interface ApiErrorPayload {
  error?: {
    code: string;
    message: string;
    details?: unknown;
  };
}

export class ApiClientError extends Error {
  status: number;
  code: string;
  details?: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export interface UserPublic {
  id: number;
  username: string;
  full_name: string;
  role_code: string;
  role_name: string;
  is_active: boolean;
  last_login_at?: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserPublic;
}

export interface CustomerAddress {
  id: number;
  address_type: string;
  line1: string;
  line2?: string | null;
  city: string;
  state_name: string;
  state_code: string;
  pincode: string;
}

export interface CustomerSummary {
  id: number;
  code: string;
  name: string;
  customer_type: "RETAILER" | "DISTRIBUTOR";
  gstin?: string | null;
  primary_state_name: string;
  primary_state_code: string;
  phone?: string | null;
  assigned_salesman_id?: number | null;
  default_shipping_address?: CustomerAddress | null;
}

export interface SalesmanOption {
  user_id: number;
  full_name: string;
  employee_code: string;
  territory?: string | null;
}

export interface ProductPack {
  pack_size_id: number;
  product_id: number;
  product_code: string;
  sku_code: string;
  product_name: string;
  display_name: string;
  category: string;
  hsn_code: string;
  gst_rate_bps: number;
  pack_weight_g: number;
  packets_per_carton: number;
  selling_price_paisa: number;
  available_stock_pkts: number;
  on_hand_stock_pkts: number;
}

export interface OrderSummary {
  id: number;
  order_number: string;
  client_order_id: string;
  order_date: string;
  status: string;
  has_shortage: boolean;
  customer_id: number;
  customer_code: string;
  customer_name: string;
  customer_type: string;
  place_of_supply_state_code: string;
  place_of_supply_state_name: string;
  salesman_id: number;
  salesman_name: string;
  total_packets: number;
  ordered_total_packets: number;
  taxable_total_paisa: number;
  estimated_grand_total_paisa: number;
  admin_remarks?: string | null;
  rejection_reason?: string | null;
  cancellation_reason?: string | null;
  submitted_at?: string | null;
  approved_at?: string | null;
  created_at: string;
}

export interface OrderItemDetail {
  id: number;
  pack_size_id: number;
  sku_code: string;
  display_name: string;
  hsn_code: string;
  gst_rate_bps: number;
  packets_per_carton: number;
  ordered_qty_pkts: number;
  approved_qty_pkts?: number | null;
  effective_qty_pkts: number;
  original_unit_price_paisa: number;
  unit_price_paisa: number;
  is_qty_modified: boolean;
  is_price_modified: boolean;
  line_taxable_paisa: number;
  live_on_hand_pkts: number;
  live_reserved_pkts: number;
  live_available_pkts: number;
  shortage_pkts: number;
}

export interface TaxEstimateBreakdown {
  supply_type: "INTRA_STATE" | "INTER_STATE";
  factory_state_code: string;
  place_of_supply_state_code: string;
  taxable_total_paisa: number;
  cgst_total_paisa: number;
  sgst_total_paisa: number;
  igst_total_paisa: number;
  grand_total_paisa: number;
}

export interface StatusHistoryEntry {
  id: number;
  from_status?: string | null;
  to_status: string;
  changed_by_name: string;
  reason?: string | null;
  changed_at: string;
}

export interface OrderApprovalRecord {
  id: number;
  decision: string;
  reviewed_by_name: string;
  ordered_total_pkts: number;
  available_total_pkts: number;
  shortage_pkts: number;
  stock_snapshot: Record<string, unknown>;
  remarks?: string | null;
  decided_at: string;
}

export interface StockReservationRecord {
  id: number;
  sales_order_item_id: number;
  pack_size_id: number;
  sku_code: string;
  reserved_qty_pkts: number;
  status: "ACTIVE" | "RELEASED" | "FULFILLED";
  reserved_by_name: string;
  reserved_at: string;
  released_by_name?: string | null;
  released_at?: string | null;
  release_reason?: string | null;
}

export interface OrderAuditEntry {
  id: number;
  actor_user_id?: number | null;
  actor_name: string;
  actor_role: string;
  action: string;
  entity_table: string;
  entity_id: number;
  before_state?: Record<string, unknown> | null;
  after_state?: Record<string, unknown> | null;
  reason?: string | null;
  occurred_at: string;
}

export interface OrderDetail extends OrderSummary {
  version: number;
  customer_gstin?: string | null;
  customer_phone?: string | null;
  salesman_employee_code?: string | null;
  salesman_territory?: string | null;
  notes?: string | null;
  approved_by_name?: string | null;
  rejected_by_name?: string | null;
  rejected_at?: string | null;
  cancelled_by_name?: string | null;
  cancelled_at?: string | null;
  is_duplicate_replay: boolean;
  tax_estimate: TaxEstimateBreakdown;
  items: OrderItemDetail[];
  status_history: StatusHistoryEntry[];
  approvals: OrderApprovalRecord[];
  reservations: StockReservationRecord[];
  audit_trail: OrderAuditEntry[];
}

export interface PaginatedOrders {
  items: OrderSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AdminOrdersSummary {
  total_count: number;
  submitted_count: number;
  under_review_count: number;
  correction_requested_count: number;
  pending_verification_count: number;
  approved_count: number;
  rejected_count: number;
  cancelled_count: number;
  shortage_count: number;
  pending_value_paisa: number;
  approved_value_paisa: number;
}

export interface CreateOrderPayload {
  customer_id: number;
  client_order_id: string;
  notes?: string | null;
  items: Array<{ pack_size_id: number; ordered_qty_pkts: number }>;
}

export interface SalesmanResubmitPayload {
  notes?: string | null;
  items: Array<{ pack_size_id: number; ordered_qty_pkts: number }>;
}

export interface AdminModifyOrderPayload {
  items: Array<{
    id: number;
    approved_qty_pkts: number;
    unit_price_paisa: number;
  }>;
  admin_remarks?: string | null;
  reason?: string | null;
  expected_version?: number;
}

export interface AdminReviewHoldPayload {
  admin_remarks?: string | null;
  reason?: string | null;
  expected_version?: number;
}

export interface AdminApprovePayload {
  admin_remarks?: string | null;
  reason?: string | null;
  expected_version?: number;
}

export interface AdminReasonPayload {
  reason: string;
  admin_remarks?: string | null;
  expected_version?: number;
}

const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) || "http://localhost:8000/api/v1";

const TOKEN_STORAGE_KEY = "ota_access_token";

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setStoredToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (networkErr) {
    throw new ApiClientError(
      0,
      "NETWORK_ERROR",
      "Unable to reach factory server. Check your connection and retry.",
      networkErr
    );
  }

  if (!res.ok) {
    let payload: ApiErrorPayload | null = null;
    try {
      payload = (await res.json()) as ApiErrorPayload;
    } catch {
      payload = null;
    }
    const errCode = payload?.error?.code ?? `HTTP_${res.status}`;
    const errMsg = payload?.error?.message ?? `Request failed with status ${res.status}.`;
    throw new ApiClientError(res.status, errCode, errMsg, payload?.error?.details);
  }

  return (await res.json()) as T;
}

export const api = {
  login: (username: string, password: string) =>
    request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  getMe: () => request<UserPublic>("/auth/me"),
  getCustomers: (search?: string) => {
    const q = search ? `?search=${encodeURIComponent(search)}` : "";
    return request<CustomerSummary[]>(`/sales/customers${q}`);
  },
  getProducts: (customerId?: number) => {
    const q = customerId ? `?customer_id=${customerId}` : "";
    return request<ProductPack[]>(`/sales/products${q}`);
  },
  getSalesmen: () => request<SalesmanOption[]>("/sales/salesmen"),
  submitOrder: (payload: CreateOrderPayload) =>
    request<OrderDetail>("/orders", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getMyOrders: (page = 1, pageSize = 20, status?: string, search?: string) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status) params.set("status", status);
    if (search) params.set("search", search);
    return request<PaginatedOrders>(`/orders/my?${params.toString()}`);
  },
  getOrderDetail: (orderId: number) => request<OrderDetail>(`/orders/${orderId}`),
  resubmitSalesmanOrder: (orderId: number, payload: SalesmanResubmitPayload) =>
    request<OrderDetail>(`/orders/${orderId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  cancelSalesmanOrder: (orderId: number, reason: string) =>
    request<OrderDetail>(`/orders/${orderId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  getAdminOrdersSummary: () => request<AdminOrdersSummary>("/admin/orders/summary"),
  getAdminOrders: (opts: {
    page?: number;
    pageSize?: number;
    status?: string;
    pendingVerification?: boolean;
    customerId?: number | null;
    salesmanId?: number | null;
    dateFrom?: string;
    dateTo?: string;
    hasShortage?: boolean | null;
    search?: string;
  }) => {
    const params = new URLSearchParams({
      page: String(opts.page ?? 1),
      page_size: String(opts.pageSize ?? 20),
    });
    if (opts.status) params.set("status", opts.status);
    if (opts.pendingVerification) params.set("pending_verification", "true");
    if (opts.customerId) params.set("customer_id", String(opts.customerId));
    if (opts.salesmanId) params.set("salesman_id", String(opts.salesmanId));
    if (opts.dateFrom) params.set("date_from", opts.dateFrom);
    if (opts.dateTo) params.set("date_to", opts.dateTo);
    if (opts.hasShortage !== null && opts.hasShortage !== undefined) {
      params.set("has_shortage", String(opts.hasShortage));
    }
    if (opts.search) params.set("search", opts.search);
    return request<PaginatedOrders>(`/admin/orders?${params.toString()}`);
  },
  getAdminOrderDetail: (orderId: number) => request<OrderDetail>(`/admin/orders/${orderId}`),
  modifyAdminOrder: (orderId: number, payload: AdminModifyOrderPayload) =>
    request<OrderDetail>(`/admin/orders/${orderId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  holdOrderUnderReview: (orderId: number, payload: AdminReviewHoldPayload) =>
    request<OrderDetail>(`/admin/orders/${orderId}/review`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  requestOrderCorrection: (orderId: number, payload: AdminReasonPayload) =>
    request<OrderDetail>(`/admin/orders/${orderId}/request-correction`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  approveAdminOrder: (orderId: number, payload: AdminApprovePayload) =>
    request<OrderDetail>(`/admin/orders/${orderId}/approve`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  rejectAdminOrder: (orderId: number, payload: AdminReasonPayload) =>
    request<OrderDetail>(`/admin/orders/${orderId}/reject`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  cancelAdminOrder: (orderId: number, payload: AdminReasonPayload) =>
    request<OrderDetail>(`/admin/orders/${orderId}/cancel`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

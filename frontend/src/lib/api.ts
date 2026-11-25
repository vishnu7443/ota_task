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
  invoice_id?: number | null;
  invoice_number?: string | null;
  invoice_doc_status?: string | null;
  invoice_dispatch_status?: string | null;
  invoice_paid_paisa?: number | null;
  invoice_outstanding_paisa?: number | null;
  invoice_payment_status?: string | null;
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

export interface OrderDispatchTrackingItem {
  id: number;
  dispatch_number: string;
  status: string;
  dispatch_date: string;
  delivery_date?: string | null;
  vehicle_number?: string | null;
  transporter_name?: string | null;
  total_dispatched_pkts: number;
  total_received_pkts: number;
  delivery_remarks?: string | null;
  delivery_exception_reason?: string | null;
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
  invoice_grand_total_paisa?: number | null;
  tax_estimate: TaxEstimateBreakdown;
  items: OrderItemDetail[];
  status_history: StatusHistoryEntry[];
  approvals: OrderApprovalRecord[];
  reservations: StockReservationRecord[];
  audit_trail: OrderAuditEntry[];
  dispatches?: OrderDispatchTrackingItem[];
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

// --- Phase 6: Purchasing & Inventory Interfaces ---

export interface Supplier {
  id: number;
  code: string;
  name: string;
  contact_person: string | null;
  phone: string | null;
  email: string | null;
  gstin: string | null;
  state_name: string;
  state_code: string;
  address: string;
  is_active: boolean;
  po_count: number;
  receipt_count: number;
  total_purchased_paisa: number;
  created_at: string;
  updated_at: string;
}

export interface SupplierCreatePayload {
  code: string;
  name: string;
  contact_person?: string | null;
  phone?: string | null;
  email?: string | null;
  gstin?: string | null;
  state_name: string;
  state_code: string;
  address: string;
  is_active?: boolean;
}

export interface SupplierUpdatePayload {
  name: string;
  contact_person?: string | null;
  phone?: string | null;
  email?: string | null;
  gstin?: string | null;
  state_name: string;
  state_code: string;
  address: string;
  is_active: boolean;
}

export interface PurchaseOrderItem {
  id: number;
  material_id: number;
  material_code: string;
  material_name: string;
  material_category: string;
  base_uom: string;
  display_uom: string;
  entered_qty: string;
  entered_uom: string;
  ordered_qty_base: string;
  received_qty_base: string;
  rejected_qty_base: string;
  remaining_qty_base: string;
  unit_rate_paisa: number;
  gst_rate_bps: number;
  line_subtotal_paisa: number;
  line_tax_paisa: number;
  line_total_paisa: number;
}

export interface PurchaseOrderSummary {
  id: number;
  po_number: string;
  supplier_id: number;
  supplier_code: string;
  supplier_name: string;
  order_date: string;
  expected_date: string | null;
  status: string;
  subtotal_paisa: number;
  tax_paisa: number;
  total_paisa: number;
  notes: string | null;
  rejection_reason: string | null;
  created_by_name: string;
  approved_by_name: string | null;
  approved_at: string | null;
  created_at: string;
  item_count: number;
}

export interface GoodsReceiptItem {
  id: number;
  purchase_order_item_id: number | null;
  material_id: number;
  material_code: string;
  material_name: string;
  base_uom: string;
  display_uom: string;
  entered_uom: string;
  received_qty_entered: string;
  rejected_qty_entered: string;
  accepted_qty_entered: string;
  received_qty_base: string;
  rejected_qty_base: string;
  accepted_qty_base: string;
  entered_unit_rate_paisa: number;
  gst_rate_bps: number;
  unit_cost_paisa_per_base: string;
  line_subtotal_paisa: number;
  line_tax_paisa: number;
  line_total_paisa: number;
  batch_code: string | null;
  expiry_date: string | null;
  rejection_reason: string | null;
}

export interface GoodsReceiptSummary {
  id: number;
  receipt_number: string;
  client_receipt_id: string;
  purchase_order_id: number | null;
  po_number: string | null;
  supplier_id: number;
  supplier_code: string;
  supplier_name: string;
  supplier_bill_ref: string | null;
  receipt_date: string;
  status: string;
  subtotal_paisa: number;
  input_gst_paisa: number;
  total_paisa: number;
  discrepancy_notes: string | null;
  is_duplicate_replay: boolean;
  received_by_name: string;
  verified_by_name: string | null;
  posted_by_name: string | null;
  posted_at: string | null;
  created_at: string;
}

export interface GoodsReceiptDetail extends GoodsReceiptSummary {
  items: GoodsReceiptItem[];
}

export interface PurchaseOrderDetail extends PurchaseOrderSummary {
  items: PurchaseOrderItem[];
  receipts: GoodsReceiptSummary[];
}

export interface SupplierDetail extends Supplier {
  purchase_orders: PurchaseOrderSummary[];
  purchase_receipts: GoodsReceiptSummary[];
}

export interface PurchaseOrderCreatePayload {
  supplier_id: number;
  order_date?: string | null;
  expected_date?: string | null;
  notes?: string | null;
  submit_immediately?: boolean;
  items: Array<{
    material_id: number;
    entered_qty: string | number;
    entered_uom: string;
    unit_rate_paisa: number;
    gst_rate_bps: number;
  }>;
}

export interface GoodsReceiptCreatePayload {
  client_receipt_id: string;
  purchase_order_id?: number | null;
  supplier_id?: number | null;
  supplier_bill_ref?: string | null;
  receipt_date?: string | null;
  discrepancy_notes?: string | null;
  submit_immediately?: boolean;
  items: Array<{
    purchase_order_item_id?: number | null;
    material_id: number;
    entered_uom: string;
    received_qty_entered: string | number;
    rejected_qty_entered?: string | number;
    unit_rate_paisa?: number | null;
    gst_rate_bps?: number | null;
    batch_code?: string | null;
    expiry_date?: string | null;
    rejection_reason?: string | null;
    allow_excess?: boolean;
  }>;
}

export interface MaterialSummary {
  id: number;
  code: string;
  name: string;
  material_category: string;
  unit_dimension: string;
  base_uom: string;
  display_uom: string;
  reorder_level_base: string;
  is_active: boolean;
}

export interface InventoryBalanceSummary {
  item_type: "MATERIAL" | "PACK_SIZE";
  item_id: number;
  item_category: "RAW_MATERIAL" | "PACKAGING_MATERIAL" | "FINISHED_GOOD";
  code: string;
  name: string;
  unit_dimension: string;
  base_uom: string;
  display_uom: string;
  display_factor: string;
  reorder_level_base: string;
  opening_qty_base: string;
  received_qty_base: string;
  issued_qty_base: string;
  dispatched_qty_base: string;
  adjusted_qty_base: string;
  physical_qty_base: string;
  reserved_qty_base: string;
  available_qty_base: string;
  is_low_stock: boolean;
  open_lot_value_paisa: number;
}

export interface InventoryDashboardData {
  total_items: number;
  raw_material_count: number;
  packaging_material_count: number;
  finished_good_count: number;
  low_stock_count: number;
  pending_adjustments_count: number;
  total_stock_value_paisa: number;
  items: InventoryBalanceSummary[];
}

export interface InventoryLedgerEntry {
  id: number;
  occurred_at: string;
  item_category: string;
  item_type: string;
  item_id: number;
  item_code: string;
  item_name: string;
  base_uom: string;
  display_uom: string;
  movement_type: string;
  entered_qty: string | null;
  entered_uom: string | null;
  signed_qty_base: string;
  unit_cost_paisa_per_base: string;
  total_cost_paisa: number;
  source_doc_type: string;
  reference_code: string | null;
  notes: string | null;
  actor_name: string;
  opening_balance_id: number | null;
  purchase_receipt_item_id: number | null;
  stock_adjustment_id: number | null;
  production_run_id: number | null;
  dispatch_item_id: number | null;
  credit_note_item_id: number | null;
  dispatch_id: number | null;
  invoice_id: number | null;
}

export interface ProductSummary {
  id: number;
  product_code: string;
  name: string;
  category: string;
  hsn_code: string;
  gst_rate_bps: number;
  is_active: boolean;
}

export interface PackSizeOption {
  id: number;
  product_id: number;
  product_code: string;
  product_name: string;
  sku_code: string;
  display_name: string;
  pack_weight_g: number;
  packets_per_carton: number;
  base_selling_price_paisa: number;
  is_active: boolean;
  has_active_bom: boolean;
  active_bom_version_no: number | null;
}

export interface RecipeTemplate {
  id: number;
  code: string;
  name: string;
  product_id: number | null;
  base_yield_weight_g: string;
  notes: string | null;
  is_active: boolean;
}

export interface ProductionCatalog {
  products: ProductSummary[];
  pack_sizes: PackSizeOption[];
  recipe_templates: RecipeTemplate[];
}

export interface BomComponent {
  id: number;
  material_id: number;
  material_code: string;
  material_name: string;
  material_category: string;
  unit_dimension: string;
  input_role: string;
  std_qty_base: string;
  display_qty: string;
  display_uom: string;
  base_uom: string;
  sort_order: number;
}

export interface BomVersion {
  id: number;
  bom_header_id: number;
  version_no: number;
  recipe_template_id: number | null;
  recipe_template_name: string | null;
  expected_yield_pkts: number;
  batch_multiplier: string;
  status: string;
  effective_date: string | null;
  notes: string | null;
  created_by_name: string;
  activated_by_name: string | null;
  activated_at: string | null;
  created_at: string;
  run_count: number;
  is_locked: boolean;
  components: BomComponent[];
}

export interface BomHeader {
  id: number;
  pack_size_id: number;
  sku_code: string;
  display_name: string;
  product_id: number;
  product_name: string;
  pack_weight_g: number;
  packets_per_carton: number;
  active_version_id: number | null;
  active_version: BomVersion | null;
  all_versions: BomVersion[];
}

export interface MaterialRequirement {
  material_id: number;
  material_code: string;
  material_name: string;
  material_category: string;
  unit_dimension: string;
  input_role: string;
  bom_std_qty_base: string;
  exact_scaled_qty_base: string;
  standard_qty_base: string;
  was_rounded_up: boolean;
  rounding_note: string | null;
  display_qty: string;
  display_uom: string;
  base_uom: string;
  display_factor: string;
  on_hand_qty_base: string;
  reserved_qty_base: string;
  available_qty_base: string;
  additional_required_base: string;
  is_shortage: boolean;
}

export interface BomCalculation {
  pack_size_id: number;
  sku_code: string;
  display_name: string;
  bom_version_id: number;
  version_no: number;
  batch_multiplier: string;
  expected_output_pkts: number;
  requirements: MaterialRequirement[];
  has_shortages: boolean;
  shortage_summary: string;
}

export interface ProductionMaterialIssue {
  id: number;
  material_id: number;
  material_code: string;
  material_name: string;
  material_category: string;
  issue_phase: string;
  planned_qty_base: string;
  issued_qty_base: string;
  actual_consumed_qty_base: string;
  actual_good_used_base: string;
  damaged_qty_base: string;
  returned_unused_qty_base: string;
  wasted_qty_base: string;
  cost_absorbed_paisa: number;
  display_uom: string;
  base_uom: string;
  display_factor: string;
  available_qty_base: string;
  issued_by_name: string | null;
  issued_at: string | null;
}

export interface ProductionOutput {
  id: number;
  good_qty_pkts: number;
  rejected_qty_pkts: number;
  total_qty_pkts: number;
  batch_code: string;
  expiry_date: string | null;
  quality_remarks: string | null;
  recorded_by_name: string;
  recorded_at: string;
}

export interface ProductionWastage {
  id: number;
  material_id: number | null;
  material_code: string | null;
  material_name: string | null;
  pack_size_id: number | null;
  wastage_type: string;
  qty_base: string;
  uom: string;
  cost_impact_paisa: number;
  reason: string;
  recorded_by_name: string;
  recorded_at: string;
}

export interface ProductionVariance {
  id: number;
  variance_scope: string;
  material_id: number | null;
  material_code: string | null;
  material_name: string | null;
  planned_qty_base: string;
  actual_qty_base: string;
  variance_qty_base: string;
  variance_pct: string | null;
  tolerance_pct: string;
  is_flagged: boolean;
  formula_explanation: string;
  display_uom: string;
  base_uom: string;
  display_factor: string;
  computed_at: string;
}

export interface VarianceAlert {
  id: number;
  production_run_id: number;
  run_number: string;
  sku_code: string;
  production_variance_id: number;
  alert_type: string;
  message: string;
  status: string;
  acknowledged_by_name: string | null;
  acknowledged_at: string | null;
  acknowledgement_note: string | null;
  created_at: string;
}

export interface ProductionRunDetail {
  id: number;
  run_number: string;
  pack_size_id: number;
  sku_code: string;
  display_name: string;
  packets_per_carton: number;
  bom_version_id: number;
  version_no: number;
  bom_status: string;
  bom_expected_yield_pkts: number;
  batch_multiplier: string;
  expected_output_pkts: number;
  actual_good_output_pkts: number;
  rejected_output_pkts: number;
  status: string;
  run_date: string;
  planned_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  posted_at: string | null;
  cancelled_at: string | null;
  supervisor_name: string;
  posted_by_name: string | null;
  quality_remarks: string | null;
  notes: string | null;
  total_material_cost_paisa: number;
  material_issues: ProductionMaterialIssue[];
  outputs: ProductionOutput[];
  wastages: ProductionWastage[];
  variances: ProductionVariance[];
  alerts: VarianceAlert[];
}

export interface ProductionRunSummary {
  id: number;
  run_number: string;
  pack_size_id: number;
  sku_code: string;
  display_name: string;
  bom_version_id: number;
  version_no: number;
  batch_multiplier: string;
  expected_output_pkts: number;
  actual_good_output_pkts: number;
  rejected_output_pkts: number;
  status: string;
  run_date: string;
  supervisor_name: string;
  has_flagged_variance: boolean;
  open_alert_count: number;
  damaged_packaging_qty: string;
}

export interface ShortageItem {
  material_id: number;
  material_code: string;
  material_name: string;
  display_uom: string;
  base_uom: string;
  display_factor: string;
  required_qty_base: string;
  available_qty_base: string;
  shortage_qty_base: string;
}

export interface ProductionDashboardData {
  total_runs: number;
  draft_count: number;
  planned_count: number;
  in_progress_count: number;
  completed_count: number;
  posted_count: number;
  cancelled_count: number;
  total_expected_output_pkts: number;
  total_good_output_pkts: number;
  total_rejected_output_pkts: number;
  total_damaged_packaging_units: string;
  flagged_variance_count: number;
  open_alerts_count: number;
  upcoming_shortages: ShortageItem[];
  open_alerts: VarianceAlert[];
  runs: ProductionRunSummary[];
}

export interface ProductionVarianceReportRow {
  run_id: number;
  run_number: string;
  run_date: string;
  sku_code: string;
  display_name: string;
  bom_version_no: number;
  batch_multiplier: string;
  expected_output_pkts: number;
  actual_good_output_pkts: number;
  rejected_output_pkts: number;
  yield_variance_pct: string | null;
  oil_variance_pct: string | null;
  damaged_packaging_qty: string;
  status: string;
  flagged_count: number;
}

export interface StockAdjustment {
  id: number;
  adjustment_number: string;
  item_category: string;
  item_type: string;
  item_id: number;
  item_code: string;
  item_name: string;
  base_uom: string;
  display_uom: string;
  adjustment_type: string;
  entered_qty: string;
  entered_uom: string;
  delta_qty_base: string;
  unit_cost_paisa_per_base: string;
  reason: string;
  status: string;
  requested_by_name: string;
  approved_by_name: string | null;
  rejection_reason: string | null;
  requested_at: string;
  posted_at: string | null;
}

export interface StockAdjustmentCreatePayload {
  item_type: "MATERIAL" | "PACK_SIZE";
  item_id: number;
  adjustment_type: "DAMAGED" | "EXPIRED" | "MISSING" | "COUNT_CORRECTION" | "SUPPLIER_RETURN" | "OTHER";
  entered_qty: string | number;
  entered_uom: string;
  unit_cost_paisa_per_base?: number | null;
  reason: string;
  post_immediately?: boolean;
}

export interface PurchaseReceiptReportRow {
  receipt_id: number;
  receipt_number: string;
  receipt_date: string;
  po_number: string | null;
  supplier_code: string;
  supplier_name: string;
  material_code: string;
  material_name: string;
  entered_uom: string;
  received_qty_entered: string;
  rejected_qty_entered: string;
  accepted_qty_entered: string;
  accepted_qty_base: string;
  base_uom: string;
  entered_unit_rate_paisa: number;
  line_total_paisa: number;
  batch_code: string | null;
  status: string;
}

export interface StockReportsSummary {
  current_stock: InventoryBalanceSummary[];
  low_stock_items: InventoryBalanceSummary[];
  purchase_receipts: PurchaseReceiptReportRow[];
  adjustments: StockAdjustment[];
}

const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) || "/api/v1";

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

  // --- Phase 6: Suppliers, Purchase Orders, Goods Receipts ---
  getSuppliers: (opts?: { activeOnly?: boolean; search?: string }) => {
    const params = new URLSearchParams();
    if (opts?.activeOnly) params.set("active_only", "true");
    if (opts?.search) params.set("search", opts.search);
    const qs = params.toString();
    return request<Supplier[]>(`/purchasing/suppliers${qs ? `?${qs}` : ""}`);
  },
  getSupplierDetail: (supplierId: number) =>
    request<SupplierDetail>(`/purchasing/suppliers/${supplierId}`),
  createSupplier: (payload: SupplierCreatePayload) =>
    request<Supplier>("/purchasing/suppliers", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateSupplier: (supplierId: number, payload: SupplierUpdatePayload) =>
    request<Supplier>(`/purchasing/suppliers/${supplierId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),

  getPurchaseOrders: (opts?: { supplierId?: number; status?: string; search?: string }) => {
    const params = new URLSearchParams();
    if (opts?.supplierId) params.set("supplier_id", String(opts.supplierId));
    if (opts?.status) params.set("status", opts.status);
    if (opts?.search) params.set("search", opts.search);
    const qs = params.toString();
    return request<PurchaseOrderSummary[]>(`/purchasing/orders${qs ? `?${qs}` : ""}`);
  },
  getPurchaseOrderDetail: (poId: number) =>
    request<PurchaseOrderDetail>(`/purchasing/orders/${poId}`),
  createPurchaseOrder: (payload: PurchaseOrderCreatePayload) =>
    request<PurchaseOrderDetail>("/purchasing/orders", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  submitPurchaseOrder: (poId: number) =>
    request<PurchaseOrderDetail>(`/purchasing/orders/${poId}/submit`, { method: "POST" }),
  approvePurchaseOrder: (poId: number) =>
    request<PurchaseOrderDetail>(`/purchasing/orders/${poId}/approve`, { method: "POST" }),
  rejectPurchaseOrder: (poId: number, reason: string) =>
    request<PurchaseOrderDetail>(`/purchasing/orders/${poId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  cancelPurchaseOrder: (poId: number, reason: string) =>
    request<PurchaseOrderDetail>(`/purchasing/orders/${poId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  getGoodsReceipts: (opts?: {
    supplierId?: number;
    purchaseOrderId?: number;
    status?: string;
    dateFrom?: string;
    dateTo?: string;
    search?: string;
  }) => {
    const params = new URLSearchParams();
    if (opts?.supplierId) params.set("supplier_id", String(opts.supplierId));
    if (opts?.purchaseOrderId) params.set("purchase_order_id", String(opts.purchaseOrderId));
    if (opts?.status) params.set("status", opts.status);
    if (opts?.dateFrom) params.set("date_from", opts.dateFrom);
    if (opts?.dateTo) params.set("date_to", opts.dateTo);
    if (opts?.search) params.set("search", opts.search);
    const qs = params.toString();
    return request<GoodsReceiptSummary[]>(`/purchasing/receipts${qs ? `?${qs}` : ""}`);
  },
  getGoodsReceiptDetail: (receiptId: number) =>
    request<GoodsReceiptDetail>(`/purchasing/receipts/${receiptId}`),
  createGoodsReceipt: (payload: GoodsReceiptCreatePayload) =>
    request<GoodsReceiptDetail>("/purchasing/receipts", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  submitGoodsReceipt: (receiptId: number) =>
    request<GoodsReceiptDetail>(`/purchasing/receipts/${receiptId}/submit`, { method: "POST" }),
  verifyGoodsReceipt: (receiptId: number) =>
    request<GoodsReceiptDetail>(`/purchasing/receipts/${receiptId}/verify`, { method: "POST" }),
  postGoodsReceipt: (receiptId: number) =>
    request<GoodsReceiptDetail>(`/purchasing/receipts/${receiptId}/post`, { method: "POST" }),

  // --- Phase 6: Inventory, Ledger, Adjustments & Stock Reports ---
  getMaterials: (opts?: { category?: string; search?: string }) => {
    const params = new URLSearchParams();
    if (opts?.category) params.set("category", opts.category);
    if (opts?.search) params.set("search", opts.search);
    const qs = params.toString();
    return request<MaterialSummary[]>(`/inventory/materials${qs ? `?${qs}` : ""}`);
  },
  getInventoryOverview: (opts?: {
    itemCategory?: string;
    lowStockOnly?: boolean;
    search?: string;
  }) => {
    const params = new URLSearchParams();
    if (opts?.itemCategory) params.set("item_category", opts.itemCategory);
    if (opts?.lowStockOnly) params.set("low_stock_only", "true");
    if (opts?.search) params.set("search", opts.search);
    const qs = params.toString();
    return request<InventoryDashboardData>(`/inventory/overview${qs ? `?${qs}` : ""}`);
  },
  getInventoryLedger: (opts?: {
    itemCategory?: string;
    materialId?: number;
    packSizeId?: number;
    productionRunId?: number;
    movementType?: string;
    dateFrom?: string;
    dateTo?: string;
    limit?: number;
  }) => {
    const params = new URLSearchParams();
    if (opts?.itemCategory) params.set("item_category", opts.itemCategory);
    if (opts?.materialId) params.set("material_id", String(opts.materialId));
    if (opts?.packSizeId) params.set("pack_size_id", String(opts.packSizeId));
    if (opts?.productionRunId) params.set("production_run_id", String(opts.productionRunId));
    if (opts?.movementType) params.set("movement_type", opts.movementType);
    if (opts?.dateFrom) params.set("date_from", opts.dateFrom);
    if (opts?.dateTo) params.set("date_to", opts.dateTo);
    if (opts?.limit) params.set("limit", String(opts.limit));
    const qs = params.toString();
    return request<InventoryLedgerEntry[]>(`/inventory/ledger${qs ? `?${qs}` : ""}`);
  },
  getStockAdjustments: (opts?: { status?: string; itemCategory?: string }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.itemCategory) params.set("item_category", opts.itemCategory);
    const qs = params.toString();
    return request<StockAdjustment[]>(`/inventory/adjustments${qs ? `?${qs}` : ""}`);
  },
  createStockAdjustment: (payload: StockAdjustmentCreatePayload) =>
    request<StockAdjustment>("/inventory/adjustments", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  approveStockAdjustment: (adjustmentId: number) =>
    request<StockAdjustment>(`/inventory/adjustments/${adjustmentId}/approve`, {
      method: "POST",
    }),
  rejectStockAdjustment: (adjustmentId: number, reason: string) =>
    request<StockAdjustment>(`/inventory/adjustments/${adjustmentId}/reject`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  getStockReportsSummary: (opts?: { dateFrom?: string; dateTo?: string }) => {
    const params = new URLSearchParams();
    if (opts?.dateFrom) params.set("date_from", opts.dateFrom);
    if (opts?.dateTo) params.set("date_to", opts.dateTo);
    const qs = params.toString();
    return request<StockReportsSummary>(`/inventory/reports/summary${qs ? `?${qs}` : ""}`);
  },

  // ── Phase 7: BOM & Production ──────────────────────────────────────────
  getProductionCatalog: () => request<ProductionCatalog>("/production/catalog"),
  createPackSize: (payload: {
    product_id: number;
    sku_code: string;
    display_name: string;
    pack_weight_g: number;
    packets_per_carton: number;
    base_selling_price_paisa?: number;
  }) =>
    request<PackSizeOption>("/production/catalog/pack-sizes", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  createMaterial: (payload: {
    code: string;
    name: string;
    material_category: "RAW_MATERIAL" | "PACKAGING_MATERIAL";
    unit_dimension: "MASS" | "VOLUME" | "COUNT";
    display_uom: string;
    reorder_level_display: string;
  }) =>
    request<MaterialSummary>("/production/catalog/materials", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getBoms: () => request<BomHeader[]>("/production/bom"),
  getBom: (packSizeId: number) => request<BomHeader>(`/production/bom/${packSizeId}`),
  createBomVersion: (payload: {
    pack_size_id: number;
    recipe_template_id?: number | null;
    expected_yield_pkts: number;
    effective_date?: string | null;
    notes?: string | null;
    activate?: boolean;
    components: Array<{
      material_id: number;
      input_role: "COOKING_RAW" | "PACKAGING";
      display_qty: string;
      display_uom: string;
    }>;
  }) =>
    request<BomVersion>("/production/bom/versions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  activateBomVersion: (versionId: number) =>
    request<BomVersion>(`/production/bom/versions/${versionId}/activate`, {
      method: "POST",
    }),
  calculateBom: (payload: {
    pack_size_id: number;
    batch_multiplier?: string | null;
    target_output_pkts?: number | null;
    bom_version_id?: number | null;
  }) => {
    const params = new URLSearchParams();
    if (payload.batch_multiplier) params.set("batch_multiplier", payload.batch_multiplier);
    if (payload.target_output_pkts) params.set("target_output_pkts", String(payload.target_output_pkts));
    if (payload.bom_version_id) params.set("bom_version_id", String(payload.bom_version_id));
    const qs = params.toString();
    return request<BomCalculation>(
      `/production/bom/${payload.pack_size_id}/calculate${qs ? `?${qs}` : ""}`
    );
  },
  getProductionDashboard: (opts?: { status?: string; packSizeId?: number }) => {
    const params = new URLSearchParams();
    if (opts?.status) params.set("status", opts.status);
    if (opts?.packSizeId) params.set("pack_size_id", String(opts.packSizeId));
    const qs = params.toString();
    return request<ProductionDashboardData>(`/production/dashboard${qs ? `?${qs}` : ""}`);
  },
  getProductionRunDetail: (runId: number) =>
    request<ProductionRunDetail>(`/production/runs/${runId}`),
  createProductionRun: (payload: {
    pack_size_id: number;
    batch_multiplier?: string | null;
    target_output_pkts?: number | null;
    run_date?: string | null;
    notes?: string | null;
    plan_immediately?: boolean;
  }) =>
    request<ProductionRunDetail>("/production/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  planProductionRun: (runId: number) =>
    request<ProductionRunDetail>(`/production/runs/${runId}/plan`, { method: "POST" }),
  issueProductionMaterials: (
    runId: number,
    payload: {
      items: Array<{ material_id: number; issued_qty: string; issued_uom: string }>;
      require_all_bom_stock?: boolean;
      notes?: string | null;
    }
  ) =>
    request<ProductionRunDetail>(`/production/runs/${runId}/issue-materials`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  completeProductionRun: (
    runId: number,
    payload: {
      good_output_pkts: number;
      rejected_output_pkts: number;
      batch_code: string;
      expiry_date?: string | null;
      quality_remarks?: string | null;
      consumptions: Array<{
        material_id: number;
        actual_consumed_qty?: string | null;
        actual_good_used_qty?: string | null;
        damaged_packaging_qty?: string;
        returned_unused_qty?: string;
        wasted_qty?: string;
        uom: string;
      }>;
    }
  ) =>
    request<ProductionRunDetail>(`/production/runs/${runId}/complete`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  postProductionRun: (runId: number) =>
    request<ProductionRunDetail>(`/production/runs/${runId}/post`, { method: "POST" }),
  cancelProductionRun: (
    runId: number,
    payload: {
      reason: string;
      returned_items?: Array<{ material_id: number; returned_qty: string; uom: string }>;
    }
  ) =>
    request<ProductionRunDetail>(`/production/runs/${runId}/cancel`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  acknowledgeVarianceAlert: (alertId: number, note?: string | null) =>
    request<VarianceAlert>(`/production/alerts/${alertId}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({ note: note || null }),
    }),
  getProductionVarianceReport: () =>
    request<ProductionVarianceReportRow[]>("/production/reports/variances"),

  // ── Phase 8: GST Billing, Credit Notes, Dispatch & Delivery ───────────────
  getBillingDashboard: (opts?: { docStatus?: string; dispatchStatus?: string; search?: string }) => {
    const params = new URLSearchParams();
    if (opts?.docStatus) params.set("doc_status", opts.docStatus);
    if (opts?.dispatchStatus) params.set("dispatch_status", opts.dispatchStatus);
    if (opts?.search) params.set("search", opts.search);
    const qs = params.toString();
    return request<BillingDashboardData>(`/billing/dashboard${qs ? `?${qs}` : ""}`);
  },
  getInvoices: (opts?: { docStatus?: string; dispatchStatus?: string; search?: string }) => {
    const params = new URLSearchParams();
    if (opts?.docStatus) params.set("doc_status", opts.docStatus);
    if (opts?.dispatchStatus) params.set("dispatch_status", opts.dispatchStatus);
    if (opts?.search) params.set("search", opts.search);
    const qs = params.toString();
    return request<InvoiceSummary[]>(`/billing/invoices${qs ? `?${qs}` : ""}`);
  },
  createInvoice: (payload: {
    sales_order_id: number;
    invoice_date?: string | null;
    apply_round_off?: boolean;
    notes?: string | null;
    item_discounts?: Array<{ sales_order_item_id: number; discount_paisa: number }>;
    issue_immediately?: boolean;
  }) =>
    request<InvoiceDetail>("/billing/invoices", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getInvoiceDetail: (invoiceId: number) => request<InvoiceDetail>(`/billing/invoices/${invoiceId}`),
  verifyInvoice: (invoiceId: number, payload: { remarks?: string | null; expected_version?: number }) =>
    request<InvoiceDetail>(`/billing/invoices/${invoiceId}/verify`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  issueInvoice: (
    invoiceId: number,
    payload: { verification_remarks?: string | null; expected_version?: number }
  ) =>
    request<InvoiceDetail>(`/billing/invoices/${invoiceId}/issue`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  fetchInvoicePdfBlob: async (invoiceId: number): Promise<Blob> => {
    const token = getStoredToken();
    const res = await fetch(`${API_BASE}/billing/invoices/${invoiceId}/pdf`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      throw new ApiClientError(res.status, "PDF_ERROR", "Unable to download invoice PDF.");
    }
    return res.blob();
  },
  getCreditNotes: () => request<CreditNote[]>("/billing/credit-notes"),
  createCreditNote: (payload: {
    original_invoice_id: number;
    note_type: "INVOICE_CANCELLATION" | "SALES_RETURN" | "VALUE_ADJUSTMENT";
    issue_date?: string | null;
    reason: string;
    cancel_original_invoice?: boolean;
    issue_immediately?: boolean;
    items?: Array<{
      invoice_item_id: number;
      qty_pkts: number;
      taxable_override_paisa?: number | null;
      return_disposition: "NONE_NOT_DISPATCHED" | "RESTOCK_SELLABLE" | "SCRAP_DAMAGED";
    }>;
  }) =>
    request<CreditNote>("/billing/credit-notes", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  issueCreditNote: (cnId: number) =>
    request<CreditNote>(`/billing/credit-notes/${cnId}/issue`, { method: "POST" }),
  getDispatchDashboard: (status?: string) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    const qs = params.toString();
    return request<DispatchDashboardData>(`/billing/dispatches/dashboard${qs ? `?${qs}` : ""}`);
  },
  getDispatchDetail: (dispatchId: number) => request<DispatchDetail>(`/billing/dispatches/${dispatchId}`),
  createDispatch: (payload: {
    invoice_id: number;
    dispatch_date?: string | null;
    transporter_name?: string | null;
    vehicle_number?: string | null;
    lr_number?: string | null;
    packing_verified?: boolean;
    packing_remarks?: string | null;
    notes?: string | null;
    post_immediately?: boolean;
    items: Array<{ invoice_item_id: number; dispatched_qty_pkts: number; batch_code_ref?: string | null }>;
  }) =>
    request<DispatchDetail>("/billing/dispatches", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  markDispatchReady: (
    dispatchId: number,
    payload: {
      remarks?: string | null;
      transporter_name?: string | null;
      vehicle_number?: string | null;
      lr_number?: string | null;
      expected_version?: number;
    }
  ) =>
    request<DispatchDetail>(`/billing/dispatches/${dispatchId}/ready`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  postDispatch: (
    dispatchId: number,
    payload: {
      remarks?: string | null;
      transporter_name?: string | null;
      vehicle_number?: string | null;
      lr_number?: string | null;
      expected_version?: number;
    }
  ) =>
    request<DispatchDetail>(`/billing/dispatches/${dispatchId}/post`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateDeliveryStatus: (
    dispatchId: number,
    payload: {
      target_status: "IN_TRANSIT" | "DELIVERED" | "DELIVERY_EXCEPTION";
      delivery_date?: string | null;
      remarks?: string | null;
      exception_reason?: string | null;
      expected_version?: number;
      items?: Array<{ dispatch_item_id: number; received_qty_pkts: number; discrepancy_remarks?: string | null }>;
    }
  ) =>
    request<DispatchDetail>(`/billing/dispatches/${dispatchId}/delivery`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getBillingReports: (opts?: { dateFrom?: string; dateTo?: string }) => {
    const params = new URLSearchParams();
    if (opts?.dateFrom) params.set("date_from", opts.dateFrom);
    if (opts?.dateTo) params.set("date_to", opts.dateTo);
    const qs = params.toString();
    return request<BillingReportsBundle>(`/billing/reports${qs ? `?${qs}` : ""}`);
  },
};

// ── Phase 8 TypeScript Types ────────────────────────────────────────────────

export interface ReadyForBillingOrder {
  sales_order_id: number;
  order_number: string;
  order_date: string;
  customer_id: number;
  customer_name: string;
  customer_gstin: string | null;
  place_of_supply_state_code: string;
  place_of_supply_state_name: string;
  supply_type: "INTRA_STATE" | "INTER_STATE";
  total_packets: number;
  taxable_total_paisa: number;
  estimated_tax_paisa: number;
  estimated_grand_total_paisa: number;
  approved_at: string | null;
}

export interface InvoiceItem {
  id: number;
  sales_order_item_id: number;
  pack_size_id: number;
  sku_code: string;
  product_name: string;
  description: string;
  hsn_code: string;
  qty_pkts: number;
  uom: string;
  unit_price_paisa: number;
  discount_paisa: number;
  taxable_paisa: number;
  gst_rate_bps: number;
  cgst_rate_bps: number;
  sgst_rate_bps: number;
  igst_rate_bps: number;
  cgst_paisa: number;
  sgst_paisa: number;
  igst_paisa: number;
  line_total_paisa: number;
  dispatched_qty_pkts: number;
  remaining_dispatch_qty_pkts: number;
}

export interface InvoiceTaxComponent {
  id: number;
  hsn_code: string;
  tax_type: "CGST" | "SGST" | "IGST";
  rate_bps: number;
  taxable_base_paisa: number;
  tax_amount_paisa: number;
}

export interface InvoiceSummary {
  id: number;
  draft_ref: string;
  invoice_number: string | null;
  financial_year: string;
  sales_order_id: number;
  order_number: string;
  customer_id: number;
  customer_name: string;
  buyer_gstin: string | null;
  place_of_supply_state_code: string;
  place_of_supply_state_name: string;
  nature_of_supply: "B2B" | "B2C";
  supply_type: "INTRA_STATE" | "INTER_STATE";
  invoice_date: string;
  due_date: string;
  doc_status: string;
  payment_status: string;
  dispatch_status: string;
  taxable_total_paisa: number;
  cgst_total_paisa: number;
  sgst_total_paisa: number;
  igst_total_paisa: number;
  round_off_paisa: number;
  grand_total_paisa: number;
  credited_paisa: number;
  paid_paisa: number;
  outstanding_paisa: number;
  total_qty_pkts: number;
  dispatched_qty_pkts: number;
  remaining_dispatch_qty_pkts: number;
  issued_at: string | null;
  created_at: string;
}

export interface CreditNoteItem {
  id: number;
  invoice_item_id: number;
  pack_size_id: number;
  sku_code: string;
  description: string;
  qty_pkts: number;
  return_disposition: string;
  taxable_reversed_paisa: number;
  cgst_reversed_paisa: number;
  sgst_reversed_paisa: number;
  igst_reversed_paisa: number;
  line_total_reversed_paisa: number;
}

export interface CreditNote {
  id: number;
  draft_ref: string;
  cn_number: string | null;
  financial_year: string;
  original_invoice_id: number;
  original_invoice_number: string | null;
  customer_id: number;
  customer_name: string;
  supply_type: string;
  note_type: string;
  issue_date: string;
  reason: string;
  status: string;
  cancel_original_invoice: boolean;
  taxable_reversed_paisa: number;
  cgst_reversed_paisa: number;
  sgst_reversed_paisa: number;
  igst_reversed_paisa: number;
  round_off_reversed_paisa: number;
  total_reversed_paisa: number;
  created_by_name: string;
  approved_by_name: string | null;
  issued_by_name: string | null;
  issued_at: string | null;
  created_at: string;
  items: CreditNoteItem[];
}

export interface DispatchItem {
  id: number;
  invoice_item_id: number;
  pack_size_id: number;
  sku_code: string;
  display_name: string;
  dispatched_qty_pkts: number;
  batch_code_ref: string | null;
  received_qty_pkts: number | null;
  discrepancy_qty_pkts: number;
  discrepancy_remarks: string | null;
}

export interface DispatchStatusHistoryEntry {
  id: number;
  from_status: string | null;
  to_status: string;
  changed_by_name: string;
  reason: string | null;
  changed_at: string;
}

export interface DispatchDetail {
  id: number;
  dispatch_number: string;
  invoice_id: number;
  invoice_number: string | null;
  sales_order_id: number;
  order_number: string;
  customer_id: number;
  customer_name: string;
  status: string;
  dispatch_date: string;
  transporter_name: string | null;
  vehicle_number: string | null;
  lr_number: string | null;
  packing_verified: boolean;
  packing_remarks: string | null;
  notes: string | null;
  created_by_name: string;
  created_at: string;
  ready_by_name: string | null;
  ready_at: string | null;
  dispatched_by_name: string | null;
  dispatched_at: string | null;
  in_transit_at: string | null;
  delivery_date: string | null;
  delivery_confirmed_by_name: string | null;
  delivery_confirmed_at: string | null;
  delivery_remarks: string | null;
  delivery_exception_reason: string | null;
  version: number;
  total_dispatched_pkts: number;
  total_received_pkts: number;
  items: DispatchItem[];
  status_history: DispatchStatusHistoryEntry[];
}

export interface InvoicePaymentAllocation {
  id: number;
  payment_id: number;
  payment_number: string;
  payment_date: string;
  payment_mode: string;
  reference_no: string | null;
  allocated_paisa: number;
  status: string;
  allocated_at: string;
  reversal_reason: string | null;
}

export interface InvoiceAuditEntry {
  id: number;
  actor_name: string;
  actor_role: string;
  action: string;
  entity_table: string;
  reason: string | null;
  after_state: Record<string, unknown> | null;
  occurred_at: string;
}

export interface InvoiceDetail extends InvoiceSummary {
  seller_legal_name: string;
  seller_gstin: string;
  seller_state_name: string;
  seller_state_code: string;
  seller_address: string;
  customer_type: string;
  billing_address_snapshot: string;
  shipping_address_snapshot: string;
  payment_terms: string;
  discount_total_paisa: number;
  amount_in_words: string;
  notes: string | null;
  legal_declaration: string;
  tax_calculation_snapshot: Record<string, unknown>;
  created_by_name: string;
  verified_by_name: string | null;
  verified_at: string | null;
  verification_remarks: string | null;
  issued_by_name: string | null;
  version: number;
  items: InvoiceItem[];
  tax_components: InvoiceTaxComponent[];
  credit_notes: CreditNote[];
  dispatches: DispatchDetail[];
  allocations?: InvoicePaymentAllocation[];
  audit_trail: InvoiceAuditEntry[];
}

export interface ReadyForDispatchInvoice {
  invoice_id: number;
  invoice_number: string;
  sales_order_id: number;
  order_number: string;
  customer_id: number;
  customer_name: string;
  place_of_supply_state_code: string;
  invoice_date: string;
  dispatch_status: string;
  total_qty_pkts: number;
  dispatched_qty_pkts: number;
  remaining_qty_pkts: number;
  fg_on_hand_sufficient: boolean;
}

export interface BillingDashboardData {
  ready_for_billing_count: number;
  draft_invoices_count: number;
  issued_invoices_count: number;
  cancelled_invoices_count: number;
  total_taxable_paisa: number;
  total_cgst_paisa: number;
  total_sgst_paisa: number;
  total_igst_paisa: number;
  total_invoiced_paisa: number;
  total_credited_paisa: number;
  total_outstanding_paisa: number;
  ready_orders: ReadyForBillingOrder[];
  invoices: InvoiceSummary[];
}

export interface DispatchDashboardData {
  ready_for_dispatch_invoices_count: number;
  created_count: number;
  ready_count: number;
  dispatched_count: number;
  in_transit_count: number;
  delivered_count: number;
  exception_count: number;
  ready_invoices: ReadyForDispatchInvoice[];
  dispatches: DispatchDetail[];
}

export interface SalesInvoiceRegisterRow {
  invoice_id: number;
  invoice_number: string;
  invoice_date: string;
  financial_year: string;
  order_number: string;
  customer_name: string;
  buyer_gstin: string | null;
  place_of_supply_state_code: string;
  nature_of_supply: string;
  supply_type: string;
  doc_status: string;
  dispatch_status: string;
  payment_status: string;
  taxable_total_paisa: number;
  cgst_total_paisa: number;
  sgst_total_paisa: number;
  igst_total_paisa: number;
  round_off_paisa: number;
  grand_total_paisa: number;
  credited_paisa: number;
  outstanding_paisa: number;
}

export interface GstHsnReportRow {
  hsn_code: string;
  supply_type: string;
  tax_rate_bps: number;
  taxable_value_paisa: number;
  cgst_paisa: number;
  sgst_paisa: number;
  igst_paisa: number;
  total_tax_paisa: number;
}

export interface GstSummaryReport {
  gross_taxable_paisa: number;
  gross_cgst_paisa: number;
  gross_sgst_paisa: number;
  gross_igst_paisa: number;
  credited_taxable_paisa: number;
  credited_cgst_paisa: number;
  credited_sgst_paisa: number;
  credited_igst_paisa: number;
  net_taxable_paisa: number;
  net_cgst_paisa: number;
  net_sgst_paisa: number;
  net_igst_paisa: number;
  disclaimer: string;
  hsn_rows: GstHsnReportRow[];
}

export interface CustomerSalesSummaryRow {
  customer_id: number;
  customer_name: string;
  customer_type: string;
  buyer_gstin: string | null;
  state_code: string;
  invoice_count: number;
  total_qty_pkts: number;
  taxable_paisa: number;
  gst_paisa: number;
  grand_total_paisa: number;
  credited_paisa: number;
  outstanding_paisa: number;
}

export interface ProductSalesSummaryRow {
  pack_size_id: number;
  sku_code: string;
  description: string;
  hsn_code: string;
  total_qty_pkts: number;
  taxable_paisa: number;
  cgst_paisa: number;
  sgst_paisa: number;
  igst_paisa: number;
  line_total_paisa: number;
}

export interface DispatchRegisterRow {
  dispatch_id: number;
  dispatch_number: string;
  dispatch_date: string;
  invoice_number: string;
  order_number: string;
  customer_name: string;
  status: string;
  transporter_name: string | null;
  vehicle_number: string | null;
  total_dispatched_pkts: number;
  total_received_pkts: number;
  delivery_date: string | null;
}

export interface BillingReportsBundle {
  sales_register: SalesInvoiceRegisterRow[];
  gst_summary: GstSummaryReport;
  credit_notes: CreditNote[];
  dispatch_register: DispatchRegisterRow[];
  customer_sales: CustomerSalesSummaryRow[];
  product_sales: ProductSalesSummaryRow[];
  outstanding_invoices: SalesInvoiceRegisterRow[];
}

// ── Phase 9: Payments, Accounts Receivable, Product Costing & Profitability ────────

export interface ProductionOverhead {
  id: number;
  production_run_id: number | null;
  period_month: string;
  overhead_type: string;
  allocation_scope: string;
  amount_paisa: number;
  notes: string | null;
  is_voided: boolean;
  void_reason: string | null;
  voided_by_name: string | null;
  voided_at: string | null;
  recorded_by_name: string;
  recorded_at: string;
}

export interface MaterialCostLine {
  material_id: number;
  material_code: string;
  material_name: string;
  issue_phase: string;
  display_uom: string;
  planned_qty_base: string;
  actual_consumed_qty_base: string;
  damaged_qty_base: string;
  wasted_qty_base: string;
  returned_unused_qty_base: string;
  planned_cost_paisa: number;
  actual_cost_paisa: number;
  damaged_cost_paisa: number;
  wasted_cost_paisa: number;
  cost_variance_paisa: number;
}

export interface ProductionCostSummary {
  id: number;
  production_run_id: number;
  run_number: string;
  run_date: string;
  pack_size_id: number;
  sku_code: string;
  display_name: string;
  snapshot_version: number;
  is_current: boolean;
  cost_status: "PRELIMINARY" | "FINALIZED";
  valuation_method: string;
  planned_raw_cost_paisa: number;
  planned_pkg_cost_paisa: number;
  planned_overhead_cost_paisa: number;
  planned_total_cost_paisa: number;
  planned_cost_per_packet_paisa: string;
  raw_material_cost_paisa: number;
  good_packaging_cost_paisa: number;
  damaged_packaging_cost_paisa: number;
  packaging_cost_paisa: number;
  raw_wastage_cost_paisa: number;
  rejected_output_cost_impact_paisa: number;
  direct_labour_paisa: number;
  gas_power_paisa: number;
  other_direct_overhead_paisa: number;
  direct_overhead_paisa: number;
  allocated_overhead_paisa: number;
  total_cost_paisa: number;
  expected_output_pkts: number;
  good_packets: number;
  rejected_packets: number;
  cost_per_packet_paisa: number | null;
  exact_cost_per_packet_paisa: string | null;
  selling_price_snapshot_paisa: number;
  gross_margin_per_pkt_paisa: number | null;
  gross_margin_pct: string | null;
  material_variance_paisa: number;
  cost_per_pkt_variance_paisa: number | null;
  material_lines: MaterialCostLine[];
  notes: string | null;
  computed_by_name: string;
  computed_at: string;
}

export interface RunCostingDetail {
  production_run_id: number;
  run_number: string;
  sku_code: string;
  display_name: string;
  run_status: string;
  run_date: string;
  current_summary: ProductionCostSummary | null;
  history_snapshots: ProductionCostSummary[];
  overheads: ProductionOverhead[];
}

export interface ProductCostAggregate {
  pack_size_id: number;
  sku_code: string;
  display_name: string;
  run_count: number;
  total_good_packets: number;
  total_rejected_packets: number;
  total_raw_cost_paisa: number;
  total_pkg_cost_paisa: number;
  total_overhead_cost_paisa: number;
  total_cost_paisa: number;
  weighted_avg_cost_per_pkt_paisa: number;
  latest_cost_per_pkt_paisa: number;
  selling_price_paisa: number;
  unit_gross_margin_paisa: number;
  unit_gross_margin_pct: string;
}

export interface CostingDashboardData {
  valuation_method: string;
  total_costed_runs: number;
  total_finalized_runs: number;
  total_good_packets: number;
  total_batch_cost_paisa: number;
  total_wastage_and_damage_paisa: number;
  runs: ProductionCostSummary[];
  product_summaries: ProductCostAggregate[];
  monthly_pools: ProductionOverhead[];
}

export interface PaymentAllocationDetail {
  id: number;
  payment_id: number;
  payment_number: string;
  invoice_id: number;
  invoice_number: string;
  invoice_date: string;
  due_date: string;
  invoice_grand_total_paisa: number;
  invoice_outstanding_paisa: number;
  allocated_paisa: number;
  status: string;
  allocated_by_name: string;
  allocated_at: string;
  reversed_by_name: string | null;
  reversed_at: string | null;
  reversal_reason: string | null;
  notes: string | null;
}

export interface PaymentRefundDetail {
  id: number;
  refund_number: string;
  financial_year: string;
  payment_id: number;
  customer_id: number;
  refund_date: string;
  amount_paisa: number;
  refund_mode: string;
  reference_no: string | null;
  reason: string;
  status: string;
  refunded_by_name: string;
  refunded_at: string;
}

export interface PaymentDetail {
  id: number;
  payment_number: string;
  financial_year: string;
  customer_id: number;
  customer_code: string;
  customer_name: string;
  payment_date: string;
  amount_paisa: number;
  allocated_paisa: number;
  refunded_paisa: number;
  unallocated_paisa: number;
  payment_mode: string;
  reference_no: string | null;
  remarks: string | null;
  is_advance: boolean;
  idempotency_key: string;
  status: string;
  reversal_reason: string | null;
  reversed_by_name: string | null;
  reversed_at: string | null;
  recorded_by_name: string;
  recorded_at: string;
  version: number;
  allocations: PaymentAllocationDetail[];
  refunds: PaymentRefundDetail[];
}

export interface PaginatedPayments {
  items: PaymentDetail[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface OpenInvoiceForAllocation {
  invoice_id: number;
  invoice_number: string;
  order_number: string;
  invoice_date: string;
  due_date: string;
  grand_total_paisa: number;
  credited_paisa: number;
  paid_paisa: number;
  outstanding_paisa: number;
  payment_status: string;
  days_past_due: number;
  is_overdue: boolean;
}

export interface CustomerArSummary {
  customer_id: number;
  customer_code: string;
  customer_name: string;
  customer_type: string;
  gstin: string | null;
  state_name: string;
  credit_days: number;
  salesman_name: string | null;
  total_invoiced_paisa: number;
  total_credited_paisa: number;
  total_payments_received_paisa: number;
  total_refunded_paisa: number;
  total_allocated_paisa: number;
  advance_balance_paisa: number;
  total_outstanding_paisa: number;
  net_receivable_paisa: number;
  overdue_balance_paisa: number;
  pending_invoices_count: number;
  overdue_invoices_count: number;
}

export interface PaginatedCustomerAr {
  items: CustomerArSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  summary_total_invoiced_paisa: number;
  summary_total_received_paisa: number;
  summary_total_outstanding_paisa: number;
  summary_total_overdue_paisa: number;
  summary_total_advance_paisa: number;
}

export interface AgeingInvoiceRow {
  invoice_id: number;
  invoice_number: string;
  customer_id: number;
  customer_name: string;
  invoice_date: string;
  due_date: string;
  days_past_due: number;
  is_overdue: boolean;
  ageing_bucket: string;
  original_paisa: number;
  credited_paisa: number;
  paid_paisa: number;
  outstanding_paisa: number;
  payment_status: string;
}

export interface AgeingCustomerRow {
  customer_id: number;
  customer_code: string;
  customer_name: string;
  not_due_paisa: number;
  overdue_1_30_paisa: number;
  bucket_0_30_paisa: number;
  bucket_31_60_paisa: number;
  bucket_61_90_paisa: number;
  bucket_90_plus_paisa: number;
  total_outstanding_paisa: number;
  overdue_total_paisa: number;
}

export interface AgeingReport {
  as_of_date: string;
  not_due_paisa: number;
  overdue_1_30_paisa: number;
  bucket_0_30_paisa: number;
  bucket_31_60_paisa: number;
  bucket_61_90_paisa: number;
  bucket_90_plus_paisa: number;
  total_outstanding_paisa: number;
  overdue_total_paisa: number;
  customers: AgeingCustomerRow[];
  invoices: AgeingInvoiceRow[];
  total_invoices: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CustomerStatementEntry {
  entry_date: string;
  occurred_at: string;
  entry_type: string;
  reference_number: string;
  description: string;
  debit_paisa: number;
  credit_paisa: number;
  running_balance_paisa: number;
  linked_invoice_id: number | null;
  linked_payment_id: number | null;
}

export interface CustomerStatement {
  customer_id: number;
  customer_code: string;
  customer_name: string;
  gstin: string | null;
  state_name: string;
  credit_days: number;
  total_invoiced_paisa: number;
  total_credited_paisa: number;
  total_payments_received_paisa: number;
  total_refunded_paisa: number;
  advance_balance_paisa: number;
  total_outstanding_paisa: number;
  net_balance_paisa: number;
  open_invoices: OpenInvoiceForAllocation[];
  entries: CustomerStatementEntry[];
}

export interface ProductProfitabilityRow {
  pack_size_id: number;
  sku_code: string;
  display_name: string;
  hsn_code: string;
  invoiced_qty_pkts: number;
  returned_qty_pkts: number;
  net_sold_qty_pkts: number;
  gross_revenue_paisa: number;
  credited_revenue_paisa: number;
  net_revenue_paisa: number;
  gst_collected_paisa: number;
  dispatched_cogs_paisa: number;
  pending_dispatch_estimated_cogs_paisa: number;
  total_cogs_paisa: number;
  gross_profit_paisa: number;
  gross_margin_pct: string;
}

export interface CustomerProfitabilityRow {
  customer_id: number;
  customer_code: string;
  customer_name: string;
  customer_type: string;
  invoice_count: number;
  net_revenue_paisa: number;
  gst_collected_paisa: number;
  total_cogs_paisa: number;
  gross_profit_paisa: number;
  gross_margin_pct: string;
  cash_received_paisa: number;
  outstanding_receivables_paisa: number;
}

export interface OrderProfitabilityRow {
  sales_order_id: number;
  order_number: string;
  order_date: string;
  invoice_id: number;
  invoice_number: string;
  invoice_date: string;
  customer_name: string;
  doc_status: string;
  net_revenue_paisa: number;
  gst_collected_paisa: number;
  total_cogs_paisa: number;
  gross_profit_paisa: number;
  gross_margin_pct: string;
  cash_received_paisa: number;
  outstanding_paisa: number;
}

export interface DateProfitabilityRow {
  period_date: string;
  invoice_count: number;
  net_revenue_paisa: number;
  gst_collected_paisa: number;
  total_cogs_paisa: number;
  gross_profit_paisa: number;
  gross_margin_pct: string;
  cash_collected_on_date_paisa: number;
}

export interface ProfitabilityReport {
  gross_revenue_paisa: number;
  credited_revenue_paisa: number;
  net_revenue_paisa: number;
  gst_collected_paisa: number;
  dispatched_cogs_paisa: number;
  pending_dispatch_estimated_cogs_paisa: number;
  total_cogs_paisa: number;
  gross_profit_paisa: number;
  gross_margin_pct: string;
  cash_received_paisa: number;
  outstanding_receivables_paisa: number;
  disclaimer: string;
  by_product: ProductProfitabilityRow[];
  by_customer: CustomerProfitabilityRow[];
  by_order: OrderProfitabilityRow[];
  by_date: DateProfitabilityRow[];
}

export interface PaymentTrendRow {
  payment_date: string;
  payment_count: number;
  total_received_paisa: number;
}

export interface CostingSummaryCardRow {
  production_run_id: number;
  run_number: string;
  sku_code: string;
  display_name: string;
  cost_status: string;
  good_packets: number;
  total_cost_paisa: number;
  cost_per_packet_paisa: number | null;
  gross_margin_per_pkt_paisa: number | null;
  gross_margin_pct: string | null;
}

export interface FinanceDashboardData {
  total_invoiced_taxable_paisa: number;
  total_gst_collected_paisa: number;
  total_invoiced_gross_paisa: number;
  total_credited_paisa: number;
  net_invoiced_sales_paisa: number;
  payments_received_paisa: number;
  total_refunded_paisa: number;
  net_cash_collected_paisa: number;
  customer_advances_paisa: number;
  outstanding_receivables_paisa: number;
  overdue_receivables_paisa: number;
  total_cogs_paisa: number;
  gross_profit_paisa: number;
  gross_margin_pct: string;
  profitability_disclaimer: string;
  recent_payments: PaymentDetail[];
  recent_outstanding_invoices: AgeingInvoiceRow[];
  payment_trends: PaymentTrendRow[];
  product_profitability: ProductProfitabilityRow[];
  costing_summary: CostingSummaryCardRow[];
}

export interface SalesmanCustomerAr {
  customer_id: number;
  customer_code: string;
  customer_name: string;
  total_invoiced_paisa: number;
  total_paid_paisa: number;
  advance_balance_paisa: number;
  total_outstanding_paisa: number;
  open_invoices: OpenInvoiceForAllocation[];
}

export const costingApi = {
  getDashboard: (opts?: { dateFrom?: string; dateTo?: string; packSizeId?: number }) => {
    const p = new URLSearchParams();
    if (opts?.dateFrom) p.set("date_from", opts.dateFrom);
    if (opts?.dateTo) p.set("date_to", opts.dateTo);
    if (opts?.packSizeId) p.set("pack_size_id", String(opts.packSizeId));
    const qs = p.toString();
    return request<CostingDashboardData>(`/costing/dashboard${qs ? `?${qs}` : ""}`);
  },
  getRunCosting: (runId: number) => request<RunCostingDetail>(`/costing/runs/${runId}`),
  addRunOverhead: (
    runId: number,
    payload: { overhead_type: string; amount_paisa: number; notes?: string | null }
  ) =>
    request<RunCostingDetail>(`/costing/runs/${runId}/overheads`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  finalizeRunCosting: (
    runId: number,
    payload: {
      overheads: Array<{ overhead_type: string; amount_paisa: number; notes?: string | null }>;
      notes?: string | null;
    }
  ) =>
    request<RunCostingDetail>(`/costing/runs/${runId}/finalize`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  voidOverhead: (overheadId: number, reason: string) =>
    request<{ status: string; overhead_id: number }>(`/costing/overheads/${overheadId}/void`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  addMonthlyPoolOverhead: (payload: {
    period_month: string;
    overhead_type: string;
    amount_paisa: number;
    notes?: string | null;
  }) =>
    request<ProductionOverhead>("/costing/monthly-pools", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  reallocateMonthlyPool: (periodMonth: string) =>
    request<{ period_month: string; updated_runs_count: number }>(
      `/costing/monthly-pools/${periodMonth}/reallocate`,
      { method: "POST" }
    ),
};

export const financeApi = {
  getDashboard: (opts?: { dateFrom?: string; dateTo?: string }) => {
    const p = new URLSearchParams();
    if (opts?.dateFrom) p.set("date_from", opts.dateFrom);
    if (opts?.dateTo) p.set("date_to", opts.dateTo);
    const qs = p.toString();
    return request<FinanceDashboardData>(`/finance/dashboard${qs ? `?${qs}` : ""}`);
  },
  getPayments: (opts?: {
    customerId?: number;
    status?: string;
    paymentMode?: string;
    dateFrom?: string;
    dateTo?: string;
    search?: string;
    page?: number;
    pageSize?: number;
  }) => {
    const p = new URLSearchParams();
    if (opts?.customerId) p.set("customer_id", String(opts.customerId));
    if (opts?.status) p.set("status", opts.status);
    if (opts?.paymentMode) p.set("payment_mode", opts.paymentMode);
    if (opts?.dateFrom) p.set("date_from", opts.dateFrom);
    if (opts?.dateTo) p.set("date_to", opts.dateTo);
    if (opts?.search) p.set("search", opts.search);
    if (opts?.page) p.set("page", String(opts.page));
    if (opts?.pageSize) p.set("page_size", String(opts.pageSize));
    const qs = p.toString();
    return request<PaginatedPayments>(`/finance/payments${qs ? `?${qs}` : ""}`);
  },
  recordPayment: (payload: {
    customer_id: number;
    payment_date?: string | null;
    amount_paisa: number;
    payment_mode: string;
    reference_no?: string | null;
    remarks?: string | null;
    client_payment_id: string;
    allocations: Array<{ invoice_id: number; allocated_paisa: number }>;
  }) =>
    request<PaymentDetail>("/finance/payments", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getPaymentDetail: (paymentId: number) => request<PaymentDetail>(`/finance/payments/${paymentId}`),
  allocatePayment: (
    paymentId: number,
    payload: {
      allocations: Array<{ invoice_id: number; allocated_paisa: number }>;
      notes?: string | null;
      expected_version?: number;
    }
  ) =>
    request<PaymentDetail>(`/finance/payments/${paymentId}/allocate`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  reverseAllocation: (allocationId: number, reason: string) =>
    request<PaymentDetail>(`/finance/allocations/${allocationId}/reverse`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  reversePayment: (paymentId: number, payload: { reason: string; expected_version?: number }) =>
    request<PaymentDetail>(`/finance/payments/${paymentId}/reverse`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  refundPayment: (
    paymentId: number,
    payload: {
      amount_paisa: number;
      refund_date?: string | null;
      refund_mode: string;
      reference_no?: string | null;
      reason: string;
      expected_version?: number;
    }
  ) =>
    request<PaymentDetail>(`/finance/payments/${paymentId}/refund`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  fetchReceiptPdfBlob: async (paymentId: number): Promise<Blob> => {
    const token = getStoredToken();
    const res = await fetch(`${API_BASE}/finance/payments/${paymentId}/receipt-pdf`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      throw new ApiClientError(res.status, "PDF_ERROR", "Unable to download payment receipt PDF.");
    }
    return res.blob();
  },
  getReceivables: (opts?: {
    asOfDate?: string;
    customerId?: number;
    search?: string;
    onlyOutstanding?: boolean;
    page?: number;
    pageSize?: number;
  }) => {
    const p = new URLSearchParams();
    if (opts?.asOfDate) p.set("as_of_date", opts.asOfDate);
    if (opts?.customerId) p.set("customer_id", String(opts.customerId));
    if (opts?.search) p.set("search", opts.search);
    if (opts?.onlyOutstanding) p.set("only_outstanding", "true");
    if (opts?.page) p.set("page", String(opts.page));
    if (opts?.pageSize) p.set("page_size", String(opts.pageSize));
    const qs = p.toString();
    return request<PaginatedCustomerAr>(`/finance/receivables${qs ? `?${qs}` : ""}`);
  },
  getAgeingReport: (opts?: {
    asOfDate?: string;
    customerId?: number;
    search?: string;
    page?: number;
    pageSize?: number;
  }) => {
    const p = new URLSearchParams();
    if (opts?.asOfDate) p.set("as_of_date", opts.asOfDate);
    if (opts?.customerId) p.set("customer_id", String(opts.customerId));
    if (opts?.search) p.set("search", opts.search);
    if (opts?.page) p.set("page", String(opts.page));
    if (opts?.pageSize) p.set("page_size", String(opts.pageSize));
    const qs = p.toString();
    return request<AgeingReport>(`/finance/receivables/ageing${qs ? `?${qs}` : ""}`);
  },
  getCustomerStatement: (customerId: number, opts?: { dateFrom?: string; dateTo?: string }) => {
    const p = new URLSearchParams();
    if (opts?.dateFrom) p.set("date_from", opts.dateFrom);
    if (opts?.dateTo) p.set("date_to", opts.dateTo);
    const qs = p.toString();
    return request<CustomerStatement>(
      `/finance/receivables/customers/${customerId}/statement${qs ? `?${qs}` : ""}`
    );
  },
  getOpenInvoicesForCustomer: (customerId: number) =>
    request<OpenInvoiceForAllocation[]>(`/finance/receivables/open-invoices/${customerId}`),
  getSalesmanCustomerReceivables: () =>
    request<SalesmanCustomerAr[]>("/finance/my-customers/receivables"),
  getProfitability: (opts?: {
    dateFrom?: string;
    dateTo?: string;
    customerId?: number;
    packSizeId?: number;
  }) => {
    const p = new URLSearchParams();
    if (opts?.dateFrom) p.set("date_from", opts.dateFrom);
    if (opts?.dateTo) p.set("date_to", opts.dateTo);
    if (opts?.customerId) p.set("customer_id", String(opts.customerId));
    if (opts?.packSizeId) p.set("pack_size_id", String(opts.packSizeId));
    const qs = p.toString();
    return request<ProfitabilityReport>(`/finance/profitability${qs ? `?${qs}` : ""}`);
  },
};

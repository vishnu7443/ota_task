import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  Ban,
  CheckCircle2,
  Clock,
  FileClock,
  Lock,
  Package,
  PauseCircle,
  RotateCcw,
  Save,
  ShieldCheck,
  Store,
  UserCheck,
  XCircle,
} from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api, type OrderDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDateTimeIst, formatInrFromPaisa, formatOrderDate } from "@/lib/money";

function rupeesStringToPaisa(val: string, fallbackPaisa: number): number {
  const num = Number(val);
  if (Number.isNaN(num) || num < 0) return fallbackPaisa;
  return Math.round(num * 100);
}

function paisaToRupeesInput(paisa: number): string {
  return (paisa / 100).toFixed(2);
}

export function AdminOrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const detailQuery = useQuery({
    queryKey: ["admin-order-detail", orderId],
    queryFn: () => api.getAdminOrderDetail(Number(orderId)),
    enabled: Boolean(orderId),
    refetchInterval: 15_000,
  });

  const order = detailQuery.data;
  const isFactoryAdmin = user?.role_code === "FACTORY_ADMIN";
  const isEditableState = order?.status === "SUBMITTED" || order?.status === "UNDER_REVIEW";
  const canFactoryAdminEdit = Boolean(isFactoryAdmin && isEditableState);

  const [draftQtyByItem, setDraftQtyByItem] = useState<Record<number, number>>({});
  const [draftPriceTextByItem, setDraftPriceTextByItem] = useState<Record<number, string>>({});
  const [adminRemarks, setAdminRemarks] = useState("");
  const [decisionReason, setDecisionReason] = useState("");
  const [actionBanner, setActionBanner] = useState<{
    kind: "success" | "error";
    title: string;
    detail?: string;
  } | null>(null);

  useEffect(() => {
    if (!order) return;
    const qtyMap: Record<number, number> = {};
    const priceMap: Record<number, string> = {};
    order.items.forEach((it) => {
      qtyMap[it.id] = it.effective_qty_pkts;
      priceMap[it.id] = paisaToRupeesInput(it.unit_price_paisa);
    });
    setDraftQtyByItem(qtyMap);
    setDraftPriceTextByItem(priceMap);
    setAdminRemarks(order.admin_remarks ?? "");
  }, [order?.id, order?.version]);

  const draftAnalysis = useMemo(() => {
    if (!order) {
      return {
        hasItemChanges: false,
        hasRemarkChanges: false,
        hasDraftShortage: false,
        shortageLines: [] as Array<{
          sku: string;
          name: string;
          req: number;
          avail: number;
          short: number;
        }>,
        taxableTotal: 0,
        cgstTotal: 0,
        sgstTotal: 0,
        igstTotal: 0,
        grandTotal: 0,
        payloadItems: [] as Array<{ id: number; approved_qty_pkts: number; unit_price_paisa: number }>,
      };
    }

    const isIntra = order.tax_estimate.supply_type === "INTRA_STATE";
    const isReservedOrLater = ["APPROVED", "INVOICED", "PARTIALLY_DISPATCHED", "DISPATCHED"].includes(
      order.status
    );
    let hasItemChanges = false;
    let taxableTotal = 0;
    let cgstTotal = 0;
    let sgstTotal = 0;
    let igstTotal = 0;
    const shortageLines: Array<{
      sku: string;
      name: string;
      req: number;
      avail: number;
      short: number;
    }> = [];
    const payloadItems: Array<{ id: number; approved_qty_pkts: number; unit_price_paisa: number }> = [];

    order.items.forEach((item) => {
      const qty = draftQtyByItem[item.id] ?? item.effective_qty_pkts;
      const priceText = draftPriceTextByItem[item.id] ?? paisaToRupeesInput(item.unit_price_paisa);
      const unitPaisa = rupeesStringToPaisa(priceText, item.unit_price_paisa);

      if (qty !== item.effective_qty_pkts || unitPaisa !== item.unit_price_paisa) {
        hasItemChanges = true;
      }

      const lineTaxable = qty * unitPaisa;
      taxableTotal += lineTaxable;

      if (isIntra) {
        const halfBps = Math.floor(item.gst_rate_bps / 2);
        const cgst = Math.floor((lineTaxable * halfBps + 5000) / 10000);
        cgstTotal += cgst;
        sgstTotal += cgst;
      } else {
        igstTotal += Math.floor((lineTaxable * item.gst_rate_bps + 5000) / 10000);
      }

      if (!isReservedOrLater) {
        const short = Math.max(0, qty - item.live_available_pkts);
        if (short > 0) {
          shortageLines.push({
            sku: item.sku_code,
            name: item.display_name,
            req: qty,
            avail: item.live_available_pkts,
            short,
          });
        }
      }

      payloadItems.push({
        id: item.id,
        approved_qty_pkts: qty,
        unit_price_paisa: unitPaisa,
      });
    });

    const hasRemarkChanges = adminRemarks.trim() !== (order.admin_remarks ?? "").trim();

    return {
      hasItemChanges,
      hasRemarkChanges,
      hasDraftShortage: shortageLines.length > 0,
      shortageLines,
      taxableTotal,
      cgstTotal,
      sgstTotal,
      igstTotal,
      grandTotal: taxableTotal + cgstTotal + sgstTotal + igstTotal,
      payloadItems,
    };
  }, [order, draftQtyByItem, draftPriceTextByItem, adminRemarks]);

  const applyServerUpdate = (updated: OrderDetail, title: string, detail?: string) => {
    queryClient.setQueryData(["admin-order-detail", orderId], updated);
    queryClient.invalidateQueries({ queryKey: ["admin-orders"] });
    queryClient.invalidateQueries({ queryKey: ["admin-orders-summary"] });
    queryClient.invalidateQueries({ queryKey: ["admin-dashboard-orders"] });
    setDecisionReason("");
    setActionBanner({ kind: "success", title, detail });
  };

  const handleActionError = (err: unknown) => {
    if (err instanceof ApiClientError) {
      setActionBanner({
        kind: "error",
        title: err.code === "INSUFFICIENT_STOCK" ? "Approval Blocked — Insufficient Stock" : err.code,
        detail: err.message,
      });
      detailQuery.refetch();
    } else if (err instanceof Error) {
      setActionBanner({ kind: "error", title: "Action Failed", detail: err.message });
    } else {
      setActionBanner({ kind: "error", title: "Action Failed", detail: "Unexpected error occurred." });
    }
  };

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!order) throw new Error("Order not loaded.");
      return api.modifyAdminOrder(order.id, {
        items: draftAnalysis.payloadItems,
        admin_remarks: adminRemarks.trim(),
        reason: decisionReason.trim() || undefined,
        expected_version: order.version,
      });
    },
    onSuccess: (updated) =>
      applyServerUpdate(
        updated,
        "Order revisions saved",
        "Updated quantities/prices/remarks recalculated server-side and recorded in Audit Log."
      ),
    onError: handleActionError,
  });

  const holdReviewMutation = useMutation({
    mutationFn: () => {
      if (!order) throw new Error("Order not loaded.");
      return api.holdOrderUnderReview(order.id, {
        admin_remarks: adminRemarks.trim() || null,
        reason: decisionReason.trim() || null,
        expected_version: order.version,
      });
    },
    onSuccess: (updated) =>
      applyServerUpdate(
        updated,
        "Order placed Under Review",
        "Stock coverage snapshot and verification note recorded."
      ),
    onError: handleActionError,
  });

  const requestCorrectionMutation = useMutation({
    mutationFn: () => {
      if (!order) throw new Error("Order not loaded.");
      return api.requestOrderCorrection(order.id, {
        reason: decisionReason.trim(),
        admin_remarks: adminRemarks.trim() || decisionReason.trim(),
        expected_version: order.version,
      });
    },
    onSuccess: (updated) =>
      applyServerUpdate(
        updated,
        "Correction requested from Salesman",
        "Salesman A/B mobile UI will sync this status and unlock order editing."
      ),
    onError: handleActionError,
  });

  const approveMutation = useMutation({
    mutationFn: async () => {
      if (!order) throw new Error("Order not loaded.");
      let currentOrder = order;
      if (draftAnalysis.hasItemChanges || draftAnalysis.hasRemarkChanges) {
        currentOrder = await api.modifyAdminOrder(order.id, {
          items: draftAnalysis.payloadItems,
          admin_remarks: adminRemarks.trim(),
          reason: decisionReason.trim() || "Verified quantities prior to approval",
          expected_version: order.version,
        });
      }
      return api.approveAdminOrder(currentOrder.id, {
        admin_remarks: adminRemarks.trim() || null,
        reason: decisionReason.trim() || null,
        expected_version: currentOrder.version,
      });
    },
    onSuccess: (updated) =>
      applyServerUpdate(
        updated,
        `Order ${updated.order_number} Approved & Stock Reserved`,
        "Available stock was atomically checked (FOR UPDATE) and reserved without deducting physical warehouse balance."
      ),
    onError: handleActionError,
  });

  const rejectMutation = useMutation({
    mutationFn: () => {
      if (!order) throw new Error("Order not loaded.");
      return api.rejectAdminOrder(order.id, {
        reason: decisionReason.trim(),
        admin_remarks: adminRemarks.trim() || decisionReason.trim(),
        expected_version: order.version,
      });
    },
    onSuccess: (updated) =>
      applyServerUpdate(
        updated,
        `Order ${updated.order_number} Rejected`,
        "Order marked REJECTED permanently and audit-logged."
      ),
    onError: handleActionError,
  });

  const cancelMutation = useMutation({
    mutationFn: () => {
      if (!order) throw new Error("Order not loaded.");
      return api.cancelAdminOrder(order.id, {
        reason: decisionReason.trim(),
        admin_remarks: adminRemarks.trim() || decisionReason.trim(),
        expected_version: order.version,
      });
    },
    onSuccess: (updated) =>
      applyServerUpdate(
        updated,
        `Order ${updated.order_number} Cancelled`,
        "Any active finished-goods reservations on this order were released atomically."
      ),
    onError: handleActionError,
  });

  const anyMutating =
    saveMutation.isPending ||
    holdReviewMutation.isPending ||
    requestCorrectionMutation.isPending ||
    approveMutation.isPending ||
    rejectMutation.isPending ||
    cancelMutation.isPending;

  const reasonLen = decisionReason.trim().length;
  const totalDraftQty = draftAnalysis.payloadItems.reduce((s, x) => s + x.approved_qty_pkts, 0);

  return (
    <DesktopAdminLayout
      title={order ? `Order Verification — ${order.order_number}` : "Order Verification"}
      subtitle={
        order
          ? `Submitted ${formatDateTimeIst(order.submitted_at)} · Revision v${order.version}`
          : "Loading order from PostgreSQL..."
      }
      actions={
        <Button asChild variant="outline">
          <Link to="/admin/orders">
            <ArrowLeft className="h-4 w-4" />
            Back to Queue
          </Link>
        </Button>
      }
    >
      {detailQuery.isLoading ? (
        <div className="h-64 animate-pulse rounded-xl bg-muted" />
      ) : detailQuery.error || !order ? (
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            Unable to load order details.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {/* Status Summary Header */}
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-card p-5 shadow-sm">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono text-lg font-bold text-primary">{order.order_number}</span>
              <StatusBadge status={order.status} />
              {order.status === "APPROVED" ? (
                <Badge variant="success" className="gap-1">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  Stock Reserved
                </Badge>
              ) : draftAnalysis.hasDraftShortage ? (
                <Badge variant="warning" className="gap-1">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  Insufficient Available Stock
                </Badge>
              ) : (
                <Badge variant="success">Stock Covered</Badge>
              )}
            </div>
            <div className="text-sm text-muted-foreground">
              Order Date: <strong className="text-foreground">{formatOrderDate(order.order_date)}</strong>
            </div>
          </div>

          {!isFactoryAdmin && (
            <div className="flex items-start gap-3 rounded-xl border border-border bg-secondary/50 p-4 text-sm">
              <Lock className="h-5 w-5 text-muted-foreground shrink-0 mt-0.5" />
              <div>
                <strong>Read-Only Oversight View ({user?.role_name}):</strong> Modifying order
                quantities, overriding prices, approving/reserving stock, and rejecting orders are
                restricted exclusively to <code>FACTORY_ADMIN</code>.
              </div>
            </div>
          )}

          {actionBanner && (
            <div
              role="alert"
              className={`rounded-xl border p-4 text-sm space-y-1 ${
                actionBanner.kind === "success"
                  ? "border-emerald-300 bg-emerald-50 text-emerald-950"
                  : "border-red-300 bg-red-50 text-red-950"
              }`}
            >
              <div className="font-bold flex items-center gap-2">
                {actionBanner.kind === "success" ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-700" />
                ) : (
                  <AlertTriangle className="h-4 w-4 text-red-700" />
                )}
                {actionBanner.title}
              </div>
              {actionBanner.detail && <p className="text-xs">{actionBanner.detail}</p>}
            </div>
          )}

          {/* Insufficient Stock Diagnostic & Policy Guard Banner */}
          {draftAnalysis.hasDraftShortage && isEditableState && (
            <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950 space-y-2">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2 font-bold">
                  <AlertTriangle className="h-5 w-5 text-amber-700" />
                  Insufficient Available Finished-Goods Stock — Approval Blocked
                </div>
                {canFactoryAdminEdit && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const matched: Record<number, number> = { ...draftQtyByItem };
                      order.items.forEach((it) => {
                        if ((matched[it.id] ?? it.effective_qty_pkts) > it.live_available_pkts) {
                          matched[it.id] = it.live_available_pkts;
                        }
                      });
                      setDraftQtyByItem(matched);
                    }}
                  >
                    Match Max Available Qty
                  </Button>
                )}
              </div>
              <ul className="list-disc pl-5 text-xs space-y-1">
                {draftAnalysis.shortageLines.map((s) => (
                  <li key={s.sku}>
                    <strong>{s.name}</strong> ({s.sku}): Requested <strong>{s.req}</strong> pkts vs
                    Available <strong>{s.avail}</strong> pkts →{" "}
                    <strong className="text-red-700">Shortage of {s.short} pkts</strong>.
                  </li>
                ))}
              </ul>
              <p className="text-xs text-amber-900/90">
                <strong>Policy (`BR-AVL-02` / `BR-AVL-03`):</strong> Available stock = Physical
                On-Hand minus Active Reservations committed to approved orders. Negative finished-goods
                stock and silent over-approval are prohibited. You may hold this order{" "}
                <em>Under Review</em> awaiting production, reduce verified quantity to cover
                available stock (with customer confirmation), request Salesman correction, or Reject.
              </p>
            </div>
          )}

          {/* Customer + Salesman Info */}
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Store className="h-4 w-4 text-primary" />
                  Customer &amp; Tax Jurisdiction
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Customer</span>
                  <span className="font-bold">
                    {order.customer_name} ({order.customer_code})
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Account Type</span>
                  <Badge variant="secondary">{order.customer_type}</Badge>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Place of Supply</span>
                  <span>
                    {order.place_of_supply_state_name} ({order.place_of_supply_state_code})
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Customer GSTIN</span>
                  <span className="font-mono text-xs">{order.customer_gstin ?? "Unregistered"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">GST Tax Rule</span>
                  <Badge variant="outline">
                    {order.tax_estimate.supply_type === "INTRA_STATE"
                      ? "Intra-State (CGST + SGST)"
                      : "Inter-State (IGST)"}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base">
                  <UserCheck className="h-4 w-4 text-primary" />
                  Salesman &amp; Lifecycle Decision Info
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Submitted By</span>
                  <span className="font-bold">{order.salesman_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Employee / Territory</span>
                  <span>
                    {order.salesman_employee_code ?? "—"} · {order.salesman_territory ?? "—"}
                  </span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="text-muted-foreground shrink-0">Salesman Notes</span>
                  <span className="text-right">{order.notes || "None"}</span>
                </div>
                {order.approved_at && (
                  <div className="flex justify-between text-emerald-800">
                    <span>Approved By</span>
                    <span className="font-semibold">
                      {order.approved_by_name} ({formatDateTimeIst(order.approved_at)})
                    </span>
                  </div>
                )}
                {order.rejected_at && (
                  <div className="flex justify-between text-red-700">
                    <span>Rejected By</span>
                    <span className="font-semibold">
                      {order.rejected_by_name} ({formatDateTimeIst(order.rejected_at)})
                    </span>
                  </div>
                )}
                {order.cancelled_at && (
                  <div className="flex justify-between text-red-700">
                    <span>Cancelled By</span>
                    <span className="font-semibold">
                      {order.cancelled_by_name} ({formatDateTimeIst(order.cancelled_at)})
                    </span>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Line Items & Interactive Quantity/Price/Stock Coverage Table */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 flex-wrap">
              <div>
                <CardTitle className="flex items-center gap-2">
                  <Package className="h-4 w-4 text-primary" />
                  Order Items, Pricing &amp; Stock Availability
                </CardTitle>
                <CardDescription>
                  Original submitted quantities &amp; price-list rates stay preserved for auditability.{" "}
                  <code>Available = On-Hand − Reserved</code>.
                </CardDescription>
              </div>
              {canFactoryAdminEdit && (draftAnalysis.hasItemChanges || draftAnalysis.hasRemarkChanges) && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    const q: Record<number, number> = {};
                    const p: Record<number, string> = {};
                    order.items.forEach((it) => {
                      q[it.id] = it.effective_qty_pkts;
                      p[it.id] = paisaToRupeesInput(it.unit_price_paisa);
                    });
                    setDraftQtyByItem(q);
                    setDraftPriceTextByItem(p);
                    setAdminRemarks(order.admin_remarks ?? "");
                  }}
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Discard Unsaved Edits
                </Button>
              )}
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-y bg-secondary/40 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      <th className="px-4 py-3">Product SKU</th>
                      <th className="px-3 py-3 text-right">Ordered</th>
                      <th className="px-3 py-3 text-right">Verified Qty</th>
                      <th className="px-3 py-3 text-right">Orig. Rate</th>
                      <th className="px-3 py-3 text-right">Unit Price (₹)</th>
                      <th className="px-3 py-3 text-right">Taxable</th>
                      <th className="px-3 py-3 text-right">Physical</th>
                      <th className="px-3 py-3 text-right">Reserved</th>
                      <th className="px-3 py-3 text-right">Available</th>
                      <th className="px-4 py-3 text-right">Stock Check</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {order.items.map((item) => {
                      const draftQty = draftQtyByItem[item.id] ?? item.effective_qty_pkts;
                      const draftPriceStr =
                        draftPriceTextByItem[item.id] ?? paisaToRupeesInput(item.unit_price_paisa);
                      const draftPricePaisa = rupeesStringToPaisa(draftPriceStr, item.unit_price_paisa);
                      const draftTaxable = draftQty * draftPricePaisa;
                      const isReservedOrLater = ["APPROVED", "INVOICED", "PARTIALLY_DISPATCHED", "DISPATCHED"].includes(
                        order.status
                      );
                      const draftShortage = isReservedOrLater
                        ? 0
                        : Math.max(0, draftQty - item.live_available_pkts);

                      return (
                        <tr key={item.id}>
                          <td className="px-4 py-3.5">
                            <div className="font-semibold">{item.display_name}</div>
                            <div className="font-mono text-xs text-muted-foreground">
                              {item.sku_code} · HSN {item.hsn_code} ({(item.gst_rate_bps / 100).toFixed(0)}%)
                            </div>
                          </td>
                          <td className="px-3 py-3.5 text-right tabular-nums text-muted-foreground">
                            {item.ordered_qty_pkts} pkts
                          </td>
                          <td className="px-3 py-3.5 text-right">
                            {canFactoryAdminEdit ? (
                              <Input
                                type="number"
                                min={0}
                                aria-label={`Verified qty for ${item.display_name}`}
                                value={draftQty}
                                onChange={(e) =>
                                  setDraftQtyByItem((prev) => ({
                                    ...prev,
                                    [item.id]: Math.max(0, parseInt(e.target.value, 10) || 0),
                                  }))
                                }
                                className="h-9 w-24 ml-auto text-right font-bold tabular-nums"
                              />
                            ) : (
                              <span className="font-bold tabular-nums">{item.effective_qty_pkts} pkts</span>
                            )}
                            {draftQty !== item.ordered_qty_pkts && (
                              <div className="mt-0.5 text-[11px] font-medium text-amber-700">
                                Orig {item.ordered_qty_pkts}
                              </div>
                            )}
                          </td>
                          <td className="px-3 py-3.5 text-right tabular-nums text-muted-foreground">
                            {formatInrFromPaisa(item.original_unit_price_paisa)}
                          </td>
                          <td className="px-3 py-3.5 text-right">
                            {canFactoryAdminEdit ? (
                              <Input
                                type="number"
                                min={0}
                                step="0.01"
                                aria-label={`Unit price for ${item.display_name}`}
                                value={draftPriceStr}
                                onChange={(e) =>
                                  setDraftPriceTextByItem((prev) => ({
                                    ...prev,
                                    [item.id]: e.target.value,
                                  }))
                                }
                                className="h-9 w-24 ml-auto text-right tabular-nums"
                              />
                            ) : (
                              <span className="tabular-nums">
                                {formatInrFromPaisa(item.unit_price_paisa)}
                              </span>
                            )}
                            {draftPricePaisa !== item.original_unit_price_paisa && (
                              <div className="mt-0.5 text-[11px] font-medium text-blue-700">
                                Modified rate
                              </div>
                            )}
                          </td>
                          <td className="px-3 py-3.5 text-right font-bold tabular-nums">
                            {formatInrFromPaisa(draftTaxable)}
                          </td>
                          <td className="px-3 py-3.5 text-right tabular-nums">
                            {item.live_on_hand_pkts} pkts
                          </td>
                          <td className="px-3 py-3.5 text-right tabular-nums text-muted-foreground">
                            {item.live_reserved_pkts} pkts
                          </td>
                          <td className="px-3 py-3.5 text-right font-semibold tabular-nums">
                            {item.live_available_pkts} pkts
                          </td>
                          <td className="px-4 py-3.5 text-right">
                            {order.status === "APPROVED" ? (
                              <Badge variant="success">Reserved</Badge>
                            ) : draftShortage > 0 ? (
                              <Badge variant="warning" className="tabular-nums">
                                Short {draftShortage}
                              </Badge>
                            ) : (
                              <Badge variant="success">OK</Badge>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Admin Verification Controls & GST Summary */}
          <div className="grid gap-4 lg:grid-cols-2">
            {isFactoryAdmin && (isEditableState || order.status === "APPROVED" || order.status === "CORRECTION_REQUESTED") && (
              <Card className="border-primary/25">
                <CardHeader>
                  <CardTitle className="text-base">Admin Verification &amp; Lifecycle Controls</CardTitle>
                  <CardDescription>
                    {isEditableState
                      ? "All edits, approvals, corrections, and rejections are logged to Audit Trail with actor and timestamp."
                      : order.status === "APPROVED"
                      ? "Order is approved and locked with active stock reservation. Pre-invoice cancellation releases stock cleanly."
                      : "Order awaits Salesman revision and resubmission, or Admin rejection/cancellation."}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-1.5">
                    <label
                      htmlFor="admin-reason"
                      className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                    >
                      Modification / Decision Reason (Required for Qty/Price Edit, Correction, Reject, or Cancel)
                    </label>
                    <Input
                      id="admin-reason"
                      value={decisionReason}
                      onChange={(e) => setDecisionReason(e.target.value)}
                      placeholder="e.g. Stock verified; adjusted to 50 pkts / Credit hold / Approved"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label
                      htmlFor="admin-remarks"
                      className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                    >
                      Administrative Remarks (Visible to Salesman)
                    </label>
                    <textarea
                      id="admin-remarks"
                      rows={2}
                      value={adminRemarks}
                      onChange={(e) => setAdminRemarks(e.target.value)}
                      disabled={!isEditableState && order.status !== "CORRECTION_REQUESTED"}
                      placeholder="Notes for dispatch team or salesman..."
                      className="w-full rounded-lg border border-input bg-card px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
                    />
                  </div>

                  {isEditableState && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {(draftAnalysis.hasItemChanges || draftAnalysis.hasRemarkChanges) && (
                        <Button
                          type="button"
                          variant="outline"
                          disabled={
                            anyMutating ||
                            totalDraftQty <= 0 ||
                            (draftAnalysis.hasItemChanges && reasonLen < 5)
                          }
                          onClick={() => saveMutation.mutate()}
                        >
                          <Save className="h-4 w-4" />
                          {saveMutation.isPending ? "Saving..." : "Save Revisions"}
                        </Button>
                      )}

                      <Button
                        type="button"
                        variant="secondary"
                        disabled={anyMutating}
                        onClick={() => holdReviewMutation.mutate()}
                      >
                        <PauseCircle className="h-4 w-4" />
                        {order.status === "SUBMITTED" ? "Mark Under Review" : "Log Stock Check"}
                      </Button>

                      <Button
                        type="button"
                        variant="outline"
                        disabled={anyMutating || reasonLen < 5}
                        onClick={() => requestCorrectionMutation.mutate()}
                      >
                        Request Correction
                      </Button>

                      <Button
                        type="button"
                        variant="default"
                        disabled={
                          anyMutating ||
                          draftAnalysis.hasDraftShortage ||
                          totalDraftQty <= 0 ||
                          (draftAnalysis.hasItemChanges && reasonLen < 5)
                        }
                        onClick={() => approveMutation.mutate()}
                      >
                        <CheckCircle2 className="h-4 w-4" />
                        {approveMutation.isPending
                          ? "Approving..."
                          : draftAnalysis.hasItemChanges
                          ? "Save & Approve Order"
                          : "Approve & Reserve Stock"}
                      </Button>

                      <Button
                        type="button"
                        variant="destructive"
                        disabled={anyMutating || reasonLen < 5}
                        onClick={() => rejectMutation.mutate()}
                      >
                        <XCircle className="h-4 w-4" />
                        Reject Order
                      </Button>
                    </div>
                  )}

                  {order.status === "CORRECTION_REQUESTED" && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      <Button
                        type="button"
                        variant="destructive"
                        disabled={anyMutating || reasonLen < 5}
                        onClick={() => rejectMutation.mutate()}
                      >
                        <XCircle className="h-4 w-4" />
                        Reject Order
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        disabled={anyMutating || reasonLen < 5}
                        onClick={() => cancelMutation.mutate()}
                      >
                        <Ban className="h-4 w-4" />
                        Cancel Order
                      </Button>
                    </div>
                  )}

                  {order.status === "APPROVED" && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      <Button asChild>
                        <Link to="/admin/billing">
                          <CheckCircle2 className="h-4 w-4" />
                          Proceed to GST Billing Desk
                        </Link>
                      </Button>
                      <Button
                        type="button"
                        variant="destructive"
                        disabled={anyMutating || reasonLen < 5}
                        onClick={() => cancelMutation.mutate()}
                      >
                        <Ban className="h-4 w-4" />
                        Cancel Approved Order &amp; Release Reservation
                      </Button>
                    </div>
                  )}
                  {order.invoice_id && (
                    <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs space-y-1.5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <span className="font-semibold">GST Invoice: </span>
                          <Link
                            to={`/admin/billing/invoices/${order.invoice_id}`}
                            className="font-mono font-bold text-primary hover:underline"
                          >
                            {order.invoice_number ?? `Draft Invoice #${order.invoice_id}`}
                          </Link>
                        </div>
                        <div className="flex gap-1.5">
                          <StatusBadge status={order.invoice_doc_status ?? "DRAFT"} />
                          {order.invoice_dispatch_status && <StatusBadge status={order.invoice_dispatch_status} />}
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" asChild>
                          <Link to={`/admin/billing/invoices/${order.invoice_id}`}>Open Invoice &amp; PDF</Link>
                        </Button>
                        {order.invoice_doc_status === "ISSUED" && order.invoice_dispatch_status !== "DISPATCHED" && (
                          <Button size="sm" asChild>
                            <Link to={`/admin/dispatch?invoice_id=${order.invoice_id}`}>Dispatch Order</Link>
                          </Button>
                        )}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* GST Financial Summary Card */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Order Financial Summary (Integer-Paisa Arithmetic)
                </CardTitle>
                <CardDescription>
                  {draftAnalysis.hasItemChanges
                    ? "Live preview reflecting unsaved edits; final values recalculate server-side."
                    : "Authoritative server-computed taxable total and GST breakdown."}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Taxable Total</span>
                  <span className="font-semibold tabular-nums">
                    {formatInrFromPaisa(draftAnalysis.taxableTotal)}
                  </span>
                </div>
                {order.tax_estimate.supply_type === "INTRA_STATE" ? (
                  <>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">CGST (2.5%)</span>
                      <span className="tabular-nums">
                        {formatInrFromPaisa(draftAnalysis.cgstTotal)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">SGST (2.5%)</span>
                      <span className="tabular-nums">
                        {formatInrFromPaisa(draftAnalysis.sgstTotal)}
                      </span>
                    </div>
                  </>
                ) : (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">IGST (5.0%)</span>
                    <span className="tabular-nums">
                      {formatInrFromPaisa(draftAnalysis.igstTotal)}
                    </span>
                  </div>
                )}
                <div className="flex justify-between border-t pt-2.5 text-base font-bold">
                  <span>Estimated Invoice Grand Total</span>
                  <span className="tabular-nums text-primary">
                    {formatInrFromPaisa(draftAnalysis.grandTotal)}
                  </span>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Reservations + Status History */}
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <ShieldCheck className="h-4 w-4 text-primary" />
                  Stock Reservations &amp; Verification Snapshots
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-xs">
                {order.reservations.length > 0 && (
                  <div className="space-y-2">
                    <div className="font-semibold uppercase tracking-wide text-muted-foreground">
                      Order Stock Reservations
                    </div>
                    {order.reservations.map((res) => (
                      <div key={res.id} className="rounded-lg border p-2.5 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-mono font-bold">{res.sku_code}</span>
                          <Badge variant={res.status === "ACTIVE" ? "success" : "secondary"}>
                            {res.status} · {res.reserved_qty_pkts} pkts
                          </Badge>
                        </div>
                        <div className="text-muted-foreground">
                          Reserved by {res.reserved_by_name} at {formatDateTimeIst(res.reserved_at)}
                        </div>
                        {res.released_at && (
                          <div className="text-red-700">
                            Released by {res.released_by_name} at {formatDateTimeIst(res.released_at)}:{" "}
                            {res.release_reason}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <div className="space-y-2">
                  <div className="font-semibold uppercase tracking-wide text-muted-foreground">
                    Verification Check History
                  </div>
                  {order.approvals.map((app) => (
                    <div key={app.id} className="rounded-lg bg-secondary/50 p-3 space-y-1">
                      <div className="flex justify-between font-semibold">
                        <span>
                          {app.decision} ({app.reviewed_by_name})
                        </span>
                        <span className="text-muted-foreground">{formatDateTimeIst(app.decided_at)}</span>
                      </div>
                      <div className="text-muted-foreground tabular-nums">
                        Requested: {app.ordered_total_pkts} pkts · Avail: {app.available_total_pkts} pkts
                        {app.shortage_pkts > 0 ? ` · Short: ${app.shortage_pkts} pkts` : ""}
                      </div>
                      {app.remarks && <div>{app.remarks}</div>}
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Clock className="h-4 w-4 text-primary" />
                  Order Status Timeline
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {order.status_history.map((h) => (
                  <div
                    key={h.id}
                    className="flex items-start justify-between gap-2 border-b pb-2 last:border-b-0 last:pb-0"
                  >
                    <div>
                      <div className="flex items-center gap-2">
                        {h.from_status && (
                          <span className="text-[11px] font-mono text-muted-foreground">
                            {h.from_status} →
                          </span>
                        )}
                        <StatusBadge status={h.to_status} />
                        <span className="text-xs font-medium">{h.changed_by_name}</span>
                      </div>
                      {h.reason && <p className="mt-1 text-xs text-muted-foreground">{h.reason}</p>}
                    </div>
                    <span className="text-xs text-muted-foreground shrink-0">
                      {formatDateTimeIst(h.changed_at)}
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>

          {/* Complete Immutable Audit Trail */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FileClock className="h-4 w-4 text-primary" />
                Immutable Audit Trail (`audit.audit_logs`)
              </CardTitle>
              <CardDescription>
                Append-only record of creation, quantity/price overrides, approvals, rejections,
                remarks, and reservation changes.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {order.audit_trail.length === 0 ? (
                <div className="p-5 text-xs text-muted-foreground">No audit logs recorded yet.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-y bg-secondary/40 text-left font-semibold uppercase tracking-wider text-muted-foreground">
                        <th className="px-4 py-2.5">Time (IST)</th>
                        <th className="px-3 py-2.5">Actor &amp; Role</th>
                        <th className="px-3 py-2.5">Action</th>
                        <th className="px-3 py-2.5">Reason</th>
                        <th className="px-4 py-2.5">Before / After State</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {order.audit_trail.map((log) => (
                        <tr key={log.id}>
                          <td className="px-4 py-2.5 text-muted-foreground whitespace-nowrap">
                            {formatDateTimeIst(log.occurred_at)}
                          </td>
                          <td className="px-3 py-2.5">
                            <div className="font-semibold">{log.actor_name}</div>
                            <div className="text-[11px] text-muted-foreground">{log.actor_role}</div>
                          </td>
                          <td className="px-3 py-2.5 font-mono font-bold text-primary">
                            {log.action}
                          </td>
                          <td className="px-3 py-2.5">{log.reason || "—"}</td>
                          <td className="px-4 py-2.5 font-mono text-[11px] text-muted-foreground">
                            {log.before_state && (
                              <div>Before: {JSON.stringify(log.before_state)}</div>
                            )}
                            {log.after_state && (
                              <div>After: {JSON.stringify(log.after_state)}</div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </DesktopAdminLayout>
  );
}

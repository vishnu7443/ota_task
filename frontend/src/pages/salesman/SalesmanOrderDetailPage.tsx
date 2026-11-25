import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useLocation, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  Clock,
  Download,
  Edit3,
  Mail,
  MessageCircle,
  MessageSquare,
  PlusCircle,
  RefreshCw,
  Truck,
  XCircle,
} from "lucide-react";
import { MobileSalesLayout } from "@/components/layouts/MobileSalesLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api, type OrderDetail } from "@/lib/api";
import { formatDateTimeIst, formatInrFromPaisa, formatOrderDate } from "@/lib/money";

export function SalesmanOrderDetailPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const location = useLocation();
  const queryClient = useQueryClient();
  const routeState = location.state as { order?: OrderDetail; justSubmitted?: boolean } | null;

  const orderQuery = useQuery({
    queryKey: ["salesman-order-detail", orderId],
    queryFn: () => api.getOrderDetail(Number(orderId)),
    initialData: routeState?.order,
    enabled: Boolean(orderId),
    refetchInterval: 10_000,
    refetchOnWindowFocus: true,
  });

  const order = orderQuery.data;

  // Correction resubmit state (only active when status === "CORRECTION_REQUESTED")
  const [isEditingCorrection, setIsEditingCorrection] = useState(false);
  const [editQuantities, setEditQuantities] = useState<Record<number, number>>({});
  const [editNotes, setEditNotes] = useState("");
  const [cancelReason, setCancelReason] = useState("");
  const [showCancelForm, setShowCancelForm] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  const resubmitMutation = useMutation({
    mutationFn: () => {
      if (!order) throw new Error("Missing order.");
      return api.resubmitSalesmanOrder(order.id, {
        notes: editNotes.trim() || null,
        items: order.items.map((item) => ({
          pack_size_id: item.pack_size_id,
          ordered_qty_pkts: editQuantities[item.pack_size_id] ?? item.ordered_qty_pkts,
        })),
      });
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(["salesman-order-detail", orderId], updated);
      queryClient.invalidateQueries({ queryKey: ["salesman-orders"] });
      setIsEditingCorrection(false);
      setActionError(null);
      setActionSuccess("Order updated with server pricing and resubmitted to Factory Admin.");
    },
    onError: (err) => {
      setActionSuccess(null);
      setActionError(err instanceof ApiClientError ? err.message : "Failed to resubmit order.");
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => {
      if (!order) throw new Error("Missing order.");
      return api.cancelSalesmanOrder(order.id, cancelReason.trim());
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(["salesman-order-detail", orderId], updated);
      queryClient.invalidateQueries({ queryKey: ["salesman-orders"] });
      setShowCancelForm(false);
      setCancelReason("");
      setActionError(null);
      setActionSuccess("Order cancelled.");
    },
    onError: (err) => {
      setActionSuccess(null);
      setActionError(err instanceof ApiClientError ? err.message : "Failed to cancel order.");
    },
  });

  const startCorrectionEdit = () => {
    if (!order) return;
    const nextQty: Record<number, number> = {};
    order.items.forEach((it) => {
      nextQty[it.pack_size_id] = it.ordered_qty_pkts;
    });
    setEditQuantities(nextQty);
    setEditNotes(order.notes ?? "");
    setActionError(null);
    setActionSuccess(null);
    setIsEditingCorrection(true);
  };

  return (
    <MobileSalesLayout
      title={order ? `Order ${order.order_number}` : "Order Status & Details"}
      subtitle={order ? `${order.customer_name} · ${formatOrderDate(order.order_date)}` : "Loading..."}
    >
      {orderQuery.isLoading && !order ? (
        <div className="h-48 animate-pulse rounded-xl bg-muted" />
      ) : orderQuery.error && !order ? (
        <Card>
          <CardContent className="p-4 text-sm text-destructive">
            Unable to load order details.
          </CardContent>
        </Card>
      ) : order ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-2">
            <Button asChild variant="ghost" size="sm" className="px-2">
              <Link to="/salesman/orders">
                <ArrowLeft className="h-4 w-4" />
                My Orders
              </Link>
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => orderQuery.refetch()}
              disabled={orderQuery.isFetching}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${orderQuery.isFetching ? "animate-spin" : ""}`} />
              Refresh Status
            </Button>
          </div>

          {routeState?.justSubmitted && order.status === "SUBMITTED" && (
            <Card className="border-emerald-200 bg-emerald-50/70">
              <CardContent className="p-4 text-center space-y-1.5">
                <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-700" />
                <div className="text-base font-bold text-emerald-950">Order Submitted!</div>
                <div className="font-mono text-xs font-bold text-emerald-800">{order.order_number}</div>
                <p className="text-xs text-emerald-800/80">
                  Sent to Factory Desk at {formatDateTimeIst(order.submitted_at)}
                </p>
              </CardContent>
            </Card>
          )}

          {/* Authoritative Status Card */}
          <Card>
            <CardContent className="p-4 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div>
                  <div className="font-mono text-sm font-bold text-primary">{order.order_number}</div>
                  <div className="text-xs text-muted-foreground">
                    Submitted: {formatDateTimeIst(order.submitted_at)}
                  </div>
                </div>
                <StatusBadge status={order.status} />
              </div>

              {order.status === "APPROVED" && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900 space-y-1">
                  <div className="flex items-center gap-1.5 font-bold">
                    <CheckCircle2 className="h-4 w-4 text-emerald-700" />
                    Approved by {order.approved_by_name ?? "Factory Admin"}
                  </div>
                  <div>Approved on {formatDateTimeIst(order.approved_at)}</div>
                  {order.admin_remarks && (
                    <div className="pt-1 border-t border-emerald-200/80">
                      <strong>Admin Remark:</strong> {order.admin_remarks}
                    </div>
                  )}
                </div>
              )}

              {order.status === "REJECTED" && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-900 space-y-1">
                  <div className="flex items-center gap-1.5 font-bold">
                    <XCircle className="h-4 w-4 text-red-700" />
                    Rejected by {order.rejected_by_name ?? "Factory Admin"}
                  </div>
                  <div>
                    <strong>Rejection Reason:</strong> {order.rejection_reason || "No reason recorded"}
                  </div>
                  {order.admin_remarks && order.admin_remarks !== order.rejection_reason && (
                    <div>
                      <strong>Remarks:</strong> {order.admin_remarks}
                    </div>
                  )}
                </div>
              )}

              {order.status === "CORRECTION_REQUESTED" && (
                <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-950 space-y-2">
                  <div className="flex items-center gap-1.5 font-bold">
                    <AlertTriangle className="h-4 w-4 text-amber-700" />
                    Correction Requested by Factory Admin
                  </div>
                  <div>{order.admin_remarks || "Please update quantities and resubmit."}</div>
                  {!isEditingCorrection && (
                    <Button type="button" size="sm" onClick={startCorrectionEdit} className="w-full">
                      <Edit3 className="h-3.5 w-3.5" />
                      Edit Quantities &amp; Resubmit
                    </Button>
                  )}
                </div>
              )}

              {order.status === "UNDER_REVIEW" && (
                <div className="rounded-lg border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-900 space-y-1">
                  <div className="font-bold">Under Factory Verification</div>
                  {order.admin_remarks && <div>{order.admin_remarks}</div>}
                  {order.has_shortage && (
                    <div>
                      Factory stock is currently below ordered quantity; Admin is reviewing allocation.
                    </div>
                  )}
                </div>
              )}

              {order.status === "SUBMITTED" && order.admin_remarks && (
                <div className="flex items-start gap-2 rounded-lg bg-secondary/70 p-2.5 text-xs">
                  <MessageSquare className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                  <div>
                    <strong>Admin Note:</strong> {order.admin_remarks}
                  </div>
                </div>
              )}

              {order.status === "CANCELLED" && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-900 space-y-1">
                  <div className="font-bold">
                    Cancelled by {order.cancelled_by_name ?? "Staff"} on {formatDateTimeIst(order.cancelled_at)}
                  </div>
                  <div>Reason: {order.cancellation_reason}</div>
                </div>
              )}

              {/* Phase 8: Salesman Invoice Availability & Dispatch / Delivery Status */}
              {order.invoice_id && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50/70 p-3 text-xs space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="font-bold text-emerald-950">
                        GST Invoice: {order.invoice_number ?? "Draft Being Prepared"}
                      </div>
                      {order.invoice_grand_total_paisa != null && (
                        <div className="text-emerald-900">
                          Total: {formatInrFromPaisa(order.invoice_grand_total_paisa)}
                        </div>
                      )}
                      {order.invoice_doc_status === "ISSUED" && (
                        <div className="text-emerald-900 mt-0.5">
                          Paid: {formatInrFromPaisa(order.invoice_paid_paisa ?? 0)} · Balance:{" "}
                          <span className="font-semibold">
                            {formatInrFromPaisa(
                              order.invoice_outstanding_paisa ??
                                Math.max(0, (order.invoice_grand_total_paisa ?? 0) - (order.invoice_paid_paisa ?? 0))
                            )}
                          </span>
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <StatusBadge status={order.invoice_doc_status ?? "DRAFT"} />
                      {order.invoice_doc_status === "ISSUED" && order.invoice_payment_status && (
                        <StatusBadge status={order.invoice_payment_status} />
                      )}
                    </div>
                  </div>
                  {order.invoice_doc_status === "ISSUED" && (
                    <div className="space-y-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="w-full"
                        onClick={async () => {
                          try {
                            const blob = await api.fetchInvoicePdfBlob(order.invoice_id!);
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = `${(order.invoice_number ?? `INV-${order.invoice_id}`).replaceAll("/", "-")}.pdf`;
                            a.click();
                            URL.revokeObjectURL(url);
                          } catch {
                            setActionError("Unable to download Invoice PDF right now.");
                          }
                        }}
                      >
                        <Download className="h-3.5 w-3.5" />
                        Download GST Invoice PDF
                      </Button>
                      <div className="grid grid-cols-2 gap-2">
                        <Button asChild size="sm" variant="outline">
                          <a
                            href={`https://wa.me/?text=${encodeURIComponent(
                              `GST Invoice ${order.invoice_number} for ${order.customer_name} (Order ${order.order_number}): Total ${formatInrFromPaisa(order.invoice_grand_total_paisa ?? 0)}, Balance ${formatInrFromPaisa(order.invoice_outstanding_paisa ?? 0)}.`
                            )}`}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            <MessageCircle className="h-3.5 w-3.5" />
                            WhatsApp
                          </a>
                        </Button>
                        <Button asChild size="sm" variant="outline">
                          <a
                            href={`mailto:?subject=${encodeURIComponent(
                              `GST Invoice ${order.invoice_number} - Kaveri Traditional Snacks`
                            )}&body=${encodeURIComponent(
                              `GST Invoice ${order.invoice_number} for ${order.customer_name} (Order ${order.order_number}): Total ${formatInrFromPaisa(order.invoice_grand_total_paisa ?? 0)}, Balance ${formatInrFromPaisa(order.invoice_outstanding_paisa ?? 0)}.`
                            )}`}
                          >
                            <Mail className="h-3.5 w-3.5" />
                            Email
                          </a>
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {(order.dispatches ?? []).length > 0 && (
                <div className="rounded-lg border p-3 text-xs space-y-2">
                  <div className="flex items-center gap-1.5 font-bold">
                    <Truck className="h-3.5 w-3.5 text-primary" />
                    Dispatch &amp; Delivery Updates
                  </div>
                  {(order.dispatches ?? []).map((d) => (
                    <div key={d.id} className="rounded bg-secondary/50 p-2 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-mono font-bold">{d.dispatch_number}</span>
                        <StatusBadge status={d.status} />
                      </div>
                      <div className="text-muted-foreground">
                        {d.total_dispatched_pkts} pkts · Dispatch: {formatOrderDate(d.dispatch_date)}
                        {d.vehicle_number ? ` · ${d.vehicle_number}` : ""}
                      </div>
                      {d.delivery_date && (
                        <div className="font-medium text-emerald-800">
                          Delivered: {formatOrderDate(d.delivery_date)} ({d.total_received_pkts} pkts received)
                        </div>
                      )}
                      {d.delivery_exception_reason && (
                        <div className="font-medium text-red-700">
                          Exception: {d.delivery_exception_reason}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {actionSuccess && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-medium text-emerald-900">
              {actionSuccess}
            </div>
          )}
          {actionError && (
            <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-medium text-red-800">
              {actionError}
            </div>
          )}

          {/* Salesman Inline Correction Editor */}
          {isEditingCorrection && order.status === "CORRECTION_REQUESTED" && (
            <Card className="border-primary/40">
              <CardContent className="p-4 space-y-3">
                <div className="text-sm font-bold">Revise Quantities &amp; Resubmit</div>
                {order.items.map((item) => (
                  <div key={item.id} className="space-y-1">
                    <div className="flex justify-between text-xs font-semibold">
                      <span>{item.display_name}</span>
                      <span className="text-muted-foreground">Prev: {item.ordered_qty_pkts} pkts</span>
                    </div>
                    <Input
                      type="number"
                      min={1}
                      value={editQuantities[item.pack_size_id] ?? item.ordered_qty_pkts}
                      onChange={(e) =>
                        setEditQuantities((prev) => ({
                          ...prev,
                          [item.pack_size_id]: Math.max(1, parseInt(e.target.value, 10) || 1),
                        }))
                      }
                    />
                  </div>
                ))}
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Order Notes</label>
                  <Input
                    value={editNotes}
                    onChange={(e) => setEditNotes(e.target.value)}
                    placeholder="Confirmation note with shop"
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    className="flex-1"
                    onClick={() => setIsEditingCorrection(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="button"
                    className="flex-1"
                    disabled={resubmitMutation.isPending}
                    onClick={() => resubmitMutation.mutate()}
                  >
                    {resubmitMutation.isPending ? "Submitting..." : "Resubmit Order"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Customer & Line Items */}
          <Card>
            <CardContent className="p-4 space-y-3 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Customer</span>
                <span className="font-semibold">{order.customer_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Place of Supply</span>
                <span>
                  {order.place_of_supply_state_name} ({order.place_of_supply_state_code})
                </span>
              </div>
              {order.notes && (
                <div className="flex justify-between gap-3 text-xs">
                  <span className="text-muted-foreground shrink-0">Your Notes</span>
                  <span className="text-right">{order.notes}</span>
                </div>
              )}

              <div className="border-t pt-3 space-y-2.5">
                <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Items &amp; Verified Quantities
                </div>
                {order.items.map((item) => (
                  <div key={item.id} className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-semibold">{item.display_name}</div>
                      <div className="text-xs text-muted-foreground tabular-nums">
                        {item.effective_qty_pkts} pkts × {formatInrFromPaisa(item.unit_price_paisa)}
                      </div>
                      {item.is_qty_modified && (
                        <div className="text-[11px] font-medium text-amber-700">
                          Originally submitted: {item.ordered_qty_pkts} pkts → Revised to {item.effective_qty_pkts} pkts
                        </div>
                      )}
                      {item.is_price_modified && (
                        <div className="text-[11px] font-medium text-blue-700">
                          Rate adjusted by Admin (orig {formatInrFromPaisa(item.original_unit_price_paisa)})
                        </div>
                      )}
                    </div>
                    <div className="font-bold tabular-nums">
                      {formatInrFromPaisa(item.line_taxable_paisa)}
                    </div>
                  </div>
                ))}
              </div>

              <div className="border-t pt-2.5 space-y-1">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>Taxable Value</span>
                  <span className="tabular-nums">
                    {formatInrFromPaisa(order.tax_estimate.taxable_total_paisa)}
                  </span>
                </div>
                {order.tax_estimate.supply_type === "INTRA_STATE" ? (
                  <>
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Est. CGST (2.5%)</span>
                      <span className="tabular-nums">
                        {formatInrFromPaisa(order.tax_estimate.cgst_total_paisa)}
                      </span>
                    </div>
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Est. SGST (2.5%)</span>
                      <span className="tabular-nums">
                        {formatInrFromPaisa(order.tax_estimate.sgst_total_paisa)}
                      </span>
                    </div>
                  </>
                ) : (
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Est. IGST (5%)</span>
                    <span className="tabular-nums">
                      {formatInrFromPaisa(order.tax_estimate.igst_total_paisa)}
                    </span>
                  </div>
                )}
                <div className="flex justify-between font-bold text-base pt-1 border-t">
                  <span>Estimated Invoice Total</span>
                  <span className="tabular-nums text-primary">
                    {formatInrFromPaisa(order.tax_estimate.grand_total_paisa)}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Status Timeline */}
          <Card>
            <CardContent className="p-4 space-y-3">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                <Clock className="h-3.5 w-3.5 text-primary" />
                Order History
              </div>
              <div className="space-y-2.5">
                {order.status_history.map((h) => (
                  <div key={h.id} className="flex items-start justify-between gap-2 border-b pb-2 last:border-b-0 last:pb-0">
                    <div>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={h.to_status} />
                        <span className="text-xs font-medium">{h.changed_by_name}</span>
                      </div>
                      {h.reason && <p className="mt-1 text-xs text-muted-foreground">{h.reason}</p>}
                    </div>
                    <span className="text-[11px] text-muted-foreground shrink-0">
                      {formatDateTimeIst(h.changed_at)}
                    </span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Withdraw option only while pre-approval (SUBMITTED or CORRECTION_REQUESTED) */}
          {(order.status === "SUBMITTED" || order.status === "CORRECTION_REQUESTED") && (
            <Card>
              <CardContent className="p-4 space-y-2">
                {!showCancelForm ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="w-full text-destructive border-destructive/30 hover:bg-red-50"
                    onClick={() => setShowCancelForm(true)}
                  >
                    Withdraw / Cancel Order
                  </Button>
                ) : (
                  <div className="space-y-2">
                    <label className="text-xs font-semibold text-muted-foreground">
                      Cancellation Reason (min 5 chars)
                    </label>
                    <Input
                      value={cancelReason}
                      onChange={(e) => setCancelReason(e.target.value)}
                      placeholder="e.g. Shop cancelled order before dispatch"
                    />
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="flex-1"
                        onClick={() => setShowCancelForm(false)}
                      >
                        Back
                      </Button>
                      <Button
                        type="button"
                        variant="destructive"
                        size="sm"
                        className="flex-1"
                        disabled={cancelMutation.isPending || cancelReason.trim().length < 5}
                        onClick={() => cancelMutation.mutate()}
                      >
                        {cancelMutation.isPending ? "Cancelling..." : "Confirm Cancel"}
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          <div className="grid grid-cols-2 gap-2.5">
            <Button asChild variant="outline" size="lg">
              <Link to="/salesman/orders">
                <ClipboardList className="h-4 w-4" />
                My Orders
              </Link>
            </Button>
            <Button asChild size="lg">
              <Link to="/salesman/new-order">
                <PlusCircle className="h-4 w-4" />
                New Order
              </Link>
            </Button>
          </div>
        </div>
      ) : null}
    </MobileSalesLayout>
  );
}

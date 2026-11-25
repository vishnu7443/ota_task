import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  CheckCircle2,
  PackageCheck,
  Plus,
  Search,
  Send,
  Trash2,
  X,
  XCircle,
} from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api, type MaterialSummary } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDateTimeIst, formatInrFromPaisa, formatOrderDate } from "@/lib/money";
import { compatibleUomsForMaterial, formatBaseQty, toNumber } from "@/lib/units";

interface DraftPoRow {
  rowKey: number;
  material_id: string;
  entered_qty: string;
  entered_uom: string;
  rate_rupees: string;
  gst_pct: string;
}

export function AdminPurchaseOrdersPage() {
  const { user } = useAuth();
  const isAdmin = user?.role_code === "FACTORY_ADMIN";
  const canCreate = user?.role_code === "FACTORY_ADMIN" || user?.role_code === "PRODUCTION_SUPERVISOR";
  const queryClient = useQueryClient();

  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const [selectedPoId, setSelectedPoId] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [banner, setBanner] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  const [supplierId, setSupplierId] = useState("");
  const [orderDate, setOrderDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [expectedDate, setExpectedDate] = useState("");
  const [notes, setNotes] = useState("");
  const [submitImmediately, setSubmitImmediately] = useState(true);
  const [reasonText, setReasonText] = useState("");
  const [rows, setRows] = useState<DraftPoRow[]>([
    { rowKey: 1, material_id: "", entered_qty: "60", entered_uom: "kg", rate_rupees: "45.00", gst_pct: "5" },
  ]);

  const suppliersQuery = useQuery({
    queryKey: ["purchasing-suppliers-active"],
    queryFn: () => api.getSuppliers({ activeOnly: true }),
  });

  const materialsQuery = useQuery({
    queryKey: ["inventory-materials"],
    queryFn: () => api.getMaterials(),
  });

  const posQuery = useQuery({
    queryKey: ["purchasing-orders", statusFilter, search],
    queryFn: () =>
      api.getPurchaseOrders({
        status: statusFilter || undefined,
        search: search.trim() || undefined,
      }),
    refetchInterval: 15_000,
  });

  const detailQuery = useQuery({
    queryKey: ["purchasing-order-detail", selectedPoId],
    queryFn: () => api.getPurchaseOrderDetail(Number(selectedPoId)),
    enabled: Boolean(selectedPoId),
  });

  const materialsMap = useMemo(() => {
    const map: Record<number, MaterialSummary> = {};
    (materialsQuery.data ?? []).forEach((m) => {
      map[m.id] = m;
    });
    return map;
  }, [materialsQuery.data]);

  const previewTotals = useMemo(() => {
    let sub = 0;
    let tax = 0;
    rows.forEach((r) => {
      const q = Number(r.entered_qty) || 0;
      const ratePaisa = Math.round((Number(r.rate_rupees) || 0) * 100);
      const gstBps = Math.round((Number(r.gst_pct) || 0) * 100);
      const lineSub = Math.round(q * ratePaisa);
      const lineTax = Math.round((lineSub * gstBps) / 10_000);
      sub += lineSub;
      tax += lineTax;
    });
    return { sub, tax, total: sub + tax };
  }, [rows]);

  const createPoMutation = useMutation({
    mutationFn: () =>
      api.createPurchaseOrder({
        supplier_id: Number(supplierId),
        order_date: orderDate || null,
        expected_date: expectedDate || null,
        notes: notes.trim() || null,
        submit_immediately: submitImmediately,
        items: rows.map((r) => ({
          material_id: Number(r.material_id),
          entered_qty: r.entered_qty,
          entered_uom: r.entered_uom,
          unit_rate_paisa: Math.round(Number(r.rate_rupees) * 100),
          gst_rate_bps: Math.round((Number(r.gst_pct) || 0) * 100),
        })),
      }),
    onSuccess: (po) => {
      queryClient.invalidateQueries({ queryKey: ["purchasing-orders"] });
      setBanner({
        kind: "success",
        msg: `Purchase Order ${po.po_number} (${po.status}) saved. Stock will increase only after Goods Receipt posting.`,
      });
      setSelectedPoId(po.id);
      setShowCreate(false);
    },
    onError: (err) => {
      const msg = err instanceof ApiClientError ? err.message : "Failed to create Purchase Order.";
      setBanner({ kind: "error", msg });
    },
  });

  const actionMutation = useMutation({
    mutationFn: async (opts: { kind: "submit" | "approve" | "reject" | "cancel"; poId: number }) => {
      if (opts.kind === "submit") return api.submitPurchaseOrder(opts.poId);
      if (opts.kind === "approve") return api.approvePurchaseOrder(opts.poId);
      if (opts.kind === "reject") return api.rejectPurchaseOrder(opts.poId, reasonText.trim());
      return api.cancelPurchaseOrder(opts.poId, reasonText.trim());
    },
    onSuccess: (po) => {
      queryClient.invalidateQueries({ queryKey: ["purchasing-orders"] });
      queryClient.invalidateQueries({ queryKey: ["purchasing-order-detail", po.id] });
      setReasonText("");
      setBanner({ kind: "success", msg: `Purchase Order ${po.po_number} updated to ${po.status}.` });
    },
    onError: (err) => {
      const msg = err instanceof ApiClientError ? err.message : "Action failed.";
      setBanner({ kind: "error", msg });
    },
  });

  const addRow = () => {
    setRows((prev) => [
      ...prev,
      {
        rowKey: Date.now() + Math.random(),
        material_id: "",
        entered_qty: "10",
        entered_uom: "kg",
        rate_rupees: "0.00",
        gst_pct: "5",
      },
    ]);
  };

  const handleMaterialChange = (idx: number, matIdStr: string) => {
    const mat = materialsMap[Number(matIdStr)];
    setRows((prev) =>
      prev.map((row, i) =>
        i === idx
          ? {
              ...row,
              material_id: matIdStr,
              entered_uom: mat ? mat.display_uom : row.entered_uom,
            }
          : row
      )
    );
  };

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    createPoMutation.mutate();
  };

  const pos = posQuery.data ?? [];
  const detail = detailQuery.data;

  return (
    <DesktopAdminLayout
      title="Purchase Orders"
      subtitle="Procure raw materials & packaging supplies without altering physical stock before receipt posting"
      actions={
        canCreate ? (
          <Button onClick={() => setShowCreate((v) => !v)}>
            {showCreate ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            {showCreate ? "Close PO Form" : "New Purchase Order"}
          </Button>
        ) : undefined
      }
    >
      <div className="space-y-6">
        {banner && (
          <div
            className={`rounded-xl border px-4 py-3 text-sm font-medium ${
              banner.kind === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-red-200 bg-red-50 text-red-800"
            }`}
          >
            {banner.msg}
          </div>
        )}

        {showCreate && canCreate && (
          <Card className="border-primary/30 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base">Create Purchase Order</CardTitle>
              <CardDescription>
                Add Raw Materials and Packaging items using dimension-safe units (kg/g, L/ml, piece).
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreateSubmit} className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-muted-foreground">Supplier</label>
                    <select
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      value={supplierId}
                      onChange={(e) => setSupplierId(e.target.value)}
                      required
                    >
                      <option value="">Select supplier...</option>
                      {(suppliersQuery.data ?? []).map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.code} — {s.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-muted-foreground">Order Date</label>
                    <Input type="date" value={orderDate} onChange={(e) => setOrderDate(e.target.value)} />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-muted-foreground">Expected Delivery</label>
                    <Input type="date" value={expectedDate} onChange={(e) => setExpectedDate(e.target.value)} />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-muted-foreground">Notes</label>
                    <Input
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="Optional vendor instructions"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Order Items
                    </span>
                    <Button type="button" size="sm" variant="outline" onClick={addRow}>
                      <Plus className="h-3.5 w-3.5" />
                      Add Material Line
                    </Button>
                  </div>

                  {rows.map((row, idx) => {
                    const mat = materialsMap[Number(row.material_id)];
                    const uoms = mat ? compatibleUomsForMaterial(mat.unit_dimension) : ["kg", "g", "L", "ml", "piece"];
                    return (
                      <div key={row.rowKey} className="grid gap-2 sm:grid-cols-12 items-end rounded-lg border p-3 bg-secondary/20">
                        <div className="sm:col-span-4 space-y-1">
                          <label className="text-[11px] font-semibold text-muted-foreground">Material</label>
                          <select
                            className="flex h-9 w-full rounded-md border border-input bg-background px-2.5 text-xs"
                            value={row.material_id}
                            onChange={(e) => handleMaterialChange(idx, e.target.value)}
                            required
                          >
                            <option value="">Select material...</option>
                            {(materialsQuery.data ?? []).map((m) => (
                              <option key={m.id} value={m.id}>
                                {m.code} — {m.name} ({m.material_category === "RAW_MATERIAL" ? "RM" : "Pkg"})
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="sm:col-span-2 space-y-1">
                          <label className="text-[11px] font-semibold text-muted-foreground">Qty</label>
                          <Input
                            type="number"
                            step="0.001"
                            min="0.001"
                            className="h-9 text-xs"
                            value={row.entered_qty}
                            onChange={(e) =>
                              setRows((p) => p.map((r, i) => (i === idx ? { ...r, entered_qty: e.target.value } : r)))
                            }
                            required
                          />
                        </div>
                        <div className="sm:col-span-2 space-y-1">
                          <label className="text-[11px] font-semibold text-muted-foreground">Unit</label>
                          <select
                            className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-xs"
                            value={row.entered_uom}
                            onChange={(e) =>
                              setRows((p) => p.map((r, i) => (i === idx ? { ...r, entered_uom: e.target.value } : r)))
                            }
                          >
                            {uoms.map((u) => (
                              <option key={u} value={u}>
                                {u}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="sm:col-span-2 space-y-1">
                          <label className="text-[11px] font-semibold text-muted-foreground">Rate (₹ / UOM)</label>
                          <Input
                            type="number"
                            step="0.01"
                            min="0"
                            className="h-9 text-xs"
                            value={row.rate_rupees}
                            onChange={(e) =>
                              setRows((p) => p.map((r, i) => (i === idx ? { ...r, rate_rupees: e.target.value } : r)))
                            }
                            required
                          />
                        </div>
                        <div className="sm:col-span-1 space-y-1">
                          <label className="text-[11px] font-semibold text-muted-foreground">GST%</label>
                          <Input
                            type="number"
                            step="0.5"
                            min="0"
                            max="28"
                            className="h-9 text-xs"
                            value={row.gst_pct}
                            onChange={(e) =>
                              setRows((p) => p.map((r, i) => (i === idx ? { ...r, gst_pct: e.target.value } : r)))
                            }
                          />
                        </div>
                        <div className="sm:col-span-1 flex justify-end">
                          {rows.length > 1 && (
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              onClick={() => setRows((p) => p.filter((_, i) => i !== idx))}
                            >
                              <Trash2 className="h-4 w-4 text-red-600" />
                            </Button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-t pt-4">
                  <div className="text-xs text-muted-foreground space-y-0.5 tabular-nums">
                    <div>
                      Subtotal: <strong className="text-foreground">{formatInrFromPaisa(previewTotals.sub)}</strong> · Tax:{" "}
                      <strong className="text-foreground">{formatInrFromPaisa(previewTotals.tax)}</strong> · Grand Total:{" "}
                      <strong className="text-primary text-sm">{formatInrFromPaisa(previewTotals.total)}</strong>
                    </div>
                    <label className="flex items-center gap-2 pt-1 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={submitImmediately}
                        onChange={(e) => setSubmitImmediately(e.target.checked)}
                        className="h-4 w-4 rounded border-input"
                      />
                      Submit immediately for Admin approval
                    </label>
                  </div>
                  <Button type="submit" disabled={createPoMutation.isPending}>
                    {createPoMutation.isPending ? "Creating PO..." : "Create Purchase Order"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-1.5">
            {["", "DRAFT", "SUBMITTED", "APPROVED", "PARTIALLY_RECEIVED", "RECEIVED", "REJECTED"].map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => setStatusFilter(st)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
                  statusFilter === st
                    ? "bg-primary text-primary-foreground"
                    : "bg-card border text-muted-foreground hover:text-foreground"
                }`}
              >
                {st || "All Statuses"}
              </button>
            ))}
          </div>
          <div className="relative w-64">
            <Search className="h-4 w-4 absolute left-3 top-2.5 text-muted-foreground" />
            <Input
              className="pl-9 h-9"
              placeholder="Search PO# or supplier..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Purchase Orders ({pos.length})</CardTitle>
              <CardDescription>Select any PO to review lines, approve, or start Goods Receipt</CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="py-2 pr-3">PO #</th>
                    <th className="py-2 pr-3">Supplier</th>
                    <th className="py-2 pr-3">Date</th>
                    <th className="py-2 pr-3 text-right">Total</th>
                    <th className="py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {pos.map((po) => (
                    <tr
                      key={po.id}
                      onClick={() => setSelectedPoId(po.id)}
                      className={`cursor-pointer hover:bg-secondary/40 ${
                        selectedPoId === po.id ? "bg-primary/5" : ""
                      }`}
                    >
                      <td className="py-3 pr-3 font-mono text-xs font-semibold">{po.po_number}</td>
                      <td className="py-3 pr-3">
                        <div className="font-medium text-foreground">{po.supplier_name}</div>
                        <div className="text-xs text-muted-foreground">
                          {po.item_count} line(s) · By {po.created_by_name}
                        </div>
                      </td>
                      <td className="py-3 pr-3 text-xs text-muted-foreground">{formatOrderDate(po.order_date)}</td>
                      <td className="py-3 pr-3 text-right font-semibold tabular-nums">
                        {formatInrFromPaisa(po.total_paisa)}
                      </td>
                      <td className="py-3">
                        <StatusBadge status={po.status} />
                      </td>
                    </tr>
                  ))}
                  {pos.length === 0 && (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-muted-foreground">
                        No purchase orders found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">PO Details &amp; Workflow</CardTitle>
            </CardHeader>
            <CardContent>
              {!detail ? (
                <p className="text-sm text-muted-foreground py-8 text-center">
                  Click a Purchase Order to inspect ordered vs received quantities and perform actions.
                </p>
              ) : (
                <div className="space-y-4 text-sm">
                  <div className="flex items-start justify-between border-b pb-3">
                    <div>
                      <div className="font-mono font-bold text-base">{detail.po_number}</div>
                      <div className="text-xs text-muted-foreground">{detail.supplier_name}</div>
                      <div className="text-[11px] text-muted-foreground mt-1">
                        Created {formatDateTimeIst(detail.created_at)}
                      </div>
                    </div>
                    <StatusBadge status={detail.status} />
                  </div>

                  <div className="space-y-2">
                    {detail.items.map((it) => (
                      <div key={it.id} className="rounded-lg border p-2.5 text-xs space-y-1">
                        <div className="flex justify-between font-semibold">
                          <span>
                            {it.material_name} ({it.material_code})
                          </span>
                          <span className="tabular-nums">{formatInrFromPaisa(it.line_total_paisa)}</span>
                        </div>
                        <div className="text-muted-foreground flex justify-between">
                          <span>
                            Ordered: {it.entered_qty} {it.entered_uom} ({formatBaseQty(it.ordered_qty_base, it.base_uom)})
                          </span>
                          <span className="tabular-nums">Rate: {formatInrFromPaisa(it.unit_rate_paisa)}/{it.entered_uom}</span>
                        </div>
                        <div className="text-[11px] flex justify-between text-emerald-700">
                          <span>Accepted: {formatBaseQty(it.received_qty_base, it.base_uom)}</span>
                          <span className="text-amber-700">Remaining: {formatBaseQty(it.remaining_qty_base, it.base_uom)}</span>
                        </div>
                      </div>
                    ))}
                  </div>

                  {detail.rejection_reason && (
                    <div className="rounded-lg border border-red-200 bg-red-50 p-2.5 text-xs text-red-800">
                      Reason: {detail.rejection_reason}
                    </div>
                  )}

                  <div className="space-y-2 pt-2 border-t">
                    {canCreate && detail.status === "DRAFT" && (
                      <Button
                        className="w-full"
                        onClick={() => actionMutation.mutate({ kind: "submit", poId: detail.id })}
                        disabled={actionMutation.isPending}
                      >
                        <Send className="h-4 w-4" />
                        Submit PO for Approval
                      </Button>
                    )}

                    {isAdmin && detail.status === "SUBMITTED" && (
                      <div className="space-y-2">
                        <Button
                          className="w-full bg-emerald-700 hover:bg-emerald-800"
                          onClick={() => actionMutation.mutate({ kind: "approve", poId: detail.id })}
                          disabled={actionMutation.isPending}
                        >
                          <CheckCircle2 className="h-4 w-4" />
                          Approve Purchase Order
                        </Button>
                        <Input
                          placeholder="Rejection/cancellation reason (min 5 chars)..."
                          value={reasonText}
                          onChange={(e) => setReasonText(e.target.value)}
                        />
                        <Button
                          variant="destructive"
                          className="w-full"
                          disabled={reasonText.trim().length < 5 || actionMutation.isPending}
                          onClick={() => actionMutation.mutate({ kind: "reject", poId: detail.id })}
                        >
                          <XCircle className="h-4 w-4" />
                          Reject PO
                        </Button>
                      </div>
                    )}

                    {canCreate &&
                      (detail.status === "APPROVED" || detail.status === "PARTIALLY_RECEIVED") && (
                        <Button className="w-full" asChild>
                          <Link to={`/admin/purchasing/receipts?po_id=${detail.id}`}>
                            <PackageCheck className="h-4 w-4" />
                            Record Goods Receipt against {detail.po_number}
                          </Link>
                        </Button>
                      )}

                    {isAdmin &&
                      toNumber(
                        detail.items.reduce((acc, i) => acc + Number(i.received_qty_base), 0)
                      ) === 0 &&
                      ["DRAFT", "SUBMITTED", "APPROVED"].includes(detail.status) && (
                        <div className="pt-2 space-y-2">
                          <Input
                            placeholder="Cancel reason (if cancelling PO)..."
                            value={reasonText}
                            onChange={(e) => setReasonText(e.target.value)}
                          />
                          <Button
                            variant="outline"
                            className="w-full text-red-700 border-red-200 hover:bg-red-50"
                            disabled={reasonText.trim().length < 5 || actionMutation.isPending}
                            onClick={() => actionMutation.mutate({ kind: "cancel", poId: detail.id })}
                          >
                            Cancel PO
                          </Button>
                        </div>
                      )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </DesktopAdminLayout>
  );
}

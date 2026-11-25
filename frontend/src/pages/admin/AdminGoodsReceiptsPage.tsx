import React, { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, ClipboardCheck, PackageCheck, Plus, Send, ShieldCheck, X } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api, type GoodsReceiptDetail, type PurchaseOrderDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDateTimeIst, formatInrFromPaisa, formatOrderDate } from "@/lib/money";
import { compatibleUomsForMaterial, formatBaseQty } from "@/lib/units";

interface ReceiptDraftRow {
  purchase_order_item_id: number | null;
  material_id: number;
  material_code: string;
  material_name: string;
  unit_dimension: string;
  entered_uom: string;
  received_qty_entered: string;
  rejected_qty_entered: string;
  rejection_reason: string;
  batch_code: string;
  expiry_date: string;
  allow_excess: boolean;
  remaining_hint: string;
}

export function AdminGoodsReceiptsPage() {
  const { user } = useAuth();
  const canOperate =
    user?.role_code === "FACTORY_ADMIN" || user?.role_code === "PRODUCTION_SUPERVISOR";
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const urlPoId = searchParams.get("po_id");

  const [selectedReceiptId, setSelectedReceiptId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [showCreate, setShowCreate] = useState(Boolean(urlPoId));
  const [chosenPoId, setChosenPoId] = useState<string>(urlPoId ?? "");
  const [supplierBillRef, setSupplierBillRef] = useState("");
  const [receiptDate, setReceiptDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [discrepancyNotes, setDiscrepancyNotes] = useState("");
  const [submitImmediately, setSubmitImmediately] = useState(true);
  const [draftRows, setDraftRows] = useState<ReceiptDraftRow[]>([]);
  const [clientReceiptUuid, setClientReceiptUuid] = useState(() => crypto.randomUUID());
  const [banner, setBanner] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  const receiptsQuery = useQuery({
    queryKey: ["purchasing-receipts", statusFilter],
    queryFn: () => api.getGoodsReceipts({ status: statusFilter || undefined }),
    refetchInterval: 15_000,
  });

  const openPosQuery = useQuery({
    queryKey: ["purchasing-open-pos"],
    queryFn: async () => {
      const [approved, partial] = await Promise.all([
        api.getPurchaseOrders({ status: "APPROVED" }),
        api.getPurchaseOrders({ status: "PARTIALLY_RECEIVED" }),
      ]);
      return [...approved, ...partial];
    },
  });

  const materialsQuery = useQuery({
    queryKey: ["inventory-materials"],
    queryFn: () => api.getMaterials(),
  });

  const chosenPoDetailQuery = useQuery({
    queryKey: ["purchasing-order-detail", chosenPoId],
    queryFn: () => api.getPurchaseOrderDetail(Number(chosenPoId)),
    enabled: Boolean(chosenPoId),
  });

  const receiptDetailQuery = useQuery({
    queryKey: ["purchasing-receipt-detail", selectedReceiptId],
    queryFn: () => api.getGoodsReceiptDetail(Number(selectedReceiptId)),
    enabled: Boolean(selectedReceiptId),
  });

  useEffect(() => {
    const po: PurchaseOrderDetail | undefined = chosenPoDetailQuery.data;
    const mats = materialsQuery.data ?? [];
    if (!po || mats.length === 0) return;

    const loaded: ReceiptDraftRow[] = po.items
      .filter((it) => Number(it.remaining_qty_base) > 0)
      .map((it) => {
        const mat = mats.find((m) => m.id === it.material_id);
        const dim = mat?.unit_dimension ?? "COUNT";
        const factor =
          it.entered_uom === "kg" || it.entered_uom === "L" ? 1000 : 1;
        const remEntered = Number(it.remaining_qty_base) / factor;
        return {
          purchase_order_item_id: it.id,
          material_id: it.material_id,
          material_code: it.material_code,
          material_name: it.material_name,
          unit_dimension: dim,
          entered_uom: it.entered_uom,
          received_qty_entered: String(remEntered),
          rejected_qty_entered: "0",
          rejection_reason: "",
          batch_code: "",
          expiry_date: "",
          allow_excess: false,
          remaining_hint: `${remEntered} ${it.entered_uom}`,
        };
      });
    setDraftRows(loaded);
  }, [chosenPoDetailQuery.data, materialsQuery.data]);

  const createMutation = useMutation({
    mutationFn: () =>
      api.createGoodsReceipt({
        client_receipt_id: clientReceiptUuid,
        purchase_order_id: Number(chosenPoId),
        supplier_bill_ref: supplierBillRef.trim() || null,
        receipt_date: receiptDate || null,
        discrepancy_notes: discrepancyNotes.trim() || null,
        submit_immediately: submitImmediately,
        items: draftRows
          .filter((r) => Number(r.received_qty_entered) > 0)
          .map((r) => ({
            purchase_order_item_id: r.purchase_order_item_id,
            material_id: r.material_id,
            entered_uom: r.entered_uom,
            received_qty_entered: r.received_qty_entered,
            rejected_qty_entered: r.rejected_qty_entered || "0",
            rejection_reason: Number(r.rejected_qty_entered) > 0 ? r.rejection_reason.trim() : null,
            batch_code: r.batch_code.trim() || null,
            expiry_date: r.expiry_date || null,
            allow_excess: r.allow_excess,
          })),
      }),
    onSuccess: (gr) => {
      queryClient.invalidateQueries({ queryKey: ["purchasing-receipts"] });
      queryClient.invalidateQueries({ queryKey: ["purchasing-orders"] });
      queryClient.invalidateQueries({ queryKey: ["purchasing-open-pos"] });
      setBanner({
        kind: "success",
        msg: `Goods Receipt ${gr.receipt_number} (${gr.status}) recorded. Complete Verify -> Post to increment physical inventory.`,
      });
      setSelectedReceiptId(gr.id);
      setClientReceiptUuid(crypto.randomUUID());
      setShowCreate(false);
      setSearchParams({});
    },
    onError: (err) => {
      const msg = err instanceof ApiClientError ? err.message : "Failed to save goods receipt.";
      setBanner({ kind: "error", msg });
    },
  });

  const stepMutation = useMutation({
    mutationFn: async (opts: { step: "submit" | "verify" | "post"; id: number }) => {
      if (opts.step === "submit") return api.submitGoodsReceipt(opts.id);
      if (opts.step === "verify") return api.verifyGoodsReceipt(opts.id);
      return api.postGoodsReceipt(opts.id);
    },
    onSuccess: (gr: GoodsReceiptDetail) => {
      queryClient.invalidateQueries({ queryKey: ["purchasing-receipts"] });
      queryClient.invalidateQueries({ queryKey: ["purchasing-receipt-detail", gr.id] });
      queryClient.invalidateQueries({ queryKey: ["purchasing-orders"] });
      queryClient.invalidateQueries({ queryKey: ["purchasing-open-pos"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-overview"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-ledger"] });
      setBanner({
        kind: "success",
        msg:
          gr.status === "POSTED"
            ? `Goods Receipt ${gr.receipt_number} POSTED! Accepted stock added to physical inventory & CostLot ledger.`
            : `Goods Receipt ${gr.receipt_number} moved to ${gr.status}.`,
      });
    },
    onError: (err) => {
      const msg = err instanceof ApiClientError ? err.message : "Transition failed.";
      setBanner({ kind: "error", msg });
    },
  });

  const receipts = receiptsQuery.data ?? [];
  const detail = receiptDetailQuery.data;

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    createMutation.mutate();
  };

  return (
    <DesktopAdminLayout
      title="Goods Receipts"
      subtitle="Verify incoming deliveries, record damaged/rejected quantities, and post accepted stock into inventory"
      actions={
        canOperate ? (
          <Button
            onClick={() => {
              setClientReceiptUuid(crypto.randomUUID());
              setShowCreate((v) => !v);
            }}
          >
            {showCreate ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            {showCreate ? "Close Receipt Form" : "Record Goods Receipt"}
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

        {showCreate && canOperate && (
          <Card className="border-primary/30 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base">Receive Against Approved Purchase Order</CardTitle>
              <CardDescription>
                Only Accepted quantity (Received - Rejected) enters physical inventory when posted.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreate} className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-muted-foreground">Approved Purchase Order</label>
                    <select
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                      value={chosenPoId}
                      onChange={(e) => setChosenPoId(e.target.value)}
                      required
                    >
                      <option value="">Select Approved / Partial PO...</option>
                      {(openPosQuery.data ?? []).map((po) => (
                        <option key={po.id} value={po.id}>
                          {po.po_number} — {po.supplier_name} ({po.status})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-muted-foreground">Supplier Bill / Invoice Ref</label>
                    <Input
                      value={supplierBillRef}
                      onChange={(e) => setSupplierBillRef(e.target.value)}
                      placeholder="e.g. CAM-INV-2026-088"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-muted-foreground">Receipt Date</label>
                    <Input type="date" value={receiptDate} onChange={(e) => setReceiptDate(e.target.value)} />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-muted-foreground">Inspection Notes</label>
                    <Input
                      value={discrepancyNotes}
                      onChange={(e) => setDiscrepancyNotes(e.target.value)}
                      placeholder="Shortage/packing condition notes"
                    />
                  </div>
                </div>

                {draftRows.length > 0 && (
                  <div className="space-y-3">
                    {draftRows.map((row, idx) => (
                      <div key={row.material_id} className="rounded-lg border p-3 bg-secondary/20 space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="text-sm font-semibold">
                            {row.material_name} <span className="font-mono text-xs text-muted-foreground">({row.material_code})</span>
                          </span>
                          <span className="text-xs text-muted-foreground">PO Remaining: {row.remaining_hint}</span>
                        </div>
                        <div className="grid gap-2 sm:grid-cols-6 items-end">
                          <div className="space-y-1">
                            <label className="text-[11px] font-semibold text-muted-foreground">Unit</label>
                            <select
                              className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-xs"
                              value={row.entered_uom}
                              onChange={(e) =>
                                setDraftRows((p) =>
                                  p.map((r, i) => (i === idx ? { ...r, entered_uom: e.target.value } : r))
                                )
                              }
                            >
                              {compatibleUomsForMaterial(row.unit_dimension).map((u) => (
                                <option key={u} value={u}>
                                  {u}
                                </option>
                              ))}
                            </select>
                          </div>
                          <div className="space-y-1">
                            <label className="text-[11px] font-semibold text-muted-foreground">Received Qty</label>
                            <Input
                              type="number"
                              step="0.001"
                              min="0"
                              className="h-9 text-xs"
                              value={row.received_qty_entered}
                              onChange={(e) =>
                                setDraftRows((p) =>
                                  p.map((r, i) => (i === idx ? { ...r, received_qty_entered: e.target.value } : r))
                                )
                              }
                            />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[11px] font-semibold text-muted-foreground">Damaged / Rejected</label>
                            <Input
                              type="number"
                              step="0.001"
                              min="0"
                              className="h-9 text-xs"
                              value={row.rejected_qty_entered}
                              onChange={(e) =>
                                setDraftRows((p) =>
                                  p.map((r, i) => (i === idx ? { ...r, rejected_qty_entered: e.target.value } : r))
                                )
                              }
                            />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[11px] font-semibold text-muted-foreground">Batch Code</label>
                            <Input
                              className="h-9 text-xs"
                              value={row.batch_code}
                              onChange={(e) =>
                                setDraftRows((p) =>
                                  p.map((r, i) => (i === idx ? { ...r, batch_code: e.target.value } : r))
                                )
                              }
                              placeholder="Optional batch"
                            />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[11px] font-semibold text-muted-foreground">Expiry Date</label>
                            <Input
                              type="date"
                              className="h-9 text-xs"
                              value={row.expiry_date}
                              onChange={(e) =>
                                setDraftRows((p) =>
                                  p.map((r, i) => (i === idx ? { ...r, expiry_date: e.target.value } : r))
                                )
                              }
                            />
                          </div>
                          <div className="flex items-center pb-1.5">
                            <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                              <input
                                type="checkbox"
                                checked={row.allow_excess}
                                onChange={(e) =>
                                  setDraftRows((p) =>
                                    p.map((r, i) => (i === idx ? { ...r, allow_excess: e.target.checked } : r))
                                  )
                                }
                              />
                              Allow excess
                            </label>
                          </div>
                        </div>
                        {Number(row.rejected_qty_entered) > 0 && (
                          <div>
                            <Input
                              className="h-9 text-xs"
                              placeholder="Mandatory reason for rejected / damaged quantity..."
                              value={row.rejection_reason}
                              onChange={(e) =>
                                setDraftRows((p) =>
                                  p.map((r, i) => (i === idx ? { ...r, rejection_reason: e.target.value } : r))
                                )
                              }
                              required
                            />
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-t pt-3">
                  <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
                    <input
                      type="checkbox"
                      checked={submitImmediately}
                      onChange={(e) => setSubmitImmediately(e.target.checked)}
                    />
                    Submit immediately for quality verification
                  </label>
                  <Button type="submit" disabled={createMutation.isPending || draftRows.length === 0}>
                    {createMutation.isPending ? "Saving..." : "Save Goods Receipt"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        <div className="flex flex-wrap gap-1.5">
          {["", "DRAFT", "SUBMITTED", "VERIFIED", "POSTED"].map((st) => (
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
              {st || "All Receipts"}
            </button>
          ))}
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Goods Receipts ({receipts.length})</CardTitle>
              <CardDescription>Click a receipt row to inspect items and execute Submit / Verify / Post</CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="py-2 pr-3">GRN #</th>
                    <th className="py-2 pr-3">PO / Supplier</th>
                    <th className="py-2 pr-3">Date</th>
                    <th className="py-2 pr-3 text-right">Accepted Value</th>
                    <th className="py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {receipts.map((gr) => (
                    <tr
                      key={gr.id}
                      onClick={() => setSelectedReceiptId(gr.id)}
                      className={`cursor-pointer hover:bg-secondary/40 ${
                        selectedReceiptId === gr.id ? "bg-primary/5" : ""
                      }`}
                    >
                      <td className="py-3 pr-3 font-mono text-xs font-semibold">{gr.receipt_number}</td>
                      <td className="py-3 pr-3">
                        <div className="font-medium">{gr.supplier_name}</div>
                        <div className="text-xs text-muted-foreground">
                          {gr.po_number ?? "Standalone"} · Bill: {gr.supplier_bill_ref ?? "—"}
                        </div>
                      </td>
                      <td className="py-3 pr-3 text-xs text-muted-foreground">{formatOrderDate(gr.receipt_date)}</td>
                      <td className="py-3 pr-3 text-right font-semibold tabular-nums">
                        {formatInrFromPaisa(gr.total_paisa)}
                      </td>
                      <td className="py-3">
                        <StatusBadge status={gr.status} />
                      </td>
                    </tr>
                  ))}
                  {receipts.length === 0 && (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-muted-foreground">
                        No goods receipts recorded yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <PackageCheck className="h-4 w-4 text-primary" />
                Receipt Verification &amp; Posting
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!detail ? (
                <p className="text-sm text-muted-foreground py-8 text-center">
                  Select a Goods Receipt to verify accepted/rejected quantities and post stock to the immutable ledger.
                </p>
              ) : (
                <div className="space-y-4 text-sm">
                  <div className="flex items-start justify-between border-b pb-3">
                    <div>
                      <div className="font-mono font-bold text-base">{detail.receipt_number}</div>
                      <div className="text-xs text-muted-foreground">{detail.supplier_name}</div>
                      <div className="text-[11px] text-muted-foreground mt-0.5">
                        Received by {detail.received_by_name}
                        {detail.posted_at ? ` · Posted ${formatDateTimeIst(detail.posted_at)}` : ""}
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
                            Rec: {it.received_qty_entered} {it.entered_uom} · Rej: {it.rejected_qty_entered}{" "}
                            {it.entered_uom}
                          </span>
                          <span className="font-semibold text-emerald-700">
                            Acc: {it.accepted_qty_entered} {it.entered_uom} ({formatBaseQty(it.accepted_qty_base, it.base_uom)})
                          </span>
                        </div>
                        {it.rejection_reason && (
                          <div className="text-red-700 text-[11px]">Damaged/Rejected: {it.rejection_reason}</div>
                        )}
                        {it.batch_code && (
                          <div className="text-[11px] text-muted-foreground">
                            Batch: {it.batch_code} {it.expiry_date ? `· Exp: ${it.expiry_date}` : ""}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>

                  {canOperate && (
                    <div className="space-y-2 pt-2 border-t">
                      {detail.status === "DRAFT" && (
                        <Button
                          className="w-full"
                          onClick={() => stepMutation.mutate({ step: "submit", id: detail.id })}
                          disabled={stepMutation.isPending}
                        >
                          <Send className="h-4 w-4" />
                          Submit Receipt
                        </Button>
                      )}
                      {detail.status === "SUBMITTED" && (
                        <Button
                          className="w-full"
                          onClick={() => stepMutation.mutate({ step: "verify", id: detail.id })}
                          disabled={stepMutation.isPending}
                        >
                          <ShieldCheck className="h-4 w-4" />
                          Verify Quality &amp; Quantities
                        </Button>
                      )}
                      {detail.status === "VERIFIED" && (
                        <Button
                          className="w-full bg-emerald-700 hover:bg-emerald-800"
                          onClick={() => stepMutation.mutate({ step: "post", id: detail.id })}
                          disabled={stepMutation.isPending}
                        >
                          <CheckCircle2 className="h-4 w-4" />
                          Post Accepted Stock to Inventory
                        </Button>
                      )}
                      {detail.status === "POSTED" && (
                        <div className="flex items-center gap-2 rounded-lg bg-emerald-50 border border-emerald-200 p-3 text-xs text-emerald-800">
                          <ClipboardCheck className="h-4 w-4 shrink-0" />
                          Posted irreversibly to InventoryMovement ledger and CostLots.
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </DesktopAdminLayout>
  );
}

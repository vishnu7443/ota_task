import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Plus, XCircle } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api, type InventoryBalanceSummary } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDateTimeIst } from "@/lib/money";
import { compatibleUomsForMaterial, formatBaseQty, formatDisplayQty } from "@/lib/units";

const ADJUSTMENT_TYPES = [
  "DAMAGED",
  "EXPIRED",
  "MISSING",
  "COUNT_CORRECTION",
  "SUPPLIER_RETURN",
  "OTHER",
] as const;

export function AdminStockAdjustmentsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role_code === "FACTORY_ADMIN";
  const canRequest = isAdmin || user?.role_code === "PRODUCTION_SUPERVISOR";
  const queryClient = useQueryClient();

  const [selectedKey, setSelectedKey] = useState("");
  const [adjType, setAdjType] = useState<(typeof ADJUSTMENT_TYPES)[number]>("DAMAGED");
  const [enteredQty, setEnteredQty] = useState("-1");
  const [enteredUom, setEnteredUom] = useState("kg");
  const [reason, setReason] = useState("");
  const [postImmediately, setPostImmediately] = useState(false);
  const [rejectReasons, setRejectReasons] = useState<Record<number, string>>({});
  const [banner, setBanner] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  const overviewQuery = useQuery({
    queryKey: ["inventory-overview-all"],
    queryFn: () => api.getInventoryOverview(),
  });

  const adjustmentsQuery = useQuery({
    queryKey: ["inventory-adjustments"],
    queryFn: () => api.getStockAdjustments(),
    refetchInterval: 15_000,
  });

  const itemsMap = useMemo(() => {
    const map: Record<string, InventoryBalanceSummary> = {};
    (overviewQuery.data?.items ?? []).forEach((it) => {
      map[`${it.item_type}:${it.item_id}`] = it;
    });
    return map;
  }, [overviewQuery.data]);

  const selectedItem = itemsMap[selectedKey];
  const validUoms = selectedItem
    ? selectedItem.item_type === "PACK_SIZE"
      ? ["packet", "carton"]
      : compatibleUomsForMaterial(selectedItem.unit_dimension)
    : ["kg", "g", "L", "ml", "piece", "packet"];

  const handleSelectItem = (key: string) => {
    setSelectedKey(key);
    const it = itemsMap[key];
    if (it) setEnteredUom(it.display_uom);
  };

  const createMutation = useMutation({
    mutationFn: () => {
      if (!selectedItem) throw new Error("Select an item");
      return api.createStockAdjustment({
        item_type: selectedItem.item_type,
        item_id: selectedItem.item_id,
        adjustment_type: adjType,
        entered_qty: enteredQty,
        entered_uom: enteredUom,
        reason: reason.trim(),
        post_immediately: isAdmin ? postImmediately : false,
      });
    },
    onSuccess: (adj) => {
      queryClient.invalidateQueries({ queryKey: ["inventory-adjustments"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-overview"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-ledger"] });
      setReason("");
      setBanner({
        kind: "success",
        msg:
          adj.status === "POSTED"
            ? `Adjustment ${adj.adjustment_number} posted to ledger immediately.`
            : `Adjustment ${adj.adjustment_number} submitted for Factory Admin approval.`,
      });
    },
    onError: (err) => {
      const msg = err instanceof ApiClientError ? err.message : "Failed to create stock adjustment.";
      setBanner({ kind: "error", msg });
    },
  });

  const actionMutation = useMutation({
    mutationFn: async (opts: { kind: "approve" | "reject"; id: number }) => {
      if (opts.kind === "approve") return api.approveStockAdjustment(opts.id);
      return api.rejectStockAdjustment(opts.id, (rejectReasons[opts.id] ?? "").trim());
    },
    onSuccess: (adj) => {
      queryClient.invalidateQueries({ queryKey: ["inventory-adjustments"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-overview"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-ledger"] });
      setBanner({ kind: "success", msg: `Adjustment ${adj.adjustment_number} updated to ${adj.status}.` });
    },
    onError: (err) => {
      const msg = err instanceof ApiClientError ? err.message : "Failed to update adjustment.";
      setBanner({ kind: "error", msg });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    createMutation.mutate();
  };

  const adjustments = adjustmentsQuery.data ?? [];

  return (
    <DesktopAdminLayout
      title="Stock Adjustments"
      subtitle="Reason-logged wastage, leakage, supplier returns, and physical count reconciliations (negative stock & reservations strictly protected)"
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

        {canRequest && (
          <Card className="border-primary/30 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Plus className="h-4 w-4 text-primary" />
                Record Stock Adjustment Request
              </CardTitle>
              <CardDescription>
                {isAdmin
                  ? "Use negative quantity (e.g. -5) for shrinkage/damage/returns, or positive quantity for upward physical count reconciliation."
                  : "Production Supervisor requests require Factory Admin approval before modifying ledger balances."}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <div className="space-y-1 sm:col-span-2">
                  <label className="text-xs font-semibold text-muted-foreground">Inventory Item</label>
                  <select
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    value={selectedKey}
                    onChange={(e) => handleSelectItem(e.target.value)}
                    required
                  >
                    <option value="">Select Material or Finished Good...</option>
                    {(overviewQuery.data?.items ?? []).map((it) => {
                      const key = `${it.item_type}:${it.item_id}`;
                      return (
                        <option key={key} value={key}>
                          {it.code} — {it.name} (Avail:{" "}
                          {formatDisplayQty(it.available_qty_base, it.display_uom, it.display_factor)})
                        </option>
                      );
                    })}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Adjustment Type</label>
                  <select
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    value={adjType}
                    onChange={(e) => setAdjType(e.target.value as (typeof ADJUSTMENT_TYPES)[number])}
                  >
                    {ADJUSTMENT_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t.replaceAll("_", " ")}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-muted-foreground">Signed Qty</label>
                    <Input
                      type="number"
                      step="0.001"
                      value={enteredQty}
                      onChange={(e) => setEnteredQty(e.target.value)}
                      required
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-muted-foreground">Unit</label>
                    <select
                      className="flex h-10 w-full rounded-md border border-input bg-background px-2 text-sm"
                      value={enteredUom}
                      onChange={(e) => setEnteredUom(e.target.value)}
                    >
                      {validUoms.map((u) => (
                        <option key={u} value={u}>
                          {u}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div className="space-y-1 sm:col-span-2 lg:col-span-3">
                  <label className="text-xs font-semibold text-muted-foreground">
                    Mandatory Audit Reason (min 5 characters)
                  </label>
                  <Input
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="Document physical cause, damaged batch, or supplier return reference..."
                    required
                  />
                </div>
                <div className="flex flex-col justify-end gap-2">
                  {isAdmin && (
                    <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
                      <input
                        type="checkbox"
                        checked={postImmediately}
                        onChange={(e) => setPostImmediately(e.target.checked)}
                      />
                      Approve &amp; Post immediately
                    </label>
                  )}
                  <Button type="submit" disabled={createMutation.isPending}>
                    {createMutation.isPending ? "Submitting..." : "Submit Adjustment"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-primary" />
              Adjustment Requests &amp; Audit History ({adjustments.length})
            </CardTitle>
            <CardDescription>
              Posted adjustments generate immutable ledger movements linked via stock_adjustment_id.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="py-2 pr-3">Voucher #</th>
                  <th className="py-2 pr-3">Item &amp; Type</th>
                  <th className="py-2 pr-3 text-right">Delta</th>
                  <th className="py-2 pr-3">Reason</th>
                  <th className="py-2 pr-3">Workflow</th>
                  <th className="py-2">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {adjustments.map((adj) => (
                  <tr key={adj.id}>
                    <td className="py-3 pr-3 font-mono text-xs font-semibold">{adj.adjustment_number}</td>
                    <td className="py-3 pr-3">
                      <div className="font-medium text-foreground">{adj.item_name}</div>
                      <div className="text-xs text-muted-foreground">
                        {adj.item_code} · {adj.adjustment_type}
                      </div>
                    </td>
                    <td
                      className={`py-3 pr-3 text-right font-mono text-xs font-bold tabular-nums ${
                        Number(adj.delta_qty_base) >= 0 ? "text-emerald-700" : "text-red-700"
                      }`}
                    >
                      {Number(adj.delta_qty_base) > 0 ? "+" : ""}
                      {adj.entered_qty} {adj.entered_uom} ({formatBaseQty(adj.delta_qty_base, adj.base_uom)})
                    </td>
                    <td className="py-3 pr-3 text-xs max-w-xs">
                      <div className="text-foreground">{adj.reason}</div>
                      {adj.rejection_reason && (
                        <div className="text-red-700 mt-0.5">Rejected: {adj.rejection_reason}</div>
                      )}
                    </td>
                    <td className="py-3 pr-3 text-xs">
                      <StatusBadge status={adj.status} />
                      <div className="text-[11px] text-muted-foreground mt-1">
                        Req: {adj.requested_by_name}
                        {adj.approved_by_name ? ` · Rev: ${adj.approved_by_name}` : ""}
                      </div>
                      <div className="text-[10px] text-muted-foreground">{formatDateTimeIst(adj.requested_at)}</div>
                    </td>
                    <td className="py-3">
                      {isAdmin && adj.status === "PENDING_APPROVAL" ? (
                        <div className="flex flex-col gap-1.5 min-w-[180px]">
                          <Button
                            size="sm"
                            className="bg-emerald-700 hover:bg-emerald-800 h-8 text-xs"
                            onClick={() => actionMutation.mutate({ kind: "approve", id: adj.id })}
                            disabled={actionMutation.isPending}
                          >
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Approve &amp; Post
                          </Button>
                          <div className="flex gap-1">
                            <Input
                              className="h-7 text-xs"
                              placeholder="Reject reason..."
                              value={rejectReasons[adj.id] ?? ""}
                              onChange={(e) =>
                                setRejectReasons((p) => ({ ...p, [adj.id]: e.target.value }))
                              }
                            />
                            <Button
                              size="sm"
                              variant="destructive"
                              className="h-7 text-xs px-2"
                              disabled={(rejectReasons[adj.id] ?? "").trim().length < 5}
                              onClick={() => actionMutation.mutate({ kind: "reject", id: adj.id })}
                            >
                              <XCircle className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                  </tr>
                ))}
                {adjustments.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-muted-foreground">
                      No stock adjustments recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>
    </DesktopAdminLayout>
  );
}

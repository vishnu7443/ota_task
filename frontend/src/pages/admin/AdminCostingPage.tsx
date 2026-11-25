import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Calculator, History, PlusCircle, RefreshCw, ShieldCheck } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, costingApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDateTimeIst, formatInrFromPaisa, formatOrderDate } from "@/lib/money";

export function AdminCostingPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canOperate =
    user?.role_code === "FACTORY_ADMIN" || user?.role_code === "PRODUCTION_SUPERVISOR";
  const isAdmin = user?.role_code === "FACTORY_ADMIN";

  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [labourRs, setLabourRs] = useState("1200");
  const [gasPowerRs, setGasPowerRs] = useState("600");
  const [otherRs, setOtherRs] = useState("0");
  const [finalizeNotes, setFinalizeNotes] = useState("");

  // Monthly Pool form
  const [poolMonth, setPoolMonth] = useState("2026-11");
  const [poolType, setPoolType] = useState("FACTORY_RENT");
  const [poolAmountRs, setPoolAmountRs] = useState("");
  const [poolNotes, setPoolNotes] = useState("");

  const [banner, setBanner] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  const dashQuery = useQuery({
    queryKey: ["costing-dashboard"],
    queryFn: () => costingApi.getDashboard(),
    refetchInterval: 15_000,
  });

  const detailQuery = useQuery({
    queryKey: ["costing-run-detail", selectedRunId],
    queryFn: () => costingApi.getRunCosting(selectedRunId!),
    enabled: selectedRunId !== null,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["costing-dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["costing-run-detail"] });
    queryClient.invalidateQueries({ queryKey: ["finance-dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["profitability-report"] });
  };

  const finalizeMutation = useMutation({
    mutationFn: (runId: number) => {
      const overheads: Array<{ overhead_type: string; amount_paisa: number; notes?: string | null }> =
        [];
      const lPaisa = Math.round(Number(labourRs || 0) * 100);
      const gPaisa = Math.round(Number(gasPowerRs || 0) * 100);
      const oPaisa = Math.round(Number(otherRs || 0) * 100);
      if (lPaisa > 0) overheads.push({ overhead_type: "DIRECT_LABOUR", amount_paisa: lPaisa, notes: finalizeNotes.trim() || "Direct batch labour" });
      if (gPaisa > 0) overheads.push({ overhead_type: "GAS_POWER", amount_paisa: gPaisa, notes: finalizeNotes.trim() || "Cooking gas & power" });
      if (oPaisa > 0) overheads.push({ overhead_type: "OTHER_PRODUCTION_EXPENSE", amount_paisa: oPaisa, notes: finalizeNotes.trim() || "Other run expense" });
      return costingApi.finalizeRunCosting(runId, {
        overheads,
        notes: finalizeNotes.trim() || "Step 8 finalized production batch costing",
      });
    },
    onSuccess: (res) => {
      invalidate();
      setBanner({
        kind: "success",
        msg: `Costing finalized (Snapshot v${res.current_summary?.snapshot_version}) for ${res.run_number}: ${formatInrFromPaisa(res.current_summary?.cost_per_packet_paisa ?? 0)} / pkt.`,
      });
    },
    onError: (err) =>
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Failed to finalize costing.",
      }),
  });

  const voidMutation = useMutation({
    mutationFn: (opts: { id: number; reason: string }) =>
      costingApi.voidOverhead(opts.id, opts.reason),
    onSuccess: () => {
      invalidate();
      setBanner({ kind: "success", msg: "Overhead entry voided and new immutable snapshot calculated." });
    },
    onError: (err) =>
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Failed to void overhead.",
      }),
  });

  const poolMutation = useMutation({
    mutationFn: () =>
      costingApi.addMonthlyPoolOverhead({
        period_month: poolMonth.trim(),
        overhead_type: poolType,
        amount_paisa: Math.round(Number(poolAmountRs || 0) * 100),
        notes: poolNotes.trim() || null,
      }),
    onSuccess: () => {
      invalidate();
      setPoolAmountRs("");
      setPoolNotes("");
      setBanner({
        kind: "success",
        msg: `Monthly overhead pool recorded & allocated proportionally by good packets across ${poolMonth}.`,
      });
    },
    onError: (err) =>
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Failed to allocate monthly overhead.",
      }),
  });

  const d = dashQuery.data;
  const detail = detailQuery.data;

  return (
    <DesktopAdminLayout
      title="Product Costing Engine & Overhead Allocation"
      subtitle="FIFO actual raw material + packaging absorption, wastage/rejection cost tracking, and Step 8 overhead snapshots"
      actions={
        <Button asChild variant="outline">
          <Link to="/admin/finance/profitability">Profitability &amp; COGS →</Link>
        </Button>
      }
    >
      <div className="space-y-6">
        {banner && (
          <div
            className={`rounded-xl border px-4 py-3 text-sm font-medium ${
              banner.kind === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : "border-red-200 bg-red-50 text-red-900"
            }`}
          >
            {banner.msg}
          </div>
        )}

        {d && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs font-semibold uppercase text-muted-foreground">Valuation Policy</div>
                  <div className="mt-1 text-xl font-bold text-primary">{d.valuation_method}</div>
                  <div className="text-xs text-muted-foreground">Per lot CostLotConsumption</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs font-semibold uppercase text-muted-foreground">Costed Batches</div>
                  <div className="mt-1 text-xl font-bold tabular-nums">
                    {d.total_costed_runs}{" "}
                    <span className="text-xs font-normal text-muted-foreground">
                      ({d.total_finalized_runs} finalized)
                    </span>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs font-semibold uppercase text-muted-foreground">Good Output</div>
                  <div className="mt-1 text-xl font-bold tabular-nums">{d.total_good_packets} pkts</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs font-semibold uppercase text-muted-foreground">Total Batch Cost</div>
                  <div className="mt-1 text-xl font-bold tabular-nums">
                    {formatInrFromPaisa(d.total_batch_cost_paisa)}
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs font-semibold uppercase text-muted-foreground">Damaged / Rej. Impact</div>
                  <div className="mt-1 text-xl font-bold text-amber-700 tabular-nums">
                    {formatInrFromPaisa(d.total_wastage_and_damage_paisa)}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Product-Level Weighted Cost Summary */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">SKU Unit Cost &amp; Standard Margin Summary</CardTitle>
              </CardHeader>
              <CardContent className="p-0 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                      <th className="px-4 py-2">SKU</th>
                      <th className="px-3 py-2 text-right">Runs</th>
                      <th className="px-3 py-2 text-right">Good Pkts</th>
                      <th className="px-3 py-2 text-right">Raw Mat.</th>
                      <th className="px-3 py-2 text-right">Packaging</th>
                      <th className="px-3 py-2 text-right">Overheads</th>
                      <th className="px-3 py-2 text-right">Latest Cost/Pkt</th>
                      <th className="px-3 py-2 text-right">Selling Price</th>
                      <th className="px-4 py-2 text-right">Unit Margin</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {d.product_summaries.map((ps) => (
                      <tr key={ps.pack_size_id}>
                        <td className="px-4 py-2.5 font-semibold">
                          {ps.display_name}{" "}
                          <span className="font-mono text-muted-foreground">[{ps.sku_code}]</span>
                        </td>
                        <td className="px-3 py-2.5 text-right">{ps.run_count}</td>
                        <td className="px-3 py-2.5 text-right font-bold">{ps.total_good_packets}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">
                          {formatInrFromPaisa(ps.total_raw_cost_paisa)}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums">
                          {formatInrFromPaisa(ps.total_pkg_cost_paisa)}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums">
                          {formatInrFromPaisa(ps.total_overhead_cost_paisa)}
                        </td>
                        <td className="px-3 py-2.5 text-right font-bold text-primary tabular-nums">
                          {formatInrFromPaisa(ps.latest_cost_per_pkt_paisa)}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums">
                          {formatInrFromPaisa(ps.selling_price_paisa)}
                        </td>
                        <td className="px-4 py-2.5 text-right font-bold text-emerald-700 tabular-nums">
                          {formatInrFromPaisa(ps.unit_gross_margin_paisa)} ({ps.unit_gross_margin_pct}%)
                        </td>
                      </tr>
                    ))}
                    {d.product_summaries.length === 0 && (
                      <tr>
                        <td colSpan={9} className="py-6 text-center text-muted-foreground">
                          Post a production run first to view cost breakdowns.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </CardContent>
            </Card>

            {/* Production Batch Cost Ledger */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Calculator className="h-4 w-4 text-primary" />
                  Production Batch Costing Ledger
                </CardTitle>
                <CardDescription>
                  Click Inspect / Add Overheads to enter Step 8 Labour, Gas &amp; Power or inspect snapshot versions.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                      <th className="px-4 py-2.5">Run #</th>
                      <th className="px-3 py-2.5">Date</th>
                      <th className="px-3 py-2.5">SKU</th>
                      <th className="px-3 py-2.5 text-right">Good / Exp</th>
                      <th className="px-3 py-2.5 text-right">Planned Cost</th>
                      <th className="px-3 py-2.5 text-right">Actual Mat+Pkg</th>
                      <th className="px-3 py-2.5 text-right">Overheads</th>
                      <th className="px-3 py-2.5 text-right">Total Cost</th>
                      <th className="px-3 py-2.5 text-right">Cost / Pkt</th>
                      <th className="px-3 py-2.5">Status</th>
                      <th className="px-4 py-2.5 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {d.runs.map((r) => (
                      <tr
                        key={r.id}
                        className={selectedRunId === r.production_run_id ? "bg-primary/5" : "hover:bg-secondary/30"}
                      >
                        <td className="px-4 py-2.5 font-mono font-bold">
                          <Link
                            to={`/admin/production/runs/${r.production_run_id}`}
                            className="text-primary hover:underline"
                          >
                            {r.run_number}
                          </Link>
                          <span className="ml-1 text-[10px] text-muted-foreground">
                            v{r.snapshot_version}
                          </span>
                        </td>
                        <td className="px-3 py-2.5">{formatOrderDate(r.run_date)}</td>
                        <td className="px-3 py-2.5">{r.display_name}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">
                          {r.good_packets} / {r.expected_output_pkts}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums">
                          {formatInrFromPaisa(r.planned_total_cost_paisa)}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums">
                          {formatInrFromPaisa(r.raw_material_cost_paisa + r.packaging_cost_paisa)}
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums">
                          {formatInrFromPaisa(r.direct_overhead_paisa + r.allocated_overhead_paisa)}
                        </td>
                        <td className="px-3 py-2.5 text-right font-bold tabular-nums">
                          {formatInrFromPaisa(r.total_cost_paisa)}
                        </td>
                        <td className="px-3 py-2.5 text-right font-bold text-primary tabular-nums">
                          {r.cost_per_packet_paisa != null
                            ? formatInrFromPaisa(r.cost_per_packet_paisa)
                            : "—"}
                        </td>
                        <td className="px-3 py-2.5">
                          <StatusBadge status={r.cost_status} />
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <Button
                            size="sm"
                            variant={selectedRunId === r.production_run_id ? "default" : "outline"}
                            onClick={() => setSelectedRunId(r.production_run_id)}
                          >
                            Inspect / Cost
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>

            {/* Selected Run Drill-Down & Step 8 Overhead Form */}
            {detail && detail.current_summary && (
              <div className="space-y-4">
                <Card className="border-primary/40">
                  <CardHeader>
                    <CardTitle className="text-base flex items-center justify-between">
                      <span>
                        Run Cost Breakdown — {detail.run_number} ({detail.display_name})
                      </span>
                      <Badge variant="outline">
                        Snapshot v{detail.current_summary.snapshot_version}
                      </Badge>
                    </CardTitle>
                    <CardDescription>
                      Includes planned-vs-actual variance cost, damaged packaging cost, and full snapshot history.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-5">
                    <div className="grid gap-3 sm:grid-cols-4 text-xs">
                      <div className="rounded-lg border p-3">
                        <div className="text-muted-foreground">Raw Material Cost</div>
                        <div className="text-base font-bold">
                          {formatInrFromPaisa(detail.current_summary.raw_material_cost_paisa)}
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          Planned: {formatInrFromPaisa(detail.current_summary.planned_raw_cost_paisa)}
                        </div>
                      </div>
                      <div className="rounded-lg border p-3">
                        <div className="text-muted-foreground">Packaging (incl. Damaged)</div>
                        <div className="text-base font-bold">
                          {formatInrFromPaisa(detail.current_summary.packaging_cost_paisa)}
                        </div>
                        <div className="text-[11px] text-amber-700">
                          Damaged share:{" "}
                          {formatInrFromPaisa(detail.current_summary.damaged_packaging_cost_paisa)}
                        </div>
                      </div>
                      <div className="rounded-lg border p-3">
                        <div className="text-muted-foreground">Direct &amp; Pool Overheads</div>
                        <div className="text-base font-bold">
                          {formatInrFromPaisa(
                            detail.current_summary.direct_overhead_paisa +
                              detail.current_summary.allocated_overhead_paisa
                          )}
                        </div>
                        <div className="text-[11px] text-muted-foreground">
                          Labour {formatInrFromPaisa(detail.current_summary.direct_labour_paisa)} · Gas/Power{" "}
                          {formatInrFromPaisa(detail.current_summary.gas_power_paisa)}
                        </div>
                      </div>
                      <div className="rounded-lg border bg-primary/5 p-3">
                        <div className="text-muted-foreground">Final Cost / Good Packet</div>
                        <div className="text-lg font-bold text-primary">
                          {detail.current_summary.cost_per_packet_paisa != null
                            ? formatInrFromPaisa(detail.current_summary.cost_per_packet_paisa)
                            : "—"}
                        </div>
                        <div className="text-[11px] text-emerald-700">
                          Margin:{" "}
                          {detail.current_summary.gross_margin_per_pkt_paisa != null
                            ? `${formatInrFromPaisa(detail.current_summary.gross_margin_per_pkt_paisa)} (${detail.current_summary.gross_margin_pct}%)`
                            : "—"}
                        </div>
                      </div>
                    </div>

                    {/* Planned vs Actual Material Cost Table */}
                    <div className="overflow-x-auto rounded-lg border">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="border-b bg-secondary/40 text-left uppercase text-muted-foreground">
                            <th className="px-3 py-2">Material</th>
                            <th className="px-3 py-2">Phase</th>
                            <th className="px-3 py-2 text-right">Planned Base</th>
                            <th className="px-3 py-2 text-right">Actual Base</th>
                            <th className="px-3 py-2 text-right">Planned Cost</th>
                            <th className="px-3 py-2 text-right">Actual Cost</th>
                            <th className="px-3 py-2 text-right">Damaged / Waste</th>
                            <th className="px-3 py-2 text-right">Cost Variance</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {detail.current_summary.material_lines.map((ln) => (
                            <tr key={ln.material_id}>
                              <td className="px-3 py-2 font-medium">{ln.material_name}</td>
                              <td className="px-3 py-2">{ln.issue_phase}</td>
                              <td className="px-3 py-2 text-right font-mono">{ln.planned_qty_base}</td>
                              <td className="px-3 py-2 text-right font-mono">{ln.actual_consumed_qty_base}</td>
                              <td className="px-3 py-2 text-right tabular-nums">
                                {formatInrFromPaisa(ln.planned_cost_paisa)}
                              </td>
                              <td className="px-3 py-2 text-right font-semibold tabular-nums">
                                {formatInrFromPaisa(ln.actual_cost_paisa)}
                              </td>
                              <td className="px-3 py-2 text-right text-amber-700 tabular-nums">
                                {formatInrFromPaisa(ln.damaged_cost_paisa + ln.wasted_cost_paisa)}
                              </td>
                              <td
                                className={`px-3 py-2 text-right font-bold tabular-nums ${
                                  ln.cost_variance_paisa > 0 ? "text-red-700" : "text-emerald-700"
                                }`}
                              >
                                {ln.cost_variance_paisa > 0 ? "+" : ""}
                                {formatInrFromPaisa(ln.cost_variance_paisa)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Step 8 Direct Overhead Entry */}
                    {canOperate && (
                      <div className="rounded-lg border p-4 space-y-3 bg-secondary/20">
                        <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                          <ShieldCheck className="h-3.5 w-3.5 text-primary" />
                          Step 8 Direct Overhead Entry &amp; Cost Finalization
                        </div>
                        <div className="grid gap-3 md:grid-cols-4">
                          <div>
                            <label className="text-xs font-semibold text-muted-foreground">
                              Direct Labour (₹)
                            </label>
                            <Input
                              type="number"
                              min="0"
                              value={labourRs}
                              onChange={(e) => setLabourRs(e.target.value)}
                              className="mt-1"
                            />
                          </div>
                          <div>
                            <label className="text-xs font-semibold text-muted-foreground">
                              Gas &amp; Power (₹)
                            </label>
                            <Input
                              type="number"
                              min="0"
                              value={gasPowerRs}
                              onChange={(e) => setGasPowerRs(e.target.value)}
                              className="mt-1"
                            />
                          </div>
                          <div>
                            <label className="text-xs font-semibold text-muted-foreground">
                              Other Prod. Expense (₹)
                            </label>
                            <Input
                              type="number"
                              min="0"
                              value={otherRs}
                              onChange={(e) => setOtherRs(e.target.value)}
                              className="mt-1"
                            />
                          </div>
                          <div>
                            <label className="text-xs font-semibold text-muted-foreground">Notes</label>
                            <Input
                              value={finalizeNotes}
                              onChange={(e) => setFinalizeNotes(e.target.value)}
                              placeholder="Shift labour & fuel log..."
                              className="mt-1"
                            />
                          </div>
                        </div>
                        <Button
                          size="sm"
                          disabled={finalizeMutation.isPending}
                          onClick={() => finalizeMutation.mutate(detail.production_run_id)}
                        >
                          <PlusCircle className="h-3.5 w-3.5" />
                          {finalizeMutation.isPending ? "Finalizing..." : "Record Overheads & Finalize Snapshot"}
                        </Button>
                      </div>
                    )}

                    {/* Overhead Items + Historical Immutable Snapshots */}
                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="rounded-lg border p-3 space-y-2 text-xs">
                        <div className="font-bold">Recorded Run Overheads ({detail.overheads.length})</div>
                        {detail.overheads.map((ov) => (
                          <div
                            key={ov.id}
                            className="flex items-center justify-between border-b pb-1.5 last:border-b-0"
                          >
                            <div>
                              <span className={ov.is_voided ? "line-through text-muted-foreground" : "font-semibold"}>
                                {ov.overhead_type}: {formatInrFromPaisa(ov.amount_paisa)}
                              </span>
                              <div className="text-[11px] text-muted-foreground">
                                {ov.recorded_by_name} · {formatDateTimeIst(ov.recorded_at)}
                              </div>
                            </div>
                            {!ov.is_voided && isAdmin && (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-7 text-destructive"
                                onClick={() =>
                                  voidMutation.mutate({
                                    id: ov.id,
                                    reason: "Voided erroneous overhead via Finance Costing Desk",
                                  })
                                }
                              >
                                Void
                              </Button>
                            )}
                          </div>
                        ))}
                        {detail.overheads.length === 0 && (
                          <div className="text-muted-foreground">No direct overheads added yet.</div>
                        )}
                      </div>

                      <div className="rounded-lg border p-3 space-y-2 text-xs">
                        <div className="font-bold flex items-center gap-1.5">
                          <History className="h-3.5 w-3.5 text-primary" />
                          Immutable Snapshot History ({detail.history_snapshots.length})
                        </div>
                        {detail.history_snapshots.map((sn) => (
                          <div
                            key={sn.id}
                            className="flex items-center justify-between border-b pb-1.5 last:border-b-0"
                          >
                            <div>
                              <div className="font-semibold">
                                v{sn.snapshot_version} · {sn.cost_status}
                              </div>
                              <div className="text-[11px] text-muted-foreground">
                                Total {formatInrFromPaisa(sn.total_cost_paisa)} ·{" "}
                                {formatDateTimeIst(sn.computed_at)}
                              </div>
                            </div>
                            <div className="font-bold tabular-nums">
                              {sn.cost_per_packet_paisa != null
                                ? `${formatInrFromPaisa(sn.cost_per_packet_paisa)}/pkt`
                                : "—"}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            )}

            {/* Monthly Factory Overhead Pools */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Monthly Shared Factory Overhead Pools</CardTitle>
                <CardDescription>
                  Optional monthly expenses allocated across completed/posted batches in that month proportional to good packets produced.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {canOperate && (
                  <div className="grid gap-3 md:grid-cols-5 items-end rounded-lg border p-3 bg-secondary/20">
                    <div>
                      <label className="text-xs font-semibold text-muted-foreground">Period (YYYY-MM)</label>
                      <Input
                        value={poolMonth}
                        onChange={(e) => setPoolMonth(e.target.value)}
                        className="mt-1"
                        placeholder="2026-11"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-muted-foreground">Overhead Category</label>
                      <select
                        className="mt-1 flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                        value={poolType}
                        onChange={(e) => setPoolType(e.target.value)}
                      >
                        <option value="FACTORY_RENT">Factory Rent</option>
                        <option value="MACHINE_DEPRECIATION">Equipment Depreciation</option>
                        <option value="PACKAGING_LABOUR">Packing / Supervisor Labour</option>
                        <option value="GAS_POWER">Monthly Utility / EB Bill</option>
                        <option value="OTHER_PRODUCTION_EXPENSE">Other Factory Expense</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-muted-foreground">Pool Amount (₹)</label>
                      <Input
                        type="number"
                        min="1"
                        value={poolAmountRs}
                        onChange={(e) => setPoolAmountRs(e.target.value)}
                        className="mt-1"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-muted-foreground">Notes</label>
                      <Input
                        value={poolNotes}
                        onChange={(e) => setPoolNotes(e.target.value)}
                        placeholder="Monthly factory pool..."
                        className="mt-1"
                      />
                    </div>
                    <Button
                      disabled={poolMutation.isPending || !(Number(poolAmountRs) > 0)}
                      onClick={() => poolMutation.mutate()}
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      Add &amp; Allocate
                    </Button>
                  </div>
                )}

                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                      <th className="px-4 py-2">Month</th>
                      <th className="px-3 py-2">Type</th>
                      <th className="px-3 py-2 text-right">Pool Amount</th>
                      <th className="px-3 py-2">Recorded By</th>
                      <th className="px-4 py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {d.monthly_pools.map((mp) => (
                      <tr key={mp.id}>
                        <td className="px-4 py-2 font-mono font-bold">{mp.period_month}</td>
                        <td className="px-3 py-2">{mp.overhead_type}</td>
                        <td className="px-3 py-2 text-right font-bold tabular-nums">
                          {formatInrFromPaisa(mp.amount_paisa)}
                        </td>
                        <td className="px-3 py-2">{mp.recorded_by_name}</td>
                        <td className="px-4 py-2">
                          <Badge variant={mp.is_voided ? "destructive" : "success"}>
                            {mp.is_voided ? "VOIDED" : "ALLOCATED"}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                    {d.monthly_pools.length === 0 && (
                      <tr>
                        <td colSpan={5} className="py-5 text-center text-muted-foreground">
                          No shared monthly pools configured.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </DesktopAdminLayout>
  );
}

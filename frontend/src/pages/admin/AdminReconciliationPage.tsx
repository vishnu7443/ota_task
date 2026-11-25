import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Download, Play, RefreshCw, ShieldCheck } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import { reconApi, type ReconDiscrepancy } from "@/lib/api";
import { formatDateTimeIst, formatInrFromPaisa, formatOrderDate } from "@/lib/money";

export function AdminReconciliationPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const isSupervisor = user?.role_code === "PRODUCTION_SUPERVISOR";
  const isAuditor = user?.role_code === "ACCOUNTANT_AUDITOR";
  const isAdmin = user?.role_code === "FACTORY_ADMIN";
  const isOwnerOrAdmin = user?.role_code === "FACTORY_ADMIN" || user?.role_code === "OWNER";

  const [mainTab, setMainTab] = useState<"diagnostics" | "runs">("diagnostics");
  const [diagDomain, setDiagDomain] = useState<"INVENTORY" | "SALES" | "INVOICE" | "PAYMENT" | "DISPATCH" | "PRODUCTION">("INVENTORY");
  const [periodStart, setPeriodStart] = useState("");
  const [periodEnd, setPeriodEnd] = useState("");
  const [onlyMismatches, setOnlyMismatches] = useState(false);

  const [runDomain, setRunDomain] = useState(isSupervisor ? "INVENTORY" : "FULL_SYSTEM");
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [activeDisc, setActiveDisc] = useState<ReconDiscrepancy | null>(null);
  const [actionMode, setActionMode] = useState<"investigate" | "propose" | "approve" | "resolve" | "close" | null>(null);

  const [notesInput, setNotesInput] = useState("");
  const [actionType, setActionType] = useState("STOCK_ADJUSTMENT");
  const [adjQty, setAdjQty] = useState("");
  const [adjUom, setAdjUom] = useState("kg");
  const [dismissFlag, setDismissFlag] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const invReport = useQuery({
    queryKey: ["recon-inv", periodStart, periodEnd, onlyMismatches],
    queryFn: () =>
      reconApi.getInventoryReport({
        periodStart: periodStart || undefined,
        periodEnd: periodEnd || undefined,
        onlyMismatches,
      }),
    enabled: mainTab === "diagnostics" && diagDomain === "INVENTORY",
  });

  const salesReport = useQuery({
    queryKey: ["recon-sales", periodStart, periodEnd],
    queryFn: () => reconApi.getSalesReport({ periodStart: periodStart || undefined, periodEnd: periodEnd || undefined }),
    enabled: mainTab === "diagnostics" && diagDomain === "SALES" && !isSupervisor,
  });

  const invBillReport = useQuery({
    queryKey: ["recon-invoices", periodStart, periodEnd],
    queryFn: () => reconApi.getInvoicesReport({ periodStart: periodStart || undefined, periodEnd: periodEnd || undefined }),
    enabled: mainTab === "diagnostics" && diagDomain === "INVOICE" && !isSupervisor,
  });

  const pmtReport = useQuery({
    queryKey: ["recon-payments", periodStart, periodEnd],
    queryFn: () => reconApi.getPaymentsReport({ periodStart: periodStart || undefined, periodEnd: periodEnd || undefined }),
    enabled: mainTab === "diagnostics" && diagDomain === "PAYMENT" && !isSupervisor,
  });

  const dspReport = useQuery({
    queryKey: ["recon-dispatch", periodStart, periodEnd],
    queryFn: () => reconApi.getDispatchReport({ periodStart: periodStart || undefined, periodEnd: periodEnd || undefined }),
    enabled: mainTab === "diagnostics" && diagDomain === "DISPATCH" && !isSupervisor,
  });

  const prdReport = useQuery({
    queryKey: ["recon-production", periodStart, periodEnd],
    queryFn: () => reconApi.getProductionReport({ periodStart: periodStart || undefined, periodEnd: periodEnd || undefined }),
    enabled: mainTab === "diagnostics" && diagDomain === "PRODUCTION",
  });

  const runsQuery = useQuery({
    queryKey: ["recon-runs"],
    queryFn: () => reconApi.getRuns(),
    enabled: mainTab === "runs",
  });

  const runDetailQuery = useQuery({
    queryKey: ["recon-run-detail", selectedRunId],
    queryFn: () => reconApi.getRunDetail(selectedRunId!),
    enabled: mainTab === "runs" && selectedRunId !== null,
  });

  const startRunMut = useMutation({
    mutationFn: () =>
      reconApi.startRun({
        domain: runDomain,
        period_start: periodStart || null,
        period_end: periodEnd || null,
      }),
    onSuccess: (res) => {
      setErrorMsg(null);
      setFeedback(`Started ${res.run_number} (${res.status}) with ${res.discrepancy_count} discrepancies.`);
      setSelectedRunId(res.id);
      void qc.invalidateQueries({ queryKey: ["recon-runs"] });
      void qc.invalidateQueries({ queryKey: ["recon-run-detail", res.id] });
    },
    onError: (err: Error) => setErrorMsg(err.message),
  });

  const rerunMut = useMutation({
    mutationFn: (runId: number) => reconApi.rerunRun(runId),
    onSuccess: (res) => {
      setErrorMsg(null);
      setFeedback(`Re-ran verification for ${res.run_number}: ${res.status}`);
      void qc.invalidateQueries({ queryKey: ["recon-runs"] });
      void qc.invalidateQueries({ queryKey: ["recon-run-detail", res.id] });
    },
    onError: (err: Error) => setErrorMsg(err.message),
  });

  const workflowMut = useMutation({
    mutationFn: async () => {
      if (actionMode === "close" && selectedRunId) {
        return reconApi.closeRun(selectedRunId, notesInput);
      }
      if (!activeDisc) return null;
      if (actionMode === "investigate") {
        return reconApi.investigateDiscrepancy(activeDisc.id, { investigation_notes: notesInput });
      }
      if (actionMode === "propose") {
        return reconApi.proposeCorrection(activeDisc.id, {
          corrective_action_type: actionType,
          proposed_action: notesInput,
        });
      }
      if (actionMode === "approve") {
        return reconApi.approveCorrection(activeDisc.id, notesInput);
      }
      if (actionMode === "resolve") {
        return reconApi.resolveDiscrepancy(activeDisc.id, {
          resolution_notes: notesInput,
          dismiss: dismissFlag,
          adjustment_type: "COUNT_CORRECTION",
          entered_qty: !dismissFlag && activeDisc.corrective_action_type === "STOCK_ADJUSTMENT" ? adjQty : null,
          entered_uom: !dismissFlag && activeDisc.corrective_action_type === "STOCK_ADJUSTMENT" ? adjUom : null,
        });
      }
      return null;
    },
    onSuccess: () => {
      setErrorMsg(null);
      setFeedback("Reconciliation workflow action recorded cleanly.");
      setActionMode(null);
      setActiveDisc(null);
      setNotesInput("");
      setAdjQty("");
      setDismissFlag(false);
      void qc.invalidateQueries({ queryKey: ["recon-runs"] });
      if (selectedRunId) void qc.invalidateQueries({ queryKey: ["recon-run-detail", selectedRunId] });
      void qc.invalidateQueries({ queryKey: ["recon-inv"] });
    },
    onError: (err: Error) => setErrorMsg(err.message),
  });

  const handleExportInvCsv = async () => {
    setErrorMsg(null);
    try {
      const blob = await reconApi.exportInventoryCsvBlob({
        periodStart: periodStart || undefined,
        periodEnd: periodEnd || undefined,
        onlyMismatches,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "inventory_reconciliation.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErrorMsg(e instanceof Error ? e.message : "CSV download failed.");
    }
  };

  const allowedDiagDomains = isSupervisor
    ? (["INVENTORY", "PRODUCTION"] as const)
    : (["INVENTORY", "SALES", "INVOICE", "PAYMENT", "DISPATCH", "PRODUCTION"] as const);

  return (
    <DesktopAdminLayout
      title="Cross-Module Reconciliation Center"
      subtitle="Verify ledger-vs-balance parity, sales/GST/dispatch/AR synchronization & controlled discrepancy resolution workflows"
      actions={
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant={mainTab === "diagnostics" ? "default" : "outline"}
            onClick={() => setMainTab("diagnostics")}
          >
            Live Diagnostics
          </Button>
          <Button
            size="sm"
            variant={mainTab === "runs" ? "default" : "outline"}
            onClick={() => setMainTab("runs")}
          >
            Reconciliation Runs &amp; Discrepancies
          </Button>
        </div>
      }
    >
      <div className="space-y-6">
        <Card>
          <CardContent className="p-4 flex flex-wrap items-end gap-4">
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Period Start</label>
              <Input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} className="mt-1" />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Period End</label>
              <Input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} className="mt-1" />
            </div>
            {mainTab === "diagnostics" && diagDomain === "INVENTORY" && (
              <>
                <label className="flex items-center gap-2 text-sm pb-2">
                  <input
                    type="checkbox"
                    checked={onlyMismatches}
                    onChange={(e) => setOnlyMismatches(e.target.checked)}
                  />
                  Only Mismatches
                </label>
                <Button size="sm" variant="outline" onClick={handleExportInvCsv} className="ml-auto">
                  <Download className="h-4 w-4" />
                  Export Inventory Recon CSV
                </Button>
              </>
            )}
          </CardContent>
        </Card>

        {feedback && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            {feedback}
          </div>
        )}
        {errorMsg && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {errorMsg}
          </div>
        )}

        {mainTab === "diagnostics" && (
          <>
            <div className="flex flex-wrap gap-2">
              {allowedDiagDomains.map((dom) => (
                <Button
                  key={dom}
                  size="sm"
                  variant={diagDomain === dom ? "default" : "outline"}
                  onClick={() => setDiagDomain(dom)}
                >
                  {dom}
                </Button>
              ))}
            </div>

            {diagDomain === "INVENTORY" && invReport.data && (
              <Card>
                <CardHeader>
                  <CardTitle>
                    Inventory Ledger vs Balance Reconciliation ({invReport.data.matched_count} Matched ·{" "}
                    {invReport.data.mismatch_count} Mismatch)
                  </CardTitle>
                  <CardDescription>
                    Expected Closing = Opening + Inward - Outward vs Persisted On-Hand &amp; Open FIFO CostLots
                  </CardDescription>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                        <th className="py-2 pr-3">Item</th>
                        <th className="py-2 pr-3 text-right">Opening</th>
                        <th className="py-2 pr-3 text-right">Inward</th>
                        <th className="py-2 pr-3 text-right">Outward</th>
                        <th className="py-2 pr-3 text-right">Expected</th>
                        <th className="py-2 pr-3 text-right">Persisted</th>
                        <th className="py-2 pr-3 text-right">Diff</th>
                        <th className="py-2 pr-3 text-right">Open Lots</th>
                        <th className="py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invReport.data.items.map((r) => (
                        <tr key={`${r.item_type}-${r.item_id}`} className="border-b last:border-b-0">
                          <td className="py-2 pr-3">
                            <div className="font-semibold">{r.code}</div>
                            <div className="text-xs text-muted-foreground">{r.name} ({r.base_uom})</div>
                          </td>
                          <td className="py-2 pr-3 text-right tabular-nums">{r.opening_qty_base}</td>
                          <td className="py-2 pr-3 text-right tabular-nums text-emerald-700">{r.total_inward_qty_base}</td>
                          <td className="py-2 pr-3 text-right tabular-nums text-amber-700">{r.total_outward_qty_base}</td>
                          <td className="py-2 pr-3 text-right tabular-nums font-medium">{r.expected_closing_qty_base}</td>
                          <td className="py-2 pr-3 text-right tabular-nums font-medium">{r.persisted_closing_qty_base}</td>
                          <td className="py-2 pr-3 text-right tabular-nums font-bold">{r.difference_qty_base}</td>
                          <td className="py-2 pr-3 text-right tabular-nums">{r.cost_lot_remaining_qty_base}</td>
                          <td className="py-2"><StatusBadge status={r.status} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            )}

            {diagDomain === "SALES" && salesReport.data && (
              <Card>
                <CardHeader>
                  <CardTitle>Sales Orders vs GST Invoices ({salesReport.data.length})</CardTitle>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                        <th className="py-2">Order</th>
                        <th className="py-2">Customer</th>
                        <th className="py-2">Order Status</th>
                        <th className="py-2 text-right">Ord Pkts</th>
                        <th className="py-2 text-right">Inv Pkts</th>
                        <th className="py-2">Invoices</th>
                        <th className="py-2">Status / Issue</th>
                      </tr>
                    </thead>
                    <tbody>
                      {salesReport.data.map((r) => (
                        <tr key={r.sales_order_id} className="border-b last:border-b-0">
                          <td className="py-2 font-semibold">{r.order_number}</td>
                          <td className="py-2">{r.customer_name}</td>
                          <td className="py-2"><StatusBadge status={r.order_status} /></td>
                          <td className="py-2 text-right tabular-nums">{r.ordered_qty_pkts}</td>
                          <td className="py-2 text-right tabular-nums">{r.invoiced_qty_pkts}</td>
                          <td className="py-2 text-xs font-mono">{r.invoice_numbers.join(", ") || "—"}</td>
                          <td className="py-2">
                            <StatusBadge status={r.status} />
                            {r.issue_detail && <div className="text-xs text-red-700 mt-1">{r.issue_detail}</div>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            )}

            {diagDomain === "INVOICE" && invBillReport.data && (
              <Card>
                <CardHeader>
                  <CardTitle>Invoices, GST Split &amp; Credit Notes Check ({invBillReport.data.length})</CardTitle>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                        <th className="py-2">Invoice</th>
                        <th className="py-2">Supply</th>
                        <th className="py-2 text-right">Grand Total</th>
                        <th className="py-2 text-right">Recomputed</th>
                        <th className="py-2 text-right">Credited</th>
                        <th className="py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {invBillReport.data.map((r) => (
                        <tr key={r.invoice_id} className="border-b last:border-b-0">
                          <td className="py-2 font-semibold">{r.invoice_number}</td>
                          <td className="py-2"><StatusBadge status={r.supply_type} /></td>
                          <td className="py-2 text-right tabular-nums">{formatInrFromPaisa(r.persisted_grand_total_paisa)}</td>
                          <td className="py-2 text-right tabular-nums">{formatInrFromPaisa(r.computed_grand_total_paisa)}</td>
                          <td className="py-2 text-right tabular-nums">{formatInrFromPaisa(r.persisted_credited_paisa)}</td>
                          <td className="py-2">
                            <StatusBadge status={r.status} />
                            {r.issue_detail && <div className="text-xs text-red-700 mt-1">{r.issue_detail}</div>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            )}

            {diagDomain === "PAYMENT" && pmtReport.data && (
              <Card>
                <CardHeader>
                  <CardTitle>Payments, Allocations &amp; Receivables Parity ({pmtReport.data.length})</CardTitle>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                        <th className="py-2">Payment</th>
                        <th className="py-2">Customer</th>
                        <th className="py-2 text-right">Amount</th>
                        <th className="py-2 text-right">Allocated</th>
                        <th className="py-2 text-right">Refunded</th>
                        <th className="py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pmtReport.data.map((r) => (
                        <tr key={r.payment_id} className="border-b last:border-b-0">
                          <td className="py-2 font-semibold">{r.payment_number}</td>
                          <td className="py-2">{r.customer_name}</td>
                          <td className="py-2 text-right tabular-nums">{formatInrFromPaisa(r.amount_paisa)}</td>
                          <td className="py-2 text-right tabular-nums">{formatInrFromPaisa(r.persisted_allocated_paisa)}</td>
                          <td className="py-2 text-right tabular-nums">{formatInrFromPaisa(r.persisted_refunded_paisa)}</td>
                          <td className="py-2">
                            <StatusBadge status={r.status} />
                            {r.issue_detail && <div className="text-xs text-red-700 mt-1">{r.issue_detail}</div>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            )}

            {diagDomain === "DISPATCH" && dspReport.data && (
              <Card>
                <CardHeader>
                  <CardTitle>Invoice vs Dispatch vs Inventory Ledger ({dspReport.data.length})</CardTitle>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                        <th className="py-2">Invoice</th>
                        <th className="py-2">Dispatch Status</th>
                        <th className="py-2 text-right">Invoiced</th>
                        <th className="py-2 text-right">Dispatched</th>
                        <th className="py-2 text-right">DISPATCH_OUT Ledger</th>
                        <th className="py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dspReport.data.map((r) => (
                        <tr key={r.invoice_id} className="border-b last:border-b-0">
                          <td className="py-2 font-semibold">{r.invoice_number}</td>
                          <td className="py-2"><StatusBadge status={r.dispatch_status} /></td>
                          <td className="py-2 text-right tabular-nums">{r.invoiced_qty_pkts}</td>
                          <td className="py-2 text-right tabular-nums">{r.dispatched_qty_pkts}</td>
                          <td className="py-2 text-right tabular-nums">{r.ledger_dispatch_qty_pkts}</td>
                          <td className="py-2">
                            <StatusBadge status={r.status} />
                            {r.issue_detail && <div className="text-xs text-red-700 mt-1">{r.issue_detail}</div>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            )}

            {diagDomain === "PRODUCTION" && prdReport.data && (
              <Card>
                <CardHeader>
                  <CardTitle>Production Output, Ledger &amp; Cost Summary Reconciliation ({prdReport.data.length})</CardTitle>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                        <th className="py-2">Run</th>
                        <th className="py-2">SKU</th>
                        <th className="py-2 text-right">Good Pkts</th>
                        <th className="py-2 text-right">Ledger IN</th>
                        <th className="py-2 text-right">Cost Summary</th>
                        <th className="py-2 text-right">Var Flags</th>
                        <th className="py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {prdReport.data.map((r) => (
                        <tr key={r.production_run_id} className="border-b last:border-b-0">
                          <td className="py-2 font-semibold">{r.run_number}</td>
                          <td className="py-2">{r.sku_code}</td>
                          <td className="py-2 text-right tabular-nums">{r.actual_good_pkts}</td>
                          <td className="py-2 text-right tabular-nums">{r.ledger_output_pkts}</td>
                          <td className="py-2 text-right tabular-nums">
                            {r.cost_summary_paisa !== null ? formatInrFromPaisa(r.cost_summary_paisa) : "—"}
                          </td>
                          <td className="py-2 text-right tabular-nums">{r.bom_variance_flags_count}</td>
                          <td className="py-2">
                            <StatusBadge status={r.status} />
                            {r.issue_detail && <div className="text-xs text-red-700 mt-1">{r.issue_detail}</div>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            )}
          </>
        )}

        {mainTab === "runs" && (
          <div className="space-y-6">
            {!isAuditor && (
              <Card>
                <CardHeader>
                  <CardTitle>Start New Formal Reconciliation Run</CardTitle>
                  <CardDescription>
                    Executes deterministic scan across selected domain and freezes discrepancies into auditable workflow
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-wrap items-end gap-4">
                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Domain</label>
                    <select
                      value={runDomain}
                      onChange={(e) => setRunDomain(e.target.value)}
                      className="mt-1 flex h-11 rounded-lg border border-input bg-card px-3 text-sm"
                    >
                      {!isSupervisor && <option value="FULL_SYSTEM">FULL_SYSTEM (All Modules)</option>}
                      <option value="INVENTORY">INVENTORY</option>
                      {!isSupervisor && <option value="SALES">SALES</option>}
                      {!isSupervisor && <option value="INVOICE">INVOICE</option>}
                      {!isSupervisor && <option value="PAYMENT">PAYMENT</option>}
                      {!isSupervisor && <option value="DISPATCH">DISPATCH</option>}
                      <option value="PRODUCTION">PRODUCTION</option>
                    </select>
                  </div>
                  <Button onClick={() => startRunMut.mutate()} disabled={startRunMut.isPending}>
                    <Play className="h-4 w-4" />
                    {startRunMut.isPending ? "Scanning..." : "Run Reconciliation Scan"}
                  </Button>
                </CardContent>
              </Card>
            )}

            <div className="grid gap-6 lg:grid-cols-3">
              <Card className="lg:col-span-1">
                <CardHeader>
                  <CardTitle>Reconciliation Runs</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2.5">
                  {(runsQuery.data ?? []).length === 0 ? (
                    <div className="text-sm text-muted-foreground py-6 text-center">
                      No reconciliation runs recorded yet.
                    </div>
                  ) : (
                    runsQuery.data!.map((r) => (
                      <button
                        key={r.id}
                        type="button"
                        onClick={() => setSelectedRunId(r.id)}
                        className={`w-full rounded-lg border p-3 text-left transition-colors ${
                          selectedRunId === r.id ? "border-primary bg-primary/5" : "hover:bg-secondary/40"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-xs font-bold">{r.run_number}</span>
                          <StatusBadge status={r.status} />
                        </div>
                        <div className="mt-1 text-xs font-semibold">{r.domain}</div>
                        <div className="mt-1 text-[11px] text-muted-foreground">
                          {formatOrderDate(r.period_start)} – {formatOrderDate(r.period_end)} ·{" "}
                          {r.discrepancy_count} issues ({r.resolved_count} resolved)
                        </div>
                      </button>
                    ))
                  )}
                </CardContent>
              </Card>

              <Card className="lg:col-span-2">
                {!runDetailQuery.data ? (
                  <CardContent className="py-12 text-center text-sm text-muted-foreground">
                    Select a reconciliation run on the left to inspect discrepancies and execute resolution workflow.
                  </CardContent>
                ) : (
                  <>
                    <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <CardTitle className="font-mono">{runDetailQuery.data.run_number}</CardTitle>
                          <StatusBadge status={runDetailQuery.data.status} />
                        </div>
                        <CardDescription>
                          Domain: {runDetailQuery.data.domain} · Started by {runDetailQuery.data.started_by_name} at{" "}
                          {formatDateTimeIst(runDetailQuery.data.started_at)}
                        </CardDescription>
                      </div>
                      {runDetailQuery.data.status !== "CLOSED" && !isAuditor && (
                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => rerunMut.mutate(runDetailQuery.data!.id)}
                            disabled={rerunMut.isPending}
                          >
                            <RefreshCw className="h-3.5 w-3.5" />
                            Re-Verify
                          </Button>
                          {isOwnerOrAdmin && (
                            <Button
                              size="sm"
                              onClick={() => {
                                setActionMode("close");
                                setNotesInput("");
                              }}
                            >
                              <ShieldCheck className="h-3.5 w-3.5" />
                              Close Run
                            </Button>
                          )}
                        </div>
                      )}
                    </CardHeader>
                    <CardContent className="space-y-5">
                      <div className="space-y-3">
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                          Detected Discrepancies ({runDetailQuery.data.discrepancies.length})
                        </h4>
                        {runDetailQuery.data.discrepancies.length === 0 ? (
                          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800 flex items-center gap-2">
                            <CheckCircle2 className="h-4 w-4" />
                            Zero discrepancies detected — all records match cleanly!
                          </div>
                        ) : (
                          runDetailQuery.data.discrepancies.map((disc) => (
                            <div key={disc.id} className="rounded-lg border p-3.5 space-y-2">
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="flex items-center gap-2">
                                  <span className="font-mono text-xs font-bold">{disc.discrepancy_code}</span>
                                  <StatusBadge status={disc.severity} />
                                  <StatusBadge status={disc.status} />
                                </div>
                                <span className="text-xs font-mono text-muted-foreground">{disc.entity_ref}</span>
                              </div>
                              <p className="text-sm">{disc.difference_summary}</p>
                              {disc.investigation_notes && (
                                <div className="text-xs text-muted-foreground">
                                  <span className="font-semibold">Investigation:</span> {disc.investigation_notes}
                                </div>
                              )}
                              {disc.proposed_action && (
                                <div className="text-xs text-muted-foreground">
                                  <span className="font-semibold">Proposed ({disc.corrective_action_type}):</span>{" "}
                                  {disc.proposed_action}
                                </div>
                              )}
                              {disc.resolution_notes && (
                                <div className="text-xs text-emerald-800">
                                  <span className="font-semibold">Resolution:</span> {disc.resolution_notes}
                                </div>
                              )}

                              {!isAuditor && !["RESOLVED", "CLOSED", "DISMISSED"].includes(disc.status) && (
                                <div className="flex flex-wrap gap-2 pt-1">
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => {
                                      setActiveDisc(disc);
                                      setActionMode("investigate");
                                      setNotesInput(disc.investigation_notes || "");
                                    }}
                                  >
                                    Investigate
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => {
                                      setActiveDisc(disc);
                                      setActionMode("propose");
                                      setNotesInput(disc.proposed_action || "");
                                    }}
                                  >
                                    Propose Correction
                                  </Button>
                                  {isOwnerOrAdmin && disc.status === "ACTION_PROPOSED" && (
                                    <Button
                                      size="sm"
                                      onClick={() => {
                                        setActiveDisc(disc);
                                        setActionMode("approve");
                                        setNotesInput("");
                                      }}
                                    >
                                      Approve
                                    </Button>
                                  )}
                                  {isAdmin && (
                                    <Button
                                      size="sm"
                                      onClick={() => {
                                        setActiveDisc(disc);
                                        setActionMode("resolve");
                                        setDismissFlag(disc.status !== "APPROVED");
                                        setNotesInput("");
                                      }}
                                    >
                                      Apply / Dismiss
                                    </Button>
                                  )}
                                </div>
                              )}
                            </div>
                          ))
                        )}
                      </div>

                      <div className="space-y-2 border-t pt-4">
                        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                          Append-Only Event History ({runDetailQuery.data.events.length})
                        </h4>
                        {runDetailQuery.data.events.map((ev) => (
                          <div key={ev.id} className="text-xs flex flex-wrap justify-between border-b pb-1.5 last:border-b-0">
                            <div>
                              <span className="font-mono font-semibold">{ev.event_type}</span> ({ev.actor_name}):{" "}
                              {ev.notes}
                            </div>
                            <span className="text-muted-foreground">{formatDateTimeIst(ev.occurred_at)}</span>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </>
                )}
              </Card>
            </div>
          </div>
        )}

        {/* Workflow Action Modal */}
        {actionMode && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <Card className="w-full max-w-lg">
              <CardHeader>
                <CardTitle className="capitalize">
                  {actionMode === "close" ? "Close Reconciliation Run" : `${actionMode} Discrepancy`}
                </CardTitle>
                <CardDescription>{activeDisc?.entity_ref}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {actionMode === "propose" && (
                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Corrective Action Type</label>
                    <select
                      value={actionType}
                      onChange={(e) => setActionType(e.target.value)}
                      className="mt-1 flex h-11 w-full rounded-lg border border-input bg-card px-3 text-sm"
                    >
                      <option value="STOCK_ADJUSTMENT">STOCK_ADJUSTMENT (Authorized Ledger Posting)</option>
                      <option value="ISSUE_INVOICE">ISSUE_INVOICE</option>
                      <option value="AR_RECALC_NOTE">AR_RECALC_NOTE</option>
                      <option value="MANUAL_JOURNAL_NOTE">MANUAL_JOURNAL_NOTE</option>
                      <option value="DISPATCH_FOLLOWUP">DISPATCH_FOLLOWUP</option>
                      <option value="NO_OP_EXPLAINED">NO_OP_EXPLAINED</option>
                    </select>
                  </div>
                )}

                {actionMode === "resolve" && (
                  <>
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={dismissFlag}
                        onChange={(e) => setDismissFlag(e.target.checked)}
                      />
                      Dismiss as explained (no posting)
                    </label>
                    {!dismissFlag && activeDisc?.corrective_action_type === "STOCK_ADJUSTMENT" && (
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="text-xs font-semibold text-muted-foreground">Signed Qty</label>
                          <Input value={adjQty} onChange={(e) => setAdjQty(e.target.value)} placeholder="e.g. -2 or 5" className="mt-1" />
                        </div>
                        <div>
                          <label className="text-xs font-semibold text-muted-foreground">UOM</label>
                          <Input value={adjUom} onChange={(e) => setAdjUom(e.target.value)} placeholder="kg / packet / piece" className="mt-1" />
                        </div>
                      </div>
                    )}
                  </>
                )}

                <div>
                  <label className="text-xs font-semibold text-muted-foreground">
                    Mandatory Audit Remarks / Notes (min 5 chars)
                  </label>
                  <Input
                    value={notesInput}
                    onChange={(e) => setNotesInput(e.target.value)}
                    placeholder="Enter documented justification..."
                    className="mt-1"
                  />
                </div>

                <div className="flex justify-end gap-2">
                  <Button
                    variant="outline"
                    onClick={() => {
                      setActionMode(null);
                      setActiveDisc(null);
                    }}
                  >
                    Cancel
                  </Button>
                  <Button onClick={() => workflowMut.mutate()} disabled={workflowMut.isPending}>
                    {workflowMut.isPending ? "Saving..." : "Confirm Action"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </DesktopAdminLayout>
  );
}

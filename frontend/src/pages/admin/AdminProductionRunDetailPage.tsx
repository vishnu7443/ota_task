import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  Lock,
  Play,
  Send,
  XCircle,
} from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api, costingApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDateTimeIst, formatInrFromPaisa, formatOrderDate } from "@/lib/money";
import { compatibleUomsForMaterial, formatBaseQty, formatDisplayQty, toNumber } from "@/lib/units";

const STEPS = ["DRAFT", "PLANNED", "IN_PROGRESS", "COMPLETED", "POSTED"] as const;

export function AdminProductionRunDetailPage() {
  const { runId } = useParams();
  const id = Number(runId);
  const { user } = useAuth();
  const canOperate = user?.role_code === "FACTORY_ADMIN" || user?.role_code === "PRODUCTION_SUPERVISOR";
  const queryClient = useQueryClient();

  const [banner, setBanner] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  // Material Issue Form state (PLANNED -> IN_PROGRESS)
  const [issueQtys, setIssueQtys] = useState<Record<number, { qty: string; uom: string }>>({});
  const [issueNotes, setIssueNotes] = useState("");

  // Execution Completion Form state (IN_PROGRESS -> COMPLETED)
  const [goodPkts, setGoodPkts] = useState("");
  const [rejectedPkts, setRejectedPkts] = useState("0");
  const [batchCode, setBatchCode] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [qualityRemarks, setQualityRemarks] = useState("");
  const [consInputs, setConsInputs] = useState<
    Record<
      number,
      {
        consumed: string;
        goodUsed: string;
        damaged: string;
        returned: string;
        wasted: string;
        uom: string;
      }
    >
  >({});

  // Cancel modal state
  const [showCancel, setShowCancel] = useState(false);
  const [cancelReason, setCancelReason] = useState("");

  const runQuery = useQuery({
    queryKey: ["production-run-detail", id],
    queryFn: () => api.getProductionRunDetail(id),
    enabled: Boolean(id),
  });

  const ledgerQuery = useQuery({
    queryKey: ["production-run-ledger", id],
    queryFn: () => api.getInventoryLedger({ productionRunId: id, limit: 100 }),
    enabled: Boolean(id),
  });

  const costingQuery = useQuery({
    queryKey: ["production-run-costing", id],
    queryFn: () => costingApi.getRunCosting(Number(id)),
    enabled: Boolean(id),
  });

  const run = runQuery.data;

  useEffect(() => {
    if (!run) return;
    const initIssue: Record<number, { qty: string; uom: string }> = {};
    const initCons: Record<
      number,
      { consumed: string; goodUsed: string; damaged: string; returned: string; wasted: string; uom: string }
    > = {};

    run.material_issues.forEach((mi) => {
      const factor = toNumber(mi.display_factor) || 1;
      const plannedDisp = (toNumber(mi.planned_qty_base) / factor).toString();
      const issuedDisp = (toNumber(mi.issued_qty_base) / factor).toString();
      initIssue[mi.material_id] = {
        qty: mi.issue_phase === "RAW_ISSUE" ? plannedDisp : "0",
        uom: mi.display_uom,
      };
      initCons[mi.material_id] = {
        consumed: toNumber(mi.issued_qty_base) > 0 ? issuedDisp : plannedDisp,
        goodUsed: toNumber(mi.issued_qty_base) > 0 ? issuedDisp : plannedDisp,
        damaged: "0",
        returned: "0",
        wasted: "0",
        uom: mi.display_uom,
      };
    });

    setIssueQtys(initIssue);
    setConsInputs(initCons);
    if (!goodPkts) setGoodPkts(String(run.expected_output_pkts));
    if (!batchCode) setBatchCode(`${run.sku_code}-${run.run_date.replaceAll("-", "")}`);
  }, [run?.id, run?.status]);

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["production-run-detail", id] });
    queryClient.invalidateQueries({ queryKey: ["production-run-ledger", id] });
    queryClient.invalidateQueries({ queryKey: ["production-dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["inventory-overview"] });
    queryClient.invalidateQueries({ queryKey: ["inventory-ledger"] });
  };

  const planMutation = useMutation({
    mutationFn: () => api.planProductionRun(id),
    onSuccess: () => {
      invalidateAll();
      setBanner({ kind: "success", msg: "Production run planned cleanly." });
    },
    onError: (err) =>
      setBanner({ kind: "error", msg: err instanceof ApiClientError ? err.message : "Plan action failed." }),
  });

  const issueMutation = useMutation({
    mutationFn: () => {
      const items = Object.entries(issueQtys)
        .filter(([, v]) => Number(v.qty) > 0)
        .map(([matId, v]) => ({
          material_id: Number(matId),
          issued_qty: v.qty,
          issued_uom: v.uom,
        }));
      return api.issueProductionMaterials(id, {
        items,
        require_all_bom_stock: true,
        notes: issueNotes.trim() || null,
      });
    },
    onSuccess: () => {
      invalidateAll();
      setBanner({
        kind: "success",
        msg: "Materials issued cleanly and linked ledger movements created (IN_PROGRESS).",
      });
    },
    onError: (err) =>
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Material issue failed.",
      }),
  });

  const completeMutation = useMutation({
    mutationFn: () => {
      if (!run) throw new Error("Run not loaded");
      const consumptions = run.material_issues.map((mi) => {
        const inp = consInputs[mi.material_id];
        if (mi.issue_phase === "PACKAGING_PACK") {
          return {
            material_id: mi.material_id,
            actual_good_used_qty: inp?.goodUsed || "0",
            damaged_packaging_qty: inp?.damaged || "0",
            returned_unused_qty: inp?.returned || "0",
            uom: inp?.uom || mi.display_uom,
          };
        }
        return {
          material_id: mi.material_id,
          actual_consumed_qty: inp?.consumed || "0",
          returned_unused_qty: inp?.returned || "0",
          wasted_qty: inp?.wasted || "0",
          uom: inp?.uom || mi.display_uom,
        };
      });
      return api.completeProductionRun(id, {
        good_output_pkts: Number(goodPkts || 0),
        rejected_output_pkts: Number(rejectedPkts || 0),
        batch_code: batchCode.trim(),
        expiry_date: expiryDate || null,
        quality_remarks: qualityRemarks.trim() || null,
        consumptions,
      });
    },
    onSuccess: () => {
      invalidateAll();
      setBanner({
        kind: "success",
        msg: "Actual output, packaging damage, and consumption saved (COMPLETED). Review & Atomically Post to finish.",
      });
    },
    onError: (err) =>
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Failed to save execution results.",
      }),
  });

  const postMutation = useMutation({
    mutationFn: () => api.postProductionRun(id),
    onSuccess: () => {
      invalidateAll();
      setBanner({
        kind: "success",
        msg: "Production run POSTED atomically! Raw stock, packaging, returns, FG stock, variances & audit trail updated.",
      });
    },
    onError: (err) =>
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Atomic production posting failed.",
      }),
  });

  const cancelMutation = useMutation({
    mutationFn: () => api.cancelProductionRun(id, { reason: cancelReason.trim(), returned_items: [] }),
    onSuccess: () => {
      invalidateAll();
      setShowCancel(false);
      setBanner({ kind: "success", msg: "Production run cancelled cleanly." });
    },
    onError: (err) =>
      setBanner({ kind: "error", msg: err instanceof ApiClientError ? err.message : "Cancel failed." }),
  });

  if (runQuery.isLoading || !run) {
    return (
      <DesktopAdminLayout title="Loading Production Run...">
        <div className="h-40 animate-pulse rounded-lg bg-muted" />
      </DesktopAdminLayout>
    );
  }

  const movements = ledgerQuery.data ?? [];

  return (
    <DesktopAdminLayout
      title={`${run.run_number} — ${run.display_name}`}
      subtitle={`Pinned to BOM v${run.version_no} (${run.bom_status}) · Scheduled ${formatOrderDate(run.run_date)}`}
      actions={
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to="/admin/production">
              <ArrowLeft className="h-4 w-4" />
              All Runs
            </Link>
          </Button>
          {canOperate && (run.status === "DRAFT" || run.status === "PLANNED" || run.status === "IN_PROGRESS") && (
            <Button variant="outline" onClick={() => setShowCancel((s) => !s)}>
              <XCircle className="h-4 w-4 text-destructive" />
              Cancel / Abort
            </Button>
          )}
        </div>
      }
    >
      <div className="space-y-6">
        {banner && (
          <div
            className={`rounded-lg border px-4 py-3 text-sm font-medium ${
              banner.kind === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : "border-red-200 bg-red-50 text-red-900"
            }`}
          >
            {banner.msg}
          </div>
        )}

        {/* Lifecycle Stepper & Snapshot Header */}
        <Card>
          <CardContent className="p-5 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                {STEPS.map((step, i) => {
                  const idx = STEPS.indexOf(run.status as typeof STEPS[number]);
                  const active = run.status === step;
                  const done = idx > i;
                  return (
                    <div key={step} className="flex items-center gap-2">
                      <div
                        className={`rounded-full px-3 py-1 text-xs font-bold ${
                          active
                            ? "bg-primary text-primary-foreground"
                            : done
                            ? "bg-emerald-100 text-emerald-800"
                            : "bg-secondary text-muted-foreground"
                        }`}
                      >
                        {step.replace("_", " ")}
                      </div>
                      {i < STEPS.length - 1 && <span className="text-muted-foreground">→</span>}
                    </div>
                  );
                })}
                {run.status === "CANCELLED" && <StatusBadge status="CANCELLED" />}
              </div>
              <Badge variant="outline" className="gap-1">
                <Lock className="h-3 w-3" /> Historical BOM v{run.version_no} Pinned
              </Badge>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5 text-xs pt-2 border-t">
              <div>
                <span className="text-muted-foreground">Batch Scale / Expected</span>
                <div className="text-sm font-bold">
                  {Number(run.batch_multiplier)}× → {run.expected_output_pkts} pkts
                </div>
              </div>
              <div>
                <span className="text-muted-foreground">Good Output / Rejected</span>
                <div className="text-sm font-bold text-emerald-700">
                  {run.actual_good_output_pkts} good{" "}
                  <span className="text-red-700 font-normal">({run.rejected_output_pkts} rej)</span>
                </div>
              </div>
              <div>
                <span className="text-muted-foreground">Supervisor / Started</span>
                <div className="font-medium">{run.supervisor_name}</div>
                <div className="text-muted-foreground">{formatDateTimeIst(run.started_at)}</div>
              </div>
              <div>
                <span className="text-muted-foreground">Completed / Posted</span>
                <div className="text-muted-foreground">{formatDateTimeIst(run.completed_at)}</div>
                <div className="font-medium text-emerald-700">{formatDateTimeIst(run.posted_at)}</div>
              </div>
              <div>
                <span className="text-muted-foreground">Material Value Absorbed</span>
                <div className="text-sm font-bold">{formatInrFromPaisa(run.total_material_cost_paisa)}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        {showCancel && (
          <Card className="border-destructive/40">
            <CardHeader>
              <CardTitle className="text-sm text-destructive">Cancel / Abort Production Run</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <Input
                placeholder="Mandatory audit reason for cancelling/aborting this run (min 5 chars)..."
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
              />
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setShowCancel(false)}>
                  Keep Run
                </Button>
                <Button
                  variant="destructive"
                  disabled={cancelReason.trim().length < 5 || cancelMutation.isPending}
                  onClick={() => cancelMutation.mutate()}
                >
                  Confirm Cancellation
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* STAGE 1: DRAFT -> PLANNED */}
        {run.status === "DRAFT" && canOperate && (
          <Card className="border-primary/40">
            <CardHeader>
              <CardTitle className="text-base">Step 1: Finalize Production Plan</CardTitle>
              <CardDescription>
                Review BOM requirements below and move this draft run to PLANNED so floor staff can issue materials.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex justify-end">
              <Button onClick={() => planMutation.mutate()} disabled={planMutation.isPending}>
                <ClipboardCheck className="h-4 w-4" />
                {planMutation.isPending ? "Planning..." : "Approve & Mark PLANNED"}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* STAGE 2: PLANNED -> IN_PROGRESS (Controlled Material Issue) */}
        {run.status === "PLANNED" && canOperate && (
          <Card className="border-primary/40">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Play className="h-4 w-4 text-primary" />
                Step 2: Controlled Material Issue &amp; Start Production
              </CardTitle>
              <CardDescription>
                Enter actual quantities issued from warehouse. Leave packaging at 0 if issued at completion step, or issue all items up front.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                    <th className="py-2 pr-3">Material</th>
                    <th className="py-2 pr-3 text-right">Planned BOM Qty</th>
                    <th className="py-2 pr-3 text-right">Available in Stock</th>
                    <th className="py-2 pr-3 text-right">Issue Qty</th>
                    <th className="py-2">Unit</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {run.material_issues.map((mi) => {
                    const inp = issueQtys[mi.material_id] ?? { qty: "0", uom: mi.display_uom };
                    const dim = mi.base_uom === "g" ? "MASS" : mi.base_uom === "ml" ? "VOLUME" : "COUNT";
                    const uoms = compatibleUomsForMaterial(dim);
                    return (
                      <tr key={mi.id}>
                        <td className="py-2.5 pr-3">
                          <div className="font-medium">{mi.material_name}</div>
                          <div className="text-xs text-muted-foreground">{mi.issue_phase}</div>
                        </td>
                        <td className="py-2.5 pr-3 text-right tabular-nums">
                          {formatDisplayQty(mi.planned_qty_base, mi.display_uom, mi.display_factor)}
                        </td>
                        <td className="py-2.5 pr-3 text-right tabular-nums text-emerald-700 font-medium">
                          {formatDisplayQty(mi.available_qty_base, mi.display_uom, mi.display_factor)}
                        </td>
                        <td className="py-2.5 pr-3 w-32">
                          <Input
                            type="number"
                            step="0.001"
                            min="0"
                            className="h-9 text-right"
                            value={inp.qty}
                            onChange={(e) =>
                              setIssueQtys((prev) => ({
                                ...prev,
                                [mi.material_id]: { ...inp, qty: e.target.value },
                              }))
                            }
                          />
                        </td>
                        <td className="py-2.5 w-24">
                          <select
                            className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                            value={inp.uom}
                            onChange={(e) =>
                              setIssueQtys((prev) => ({
                                ...prev,
                                [mi.material_id]: { ...inp, uom: e.target.value },
                              }))
                            }
                          >
                            {uoms.map((u) => (
                              <option key={u} value={u}>
                                {u}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t">
                <Input
                  className="max-w-md"
                  placeholder="Optional batch start notes..."
                  value={issueNotes}
                  onChange={(e) => setIssueNotes(e.target.value)}
                />
                <Button onClick={() => issueMutation.mutate()} disabled={issueMutation.isPending}>
                  <Play className="h-4 w-4" />
                  {issueMutation.isPending ? "Issuing..." : "Issue Materials & Start Run"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* STAGE 3: IN_PROGRESS -> COMPLETED (Actual Consumption, Output & Quality) */}
        {run.status === "IN_PROGRESS" && canOperate && (
          <Card className="border-primary/40">
            <CardHeader>
              <CardTitle className="text-base">
                Step 3: Record Actual Consumption, Quality &amp; Finished Output
              </CardTitle>
              <CardDescription>
                Record actual consumption, unused returns, good packets, rejected packets, and damaged packaging separately.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                <div className="space-y-1">
                  <label className="text-xs font-semibold">Good Packets Output</label>
                  <Input
                    type="number"
                    min="0"
                    value={goodPkts}
                    onChange={(e) => setGoodPkts(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold">Rejected Finished Packets</label>
                  <Input
                    type="number"
                    min="0"
                    value={rejectedPkts}
                    onChange={(e) => setRejectedPkts(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold">Batch Code</label>
                  <Input value={batchCode} onChange={(e) => setBatchCode(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold">Expiry Date (Optional)</label>
                  <Input type="date" value={expiryDate} onChange={(e) => setExpiryDate(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold">Quality Remarks</label>
                  <Input
                    placeholder="Seal inspection / wastage notes"
                    value={qualityRemarks}
                    onChange={(e) => setQualityRemarks(e.target.value)}
                  />
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                      <th className="py-2 pr-3">Material</th>
                      <th className="py-2 pr-3 text-right">Issued at Start</th>
                      <th className="py-2 pr-3 text-right">Consumed / Good Used</th>
                      <th className="py-2 pr-3 text-right">Damaged Pkg</th>
                      <th className="py-2 pr-3 text-right">Wasted (Raw)</th>
                      <th className="py-2 pr-3 text-right">Returned Unused</th>
                      <th className="py-2">Unit</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {run.material_issues.map((mi) => {
                      const inp = consInputs[mi.material_id] ?? {
                        consumed: "0",
                        goodUsed: "0",
                        damaged: "0",
                        returned: "0",
                        wasted: "0",
                        uom: mi.display_uom,
                      };
                      const isPkg = mi.issue_phase === "PACKAGING_PACK";
                      return (
                        <tr key={mi.id}>
                          <td className="py-2.5 pr-3">
                            <div className="font-medium">{mi.material_name}</div>
                            <div className="text-xs text-muted-foreground">
                              Planned: {formatDisplayQty(mi.planned_qty_base, mi.display_uom, mi.display_factor)}
                            </div>
                          </td>
                          <td className="py-2.5 pr-3 text-right tabular-nums text-xs">
                            {formatDisplayQty(mi.issued_qty_base, mi.display_uom, mi.display_factor)}
                          </td>
                          <td className="py-2.5 pr-3 w-32">
                            <Input
                              type="number"
                              step="0.001"
                              min="0"
                              className="h-9 text-right"
                              value={isPkg ? inp.goodUsed : inp.consumed}
                              onChange={(e) =>
                                setConsInputs((prev) => ({
                                  ...prev,
                                  [mi.material_id]: isPkg
                                    ? { ...inp, goodUsed: e.target.value }
                                    : { ...inp, consumed: e.target.value },
                                }))
                              }
                            />
                          </td>
                          <td className="py-2.5 pr-3 w-28">
                            {isPkg ? (
                              <Input
                                type="number"
                                step="1"
                                min="0"
                                className="h-9 text-right"
                                value={inp.damaged}
                                onChange={(e) =>
                                  setConsInputs((prev) => ({
                                    ...prev,
                                    [mi.material_id]: { ...inp, damaged: e.target.value },
                                  }))
                                }
                              />
                            ) : (
                              <span className="text-xs text-muted-foreground block text-right">—</span>
                            )}
                          </td>
                          <td className="py-2.5 pr-3 w-28">
                            {!isPkg ? (
                              <Input
                                type="number"
                                step="0.001"
                                min="0"
                                className="h-9 text-right"
                                value={inp.wasted}
                                onChange={(e) =>
                                  setConsInputs((prev) => ({
                                    ...prev,
                                    [mi.material_id]: { ...inp, wasted: e.target.value },
                                  }))
                                }
                              />
                            ) : (
                              <span className="text-xs text-muted-foreground block text-right">—</span>
                            )}
                          </td>
                          <td className="py-2.5 pr-3 w-28">
                            <Input
                              type="number"
                              step="0.001"
                              min="0"
                              className="h-9 text-right"
                              value={inp.returned}
                              onChange={(e) =>
                                setConsInputs((prev) => ({
                                  ...prev,
                                  [mi.material_id]: { ...inp, returned: e.target.value },
                                }))
                              }
                            />
                          </td>
                          <td className="py-2.5 text-xs font-mono">{inp.uom}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="flex justify-end pt-2 border-t">
                <Button onClick={() => completeMutation.mutate()} disabled={completeMutation.isPending}>
                  <CheckCircle2 className="h-4 w-4" />
                  {completeMutation.isPending ? "Saving..." : "Record Output & Complete Run"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* STAGE 4: COMPLETED -> POSTED (Atomic Production Posting) */}
        {run.status === "COMPLETED" && canOperate && (
          <Card className="border-emerald-300 bg-emerald-50/40">
            <CardHeader>
              <CardTitle className="text-base text-emerald-950 flex items-center gap-2">
                <Send className="h-4 w-4 text-emerald-700" />
                Step 4: Atomic Production Posting &amp; Variance Audit
              </CardTitle>
              <CardDescription className="text-emerald-900">
                All output and consumption numbers are validated. Atomically post to write all residual consumption, unused returns, damaged packaging, finished goods output (+{run.actual_good_output_pkts} saleable pkts), and variances.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex justify-end">
              <Button onClick={() => postMutation.mutate()} disabled={postMutation.isPending}>
                <Send className="h-4 w-4" />
                {postMutation.isPending ? "Posting Atomically..." : "Atomically Post Production Run"}
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Material Consumption Breakdown Table (All States) */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Material Plan vs Issued vs Consumed vs Returns</CardTitle>
            <CardDescription>
              Full five-column traceability distinguishing Planned BOM, Warehouse Issued, Actual Consumed, Damaged/Wasted, and Returned Unused
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                  <th className="py-2 pr-3">Material</th>
                  <th className="py-2 pr-3 text-right">Planned (BOM)</th>
                  <th className="py-2 pr-3 text-right">Issued</th>
                  <th className="py-2 pr-3 text-right">Actual Consumed</th>
                  <th className="py-2 pr-3 text-right">Damaged / Wasted</th>
                  <th className="py-2 pr-3 text-right">Returned Unused</th>
                  <th className="py-2 text-right">FIFO Cost</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {run.material_issues.map((mi) => (
                  <tr key={mi.id}>
                    <td className="py-2.5 pr-3">
                      <div className="font-medium">{mi.material_name}</div>
                      <div className="text-xs font-mono text-muted-foreground">{mi.material_code}</div>
                    </td>
                    <td className="py-2.5 pr-3 text-right tabular-nums">
                      {formatDisplayQty(mi.planned_qty_base, mi.display_uom, mi.display_factor)}
                    </td>
                    <td className="py-2.5 pr-3 text-right tabular-nums">
                      {formatDisplayQty(mi.issued_qty_base, mi.display_uom, mi.display_factor)}
                    </td>
                    <td className="py-2.5 pr-3 text-right font-semibold tabular-nums">
                      {formatDisplayQty(mi.actual_consumed_qty_base, mi.display_uom, mi.display_factor)}
                    </td>
                    <td className="py-2.5 pr-3 text-right tabular-nums text-amber-700">
                      {Number(mi.damaged_qty_base) > 0
                        ? formatDisplayQty(mi.damaged_qty_base, mi.display_uom, mi.display_factor)
                        : Number(mi.wasted_qty_base) > 0
                        ? formatDisplayQty(mi.wasted_qty_base, mi.display_uom, mi.display_factor)
                        : "0"}
                    </td>
                    <td className="py-2.5 pr-3 text-right tabular-nums text-emerald-700">
                      {formatDisplayQty(mi.returned_unused_qty_base, mi.display_uom, mi.display_factor)}
                    </td>
                    <td className="py-2.5 text-right tabular-nums font-medium">
                      {formatInrFromPaisa(mi.cost_absorbed_paisa)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {/* Batch Cost Summary (Phase 9) */}
        {costingQuery.data?.current_summary && (
          <Card className="border-indigo-200 bg-indigo-50/30">
            <CardHeader className="pb-3 flex flex-row items-center justify-between gap-4">
              <div>
                <CardTitle className="text-base">
                  Batch Cost Summary (v{costingQuery.data.current_summary.snapshot_version} ·{" "}
                  {costingQuery.data.current_summary.cost_status})
                </CardTitle>
                <CardDescription>
                  FIFO raw &amp; packaging lots + direct &amp; monthly allocated overheads
                </CardDescription>
              </div>
              <Button asChild variant="outline" size="sm">
                <Link to="/admin/costing">Open Product Costing</Link>
              </Button>
            </CardHeader>
            <CardContent className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs">
              <div className="rounded-lg bg-white border p-2.5">
                <div className="text-muted-foreground">FIFO Raw Material</div>
                <div className="text-sm font-bold tabular-nums mt-0.5">
                  {formatInrFromPaisa(costingQuery.data.current_summary.raw_material_cost_paisa)}
                </div>
              </div>
              <div className="rounded-lg bg-white border p-2.5">
                <div className="text-muted-foreground">Packaging (incl. dmg)</div>
                <div className="text-sm font-bold tabular-nums mt-0.5">
                  {formatInrFromPaisa(costingQuery.data.current_summary.packaging_cost_paisa)}
                </div>
              </div>
              <div className="rounded-lg bg-white border p-2.5">
                <div className="text-muted-foreground">Total Overheads</div>
                <div className="text-sm font-bold tabular-nums mt-0.5">
                  {formatInrFromPaisa(
                    costingQuery.data.current_summary.direct_overhead_paisa +
                      costingQuery.data.current_summary.allocated_overhead_paisa
                  )}
                </div>
              </div>
              <div className="rounded-lg bg-white border p-2.5">
                <div className="text-muted-foreground">Total Batch Cost</div>
                <div className="text-sm font-bold tabular-nums mt-0.5">
                  {formatInrFromPaisa(costingQuery.data.current_summary.total_cost_paisa)}
                </div>
              </div>
              <div className="rounded-lg bg-white border p-2.5">
                <div className="text-muted-foreground">Actual Cost / Pkt</div>
                <div className="text-sm font-bold tabular-nums text-indigo-700 mt-0.5">
                  {costingQuery.data.current_summary.cost_per_packet_paisa != null
                    ? formatInrFromPaisa(costingQuery.data.current_summary.cost_per_packet_paisa)
                    : "—"}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  Std: ₹{(Number(costingQuery.data.current_summary.planned_cost_per_packet_paisa) / 100).toFixed(2)}
                </div>
              </div>
              <div className="rounded-lg bg-white border p-2.5">
                <div className="text-muted-foreground">Gross Margin / Pkt</div>
                <div className="text-sm font-bold tabular-nums text-emerald-700 mt-0.5">
                  {costingQuery.data.current_summary.gross_margin_per_pkt_paisa != null
                    ? formatInrFromPaisa(costingQuery.data.current_summary.gross_margin_per_pkt_paisa)
                    : "—"}
                </div>
                {costingQuery.data.current_summary.gross_margin_pct != null && (
                  <div className="text-[11px] text-emerald-700">
                    {costingQuery.data.current_summary.gross_margin_pct}%
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Variances Table */}
        {run.variances.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-600" />
                Planned vs Actual Variance Analysis
              </CardTitle>
              <CardDescription>
                Auditable variance calculations preserving formulas, baseline denominators, and tolerance evaluation
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                    <th className="py-2 pr-3">Scope / Item</th>
                    <th className="py-2 pr-3 text-right">Standard / Baseline</th>
                    <th className="py-2 pr-3 text-right">Actual</th>
                    <th className="py-2 pr-3 text-right">Variance %</th>
                    <th className="py-2 pr-3">Flag</th>
                    <th className="py-2">Formula Breakdown</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {run.variances.map((v) => (
                    <tr key={v.id} className={v.is_flagged ? "bg-amber-50/50" : ""}>
                      <td className="py-2.5 pr-3">
                        <div className="font-semibold">
                          {v.material_name ?? "Packet Yield (Finished Goods)"}
                        </div>
                        <div className="text-[11px] font-mono text-muted-foreground">
                          {v.variance_scope}
                        </div>
                      </td>
                      <td className="py-2.5 pr-3 text-right tabular-nums">
                        {formatDisplayQty(v.planned_qty_base, v.display_uom, v.display_factor)}
                      </td>
                      <td className="py-2.5 pr-3 text-right font-semibold tabular-nums">
                        {formatDisplayQty(v.actual_qty_base, v.display_uom, v.display_factor)}
                      </td>
                      <td className="py-2.5 pr-3 text-right font-mono font-bold tabular-nums">
                        {v.variance_pct !== null
                          ? `${Number(v.variance_pct) > 0 ? "+" : ""}${v.variance_pct}%`
                          : "—"}
                      </td>
                      <td className="py-2.5 pr-3">
                        {v.is_flagged ? (
                          <Badge variant="warning">Flagged (&gt; {v.tolerance_pct}%)</Badge>
                        ) : (
                          <Badge variant="secondary">OK</Badge>
                        )}
                      </td>
                      <td className="py-2.5 text-xs text-muted-foreground">{v.formula_explanation}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}

        {/* Linked Inventory Ledger Movements */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-primary" />
              Linked Inventory Ledger Movements ({movements.length})
            </CardTitle>
            <CardDescription>
              Every stock mutation triggered by {run.run_number} linked via PostgreSQL FK to this run
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                  <th className="py-2 pr-3">Time</th>
                  <th className="py-2 pr-3">Item</th>
                  <th className="py-2 pr-3">Movement Type</th>
                  <th className="py-2 pr-3 text-right">Base Delta</th>
                  <th className="py-2 pr-3 text-right">FIFO Cost</th>
                  <th className="py-2">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {movements.map((mov) => {
                  const delta = toNumber(mov.signed_qty_base);
                  return (
                    <tr key={mov.id}>
                      <td className="py-2 pr-3 text-xs text-muted-foreground whitespace-nowrap">
                        {formatDateTimeIst(mov.occurred_at)}
                      </td>
                      <td className="py-2 pr-3 font-medium">{mov.item_name}</td>
                      <td className="py-2 pr-3">
                        <Badge variant={delta > 0 ? "success" : "warning"}>{mov.movement_type}</Badge>
                      </td>
                      <td
                        className={`py-2 pr-3 text-right font-mono text-xs font-bold tabular-nums ${
                          delta > 0 ? "text-emerald-700" : "text-red-700"
                        }`}
                      >
                        {delta > 0 ? "+" : ""}
                        {formatBaseQty(mov.signed_qty_base, mov.base_uom)}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums text-xs">
                        {formatInrFromPaisa(mov.total_cost_paisa)}
                      </td>
                      <td className="py-2 text-xs text-muted-foreground">{mov.notes ?? "—"}</td>
                    </tr>
                  );
                })}
                {movements.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-muted-foreground">
                      No inventory movements posted for this run yet.
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

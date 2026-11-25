import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  Layers,
  Package,
  Plus,
} from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatOrderDate } from "@/lib/money";
import { formatDisplayQty } from "@/lib/units";

const STATUS_TABS = [
  { key: "", label: "All Runs" },
  { key: "DRAFT", label: "Draft" },
  { key: "PLANNED", label: "Planned" },
  { key: "IN_PROGRESS", label: "In Progress" },
  { key: "COMPLETED", label: "Completed" },
  { key: "POSTED", label: "Posted" },
  { key: "CANCELLED", label: "Cancelled" },
];

export function AdminProductionDashboardPage() {
  const { user } = useAuth();
  const canOperate = user?.role_code === "FACTORY_ADMIN" || user?.role_code === "PRODUCTION_SUPERVISOR";
  const canAckAlert = canOperate || user?.role_code === "OWNER";
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [statusFilter, setStatusFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [packSizeId, setPackSizeId] = useState("");
  const [batchMult, setBatchMult] = useState("1.0");
  const [runDate, setRunDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [notes, setNotes] = useState("");
  const [planImmediately, setPlanImmediately] = useState(true);
  const [banner, setBanner] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  const dashboardQuery = useQuery({
    queryKey: ["production-dashboard", statusFilter],
    queryFn: () => api.getProductionDashboard({ status: statusFilter || undefined }),
    refetchInterval: 15_000,
  });

  const catalogQuery = useQuery({
    queryKey: ["production-catalog"],
    queryFn: () => api.getProductionCatalog(),
  });

  const activePackId = Number(packSizeId || catalogQuery.data?.pack_sizes.find((p) => p.has_active_bom)?.id || 0);

  const previewQuery = useQuery({
    queryKey: ["plan-preview-calc", activePackId, batchMult],
    queryFn: () =>
      api.calculateBom({
        pack_size_id: activePackId,
        batch_multiplier: Number(batchMult) > 0 ? batchMult : "1.0",
      }),
    enabled: Boolean(showCreate && activePackId > 0),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      api.createProductionRun({
        pack_size_id: activePackId,
        batch_multiplier: batchMult,
        run_date: runDate || null,
        notes: notes.trim() || null,
        plan_immediately: planImmediately,
      }),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["production-dashboard"] });
      setShowCreate(false);
      navigate(`/admin/production/runs/${run.id}`);
    },
    onError: (err) => {
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Failed to create production run.",
      });
    },
  });

  const ackMutation = useMutation({
    mutationFn: (alertId: number) => api.acknowledgeVarianceAlert(alertId, "Reviewed on production desk"),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["production-dashboard"] });
      setBanner({ kind: "success", msg: "Variance alert acknowledged." });
    },
  });

  const dash = dashboardQuery.data;
  const packOptions = (catalogQuery.data?.pack_sizes ?? []).filter((p) => p.has_active_bom);

  return (
    <DesktopAdminLayout
      title="Production Dashboard & Planning"
      subtitle="Monitor active batches, material shortages, good packet output, wastage, and tolerance alerts"
      actions={
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to="/admin/production/boms">
              <Layers className="h-4 w-4" />
              BOM &amp; Calculator
            </Link>
          </Button>
          {canOperate && (
            <Button
              onClick={() => {
                if (!packSizeId && packOptions[0]) setPackSizeId(String(packOptions[0].id));
                setShowCreate((s) => !s);
              }}
            >
              <Plus className="h-4 w-4" />
              New Production Plan
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

        {/* KPI Cards */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardContent className="p-5 flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Runs Pipeline
                </p>
                <p className="mt-2 text-2xl font-bold tabular-nums">
                  {(dash?.planned_count ?? 0) + (dash?.in_progress_count ?? 0)} Active
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {dash?.draft_count ?? 0} Draft · {dash?.planned_count ?? 0} Planned ·{" "}
                  {dash?.in_progress_count ?? 0} In Progress · {dash?.posted_count ?? 0} Posted
                </p>
              </div>
              <Activity className="h-5 w-5 text-primary" />
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5 flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Good Output Produced
                </p>
                <p className="mt-2 text-2xl font-bold tabular-nums text-emerald-700">
                  {dash?.total_good_output_pkts ?? 0} pkts
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  vs {dash?.total_expected_output_pkts ?? 0} expected · {dash?.total_rejected_output_pkts ?? 0} rejected
                </p>
              </div>
              <Package className="h-5 w-5 text-emerald-600" />
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5 flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Wastage &amp; Damaged Pkg
                </p>
                <p className="mt-2 text-2xl font-bold tabular-nums text-amber-700">
                  {Number(dash?.total_damaged_packaging_units ?? 0)} pcs
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Tracked separately from finished output
                </p>
              </div>
              <ClipboardList className="h-5 w-5 text-amber-600" />
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5 flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Open Variance Alerts
                </p>
                <p className="mt-2 text-2xl font-bold tabular-nums text-red-700">
                  {dash?.open_alerts_count ?? 0}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {dash?.flagged_variance_count ?? 0} runs flagged (&gt; 3% tolerance)
                </p>
              </div>
              <AlertTriangle className="h-5 w-5 text-red-600" />
            </CardContent>
          </Card>
        </div>

        {/* Plan New Production Run Modal */}
        {showCreate && (
          <Card className="border-primary/40">
            <CardHeader>
              <CardTitle className="text-base">Plan New Production Run</CardTitle>
              <CardDescription>
                Select product pack size and batch multiplier. Active BOM version is automatically pinned.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-4">
                <div className="space-y-1">
                  <label className="text-xs font-semibold">Finished Product Pack Size</label>
                  <select
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    value={activePackId}
                    onChange={(e) => setPackSizeId(e.target.value)}
                  >
                    {packOptions.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.display_name} (BOM v{p.active_bom_version_no})
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold">Batch Multiplier</label>
                  <Input
                    type="number"
                    step="0.25"
                    min="0.1"
                    value={batchMult}
                    onChange={(e) => setBatchMult(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold">Planned Run Date</label>
                  <Input type="date" value={runDate} onChange={(e) => setRunDate(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold">Notes</label>
                  <Input
                    placeholder="Shift / supervisor notes"
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                  />
                </div>
              </div>

              {previewQuery.data && (
                <div className="rounded-lg border bg-secondary/30 p-3 space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                    <span>
                      Using <strong>BOM v{previewQuery.data.version_no}</strong> · Expected Output:{" "}
                      <strong>{previewQuery.data.expected_output_pkts} packets</strong>
                    </span>
                    {previewQuery.data.has_shortages ? (
                      <Badge variant="destructive">Stock Shortages Exist (Cannot Start Yet)</Badge>
                    ) : (
                      <Badge variant="success">Materials Available in Stock</Badge>
                    )}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-3 text-xs">
                    {previewQuery.data.requirements.map((r) => (
                      <div
                        key={r.material_id}
                        className={`rounded border bg-card px-2.5 py-1.5 flex justify-between ${
                          r.is_shortage ? "border-red-300 text-red-800" : ""
                        }`}
                      >
                        <span>{r.material_name}</span>
                        <strong className="tabular-nums">
                          {formatDisplayQty(r.standard_qty_base, r.display_uom, r.display_factor)}
                          {r.is_shortage && " (SHORT)"}
                        </strong>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t">
                <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
                  <input
                    type="checkbox"
                    checked={planImmediately}
                    onChange={(e) => setPlanImmediately(e.target.checked)}
                    className="h-4 w-4"
                  />
                  Mark as PLANNED immediately (uncheck to save as DRAFT first)
                </label>
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => setShowCreate(false)}>
                    Cancel
                  </Button>
                  <Button onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
                    {createMutation.isPending ? "Creating..." : "Create Production Run"}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Open Variance Alerts & Planned Shortages */}
        {((dash?.open_alerts.length ?? 0) > 0 || (dash?.upcoming_shortages.length ?? 0) > 0) && (
          <div className="grid gap-4 lg:grid-cols-2">
            {(dash?.open_alerts.length ?? 0) > 0 && (
              <Card className="border-amber-300">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2 text-amber-900">
                    <AlertTriangle className="h-4 w-4 text-amber-600" />
                    Active Variance Alerts (&gt; 3% Tolerance)
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {dash!.open_alerts.map((al) => (
                    <div
                      key={al.id}
                      className="rounded-lg border border-amber-200 bg-amber-50/70 p-2.5 flex items-start justify-between gap-2 text-xs"
                    >
                      <div>
                        <Link
                          to={`/admin/production/runs/${al.production_run_id}`}
                          className="font-semibold text-primary hover:underline"
                        >
                          {al.run_number}
                        </Link>{" "}
                        <Badge variant="warning" className="ml-1 text-[10px]">
                          {al.alert_type}
                        </Badge>
                        <p className="mt-1 text-amber-950">{al.message}</p>
                      </div>
                      {canAckAlert && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => ackMutation.mutate(al.id)}
                          disabled={ackMutation.isPending}
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Acknowledge
                        </Button>
                      )}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {(dash?.upcoming_shortages.length ?? 0) > 0 && (
              <Card className="border-red-200">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2 text-red-900">
                    <AlertTriangle className="h-4 w-4 text-red-600" />
                    Planned Run Material Shortages
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {dash!.upcoming_shortages.map((sh) => (
                    <div
                      key={sh.material_id}
                      className="rounded-lg border border-red-200 bg-red-50/60 px-3 py-2 flex items-center justify-between text-xs"
                    >
                      <div>
                        <span className="font-semibold">{sh.material_name}</span>{" "}
                        <span className="font-mono text-muted-foreground">({sh.material_code})</span>
                      </div>
                      <div className="tabular-nums text-red-800 font-semibold">
                        Need {formatDisplayQty(sh.required_qty_base, sh.display_uom, sh.display_factor)} ·
                        Short {formatDisplayQty(sh.shortage_qty_base, sh.display_uom, sh.display_factor)}
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {/* Runs Filter Tabs & Table */}
        <div className="flex flex-wrap gap-1.5">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setStatusFilter(tab.key)}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
                statusFilter === tab.key
                  ? "bg-primary text-primary-foreground"
                  : "bg-card border text-muted-foreground hover:text-foreground"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Production History &amp; Execution Queue</CardTitle>
            <CardDescription>
              Open any run to issue materials, record quality &amp; output, or execute atomic inventory posting
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="py-2 pr-3">Run # / Date</th>
                  <th className="py-2 pr-3">Product &amp; BOM</th>
                  <th className="py-2 pr-3 text-right">Scale / Expected</th>
                  <th className="py-2 pr-3 text-right">Good Output</th>
                  <th className="py-2 pr-3 text-right">Damaged Pkg</th>
                  <th className="py-2 pr-3">Variances</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {(dash?.runs ?? []).map((r) => (
                  <tr key={r.id} className="hover:bg-secondary/30">
                    <td className="py-3 pr-3">
                      <Link
                        to={`/admin/production/runs/${r.id}`}
                        className="font-mono font-bold text-primary hover:underline"
                      >
                        {r.run_number}
                      </Link>
                      <div className="text-xs text-muted-foreground">{formatOrderDate(r.run_date)}</div>
                    </td>
                    <td className="py-3 pr-3">
                      <div className="font-medium">{r.display_name}</div>
                      <div className="text-xs text-muted-foreground">
                        BOM v{r.version_no} · {r.supervisor_name}
                      </div>
                    </td>
                    <td className="py-3 pr-3 text-right tabular-nums text-xs">
                      <div>{Number(r.batch_multiplier)}× batch</div>
                      <div className="text-muted-foreground">{r.expected_output_pkts} pkts</div>
                    </td>
                    <td className="py-3 pr-3 text-right tabular-nums">
                      <div className="font-bold text-emerald-700">{r.actual_good_output_pkts} pkts</div>
                      {r.rejected_output_pkts > 0 && (
                        <div className="text-[11px] text-red-700">{r.rejected_output_pkts} rejected</div>
                      )}
                    </td>
                    <td className="py-3 pr-3 text-right tabular-nums text-xs">
                      {Number(r.damaged_packaging_qty) > 0 ? `${Number(r.damaged_packaging_qty)} pcs` : "0"}
                    </td>
                    <td className="py-3 pr-3">
                      {r.has_flagged_variance ? (
                        <Badge variant="warning">Flagged (&gt; 3%)</Badge>
                      ) : r.status === "POSTED" ? (
                        <Badge variant="secondary">Within Tol.</Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="py-3 pr-3">
                      <StatusBadge status={r.status} />
                    </td>
                    <td className="py-3 text-right">
                      <Button size="sm" variant="outline" asChild>
                        <Link to={`/admin/production/runs/${r.id}`}>
                          Open
                          <ArrowRight className="h-3.5 w-3.5" />
                        </Link>
                      </Button>
                    </td>
                  </tr>
                ))}
                {(dash?.runs ?? []).length === 0 && (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-muted-foreground">
                      No production runs recorded yet. Click "New Production Plan" to schedule a batch.
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

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, Eye, ShieldAlert, Users } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { auditApi, type AuditLogEntry } from "@/lib/api";
import { formatDateTimeIst } from "@/lib/money";

export function AdminAuditExplorerPage() {
  const [tab, setTab] = useState<"logs" | "summary" | "activity">("logs");
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState("");
  const [schemaFilter, setSchemaFilter] = useState("");
  const [corrFilter, setCorrFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [search, setSearch] = useState("");
  const [inspectRow, setInspectRow] = useState<AuditLogEntry | null>(null);
  const [exportErr, setExportErr] = useState<string | null>(null);

  const logsQuery = useQuery({
    queryKey: ["audit-logs", page, actionFilter, schemaFilter, corrFilter, dateFrom, dateTo, search],
    queryFn: () =>
      auditApi.getLogs({
        action: actionFilter || undefined,
        entitySchema: schemaFilter || undefined,
        correlationRef: corrFilter || undefined,
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        search: search || undefined,
        page,
        pageSize: 25,
      }),
    enabled: tab === "logs",
  });

  const summaryQuery = useQuery({
    queryKey: ["audit-summary", dateFrom, dateTo],
    queryFn: () =>
      auditApi.getSummary({
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
      }),
  });

  const activityQuery = useQuery({
    queryKey: ["audit-user-activity", dateFrom, dateTo],
    queryFn: () =>
      auditApi.getUserActivity({
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
      }),
    enabled: tab === "activity",
  });

  const handleExportCsv = async () => {
    setExportErr(null);
    try {
      const blob = await auditApi.exportCsvBlob({
        action: actionFilter || undefined,
        entitySchema: schemaFilter || undefined,
        correlationRef: corrFilter || undefined,
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        search: search || undefined,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "audit_logs_export.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setExportErr(e instanceof Error ? e.message : "CSV export failed.");
    }
  };

  const sum = summaryQuery.data;

  return (
    <DesktopAdminLayout
      title="Centralized Audit Trail Explorer"
      subtitle="Immutable append-only operational, financial, GST, reconciliation & security audit trail (credentials auto-redacted)"
      actions={
        <Button size="sm" variant="outline" onClick={handleExportCsv}>
          <Download className="h-4 w-4" />
          Export Audit CSV
        </Button>
      }
    >
      <div className="space-y-6">
        {sum && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <Card>
              <CardContent className="p-4">
                <div className="text-xs font-semibold uppercase text-muted-foreground">Total Events</div>
                <div className="mt-1 text-2xl font-bold tabular-nums">{sum.total_events}</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="text-xs font-semibold uppercase text-muted-foreground">Security Events</div>
                <div className="mt-1 text-2xl font-bold tabular-nums">{sum.security_events_count}</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="text-xs font-semibold uppercase text-muted-foreground">Failed Logins</div>
                <div className="mt-1 text-2xl font-bold tabular-nums text-amber-700">
                  {sum.login_failures_count}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="text-xs font-semibold uppercase text-muted-foreground">Access Denied (403)</div>
                <div className="mt-1 text-2xl font-bold tabular-nums text-red-700">
                  {sum.access_denied_count}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-4">
                <div className="text-xs font-semibold uppercase text-muted-foreground">Active Actors</div>
                <div className="mt-1 text-2xl font-bold tabular-nums">{sum.distinct_active_actors}</div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* Navigation Tabs */}
        <div className="flex flex-wrap gap-2 border-b pb-3">
          {[
            ["logs", "Audit Events Log"],
            ["summary", "Summary & Breakdown"],
            ["activity", "User Activity Report"],
          ].map(([k, label]) => (
            <Button
              key={k}
              size="sm"
              variant={tab === k ? "default" : "outline"}
              onClick={() => setTab(k as "logs" | "summary" | "activity")}
            >
              {label}
            </Button>
          ))}
        </div>

        {/* Shared Date & Filter Controls */}
        <Card>
          <CardContent className="p-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-6 items-end">
            <div>
              <label className="text-xs font-semibold text-muted-foreground">From Date</label>
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => {
                  setDateFrom(e.target.value);
                  setPage(1);
                }}
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted-foreground">To Date</label>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => {
                  setDateTo(e.target.value);
                  setPage(1);
                }}
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Module Schema</label>
              <select
                value={schemaFilter}
                onChange={(e) => {
                  setSchemaFilter(e.target.value);
                  setPage(1);
                }}
                className="mt-1 flex h-11 w-full rounded-lg border border-input bg-card px-3 text-sm"
              >
                <option value="">All Schemas</option>
                <option value="iam">iam (Auth/Users)</option>
                <option value="sales">sales (Orders)</option>
                <option value="purchasing">purchasing (PO/GRN)</option>
                <option value="inventory">inventory (Ledger/Adj)</option>
                <option value="production">production (BOM/Runs)</option>
                <option value="billing">billing (Invoice/CN/Dispatch)</option>
                <option value="finance">finance (Payments/AR)</option>
                <option value="costing">costing (Overheads)</option>
                <option value="audit">audit (Recon/Alerts)</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Action Code</label>
              <Input
                placeholder="e.g. LOGIN_FAILED"
                value={actionFilter}
                onChange={(e) => {
                  setActionFilter(e.target.value);
                  setPage(1);
                }}
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Correlation Ref</label>
              <Input
                placeholder="REQ-... or REC/..."
                value={corrFilter}
                onChange={(e) => {
                  setCorrFilter(e.target.value);
                  setPage(1);
                }}
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Search Table / Reason</label>
              <Input
                placeholder="Search keyword..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="mt-1"
              />
            </div>
          </CardContent>
        </Card>

        {exportErr && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {exportErr}
          </div>
        )}

        {tab === "logs" && (
          <Card>
            <CardHeader>
              <CardTitle>Audit Events</CardTitle>
              <CardDescription>
                {logsQuery.data ? `Showing ${logsQuery.data.items.length} of ${logsQuery.data.total} immutable audit events` : "Loading..."}
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                    <th className="py-2 pr-3">Timestamp (IST)</th>
                    <th className="py-2 pr-3">Actor &amp; Role</th>
                    <th className="py-2 pr-3">Action</th>
                    <th className="py-2 pr-3">Entity</th>
                    <th className="py-2 pr-3">Correlation Ref</th>
                    <th className="py-2 pr-3">Reason / Remarks</th>
                    <th className="py-2 text-right">State</th>
                  </tr>
                </thead>
                <tbody>
                  {(logsQuery.data?.items ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-muted-foreground">
                        No audit events match the active filters.
                      </td>
                    </tr>
                  ) : (
                    logsQuery.data!.items.map((row) => (
                      <tr key={row.id} className="border-b last:border-b-0 hover:bg-secondary/30">
                        <td className="py-2.5 pr-3 whitespace-nowrap text-xs">
                          {formatDateTimeIst(row.occurred_at)}
                        </td>
                        <td className="py-2.5 pr-3">
                          <div className="font-medium">{row.actor_full_name || row.actor_username || "Anonymous"}</div>
                          <div className="text-xs text-muted-foreground">{row.actor_role}</div>
                        </td>
                        <td className="py-2.5 pr-3">
                          <span className="inline-block rounded bg-secondary px-2 py-0.5 font-mono text-xs font-semibold">
                            {row.action}
                          </span>
                        </td>
                        <td className="py-2.5 pr-3 text-xs font-mono">
                          {row.entity_schema}.{row.entity_table} #{row.entity_id}
                        </td>
                        <td className="py-2.5 pr-3 text-xs font-mono text-muted-foreground">
                          {row.correlation_ref || "—"}
                        </td>
                        <td className="py-2.5 pr-3 max-w-xs truncate text-xs text-muted-foreground">
                          {row.reason || "—"}
                        </td>
                        <td className="py-2.5 text-right">
                          <Button size="sm" variant="outline" onClick={() => setInspectRow(row)}>
                            <Eye className="h-3.5 w-3.5" />
                            Inspect
                          </Button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>

              {logsQuery.data && logsQuery.data.total_pages > 1 && (
                <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
                  <span>
                    Page {logsQuery.data.page} of {logsQuery.data.total_pages}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                    >
                      Previous
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={page >= logsQuery.data.total_pages}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {tab === "summary" && sum && (
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShieldAlert className="h-4 w-4 text-primary" />
                  Events by Module Schema
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2.5 text-sm">
                {sum.by_schema.map((s) => (
                  <div key={s.entity_schema} className="flex items-center justify-between border-b pb-1.5 last:border-b-0">
                    <span className="font-mono font-semibold">{s.entity_schema}</span>
                    <span className="font-bold tabular-nums">{s.count}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Top Recorded Event Types</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2.5 text-sm">
                {sum.top_actions.map((a) => (
                  <div key={a.action} className="flex items-center justify-between border-b pb-1.5 last:border-b-0">
                    <span className="font-mono text-xs font-semibold">{a.action}</span>
                    <span className="font-bold tabular-nums">{a.count}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        )}

        {tab === "activity" && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-4 w-4 text-primary" />
                User Activity &amp; Security Events Report
              </CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                    <th className="py-2">User</th>
                    <th className="py-2">Role</th>
                    <th className="py-2">Status</th>
                    <th className="py-2 text-right">Logins</th>
                    <th className="py-2 text-right">Failed</th>
                    <th className="py-2 text-right">Denied</th>
                    <th className="py-2 text-right">Business Ops</th>
                    <th className="py-2">Last Login (IST)</th>
                  </tr>
                </thead>
                <tbody>
                  {(activityQuery.data ?? []).map((u) => (
                    <tr key={u.user_id} className="border-b last:border-b-0">
                      <td className="py-2.5">
                        <div className="font-semibold">{u.full_name}</div>
                        <div className="text-xs text-muted-foreground font-mono">@{u.username}</div>
                      </td>
                      <td className="py-2.5 text-xs">{u.role_name}</td>
                      <td className="py-2.5">
                        <StatusBadge status={u.is_active ? "ACTIVE" : "CANCELLED"} />
                      </td>
                      <td className="py-2.5 text-right tabular-nums">{u.login_success_count}</td>
                      <td className="py-2.5 text-right tabular-nums text-amber-700">{u.login_failed_count}</td>
                      <td className="py-2.5 text-right tabular-nums text-red-700">{u.access_denied_count}</td>
                      <td className="py-2.5 text-right tabular-nums font-semibold">{u.business_events_count}</td>
                      <td className="py-2.5 text-xs text-muted-foreground">
                        {formatDateTimeIst(u.last_login_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}

        {/* Payload Detail Modal */}
        {inspectRow && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <Card className="w-full max-w-2xl max-h-[85vh] overflow-y-auto">
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle className="font-mono text-base">{inspectRow.action} (#{inspectRow.id})</CardTitle>
                  <CardDescription>
                    {inspectRow.entity_schema}.{inspectRow.entity_table} #{inspectRow.entity_id} ·{" "}
                    {formatDateTimeIst(inspectRow.occurred_at)}
                  </CardDescription>
                </div>
                <Button size="sm" variant="outline" onClick={() => setInspectRow(null)}>
                  Close
                </Button>
              </CardHeader>
              <CardContent className="space-y-4 text-xs">
                <div>
                  <span className="font-semibold text-muted-foreground">Actor: </span>
                  {inspectRow.actor_full_name || inspectRow.actor_username || "Anonymous"} ({inspectRow.actor_role})
                  {" · "}
                  <span className="font-semibold text-muted-foreground">Correlation Ref: </span>
                  <span className="font-mono">{inspectRow.correlation_ref || "None"}</span>
                </div>
                {inspectRow.reason && (
                  <div className="rounded bg-secondary p-2.5">
                    <span className="font-semibold">Reason / Notes: </span>
                    {inspectRow.reason}
                  </div>
                )}
                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <div className="mb-1 font-semibold text-muted-foreground">Previous State (Before)</div>
                    <pre className="rounded-lg border bg-secondary/40 p-2.5 overflow-x-auto text-[11px]">
                      {inspectRow.before_state ? JSON.stringify(inspectRow.before_state, null, 2) : "null"}
                    </pre>
                  </div>
                  <div>
                    <div className="mb-1 font-semibold text-muted-foreground">New State (After)</div>
                    <pre className="rounded-lg border bg-secondary/40 p-2.5 overflow-x-auto text-[11px]">
                      {inspectRow.after_state ? JSON.stringify(inspectRow.after_state, null, 2) : "null"}
                    </pre>
                  </div>
                </div>
                {inspectRow.metadata_json && (
                  <div>
                    <div className="mb-1 font-semibold text-muted-foreground">Sanitized Metadata</div>
                    <pre className="rounded-lg border bg-secondary/40 p-2.5 overflow-x-auto text-[11px]">
                      {JSON.stringify(inspectRow.metadata_json, null, 2)}
                    </pre>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </DesktopAdminLayout>
  );
}

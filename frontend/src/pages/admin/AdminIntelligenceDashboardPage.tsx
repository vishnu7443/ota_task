import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  BarChart3,
  Boxes,
  Download,
  Factory,
  IndianRupee,
  ShieldAlert,
  TrendingUp,
} from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { intelApi } from "@/lib/api";
import { formatInrFromPaisa, formatOrderDate } from "@/lib/money";

export function AdminIntelligenceDashboardPage() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [asOfDate, setAsOfDate] = useState("");
  const [exportErr, setExportErr] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["intel-dashboard", dateFrom, dateTo, asOfDate],
    queryFn: () =>
      intelApi.getDashboard({
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        asOfDate: asOfDate || undefined,
      }),
    refetchInterval: 20_000,
  });

  const handleDownloadCsv = async () => {
    setExportErr(null);
    try {
      const blob = await intelApi.exportCsvBlob({
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        asOfDate: asOfDate || undefined,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "management_intelligence_report.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setExportErr(e instanceof Error ? e.message : "CSV download failed.");
    }
  };

  const d = query.data;

  const ageingMax = d
    ? Math.max(
        1,
        d.finance.not_due_receivables_paisa,
        d.finance.bucket_0_30_paisa,
        d.finance.bucket_31_60_paisa,
        d.finance.bucket_61_90_paisa,
        d.finance.bucket_90_plus_paisa
      )
    : 1;

  return (
    <DesktopAdminLayout
      title="Management Intelligence"
      subtitle="Unified executive visibility across Sales, GST Revenue, FIFO Stock Valuation, Batch Costing, AR Ageing & Reconciliation Governance"
      actions={
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={handleDownloadCsv}>
            <Download className="h-4 w-4" />
            Export Executive CSV
          </Button>
          <Button asChild size="sm">
            <Link to="/admin/reconciliation">Reconciliation Console</Link>
          </Button>
        </div>
      }
    >
      <div className="space-y-6">
        <Card>
          <CardContent className="p-4 flex flex-wrap items-end gap-4">
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Period Start</label>
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Period End</label>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted-foreground">Ageing As Of</label>
              <Input
                type="date"
                value={asOfDate}
                onChange={(e) => setAsOfDate(e.target.value)}
                className="mt-1"
              />
            </div>
            {(dateFrom || dateTo || asOfDate) && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setDateFrom("");
                  setDateTo("");
                  setAsOfDate("");
                }}
              >
                Reset FY Default
              </Button>
            )}
            {d && (
              <div className="ml-auto text-xs text-muted-foreground">
                Showing FY <span className="font-semibold text-foreground">{d.financial_year}</span> (
                {formatOrderDate(d.period_start)} – {formatOrderDate(d.period_end)})
              </div>
            )}
          </CardContent>
        </Card>

        {exportErr && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {exportErr}
          </div>
        )}

        {d && (
          <>
            {d.watchlist.length > 0 && (
              <Card className="border-amber-300 bg-amber-50/40">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-amber-900">
                    <ShieldAlert className="h-4 w-4 text-amber-700" />
                    Executive Action Watchlist ({d.watchlist.length})
                  </CardTitle>
                  <CardDescription>
                    Live exceptions &amp; operational controls requiring attention
                  </CardDescription>
                </CardHeader>
                <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {d.watchlist.map((w, idx) => (
                    <Link
                      key={`${w.category}-${idx}`}
                      to={w.link_path}
                      className="rounded-lg border bg-card p-3 hover:border-primary/50 transition-colors"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                          {w.category}
                        </span>
                        <StatusBadge status={w.severity} />
                      </div>
                      <div className="mt-1.5 text-sm font-semibold text-foreground">{w.title}</div>
                      <div className="mt-0.5 text-xs text-muted-foreground">{w.detail}</div>
                    </Link>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Top 6 KPI Summary */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <span>Net Sales (Excl. GST)</span>
                    <IndianRupee className="h-4 w-4 text-primary" />
                  </div>
                  <div className="mt-1.5 text-2xl font-bold tabular-nums">
                    {formatInrFromPaisa(d.sales.net_sales_excl_gst_paisa)}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    GST Collected: {formatInrFromPaisa(d.sales.gst_collected_paisa)} ·{" "}
                    {d.sales.invoice_count} Invoices · {d.sales.credit_note_count} CNs
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <span>Gross Profit &amp; Margin</span>
                    <TrendingUp className="h-4 w-4 text-emerald-700" />
                  </div>
                  <div className="mt-1.5 text-2xl font-bold tabular-nums text-emerald-700">
                    {formatInrFromPaisa(d.finance.gross_profit_paisa)}{" "}
                    <span className="text-base font-semibold">({d.finance.gross_margin_pct}%)</span>
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    COGS: {formatInrFromPaisa(d.finance.total_cogs_paisa)} (Excl. SG&amp;A opex)
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <span>Net Cash Collected</span>
                    <IndianRupee className="h-4 w-4 text-emerald-700" />
                  </div>
                  <div className="mt-1.5 text-2xl font-bold tabular-nums">
                    {formatInrFromPaisa(d.finance.net_cash_collected_paisa)}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Received: {formatInrFromPaisa(d.finance.payments_received_paisa)} · Advances:{" "}
                    {formatInrFromPaisa(d.finance.customer_advances_paisa)}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <span>Receivables &amp; Overdue</span>
                    <AlertTriangle className="h-4 w-4 text-amber-600" />
                  </div>
                  <div className="mt-1.5 text-2xl font-bold tabular-nums">
                    {formatInrFromPaisa(d.finance.total_outstanding_receivables_paisa)}
                  </div>
                  <div className="text-xs text-red-700 font-medium mt-1">
                    Overdue: {formatInrFromPaisa(d.finance.overdue_receivables_paisa)}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <span>Inventory Valuation (FIFO Lots)</span>
                    <Boxes className="h-4 w-4 text-primary" />
                  </div>
                  <div className="mt-1.5 text-2xl font-bold tabular-nums">
                    {formatInrFromPaisa(d.inventory.total_stock_valuation_paisa)}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {d.inventory.total_items} SKUs · {d.inventory.low_stock_count} Low Stock Alerts
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <span>Production Yield Efficiency</span>
                    <Factory className="h-4 w-4 text-primary" />
                  </div>
                  <div className="mt-1.5 text-2xl font-bold tabular-nums">
                    {d.production.yield_efficiency_pct}%
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {d.production.actual_good_output_pkts} good / {d.production.rejected_output_pkts} rejected pkts · Batch Cost:{" "}
                    {formatInrFromPaisa(d.production.total_batch_cost_paisa)}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Middle Grid: Order Pipeline, AR Ageing Bars & Operations Queues */}
            <div className="grid gap-6 lg:grid-cols-3">
              <Card>
                <CardHeader>
                  <CardTitle>Order Pipeline ({d.sales.order_pipeline.total_orders})</CardTitle>
                  <CardDescription>Sales order status distribution in period</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2.5 text-sm">
                  {[
                    ["Pending Verification", d.sales.order_pipeline.pending_verification, "text-amber-700"],
                    ["Approved (Awaiting Invoice)", d.sales.order_pipeline.approved, "text-primary"],
                    ["Invoiced", d.sales.order_pipeline.invoiced, "text-blue-700"],
                    ["Dispatched / Partial", d.sales.order_pipeline.dispatched_or_partial, "text-emerald-700"],
                    ["Rejected / Cancelled", d.sales.order_pipeline.rejected_or_cancelled, "text-muted-foreground"],
                  ].map(([label, val, cls]) => (
                    <div key={String(label)} className="flex items-center justify-between border-b pb-1.5 last:border-b-0">
                      <span className="text-muted-foreground">{label}</span>
                      <span className={`font-bold tabular-nums ${cls}`}>{val}</span>
                    </div>
                  ))}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Receivables Ageing Breakdown</CardTitle>
                  <CardDescription>Strictly evaluated by invoice due_date</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3 text-xs">
                  {[
                    ["Not Due", d.finance.not_due_receivables_paisa, "bg-emerald-500"],
                    ["1–30 Days", d.finance.bucket_0_30_paisa, "bg-amber-400"],
                    ["31–60 Days", d.finance.bucket_31_60_paisa, "bg-amber-600"],
                    ["61–90 Days", d.finance.bucket_61_90_paisa, "bg-red-500"],
                    ["> 90 Days", d.finance.bucket_90_plus_paisa, "bg-red-700"],
                  ].map(([label, paisa, color]) => {
                    const num = Number(paisa);
                    const width = Math.max(num > 0 ? 4 : 0, Math.round((num / ageingMax) * 100));
                    return (
                      <div key={String(label)}>
                        <div className="flex justify-between mb-1">
                          <span className="font-medium text-muted-foreground">{label}</span>
                          <span className="font-semibold tabular-nums">{formatInrFromPaisa(num)}</span>
                        </div>
                        <div className="h-2 w-full rounded-full bg-secondary overflow-hidden">
                          <div className={`h-full ${color}`} style={{ width: `${width}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Operations &amp; Audit Queues</CardTitle>
                  <CardDescription>Live cross-module backlog counts</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {[
                    ["Pending PO Approvals", d.operations.pending_purchase_orders, "/admin/purchasing/orders"],
                    ["Pending Goods Receipts", d.operations.pending_goods_receipts, "/admin/purchasing/receipts"],
                    ["Pending Stock Adjustments", d.operations.pending_stock_adjustments, "/admin/inventory/adjustments"],
                    ["Dispatches in Pipeline", d.operations.pending_dispatches, "/admin/dispatch"],
                    ["Open Recon Discrepancies", d.operations.open_reconciliation_discrepancies, "/admin/reconciliation"],
                    ["Security / Denied Events", d.operations.security_events_in_period, "/admin/audit"],
                  ].map(([label, cnt, to]) => (
                    <Link
                      key={String(label)}
                      to={String(to)}
                      className="flex items-center justify-between border-b pb-1.5 last:border-b-0 hover:text-primary"
                    >
                      <span>{label}</span>
                      <span className="font-bold tabular-nums">{cnt}</span>
                    </Link>
                  ))}
                </CardContent>
              </Card>
            </div>

            {/* Product Performance & Customer Receivables/Margin */}
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <BarChart3 className="h-4 w-4 text-primary" />
                    Product Sales &amp; Gross Margin
                  </CardTitle>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                        <th className="py-2">SKU</th>
                        <th className="py-2 text-right">Net Pkts</th>
                        <th className="py-2 text-right">Net Rev</th>
                        <th className="py-2 text-right">COGS</th>
                        <th className="py-2 text-right">Margin</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.sales.top_products.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="py-6 text-center text-muted-foreground">
                            No invoiced sales in selected period.
                          </td>
                        </tr>
                      ) : (
                        d.sales.top_products.map((p) => (
                          <tr key={p.pack_size_id} className="border-b last:border-b-0">
                            <td className="py-2">
                              <div className="font-semibold">{p.sku_code}</div>
                              <div className="text-xs text-muted-foreground">{p.display_name}</div>
                            </td>
                            <td className="py-2 text-right tabular-nums">{p.net_sold_qty_pkts}</td>
                            <td className="py-2 text-right tabular-nums">{formatInrFromPaisa(p.net_revenue_paisa)}</td>
                            <td className="py-2 text-right tabular-nums">{formatInrFromPaisa(p.total_cogs_paisa)}</td>
                            <td className="py-2 text-right tabular-nums font-semibold text-emerald-700">
                              {p.gross_margin_pct}%
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Customer Performance &amp; AR Balance</CardTitle>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                        <th className="py-2">Customer</th>
                        <th className="py-2 text-right">Net Sales</th>
                        <th className="py-2 text-right">Collected</th>
                        <th className="py-2 text-right">Outstanding</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.sales.top_customers.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="py-6 text-center text-muted-foreground">
                            No customer sales activity in period.
                          </td>
                        </tr>
                      ) : (
                        d.sales.top_customers.map((c) => (
                          <tr key={c.customer_id} className="border-b last:border-b-0">
                            <td className="py-2">
                              <div className="font-semibold">{c.customer_name}</div>
                              <div className="text-xs text-muted-foreground">
                                {c.customer_code} · {c.invoice_count} inv
                              </div>
                            </td>
                            <td className="py-2 text-right tabular-nums">{formatInrFromPaisa(c.net_revenue_paisa)}</td>
                            <td className="py-2 text-right tabular-nums text-emerald-700">
                              {formatInrFromPaisa(c.cash_received_paisa)}
                            </td>
                            <td className="py-2 text-right tabular-nums font-semibold">
                              {formatInrFromPaisa(c.outstanding_receivables_paisa)}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            </div>

            {/* Production Summary & Low Stock Alerts */}
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Production Run Summary by SKU</CardTitle>
                  <CardDescription>
                    Flagged variances: {d.production.flagged_variances_count} · Wastage/Rejection Cost:{" "}
                    {formatInrFromPaisa(d.production.total_wastage_damage_cost_paisa)}
                  </CardDescription>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                        <th className="py-2">SKU</th>
                        <th className="py-2 text-right">Runs</th>
                        <th className="py-2 text-right">Good Pkts</th>
                        <th className="py-2 text-right">Yield %</th>
                        <th className="py-2 text-right">Avg Cost/Pkt</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.production.by_sku.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="py-6 text-center text-muted-foreground">
                            No production runs in selected period.
                          </td>
                        </tr>
                      ) : (
                        d.production.by_sku.map((r) => (
                          <tr key={r.pack_size_id} className="border-b last:border-b-0">
                            <td className="py-2 font-semibold">{r.sku_code}</td>
                            <td className="py-2 text-right tabular-nums">{r.runs_count}</td>
                            <td className="py-2 text-right tabular-nums">{r.actual_good_pkts}</td>
                            <td className="py-2 text-right tabular-nums">{r.yield_efficiency_pct}%</td>
                            <td className="py-2 text-right tabular-nums">
                              {r.avg_cost_per_pkt_paisa !== null ? formatInrFromPaisa(r.avg_cost_per_pkt_paisa) : "—"}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Low Stock Watchlist ({d.inventory.low_stock_count})</CardTitle>
                  <CardDescription>Items at or below configured reorder threshold</CardDescription>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                        <th className="py-2">Item</th>
                        <th className="py-2">Category</th>
                        <th className="py-2 text-right">Available</th>
                        <th className="py-2 text-right">Reorder</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.inventory.low_stock_alerts.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="py-6 text-center text-muted-foreground">
                            All items are currently above reorder threshold.
                          </td>
                        </tr>
                      ) : (
                        d.inventory.low_stock_alerts.map((item) => {
                          const availDisp = (Number(item.available_qty_base) / Number(item.display_factor)).toFixed(2);
                          return (
                            <tr key={`${item.item_type}-${item.item_id}`} className="border-b last:border-b-0">
                              <td className="py-2">
                                <div className="font-semibold">{item.code}</div>
                                <div className="text-xs text-muted-foreground">{item.name}</div>
                              </td>
                              <td className="py-2 text-xs">{item.item_category}</td>
                              <td className="py-2 text-right font-semibold text-red-700 tabular-nums">
                                {availDisp} {item.display_uom}
                              </td>
                              <td className="py-2 text-right tabular-nums text-muted-foreground">
                                {item.reorder_level_base} {item.base_uom}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            </div>

            <div className="rounded-lg border bg-card px-4 py-3 text-xs text-muted-foreground">
              <span className="font-semibold text-foreground">Methodology Note: </span>
              {d.finance.profitability_disclaimer}
            </div>
          </>
        )}
      </div>
    </DesktopAdminLayout>
  );
}

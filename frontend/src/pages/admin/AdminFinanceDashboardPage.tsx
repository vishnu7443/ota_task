import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  Calculator,
  FileSpreadsheet,
  IndianRupee,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { financeApi } from "@/lib/api";
import { formatInrFromPaisa, formatOrderDate } from "@/lib/money";

export function AdminFinanceDashboardPage() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const dashQuery = useQuery({
    queryKey: ["finance-dashboard", dateFrom, dateTo],
    queryFn: () =>
      financeApi.getDashboard({
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
      }),
    refetchInterval: 15_000,
  });

  const d = dashQuery.data;

  return (
    <DesktopAdminLayout
      title="Financial Dashboard"
      subtitle="Live revenue (excl. GST), collections, receivables ageing, batch costing & product gross margin"
      actions={
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm">
            <Link to="/admin/finance/payments">
              <Wallet className="h-4 w-4" />
              Record / Manage Payments
            </Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link to="/admin/finance/receivables">
              <FileSpreadsheet className="h-4 w-4" />
              AR &amp; Ageing
            </Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link to="/admin/costing">
              <Calculator className="h-4 w-4" />
              Product Costing
            </Link>
          </Button>
          <Button asChild size="sm" variant="outline">
            <Link to="/admin/finance/profitability">
              <TrendingUp className="h-4 w-4" />
              Profitability
            </Link>
          </Button>
        </div>
      }
    >
      <div className="space-y-6">
        <Card>
          <CardContent className="p-4 flex flex-wrap items-end gap-4">
            <div>
              <label className="text-xs font-semibold text-muted-foreground">From Date</label>
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted-foreground">To Date</label>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="mt-1"
              />
            </div>
            {(dateFrom || dateTo) && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setDateFrom("");
                  setDateTo("");
                }}
              >
                Clear Dates
              </Button>
            )}
          </CardContent>
        </Card>

        {d && (
          <>
            {/* Top 8 Financial KPI Cards cleanly distinguishing Revenue, GST, Cash, AR & Gross Profit */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Net Revenue (Excl. GST)
                  </div>
                  <div className="mt-1.5 text-2xl font-bold tabular-nums">
                    {formatInrFromPaisa(d.net_invoiced_sales_paisa)}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    GST Tax Collected: {formatInrFromPaisa(d.total_gst_collected_paisa)}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Payments Received (Net Cash)
                  </div>
                  <div className="mt-1.5 text-2xl font-bold text-emerald-700 tabular-nums">
                    {formatInrFromPaisa(d.net_cash_collected_paisa)}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Customer Advances: {formatInrFromPaisa(d.customer_advances_paisa)}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Outstanding Receivables
                  </div>
                  <div className="mt-1.5 text-2xl font-bold text-amber-700 tabular-nums">
                    {formatInrFromPaisa(d.outstanding_receivables_paisa)}
                  </div>
                  <div className="text-xs text-red-700 mt-1 flex items-center gap-1">
                    <AlertCircle className="h-3 w-3" />
                    Overdue: {formatInrFromPaisa(d.overdue_receivables_paisa)}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="p-4">
                  <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Gross Profit &amp; Margin
                  </div>
                  <div className="mt-1.5 text-2xl font-bold text-primary tabular-nums">
                    {formatInrFromPaisa(d.gross_profit_paisa)}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    Margin: {d.gross_margin_pct}% · COGS: {formatInrFromPaisa(d.total_cogs_paisa)}
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="rounded-lg border bg-secondary/30 px-4 py-2.5 text-xs text-muted-foreground">
              {d.profitability_disclaimer}
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              {/* Recent Payments */}
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0">
                  <div>
                    <CardTitle className="text-base">Recent Customer Payments</CardTitle>
                    <CardDescription>Verified collections from persisted payment ledger</CardDescription>
                  </div>
                  <Link to="/admin/finance/payments" className="text-xs font-semibold text-primary hover:underline">
                    View All →
                  </Link>
                </CardHeader>
                <CardContent className="p-0 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                        <th className="px-4 py-2">Payment #</th>
                        <th className="px-3 py-2">Customer</th>
                        <th className="px-3 py-2">Mode</th>
                        <th className="px-3 py-2 text-right">Amount</th>
                        <th className="px-4 py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {d.recent_payments.map((p) => (
                        <tr key={p.id}>
                          <td className="px-4 py-2 font-mono font-bold">
                            <div>{p.payment_number}</div>
                            <div className="text-[11px] font-normal text-muted-foreground">
                              {formatOrderDate(p.payment_date)}
                            </div>
                          </td>
                          <td className="px-3 py-2 font-medium">{p.customer_name}</td>
                          <td className="px-3 py-2">{p.payment_mode}</td>
                          <td className="px-3 py-2 text-right font-bold tabular-nums">
                            {formatInrFromPaisa(p.amount_paisa)}
                          </td>
                          <td className="px-4 py-2">
                            <StatusBadge status={p.status} />
                          </td>
                        </tr>
                      ))}
                      {d.recent_payments.length === 0 && (
                        <tr>
                          <td colSpan={5} className="py-6 text-center text-muted-foreground">
                            No payments recorded yet.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </CardContent>
              </Card>

              {/* Recent Outstanding Invoices */}
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0">
                  <div>
                    <CardTitle className="text-base">Outstanding Invoices (By Due Date)</CardTitle>
                    <CardDescription>Ordered earliest due date first</CardDescription>
                  </div>
                  <Link to="/admin/finance/receivables" className="text-xs font-semibold text-primary hover:underline">
                    Full Ageing →
                  </Link>
                </CardHeader>
                <CardContent className="p-0 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                        <th className="px-4 py-2">Invoice #</th>
                        <th className="px-3 py-2">Customer</th>
                        <th className="px-3 py-2">Due Date</th>
                        <th className="px-3 py-2 text-right">Outstanding</th>
                        <th className="px-4 py-2">Ageing</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {d.recent_outstanding_invoices.map((inv) => (
                        <tr key={inv.invoice_id}>
                          <td className="px-4 py-2 font-mono font-bold">
                            <Link
                              to={`/admin/billing/invoices/${inv.invoice_id}`}
                              className="text-primary hover:underline"
                            >
                              {inv.invoice_number}
                            </Link>
                          </td>
                          <td className="px-3 py-2">{inv.customer_name}</td>
                          <td className="px-3 py-2">{formatOrderDate(inv.due_date)}</td>
                          <td className="px-3 py-2 text-right font-bold text-amber-700 tabular-nums">
                            {formatInrFromPaisa(inv.outstanding_paisa)}
                          </td>
                          <td className="px-4 py-2">
                            <StatusBadge status={inv.ageing_bucket} />
                          </td>
                        </tr>
                      ))}
                      {d.recent_outstanding_invoices.length === 0 && (
                        <tr>
                          <td colSpan={5} className="py-6 text-center text-muted-foreground">
                            Zero open receivables!
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            </div>

            {/* Product Profitability & Batch Costing Summary */}
            <div className="grid gap-6 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-primary" />
                    Product Profitability
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                        <th className="px-4 py-2">SKU</th>
                        <th className="px-3 py-2 text-right">Sold</th>
                        <th className="px-3 py-2 text-right">Net Rev.</th>
                        <th className="px-3 py-2 text-right">COGS</th>
                        <th className="px-3 py-2 text-right">Gross Profit</th>
                        <th className="px-4 py-2 text-right">Margin</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {d.product_profitability.map((pr) => (
                        <tr key={pr.pack_size_id}>
                          <td className="px-4 py-2 font-semibold">{pr.display_name}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{pr.net_sold_qty_pkts}</td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {formatInrFromPaisa(pr.net_revenue_paisa)}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {formatInrFromPaisa(pr.total_cogs_paisa)}
                          </td>
                          <td className="px-3 py-2 text-right font-bold text-emerald-700 tabular-nums">
                            {formatInrFromPaisa(pr.gross_profit_paisa)}
                          </td>
                          <td className="px-4 py-2 text-right font-bold tabular-nums">
                            {pr.gross_margin_pct}%
                          </td>
                        </tr>
                      ))}
                      {d.product_profitability.length === 0 && (
                        <tr>
                          <td colSpan={6} className="py-6 text-center text-muted-foreground">
                            No invoiced product sales yet.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0">
                  <div>
                    <CardTitle className="text-base flex items-center gap-2">
                      <IndianRupee className="h-4 w-4 text-primary" />
                      Production Costing Summary
                    </CardTitle>
                    <CardDescription>Latest immutable batch cost snapshots</CardDescription>
                  </div>
                  <Link to="/admin/costing" className="text-xs font-semibold text-primary hover:underline">
                    Manage Overheads →
                  </Link>
                </CardHeader>
                <CardContent className="p-0 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                        <th className="px-4 py-2">Run #</th>
                        <th className="px-3 py-2">SKU</th>
                        <th className="px-3 py-2 text-right">Total Cost</th>
                        <th className="px-3 py-2 text-right">Cost / Pkt</th>
                        <th className="px-4 py-2">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {d.costing_summary.map((cs) => (
                        <tr key={cs.production_run_id}>
                          <td className="px-4 py-2 font-mono font-bold">
                            <Link
                              to={`/admin/production/runs/${cs.production_run_id}`}
                              className="text-primary hover:underline"
                            >
                              {cs.run_number}
                            </Link>
                          </td>
                          <td className="px-3 py-2">{cs.display_name}</td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {formatInrFromPaisa(cs.total_cost_paisa)}
                          </td>
                          <td className="px-3 py-2 text-right font-bold tabular-nums">
                            {cs.cost_per_packet_paisa != null
                              ? formatInrFromPaisa(cs.cost_per_packet_paisa)
                              : "—"}
                          </td>
                          <td className="px-4 py-2">
                            <StatusBadge status={cs.cost_status} />
                          </td>
                        </tr>
                      ))}
                      {d.costing_summary.length === 0 && (
                        <tr>
                          <td colSpan={5} className="py-6 text-center text-muted-foreground">
                            No posted production batches costed yet.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            </div>

            {/* Payment Collection Trends */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Daily Payment Collection Trend</CardTitle>
              </CardHeader>
              <CardContent className="p-0 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                      <th className="px-4 py-2">Payment Date</th>
                      <th className="px-3 py-2 text-right">Receipts Count</th>
                      <th className="px-4 py-2 text-right">Net Cash Collected</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {d.payment_trends.map((t) => (
                      <tr key={t.payment_date}>
                        <td className="px-4 py-2 font-medium">{formatOrderDate(t.payment_date)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{t.payment_count}</td>
                        <td className="px-4 py-2 text-right font-bold text-emerald-700 tabular-nums">
                          {formatInrFromPaisa(t.total_received_paisa)}
                        </td>
                      </tr>
                    ))}
                    {d.payment_trends.length === 0 && (
                      <tr>
                        <td colSpan={3} className="py-6 text-center text-muted-foreground">
                          No payment trends available in selected window.
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

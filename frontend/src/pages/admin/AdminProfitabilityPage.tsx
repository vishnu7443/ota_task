import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Download, TrendingUp } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { financeApi } from "@/lib/api";
import { formatInrFromPaisa, formatOrderDate } from "@/lib/money";

function downloadCsv(filename: string, headers: string[], rows: Array<Array<string | number>>) {
  const esc = (v: string | number) => `"${String(v).replaceAll('"', '""')}"`;
  const csv = [headers.map(esc).join(","), ...rows.map((r) => r.map(esc).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function AdminProfitabilityPage() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [tab, setTab] = useState<"product" | "customer" | "order" | "date">("product");

  const profQuery = useQuery({
    queryKey: ["profitability-report", dateFrom, dateTo],
    queryFn: () =>
      financeApi.getProfitability({
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
      }),
    refetchInterval: 20_000,
  });

  const p = profQuery.data;

  const exportCsv = () => {
    if (!p) return;
    if (tab === "product") {
      downloadCsv(
        "product-profitability.csv",
        ["SKU", "Product", "HSN", "Net Sold Pkts", "Net Revenue Rs", "GST Collected Rs", "COGS Rs", "Gross Profit Rs", "Margin %"],
        p.by_product.map((r) => [
          r.sku_code,
          r.display_name,
          r.hsn_code,
          r.net_sold_qty_pkts,
          (r.net_revenue_paisa / 100).toFixed(2),
          (r.gst_collected_paisa / 100).toFixed(2),
          (r.total_cogs_paisa / 100).toFixed(2),
          (r.gross_profit_paisa / 100).toFixed(2),
          r.gross_margin_pct,
        ])
      );
    } else if (tab === "customer") {
      downloadCsv(
        "customer-profitability.csv",
        ["Customer Code", "Customer", "Invoices", "Net Revenue Rs", "GST Collected Rs", "COGS Rs", "Gross Profit Rs", "Margin %", "Cash Received Rs", "Outstanding Rs"],
        p.by_customer.map((r) => [
          r.customer_code,
          r.customer_name,
          r.invoice_count,
          (r.net_revenue_paisa / 100).toFixed(2),
          (r.gst_collected_paisa / 100).toFixed(2),
          (r.total_cogs_paisa / 100).toFixed(2),
          (r.gross_profit_paisa / 100).toFixed(2),
          r.gross_margin_pct,
          (r.cash_received_paisa / 100).toFixed(2),
          (r.outstanding_receivables_paisa / 100).toFixed(2),
        ])
      );
    } else if (tab === "order") {
      downloadCsv(
        "order-profitability.csv",
        ["Order #", "Invoice #", "Date", "Customer", "Status", "Net Revenue Rs", "GST Rs", "COGS Rs", "Gross Profit Rs", "Margin %"],
        p.by_order.map((r) => [
          r.order_number,
          r.invoice_number,
          r.invoice_date,
          r.customer_name,
          r.doc_status,
          (r.net_revenue_paisa / 100).toFixed(2),
          (r.gst_collected_paisa / 100).toFixed(2),
          (r.total_cogs_paisa / 100).toFixed(2),
          (r.gross_profit_paisa / 100).toFixed(2),
          r.gross_margin_pct,
        ])
      );
    } else {
      downloadCsv(
        "date-profitability.csv",
        ["Date", "Invoices", "Net Revenue Rs", "GST Collected Rs", "COGS Rs", "Gross Profit Rs", "Margin %", "Cash Collected Rs"],
        p.by_date.map((r) => [
          r.period_date,
          r.invoice_count,
          (r.net_revenue_paisa / 100).toFixed(2),
          (r.gst_collected_paisa / 100).toFixed(2),
          (r.total_cogs_paisa / 100).toFixed(2),
          (r.gross_profit_paisa / 100).toFixed(2),
          r.gross_margin_pct,
          (r.cash_collected_on_date_paisa / 100).toFixed(2),
        ])
      );
    }
  };

  return (
    <DesktopAdminLayout
      title="Profitability & Margin Analysis"
      subtitle="Distinguishes Revenue (excl. GST), GST Liability, COGS (FIFO + Overheads), Cash Received & Outstanding Receivables"
      actions={
        <Button variant="outline" onClick={exportCsv} disabled={!p}>
          <Download className="h-4 w-4" />
          Export CSV
        </Button>
      }
    >
      <div className="space-y-6">
        <Card>
          <CardContent className="p-4 flex flex-wrap items-end gap-4">
            <div>
              <label className="text-xs font-semibold text-muted-foreground">From Date</label>
              <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="mt-1" />
            </div>
            <div>
              <label className="text-xs font-semibold text-muted-foreground">To Date</label>
              <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="mt-1" />
            </div>
            <div className="flex flex-wrap gap-1.5 ml-auto">
              {[
                { key: "product", label: "Product-Wise" },
                { key: "customer", label: "Customer-Wise" },
                { key: "order", label: "Sales-Order-Wise" },
                { key: "date", label: "Date-Wise" },
              ].map((t) => (
                <Button
                  key={t.key}
                  size="sm"
                  variant={tab === t.key ? "default" : "outline"}
                  onClick={() => setTab(t.key as typeof tab)}
                >
                  {t.label}
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>

        {p && (
          <>
            {/* Strictly separated Financial Metrics */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
              <Card>
                <CardContent className="p-4">
                  <div className="text-[11px] font-semibold uppercase text-muted-foreground">Net Revenue (Ex-GST)</div>
                  <div className="mt-1 text-lg font-bold tabular-nums">{formatInrFromPaisa(p.net_revenue_paisa)}</div>
                  <div className="text-[11px] text-muted-foreground">CN Credited: {formatInrFromPaisa(p.credited_revenue_paisa)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-[11px] font-semibold uppercase text-muted-foreground">GST Tax Collected</div>
                  <div className="mt-1 text-lg font-bold tabular-nums">{formatInrFromPaisa(p.gst_collected_paisa)}</div>
                  <div className="text-[11px] text-muted-foreground">Excluded from revenue</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-[11px] font-semibold uppercase text-muted-foreground">Total COGS</div>
                  <div className="mt-1 text-lg font-bold tabular-nums">{formatInrFromPaisa(p.total_cogs_paisa)}</div>
                  <div className="text-[11px] text-muted-foreground">Dispatched: {formatInrFromPaisa(p.dispatched_cogs_paisa)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-[11px] font-semibold uppercase text-muted-foreground">Gross Profit</div>
                  <div className="mt-1 text-lg font-bold text-emerald-700 tabular-nums">{formatInrFromPaisa(p.gross_profit_paisa)}</div>
                  <div className="text-[11px] font-bold text-primary">Margin: {p.gross_margin_pct}%</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-[11px] font-semibold uppercase text-muted-foreground">Cash Received</div>
                  <div className="mt-1 text-lg font-bold tabular-nums">{formatInrFromPaisa(p.cash_received_paisa)}</div>
                  <div className="text-[11px] text-muted-foreground">Not counted as revenue</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-[11px] font-semibold uppercase text-muted-foreground">Open Receivables</div>
                  <div className="mt-1 text-lg font-bold text-amber-700 tabular-nums">{formatInrFromPaisa(p.outstanding_receivables_paisa)}</div>
                </CardContent>
              </Card>
            </div>

            <div className="rounded-lg border bg-secondary/30 px-4 py-2.5 text-xs text-muted-foreground">
              {p.disclaimer}
            </div>

            {tab === "product" && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-primary" /> Product-Wise Revenue, COGS &amp; Gross Profit
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                        <th className="px-4 py-2.5">SKU</th>
                        <th className="px-3 py-2.5">Product</th>
                        <th className="px-3 py-2.5 text-right">Net Pkts</th>
                        <th className="px-3 py-2.5 text-right">Gross Rev.</th>
                        <th className="px-3 py-2.5 text-right">CN Rev.</th>
                        <th className="px-3 py-2.5 text-right">Net Revenue</th>
                        <th className="px-3 py-2.5 text-right">GST Collected</th>
                        <th className="px-3 py-2.5 text-right">Total COGS</th>
                        <th className="px-3 py-2.5 text-right">Gross Profit</th>
                        <th className="px-4 py-2.5 text-right">Margin %</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {p.by_product.map((r) => (
                        <tr key={r.pack_size_id}>
                          <td className="px-4 py-2.5 font-mono font-bold">{r.sku_code}</td>
                          <td className="px-3 py-2.5 font-semibold">{r.display_name}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{r.net_sold_qty_pkts}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(r.gross_revenue_paisa)}</td>
                          <td className="px-3 py-2.5 text-right text-red-700 tabular-nums">{formatInrFromPaisa(r.credited_revenue_paisa)}</td>
                          <td className="px-3 py-2.5 text-right font-semibold tabular-nums">{formatInrFromPaisa(r.net_revenue_paisa)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(r.gst_collected_paisa)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(r.total_cogs_paisa)}</td>
                          <td className="px-3 py-2.5 text-right font-bold text-emerald-700 tabular-nums">{formatInrFromPaisa(r.gross_profit_paisa)}</td>
                          <td className="px-4 py-2.5 text-right font-bold tabular-nums">{r.gross_margin_pct}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            )}

            {tab === "customer" && (
              <Card>
                <CardHeader><CardTitle className="text-base">Customer-Wise Profitability &amp; Collections</CardTitle></CardHeader>
                <CardContent className="p-0 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                        <th className="px-4 py-2.5">Customer</th>
                        <th className="px-3 py-2.5 text-right">Invoices</th>
                        <th className="px-3 py-2.5 text-right">Net Revenue</th>
                        <th className="px-3 py-2.5 text-right">GST</th>
                        <th className="px-3 py-2.5 text-right">COGS</th>
                        <th className="px-3 py-2.5 text-right">Gross Profit</th>
                        <th className="px-3 py-2.5 text-right">Margin</th>
                        <th className="px-3 py-2.5 text-right">Allocated Cash</th>
                        <th className="px-4 py-2.5 text-right">Outstanding</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {p.by_customer.map((c) => (
                        <tr key={c.customer_id}>
                          <td className="px-4 py-2.5 font-semibold">{c.customer_name}</td>
                          <td className="px-3 py-2.5 text-right">{c.invoice_count}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(c.net_revenue_paisa)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(c.gst_collected_paisa)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(c.total_cogs_paisa)}</td>
                          <td className="px-3 py-2.5 text-right font-bold text-emerald-700 tabular-nums">{formatInrFromPaisa(c.gross_profit_paisa)}</td>
                          <td className="px-3 py-2.5 text-right font-bold tabular-nums">{c.gross_margin_pct}%</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(c.cash_received_paisa)}</td>
                          <td className="px-4 py-2.5 text-right text-amber-700 font-bold tabular-nums">{formatInrFromPaisa(c.outstanding_receivables_paisa)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            )}

            {tab === "order" && (
              <Card>
                <CardHeader><CardTitle className="text-base">Sales-Order-Wise Profitability</CardTitle></CardHeader>
                <CardContent className="p-0 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                        <th className="px-4 py-2.5">Order #</th>
                        <th className="px-3 py-2.5">Invoice #</th>
                        <th className="px-3 py-2.5">Customer</th>
                        <th className="px-3 py-2.5">Status</th>
                        <th className="px-3 py-2.5 text-right">Net Rev.</th>
                        <th className="px-3 py-2.5 text-right">COGS</th>
                        <th className="px-3 py-2.5 text-right">Gross Profit</th>
                        <th className="px-4 py-2.5 text-right">Margin</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {p.by_order.map((o) => (
                        <tr key={o.invoice_id}>
                          <td className="px-4 py-2.5 font-mono font-bold">
                            <Link to={`/admin/orders/${o.sales_order_id}`} className="text-primary hover:underline">
                              {o.order_number}
                            </Link>
                          </td>
                          <td className="px-3 py-2.5 font-mono">
                            <Link to={`/admin/billing/invoices/${o.invoice_id}`} className="hover:underline">
                              {o.invoice_number}
                            </Link>
                          </td>
                          <td className="px-3 py-2.5">{o.customer_name}</td>
                          <td className="px-3 py-2.5"><StatusBadge status={o.doc_status} /></td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(o.net_revenue_paisa)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(o.total_cogs_paisa)}</td>
                          <td className="px-3 py-2.5 text-right font-bold text-emerald-700 tabular-nums">{formatInrFromPaisa(o.gross_profit_paisa)}</td>
                          <td className="px-4 py-2.5 text-right font-bold tabular-nums">{o.gross_margin_pct}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            )}

            {tab === "date" && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Date-Wise Profitability &amp; Cash Collections</CardTitle>
                  <CardDescription>Cash collected by payment date displayed alongside accrual invoice revenue/COGS.</CardDescription>
                </CardHeader>
                <CardContent className="p-0 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                        <th className="px-4 py-2.5">Date</th>
                        <th className="px-3 py-2.5 text-right">Invoices</th>
                        <th className="px-3 py-2.5 text-right">Net Revenue</th>
                        <th className="px-3 py-2.5 text-right">GST</th>
                        <th className="px-3 py-2.5 text-right">COGS</th>
                        <th className="px-3 py-2.5 text-right">Gross Profit</th>
                        <th className="px-3 py-2.5 text-right">Margin</th>
                        <th className="px-4 py-2.5 text-right">Cash Collected</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {p.by_date.map((dRow) => (
                        <tr key={dRow.period_date}>
                          <td className="px-4 py-2.5 font-medium">{formatOrderDate(dRow.period_date)}</td>
                          <td className="px-3 py-2.5 text-right">{dRow.invoice_count}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(dRow.net_revenue_paisa)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(dRow.gst_collected_paisa)}</td>
                          <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(dRow.total_cogs_paisa)}</td>
                          <td className="px-3 py-2.5 text-right font-bold text-emerald-700 tabular-nums">{formatInrFromPaisa(dRow.gross_profit_paisa)}</td>
                          <td className="px-3 py-2.5 text-right font-bold tabular-nums">{dRow.gross_margin_pct}%</td>
                          <td className="px-4 py-2.5 text-right font-semibold text-primary tabular-nums">
                            {formatInrFromPaisa(dRow.cash_collected_on_date_paisa)}
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
      </div>
    </DesktopAdminLayout>
  );
}

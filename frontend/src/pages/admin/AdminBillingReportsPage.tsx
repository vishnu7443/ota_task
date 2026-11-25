import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { BarChart3, Download } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
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

export function AdminBillingReportsPage() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [tab, setTab] = useState<"sales" | "gst" | "cn" | "dispatch" | "customer" | "product" | "outstanding">(
    "sales"
  );

  const reportQuery = useQuery({
    queryKey: ["billing-reports", dateFrom, dateTo],
    queryFn: () =>
      api.getBillingReports({
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
      }),
    refetchInterval: 20_000,
  });

  const data = reportQuery.data;

  const exportCurrentCsv = () => {
    if (!data) return;
    if (tab === "sales") {
      downloadCsv(
        "sales-invoice-register.csv",
        ["Invoice", "Date", "FY", "Order", "Customer", "GSTIN", "POS", "Supply", "Status", "Taxable Rs", "CGST Rs", "SGST Rs", "IGST Rs", "Grand Total Rs", "Credited Rs", "Outstanding Rs"],
        data.sales_register.map((r) => [
          r.invoice_number,
          r.invoice_date,
          r.financial_year,
          r.order_number,
          r.customer_name,
          r.buyer_gstin ?? "",
          r.place_of_supply_state_code,
          r.supply_type,
          r.doc_status,
          (r.taxable_total_paisa / 100).toFixed(2),
          (r.cgst_total_paisa / 100).toFixed(2),
          (r.sgst_total_paisa / 100).toFixed(2),
          (r.igst_total_paisa / 100).toFixed(2),
          (r.grand_total_paisa / 100).toFixed(2),
          (r.credited_paisa / 100).toFixed(2),
          (r.outstanding_paisa / 100).toFixed(2),
        ])
      );
    } else if (tab === "gst") {
      downloadCsv(
        "gst-hsn-summary.csv",
        ["HSN", "Supply Type", "Rate %", "Taxable Rs", "CGST Rs", "SGST Rs", "IGST Rs", "Total Tax Rs"],
        data.gst_summary.hsn_rows.map((h) => [
          h.hsn_code,
          h.supply_type,
          (h.tax_rate_bps / 100).toFixed(2),
          (h.taxable_value_paisa / 100).toFixed(2),
          (h.cgst_paisa / 100).toFixed(2),
          (h.sgst_paisa / 100).toFixed(2),
          (h.igst_paisa / 100).toFixed(2),
          (h.total_tax_paisa / 100).toFixed(2),
        ])
      );
    } else if (tab === "cn") {
      downloadCsv(
        "credit-notes-register.csv",
        ["CN #", "Issue Date", "Original Invoice", "Customer", "Type", "Status", "Taxable Rev Rs", "CGST Rev Rs", "SGST Rev Rs", "IGST Rev Rs", "Total Rev Rs", "Reason"],
        data.credit_notes.map((c) => [
          c.cn_number ?? c.draft_ref,
          c.issue_date,
          c.original_invoice_number ?? "",
          c.customer_name,
          c.note_type,
          c.status,
          (c.taxable_reversed_paisa / 100).toFixed(2),
          (c.cgst_reversed_paisa / 100).toFixed(2),
          (c.sgst_reversed_paisa / 100).toFixed(2),
          (c.igst_reversed_paisa / 100).toFixed(2),
          (c.total_reversed_paisa / 100).toFixed(2),
          c.reason,
        ])
      );
    } else if (tab === "dispatch") {
      downloadCsv(
        "dispatch-register.csv",
        ["Dispatch #", "Date", "Invoice #", "Order #", "Customer", "Status", "Transporter", "Vehicle", "Dispatched Pkts", "Received Pkts", "Delivery Date"],
        data.dispatch_register.map((d) => [
          d.dispatch_number,
          d.dispatch_date,
          d.invoice_number,
          d.order_number,
          d.customer_name,
          d.status,
          d.transporter_name ?? "",
          d.vehicle_number ?? "",
          d.total_dispatched_pkts,
          d.total_received_pkts,
          d.delivery_date ?? "",
        ])
      );
    } else if (tab === "customer") {
      downloadCsv(
        "customer-wise-sales.csv",
        ["Customer", "Type", "State", "GSTIN", "Invoices", "Total Pkts", "Taxable Rs", "GST Rs", "Grand Total Rs", "Credited Rs", "Outstanding Rs"],
        data.customer_sales.map((c) => [
          c.customer_name,
          c.customer_type,
          c.state_code,
          c.buyer_gstin ?? "",
          c.invoice_count,
          c.total_qty_pkts,
          (c.taxable_paisa / 100).toFixed(2),
          (c.gst_paisa / 100).toFixed(2),
          (c.grand_total_paisa / 100).toFixed(2),
          (c.credited_paisa / 100).toFixed(2),
          (c.outstanding_paisa / 100).toFixed(2),
        ])
      );
    } else if (tab === "product") {
      downloadCsv(
        "product-wise-sales.csv",
        ["SKU", "Description", "HSN", "Qty Pkts", "Taxable Rs", "CGST Rs", "SGST Rs", "IGST Rs", "Line Total Rs"],
        data.product_sales.map((p) => [
          p.sku_code,
          p.description,
          p.hsn_code,
          p.total_qty_pkts,
          (p.taxable_paisa / 100).toFixed(2),
          (p.cgst_paisa / 100).toFixed(2),
          (p.sgst_paisa / 100).toFixed(2),
          (p.igst_paisa / 100).toFixed(2),
          (p.line_total_paisa / 100).toFixed(2),
        ])
      );
    } else if (tab === "outstanding") {
      downloadCsv(
        "outstanding-invoices.csv",
        ["Invoice", "Date", "Customer", "Status", "Grand Total Rs", "Outstanding Rs"],
        data.outstanding_invoices.map((r) => [
          r.invoice_number,
          r.invoice_date,
          r.customer_name,
          r.doc_status,
          (r.grand_total_paisa / 100).toFixed(2),
          (r.outstanding_paisa / 100).toFixed(2),
        ])
      );
    }
  };

  return (
    <DesktopAdminLayout
      title="Sales, GST, Credit Note & Dispatch Reports"
      subtitle="Operational financial and logistics registers derived directly from persisted invoices, credit notes, and dispatches"
      actions={
        <Button variant="outline" onClick={exportCurrentCsv} disabled={!data}>
          <Download className="h-4 w-4" />
          Export CSV
        </Button>
      }
    >
      <div className="space-y-6">
        {/* Date Filter & Tabs */}
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
                { key: "sales", label: "Sales Register" },
                { key: "gst", label: "Taxable & GST (CGST/SGST/IGST)" },
                { key: "cn", label: "Credit Notes" },
                { key: "dispatch", label: "Dispatch Register" },
                { key: "customer", label: "Customer-wise" },
                { key: "product", label: "Product-wise" },
                { key: "outstanding", label: "Outstanding Invoices" },
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

        {data && tab === "gst" && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <BarChart3 className="h-4 w-4 text-primary" />
                Outward Taxable &amp; GST Summary (Gross vs Credited vs Net)
              </CardTitle>
              <CardDescription>{data.gst_summary.disclaimer}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-4 text-sm">
                <div className="rounded-lg border p-3">
                  <div className="text-xs text-muted-foreground">Net Taxable Sales</div>
                  <div className="text-lg font-bold tabular-nums">
                    {formatInrFromPaisa(data.gst_summary.net_taxable_paisa)}
                  </div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-xs text-muted-foreground">Net CGST</div>
                  <div className="text-lg font-bold tabular-nums">
                    {formatInrFromPaisa(data.gst_summary.net_cgst_paisa)}
                  </div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-xs text-muted-foreground">Net SGST</div>
                  <div className="text-lg font-bold tabular-nums">
                    {formatInrFromPaisa(data.gst_summary.net_sgst_paisa)}
                  </div>
                </div>
                <div className="rounded-lg border p-3">
                  <div className="text-xs text-muted-foreground">Net IGST</div>
                  <div className="text-lg font-bold tabular-nums">
                    {formatInrFromPaisa(data.gst_summary.net_igst_paisa)}
                  </div>
                </div>
              </div>

              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-secondary/40 text-left text-xs uppercase text-muted-foreground">
                      <th className="px-4 py-2">HSN</th>
                      <th className="px-3 py-2">Supply Type</th>
                      <th className="px-3 py-2 text-right">GST Rate</th>
                      <th className="px-3 py-2 text-right">Taxable Value</th>
                      <th className="px-3 py-2 text-right">CGST</th>
                      <th className="px-3 py-2 text-right">SGST</th>
                      <th className="px-3 py-2 text-right">IGST</th>
                      <th className="px-4 py-2 text-right">Total Tax</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {data.gst_summary.hsn_rows.map((h) => (
                      <tr key={`${h.hsn_code}-${h.supply_type}-${h.tax_rate_bps}`}>
                        <td className="px-4 py-2 font-mono font-bold">{h.hsn_code}</td>
                        <td className="px-3 py-2"><StatusBadge status={h.supply_type} /></td>
                        <td className="px-3 py-2 text-right">{(h.tax_rate_bps / 100).toFixed(2)}%</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatInrFromPaisa(h.taxable_value_paisa)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatInrFromPaisa(h.cgst_paisa)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatInrFromPaisa(h.sgst_paisa)}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{formatInrFromPaisa(h.igst_paisa)}</td>
                        <td className="px-4 py-2 text-right font-bold tabular-nums">{formatInrFromPaisa(h.total_tax_paisa)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}

        {data && (tab === "sales" || tab === "outstanding") && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                {tab === "sales" ? "Sales Invoice Register" : "Outstanding Invoices Summary"}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y bg-secondary/40 text-left text-xs uppercase text-muted-foreground">
                    <th className="px-4 py-2.5">Invoice #</th>
                    <th className="px-3 py-2.5">Date</th>
                    <th className="px-3 py-2.5">Customer</th>
                    <th className="px-3 py-2.5">Status</th>
                    <th className="px-3 py-2.5 text-right">Taxable</th>
                    <th className="px-3 py-2.5 text-right">CGST</th>
                    <th className="px-3 py-2.5 text-right">SGST</th>
                    <th className="px-3 py-2.5 text-right">IGST</th>
                    <th className="px-3 py-2.5 text-right">Grand Total</th>
                    <th className="px-4 py-2.5 text-right">Outstanding</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {(tab === "sales" ? data.sales_register : data.outstanding_invoices).map((r) => (
                    <tr key={r.invoice_id}>
                      <td className="px-4 py-2.5 font-mono text-xs font-bold">
                        <Link to={`/admin/billing/invoices/${r.invoice_id}`} className="text-primary hover:underline">
                          {r.invoice_number}
                        </Link>
                      </td>
                      <td className="px-3 py-2.5 text-xs">{formatOrderDate(r.invoice_date)}</td>
                      <td className="px-3 py-2.5">{r.customer_name}</td>
                      <td className="px-3 py-2.5"><StatusBadge status={r.doc_status} /></td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(r.taxable_total_paisa)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(r.cgst_total_paisa)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(r.sgst_total_paisa)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(r.igst_total_paisa)}</td>
                      <td className="px-3 py-2.5 text-right font-bold tabular-nums">{formatInrFromPaisa(r.grand_total_paisa)}</td>
                      <td className="px-4 py-2.5 text-right font-bold text-amber-700 tabular-nums">
                        {formatInrFromPaisa(r.outstanding_paisa)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}

        {data && tab === "cn" && (
          <Card>
            <CardHeader><CardTitle className="text-base">Credit Note Report</CardTitle></CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y bg-secondary/40 text-left text-xs uppercase text-muted-foreground">
                    <th className="px-4 py-2.5">CN #</th>
                    <th className="px-3 py-2.5">Original Invoice</th>
                    <th className="px-3 py-2.5">Customer</th>
                    <th className="px-3 py-2.5 text-right">Taxable Rev.</th>
                    <th className="px-3 py-2.5 text-right">Total Rev.</th>
                    <th className="px-4 py-2.5">Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {data.credit_notes.map((c) => (
                    <tr key={c.id}>
                      <td className="px-4 py-2.5 font-mono text-xs font-bold">{c.cn_number ?? c.draft_ref}</td>
                      <td className="px-3 py-2.5 font-mono text-xs">{c.original_invoice_number}</td>
                      <td className="px-3 py-2.5">{c.customer_name}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(c.taxable_reversed_paisa)}</td>
                      <td className="px-3 py-2.5 text-right font-bold text-red-700 tabular-nums">{formatInrFromPaisa(c.total_reversed_paisa)}</td>
                      <td className="px-4 py-2.5 text-xs">{c.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}

        {data && tab === "dispatch" && (
          <Card>
            <CardHeader><CardTitle className="text-base">Dispatch Register</CardTitle></CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y bg-secondary/40 text-left text-xs uppercase text-muted-foreground">
                    <th className="px-4 py-2.5">Dispatch #</th>
                    <th className="px-3 py-2.5">Invoice #</th>
                    <th className="px-3 py-2.5">Customer</th>
                    <th className="px-3 py-2.5">Vehicle</th>
                    <th className="px-3 py-2.5 text-right">Dispatched</th>
                    <th className="px-3 py-2.5 text-right">Received</th>
                    <th className="px-4 py-2.5">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {data.dispatch_register.map((d) => (
                    <tr key={d.dispatch_id}>
                      <td className="px-4 py-2.5 font-mono text-xs font-bold">
                        <Link to={`/admin/dispatch/${d.dispatch_id}`} className="text-primary hover:underline">
                          {d.dispatch_number}
                        </Link>
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs">{d.invoice_number}</td>
                      <td className="px-3 py-2.5">{d.customer_name}</td>
                      <td className="px-3 py-2.5 text-xs">{d.vehicle_number ?? "—"}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{d.total_dispatched_pkts}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{d.total_received_pkts}</td>
                      <td className="px-4 py-2.5"><StatusBadge status={d.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}

        {data && tab === "customer" && (
          <Card>
            <CardHeader><CardTitle className="text-base">Customer-wise Sales</CardTitle></CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y bg-secondary/40 text-left text-xs uppercase text-muted-foreground">
                    <th className="px-4 py-2.5">Customer</th>
                    <th className="px-3 py-2.5">State / GSTIN</th>
                    <th className="px-3 py-2.5 text-right">Invoices</th>
                    <th className="px-3 py-2.5 text-right">Qty (Pkts)</th>
                    <th className="px-3 py-2.5 text-right">Taxable</th>
                    <th className="px-3 py-2.5 text-right">GST</th>
                    <th className="px-4 py-2.5 text-right">Outstanding</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {data.customer_sales.map((c) => (
                    <tr key={c.customer_id}>
                      <td className="px-4 py-2.5 font-semibold">{c.customer_name}</td>
                      <td className="px-3 py-2.5 text-xs">{c.state_code} · {c.buyer_gstin ?? "B2C"}</td>
                      <td className="px-3 py-2.5 text-right">{c.invoice_count}</td>
                      <td className="px-3 py-2.5 text-right">{c.total_qty_pkts}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(c.taxable_paisa)}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(c.gst_paisa)}</td>
                      <td className="px-4 py-2.5 text-right font-bold tabular-nums">{formatInrFromPaisa(c.outstanding_paisa)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}

        {data && tab === "product" && (
          <Card>
            <CardHeader><CardTitle className="text-base">Product-wise Sales</CardTitle></CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y bg-secondary/40 text-left text-xs uppercase text-muted-foreground">
                    <th className="px-4 py-2.5">SKU</th>
                    <th className="px-3 py-2.5">Description</th>
                    <th className="px-3 py-2.5">HSN</th>
                    <th className="px-3 py-2.5 text-right">Qty (Pkts)</th>
                    <th className="px-3 py-2.5 text-right">Taxable</th>
                    <th className="px-4 py-2.5 text-right">Line Total (Incl. GST)</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {data.product_sales.map((p) => (
                    <tr key={`${p.pack_size_id}-${p.hsn_code}`}>
                      <td className="px-4 py-2.5 font-mono text-xs font-bold">{p.sku_code}</td>
                      <td className="px-3 py-2.5">{p.description}</td>
                      <td className="px-3 py-2.5 font-mono text-xs">{p.hsn_code}</td>
                      <td className="px-3 py-2.5 text-right">{p.total_qty_pkts}</td>
                      <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(p.taxable_paisa)}</td>
                      <td className="px-4 py-2.5 text-right font-bold tabular-nums">{formatInrFromPaisa(p.line_total_paisa)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}
      </div>
    </DesktopAdminLayout>
  );
}

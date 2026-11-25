import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileText } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { formatDateTimeIst, formatInrFromPaisa, formatOrderDate } from "@/lib/money";
import { formatBaseQty, formatDisplayQty } from "@/lib/units";

type ReportTab = "current" | "low" | "receipts" | "adjustments";

export function AdminStockReportsPage() {
  const [tab, setTab] = useState<ReportTab>("current");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const reportsQuery = useQuery({
    queryKey: ["inventory-reports-summary", dateFrom, dateTo],
    queryFn: () =>
      api.getStockReportsSummary({
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
      }),
  });

  const data = reportsQuery.data;

  const exportCsv = () => {
    if (!data) return;
    let lines: string[] = [];
    let filename = "stock-report.csv";
    if (tab === "current" || tab === "low") {
      const rows = tab === "low" ? data.low_stock_items : data.current_stock;
      filename = tab === "low" ? "low-stock-report.csv" : "current-stock-report.csv";
      lines = [
        "Code,Name,Category,PhysicalBase,ReservedBase,AvailableBase,BaseUOM,ReorderBase,OpenLotValueINR,LowStock",
        ...rows.map(
          (r) =>
            `"${r.code}","${r.name}","${r.item_category}",${r.physical_qty_base},${r.reserved_qty_base},${r.available_qty_base},"${r.base_uom}",${r.reorder_level_base},${(
              r.open_lot_value_paisa / 100
            ).toFixed(2)},${r.is_low_stock}`
        ),
      ];
    } else if (tab === "receipts") {
      filename = "purchase-receipt-report.csv";
      lines = [
        "ReceiptNumber,Date,PO,Supplier,Material,EnteredUOM,Received,Rejected,Accepted,AcceptedBase,BaseUOM,TotalINR,Status",
        ...data.purchase_receipts.map(
          (r) =>
            `"${r.receipt_number}","${r.receipt_date}","${r.po_number ?? ""}","${r.supplier_name}","${r.material_name}","${r.entered_uom}",${r.received_qty_entered},${r.rejected_qty_entered},${r.accepted_qty_entered},${r.accepted_qty_base},"${r.base_uom}",${(
              r.line_total_paisa / 100
            ).toFixed(2)},"${r.status}"`
        ),
      ];
    } else {
      filename = "stock-adjustment-report.csv";
      lines = [
        "AdjustmentNumber,ItemCode,ItemName,Type,EnteredQty,EnteredUOM,BaseDelta,BaseUOM,Status,Reason,RequestedBy",
        ...data.adjustments.map(
          (a) =>
            `"${a.adjustment_number}","${a.item_code}","${a.item_name}","${a.adjustment_type}",${a.entered_qty},"${a.entered_uom}",${a.delta_qty_base},"${a.base_uom}","${a.status}","${a.reason.replaceAll(
              '"',
              '""'
            )}","${a.requested_by_name}"`
        ),
      ];
    }

    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <DesktopAdminLayout
      title="Stock Reports"
      subtitle="Audit-ready inventory position, reorder warnings, goods receipt logs, and adjustment registers"
      actions={
        <Button variant="outline" onClick={exportCsv} disabled={!data}>
          <Download className="h-4 w-4" />
          Export CSV
        </Button>
      }
    >
      <div className="space-y-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap gap-1.5">
            {(
              [
                { k: "current", label: `Current Stock (${data?.current_stock.length ?? 0})` },
                { k: "low", label: `Low Stock (${data?.low_stock_items.length ?? 0})` },
                { k: "receipts", label: `Purchase Receipts (${data?.purchase_receipts.length ?? 0})` },
                { k: "adjustments", label: `Adjustments (${data?.adjustments.length ?? 0})` },
              ] as const
            ).map((t) => (
              <button
                key={t.k}
                type="button"
                onClick={() => setTab(t.k)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold ${
                  tab === t.k
                    ? "bg-primary text-primary-foreground"
                    : "bg-card border text-muted-foreground hover:text-foreground"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 text-xs">
            <Input
              type="date"
              className="h-9 w-40"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
            <span className="text-muted-foreground">to</span>
            <Input
              type="date"
              className="h-9 w-40"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </div>
        </div>

        {(tab === "current" || tab === "low") && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <FileText className="h-4 w-4 text-primary" />
                {tab === "low" ? "Low-Stock Alert Report" : "Current Stock Valuation & Position Report"}
              </CardTitle>
              <CardDescription>
                Derived directly from physical inventory balances and open FIFO cost lots.
              </CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="py-2 pr-3">Code / Name</th>
                    <th className="py-2 pr-3">Category</th>
                    <th className="py-2 pr-3 text-right">Physical</th>
                    <th className="py-2 pr-3 text-right">Reserved</th>
                    <th className="py-2 pr-3 text-right">Available</th>
                    <th className="py-2 pr-3 text-right">Reorder Threshold</th>
                    <th className="py-2 text-right">Open Lot Value</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {(tab === "low" ? data?.low_stock_items ?? [] : data?.current_stock ?? []).map((row) => (
                    <tr key={`${row.item_type}-${row.item_id}`}>
                      <td className="py-3 pr-3">
                        <div className="font-semibold flex items-center gap-2">
                          {row.name}
                          {row.is_low_stock && <Badge variant="warning">Low</Badge>}
                        </div>
                        <div className="font-mono text-xs text-muted-foreground">{row.code}</div>
                      </td>
                      <td className="py-3 pr-3 text-xs">{row.item_category.replaceAll("_", " ")}</td>
                      <td className="py-3 pr-3 text-right tabular-nums">
                        {formatDisplayQty(row.physical_qty_base, row.display_uom, row.display_factor)}
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums text-amber-700">
                        {formatDisplayQty(row.reserved_qty_base, row.display_uom, row.display_factor)}
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums font-bold">
                        {formatDisplayQty(row.available_qty_base, row.display_uom, row.display_factor)}
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums text-xs text-muted-foreground">
                        {formatDisplayQty(row.reorder_level_base, row.display_uom, row.display_factor)}
                      </td>
                      <td className="py-3 text-right tabular-nums font-medium">
                        {formatInrFromPaisa(row.open_lot_value_paisa)}
                      </td>
                    </tr>
                  ))}
                  {(tab === "low" ? data?.low_stock_items ?? [] : data?.current_stock ?? []).length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-muted-foreground">
                        No items to display.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}

        {tab === "receipts" && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Purchase Receipt Item Register</CardTitle>
              <CardDescription>Line-by-line accepted, rejected, and batch details per receipt</CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="py-2 pr-3">GRN # / Date</th>
                    <th className="py-2 pr-3">Supplier &amp; PO</th>
                    <th className="py-2 pr-3">Material</th>
                    <th className="py-2 pr-3 text-right">Received / Rej / Acc</th>
                    <th className="py-2 pr-3 text-right">Base Posted</th>
                    <th className="py-2 pr-3 text-right">Total (INR)</th>
                    <th className="py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {(data?.purchase_receipts ?? []).map((r, i) => (
                    <tr key={`${r.receipt_id}-${r.material_code}-${i}`}>
                      <td className="py-3 pr-3 text-xs">
                        <div className="font-mono font-semibold">{r.receipt_number}</div>
                        <div className="text-muted-foreground">{formatOrderDate(r.receipt_date)}</div>
                      </td>
                      <td className="py-3 pr-3 text-xs">
                        <div className="font-medium">{r.supplier_name}</div>
                        <div className="text-muted-foreground">{r.po_number ?? "Standalone"}</div>
                      </td>
                      <td className="py-3 pr-3 text-xs">
                        <div className="font-medium">{r.material_name}</div>
                        <div className="font-mono text-muted-foreground">{r.batch_code ?? "No batch"}</div>
                      </td>
                      <td className="py-3 pr-3 text-right text-xs tabular-nums">
                        {r.received_qty_entered} / {r.rejected_qty_entered} /{" "}
                        <strong className="text-emerald-700">
                          {r.accepted_qty_entered} {r.entered_uom}
                        </strong>
                      </td>
                      <td className="py-3 pr-3 text-right text-xs tabular-nums">
                        {formatBaseQty(r.accepted_qty_base, r.base_uom)}
                      </td>
                      <td className="py-3 pr-3 text-right font-semibold tabular-nums">
                        {formatInrFromPaisa(r.line_total_paisa)}
                      </td>
                      <td className="py-3">
                        <StatusBadge status={r.status} />
                      </td>
                    </tr>
                  ))}
                  {(data?.purchase_receipts ?? []).length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-muted-foreground">
                        No purchase receipts in the selected range.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}

        {tab === "adjustments" && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Stock Adjustment Audit Register</CardTitle>
              <CardDescription>All wastage, supplier return, and physical count vouchers</CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="py-2 pr-3">Voucher #</th>
                    <th className="py-2 pr-3">Item / Type</th>
                    <th className="py-2 pr-3 text-right">Delta</th>
                    <th className="py-2 pr-3">Reason</th>
                    <th className="py-2 pr-3">Timestamp</th>
                    <th className="py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {(data?.adjustments ?? []).map((a) => (
                    <tr key={a.id}>
                      <td className="py-3 pr-3 font-mono text-xs font-semibold">{a.adjustment_number}</td>
                      <td className="py-3 pr-3 text-xs">
                        <div className="font-medium">{a.item_name}</div>
                        <div className="text-muted-foreground">{a.adjustment_type}</div>
                      </td>
                      <td className="py-3 pr-3 text-right font-mono text-xs tabular-nums">
                        {a.entered_qty} {a.entered_uom} ({formatBaseQty(a.delta_qty_base, a.base_uom)})
                      </td>
                      <td className="py-3 pr-3 text-xs max-w-xs">{a.reason}</td>
                      <td className="py-3 pr-3 text-xs text-muted-foreground">
                        {formatDateTimeIst(a.posted_at ?? a.requested_at)}
                      </td>
                      <td className="py-3">
                        <StatusBadge status={a.status} />
                      </td>
                    </tr>
                  ))}
                  {(data?.adjustments ?? []).length === 0 && (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-muted-foreground">
                        No stock adjustments recorded.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>
        )}
      </div>
    </DesktopAdminLayout>
  );
}

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { BarChart3, Download } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { formatOrderDate } from "@/lib/money";

export function AdminProductionVarianceReportPage() {
  const reportQuery = useQuery({
    queryKey: ["production-variance-report"],
    queryFn: () => api.getProductionVarianceReport(),
  });

  const rows = reportQuery.data ?? [];

  const exportCsv = () => {
    const header =
      "RunNumber,RunDate,SKU,BOMVersion,BatchMultiplier,ExpectedPackets,GoodOutput,RejectedOutput,YieldVariancePct,OilVariancePct,DamagedPackaging,FlaggedCount,Status";
    const lines = rows.map(
      (r) =>
        `"${r.run_number}","${r.run_date}","${r.sku_code}",v${r.bom_version_no},${r.batch_multiplier},${r.expected_output_pkts},${r.actual_good_output_pkts},${r.rejected_output_pkts},${r.yield_variance_pct ?? ""},${r.oil_variance_pct ?? ""},${r.damaged_packaging_qty},${r.flagged_count},"${r.status}"`
    );
    const blob = new Blob([[header, ...lines].join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "production-variance-report.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <DesktopAdminLayout
      title="Production & Variance Report"
      subtitle="Audit-ready register of posted production batches, yield efficiency, raw variance, and packaging loss"
      actions={
        <Button variant="outline" onClick={exportCsv} disabled={rows.length === 0}>
          <Download className="h-4 w-4" />
          Export CSV
        </Button>
      }
    >
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-primary" />
            Posted Production Runs ({rows.length})
          </CardTitle>
          <CardDescription>
            Every figure reconciles directly against posted production run logs and inventory ledger entries.
          </CardDescription>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="py-2 pr-3">Run # / Date</th>
                <th className="py-2 pr-3">Product (BOM)</th>
                <th className="py-2 pr-3 text-right">Expected / Good</th>
                <th className="py-2 pr-3 text-right">Yield Var %</th>
                <th className="py-2 pr-3 text-right">Oil Var %</th>
                <th className="py-2 pr-3 text-right">Damaged Pkg</th>
                <th className="py-2 pr-3 text-right">Flags</th>
                <th className="py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((r) => (
                <tr key={r.run_id} className="hover:bg-secondary/30">
                  <td className="py-3 pr-3">
                    <Link
                      to={`/admin/production/runs/${r.run_id}`}
                      className="font-mono font-bold text-primary hover:underline"
                    >
                      {r.run_number}
                    </Link>
                    <div className="text-xs text-muted-foreground">{formatOrderDate(r.run_date)}</div>
                  </td>
                  <td className="py-3 pr-3">
                    <div className="font-medium">{r.display_name}</div>
                    <div className="text-xs text-muted-foreground">
                      BOM v{r.bom_version_no} · {Number(r.batch_multiplier)}×
                    </div>
                  </td>
                  <td className="py-3 pr-3 text-right tabular-nums text-xs">
                    {r.expected_output_pkts} /{" "}
                    <strong className="text-emerald-700">{r.actual_good_output_pkts} pkts</strong>
                    {r.rejected_output_pkts > 0 && (
                      <div className="text-red-700">{r.rejected_output_pkts} rejected</div>
                    )}
                  </td>
                  <td className="py-3 pr-3 text-right font-mono tabular-nums font-semibold">
                    {r.yield_variance_pct !== null ? `${r.yield_variance_pct}%` : "—"}
                  </td>
                  <td className="py-3 pr-3 text-right font-mono tabular-nums font-semibold">
                    {r.oil_variance_pct !== null
                      ? `${Number(r.oil_variance_pct) > 0 ? "+" : ""}${r.oil_variance_pct}%`
                      : "—"}
                  </td>
                  <td className="py-3 pr-3 text-right tabular-nums text-xs">
                    {Number(r.damaged_packaging_qty)} pcs
                  </td>
                  <td className="py-3 pr-3 text-right">
                    {r.flagged_count > 0 ? (
                      <Badge variant="warning">{r.flagged_count} flagged</Badge>
                    ) : (
                      <Badge variant="secondary">0</Badge>
                    )}
                  </td>
                  <td className="py-3">
                    <StatusBadge status={r.status} />
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-muted-foreground">
                    No posted production runs yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </DesktopAdminLayout>
  );
}

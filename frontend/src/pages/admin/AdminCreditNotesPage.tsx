import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { FileSpreadsheet } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { formatInrFromPaisa, formatOrderDate } from "@/lib/money";

export function AdminCreditNotesPage() {
  const cnQuery = useQuery({
    queryKey: ["credit-notes"],
    queryFn: () => api.getCreditNotes(),
    refetchInterval: 15_000,
  });

  const rows = cnQuery.data ?? [];

  return (
    <DesktopAdminLayout
      title="GST Credit Notes Register"
      subtitle="Controlled invoice cancellations, sales returns, and tax reversals preserving gap-free FY audit history"
    >
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileSpreadsheet className="h-4 w-4 text-primary" />
            Credit Notes ({rows.length})
          </CardTitle>
          <CardDescription>
            To issue a Credit Note, open any issued GST invoice and select &ldquo;Issue Credit Note / Cancel&rdquo;.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-y bg-secondary/40 text-left text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-2.5">CN Number</th>
                <th className="px-3 py-2.5">Original Invoice</th>
                <th className="px-3 py-2.5">Customer</th>
                <th className="px-3 py-2.5">Type &amp; Status</th>
                <th className="px-3 py-2.5 text-right">Taxable Rev.</th>
                <th className="px-3 py-2.5 text-right">GST Rev.</th>
                <th className="px-3 py-2.5 text-right">Total Reversed</th>
                <th className="px-4 py-2.5">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((cn) => {
                const taxRev = cn.cgst_reversed_paisa + cn.sgst_reversed_paisa + cn.igst_reversed_paisa;
                return (
                  <tr key={cn.id} className="hover:bg-secondary/20">
                    <td className="px-4 py-3 font-mono text-xs">
                      <div className="font-bold">{cn.cn_number ?? cn.draft_ref}</div>
                      <div className="font-sans text-muted-foreground">{formatOrderDate(cn.issue_date)}</div>
                    </td>
                    <td className="px-3 py-3 font-mono text-xs">
                      <Link
                        to={`/admin/billing/invoices/${cn.original_invoice_id}`}
                        className="font-bold text-primary hover:underline"
                      >
                        {cn.original_invoice_number}
                      </Link>
                    </td>
                    <td className="px-3 py-3 font-medium">{cn.customer_name}</td>
                    <td className="px-3 py-3 space-y-1">
                      <div className="text-xs font-semibold">{cn.note_type}</div>
                      <StatusBadge status={cn.status} />
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">
                      {formatInrFromPaisa(cn.taxable_reversed_paisa)}
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">{formatInrFromPaisa(taxRev)}</td>
                    <td className="px-3 py-3 text-right font-bold text-red-700 tabular-nums">
                      {formatInrFromPaisa(cn.total_reversed_paisa)}
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground max-w-xs">{cn.reason}</td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-muted-foreground">
                    No credit notes issued yet.
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

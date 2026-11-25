import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { CheckCircle2, FileCheck2, FileText, Receipt, Search } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatInrFromPaisa, formatOrderDate } from "@/lib/money";

export function AdminBillingDashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const canOperate = user?.role_code === "FACTORY_ADMIN";

  const [docStatus, setDocStatus] = useState("");
  const [dispatchStatus, setDispatchStatus] = useState("");
  const [search, setSearch] = useState("");
  const [applyRoundOff, setApplyRoundOff] = useState(false);
  const [banner, setBanner] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  const dashQuery = useQuery({
    queryKey: ["billing-dashboard", docStatus, dispatchStatus, search],
    queryFn: () =>
      api.getBillingDashboard({
        docStatus: docStatus || undefined,
        dispatchStatus: dispatchStatus || undefined,
        search: search.trim() || undefined,
      }),
    refetchInterval: 15_000,
  });

  const generateMutation = useMutation({
    mutationFn: (opts: { salesOrderId: number; issueImmediately: boolean }) =>
      api.createInvoice({
        sales_order_id: opts.salesOrderId,
        apply_round_off: applyRoundOff,
        issue_immediately: opts.issueImmediately,
      }),
    onSuccess: (inv) => {
      queryClient.invalidateQueries({ queryKey: ["billing-dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["admin-orders"] });
      setBanner({
        kind: "success",
        msg: inv.invoice_number
          ? `Issued statutory GST invoice ${inv.invoice_number}.`
          : `Created draft invoice ${inv.draft_ref} ready for Admin verification.`,
      });
      navigate(`/admin/billing/invoices/${inv.id}`);
    },
    onError: (err) => {
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Failed to generate GST invoice.",
      });
    },
  });

  const data = dashQuery.data;

  return (
    <DesktopAdminLayout
      title="GST Billing & Invoice Dashboard"
      subtitle="Generate, verify, and issue sequential financial-year GST tax invoices from approved sales orders"
      actions={
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to="/admin/billing/credit-notes">Credit Notes</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link to="/admin/dispatch">Dispatch Queue</Link>
          </Button>
        </div>
      }
    >
      <div className="space-y-6">
        {banner && (
          <div
            className={`rounded-xl border px-4 py-3 text-sm font-medium ${
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
            <CardContent className="p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Ready for Billing
              </div>
              <div className="mt-1 text-2xl font-bold">{data?.ready_for_billing_count ?? 0}</div>
              <div className="text-xs text-muted-foreground">
                Drafts pending issue: {data?.draft_invoices_count ?? 0}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Issued Invoices Total
              </div>
              <div className="mt-1 text-2xl font-bold text-primary tabular-nums">
                {formatInrFromPaisa(data?.total_invoiced_paisa ?? 0)}
              </div>
              <div className="text-xs text-muted-foreground">
                {data?.issued_invoices_count ?? 0} issued · {data?.cancelled_invoices_count ?? 0} cancelled by CN
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Outward GST Liability
              </div>
              <div className="mt-1 text-2xl font-bold tabular-nums">
                {formatInrFromPaisa(
                  (data?.total_cgst_paisa ?? 0) +
                    (data?.total_sgst_paisa ?? 0) +
                    (data?.total_igst_paisa ?? 0)
                )}
              </div>
              <div className="text-xs text-muted-foreground tabular-nums">
                CGST+SGST {formatInrFromPaisa((data?.total_cgst_paisa ?? 0) + (data?.total_sgst_paisa ?? 0))} · IGST{" "}
                {formatInrFromPaisa(data?.total_igst_paisa ?? 0)}
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Issued Outstanding AR
              </div>
              <div className="mt-1 text-2xl font-bold text-amber-700 tabular-nums">
                {formatInrFromPaisa(data?.total_outstanding_paisa ?? 0)}
              </div>
              <div className="text-xs text-muted-foreground tabular-nums">
                Credited via CN: {formatInrFromPaisa(data?.total_credited_paisa ?? 0)}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Orders Ready for Billing (Billing Staff Queue) */}
        <Card>
          <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <FileCheck2 className="h-4 w-4 text-primary" />
                Orders Ready for Billing ({data?.ready_orders.length ?? 0})
              </CardTitle>
              <CardDescription>
                Approved orders with reserved stock awaiting GST invoice generation (tax calculated strictly server-side).
              </CardDescription>
            </div>
            {canOperate && (
              <label className="flex items-center gap-2 text-xs font-medium text-muted-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={applyRoundOff}
                  onChange={(e) => setApplyRoundOff(e.target.checked)}
                />
                Apply nearest-rupee commercial round-off
              </label>
            )}
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-y bg-secondary/40 text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2.5">Order #</th>
                  <th className="px-3 py-2.5">Customer &amp; GSTIN</th>
                  <th className="px-3 py-2.5">Place of Supply</th>
                  <th className="px-3 py-2.5">Tax Mode</th>
                  <th className="px-3 py-2.5 text-right">Qty</th>
                  <th className="px-3 py-2.5 text-right">Taxable</th>
                  <th className="px-3 py-2.5 text-right">Est. Grand Total</th>
                  <th className="px-4 py-2.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {(data?.ready_orders ?? []).map((ord) => (
                  <tr key={ord.sales_order_id} className="hover:bg-secondary/20">
                    <td className="px-4 py-3 font-mono text-xs font-bold">
                      <Link to={`/admin/orders/${ord.sales_order_id}`} className="text-primary hover:underline">
                        {ord.order_number}
                      </Link>
                      <div className="font-sans font-normal text-muted-foreground">
                        {formatOrderDate(ord.order_date)}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="font-semibold">{ord.customer_name}</div>
                      <div className="font-mono text-xs text-muted-foreground">
                        {ord.customer_gstin ?? "Unregistered B2C"}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-xs">
                      {ord.place_of_supply_state_name} ({ord.place_of_supply_state_code})
                    </td>
                    <td className="px-3 py-3">
                      <StatusBadge status={ord.supply_type} />
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">{ord.total_packets} pkts</td>
                    <td className="px-3 py-3 text-right tabular-nums">
                      {formatInrFromPaisa(ord.taxable_total_paisa)}
                    </td>
                    <td className="px-3 py-3 text-right font-bold tabular-nums">
                      {formatInrFromPaisa(ord.estimated_grand_total_paisa)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {canOperate ? (
                        <div className="flex justify-end gap-1.5">
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={generateMutation.isPending}
                            onClick={() =>
                              generateMutation.mutate({
                                salesOrderId: ord.sales_order_id,
                                issueImmediately: false,
                              })
                            }
                          >
                            Generate Draft
                          </Button>
                          <Button
                            size="sm"
                            disabled={generateMutation.isPending}
                            onClick={() =>
                              generateMutation.mutate({
                                salesOrderId: ord.sales_order_id,
                                issueImmediately: true,
                              })
                            }
                          >
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Issue GST Invoice
                          </Button>
                        </div>
                      ) : (
                        <Badge variant="outline">View Only</Badge>
                      )}
                    </td>
                  </tr>
                ))}
                {(data?.ready_orders ?? []).length === 0 && (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-muted-foreground">
                      No unbilled approved orders waiting. Approve an order in Incoming Orders first.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {/* Invoices Register */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Receipt className="h-4 w-4 text-primary" />
              GST Invoices ({data?.invoices.length ?? 0})
            </CardTitle>
            <div className="mt-2 grid gap-3 sm:grid-cols-3">
              <div className="relative">
                <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search INV #, draft ref, customer..."
                  className="pl-9"
                />
              </div>
              <select
                className="flex h-10 rounded-md border border-input bg-background px-3 text-sm"
                value={docStatus}
                onChange={(e) => setDocStatus(e.target.value)}
              >
                <option value="">All Invoice Statuses</option>
                <option value="DRAFT">Draft</option>
                <option value="ISSUED">Issued</option>
                <option value="CANCELLED_BY_CN">Cancelled by Credit Note</option>
              </select>
              <select
                className="flex h-10 rounded-md border border-input bg-background px-3 text-sm"
                value={dispatchStatus}
                onChange={(e) => setDispatchStatus(e.target.value)}
              >
                <option value="">All Dispatch States</option>
                <option value="PENDING">Pending Dispatch</option>
                <option value="PARTIAL">Partially Dispatched</option>
                <option value="DISPATCHED">Dispatched</option>
              </select>
            </div>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-y bg-secondary/40 text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2.5">Invoice #</th>
                  <th className="px-3 py-2.5">Order #</th>
                  <th className="px-3 py-2.5">Customer &amp; POS</th>
                  <th className="px-3 py-2.5">Doc / Dispatch</th>
                  <th className="px-3 py-2.5 text-right">Taxable</th>
                  <th className="px-3 py-2.5 text-right">GST</th>
                  <th className="px-3 py-2.5 text-right">Grand Total</th>
                  <th className="px-4 py-2.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {(data?.invoices ?? []).map((inv) => {
                  const gstTotal = inv.cgst_total_paisa + inv.sgst_total_paisa + inv.igst_total_paisa;
                  return (
                    <tr key={inv.id} className="hover:bg-secondary/20">
                      <td className="px-4 py-3 font-mono text-xs">
                        <Link to={`/admin/billing/invoices/${inv.id}`} className="font-bold text-primary hover:underline">
                          {inv.invoice_number ?? inv.draft_ref}
                        </Link>
                        <div className="font-sans text-muted-foreground">
                          FY {inv.financial_year} · {formatOrderDate(inv.invoice_date)}
                        </div>
                      </td>
                      <td className="px-3 py-3 font-mono text-xs">
                        <Link to={`/admin/orders/${inv.sales_order_id}`} className="hover:underline">
                          {inv.order_number}
                        </Link>
                      </td>
                      <td className="px-3 py-3">
                        <div className="font-medium">{inv.customer_name}</div>
                        <div className="text-xs text-muted-foreground">
                          {inv.place_of_supply_state_name} ({inv.place_of_supply_state_code}) · {inv.supply_type}
                        </div>
                      </td>
                      <td className="px-3 py-3 space-x-1">
                        <StatusBadge status={inv.doc_status} />
                        <StatusBadge status={inv.dispatch_status} />
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums">
                        {formatInrFromPaisa(inv.taxable_total_paisa)}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums text-xs">
                        <div>{formatInrFromPaisa(gstTotal)}</div>
                        <div className="text-muted-foreground">
                          {inv.supply_type === "INTRA_STATE" ? "CGST+SGST" : "IGST"}
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right font-bold tabular-nums">
                        {formatInrFromPaisa(inv.grand_total_paisa)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button size="sm" variant="outline" asChild>
                          <Link to={`/admin/billing/invoices/${inv.id}`}>
                            <FileText className="h-3.5 w-3.5" />
                            View
                          </Link>
                        </Button>
                      </td>
                    </tr>
                  );
                })}
                {(data?.invoices ?? []).length === 0 && (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-muted-foreground">
                      No invoices recorded yet.
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

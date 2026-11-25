import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { CheckCircle2, PackageCheck, Truck } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api, type InvoiceDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatOrderDate } from "@/lib/money";

export function AdminDispatchDashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const canOperate = user?.role_code === "FACTORY_ADMIN";

  const [statusFilter, setStatusFilter] = useState("");
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<number | null>(() => {
    const raw = searchParams.get("invoice_id");
    return raw ? Number(raw) : null;
  });
  const [qtyByItem, setQtyByItem] = useState<Record<number, number>>({});
  const [transporter, setTransporter] = useState("Kaveri Express Logistics");
  const [vehicleNumber, setVehicleNumber] = useState("TN-45-AB-2026");
  const [lrNumber, setLrNumber] = useState("");
  const [packingRemarks, setPackingRemarks] = useState("Cartons & batch seals verified");
  const [postNow, setPostNow] = useState(true);
  const [banner, setBanner] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  const dashQuery = useQuery({
    queryKey: ["dispatch-dashboard", statusFilter],
    queryFn: () => api.getDispatchDashboard(statusFilter || undefined),
    refetchInterval: 15_000,
  });

  const selectedInvQuery = useQuery<InvoiceDetail>({
    queryKey: ["dispatch-selected-invoice", selectedInvoiceId],
    queryFn: () => api.getInvoiceDetail(selectedInvoiceId!),
    enabled: Boolean(selectedInvoiceId),
  });

  useEffect(() => {
    const inv = selectedInvQuery.data;
    if (!inv) return;
    const init: Record<number, number> = {};
    inv.items.forEach((it) => {
      if (it.remaining_dispatch_qty_pkts > 0) {
        init[it.id] = it.remaining_dispatch_qty_pkts;
      }
    });
    setQtyByItem(init);
  }, [selectedInvQuery.data?.id]);

  const createDspMutation = useMutation({
    mutationFn: () => {
      const inv = selectedInvQuery.data!;
      const items = inv.items
        .map((it) => ({
          invoice_item_id: it.id,
          dispatched_qty_pkts: Number(qtyByItem[it.id] ?? 0),
        }))
        .filter((x) => x.dispatched_qty_pkts > 0);
      return api.createDispatch({
        invoice_id: inv.id,
        transporter_name: transporter.trim() || null,
        vehicle_number: vehicleNumber.trim() || null,
        lr_number: lrNumber.trim() || null,
        packing_verified: true,
        packing_remarks: packingRemarks.trim() || null,
        post_immediately: postNow,
        items,
      });
    },
    onSuccess: (dsp) => {
      queryClient.invalidateQueries({ queryKey: ["dispatch-dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["billing-dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-overview"] });
      setSelectedInvoiceId(null);
      setBanner({
        kind: "success",
        msg: `Dispatch ${dsp.dispatch_number} (${dsp.status}) recorded cleanly.`,
      });
      navigate(`/admin/dispatch/${dsp.id}`);
    },
    onError: (err) => {
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Failed to record dispatch.",
      });
    },
  });

  const data = dashQuery.data;
  const selInv = selectedInvQuery.data;

  return (
    <DesktopAdminLayout
      title="Dispatch Queue & Delivery Tracking"
      subtitle="Verify finished goods, create partial or full dispatches against issued GST invoices, deduct ledger stock atomically, and track deliveries"
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

        {/* KPI Strip */}
        <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {[
            { label: "Ready Invoices", val: data?.ready_for_dispatch_invoices_count ?? 0 },
            { label: "Created", val: data?.created_count ?? 0 },
            { label: "Packing Ready", val: data?.ready_count ?? 0 },
            { label: "Dispatched", val: data?.dispatched_count ?? 0 },
            { label: "In Transit / Deliv.", val: (data?.in_transit_count ?? 0) + (data?.delivered_count ?? 0) },
            { label: "Exceptions", val: data?.exception_count ?? 0 },
          ].map((k) => (
            <Card key={k.label}>
              <CardContent className="p-4">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {k.label}
                </div>
                <div className="mt-1 text-2xl font-bold tabular-nums">{k.val}</div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Create Dispatch Form Drawer / Panel */}
        {selInv && canOperate && (
          <Card className="border-primary/40">
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-base">
                  Create Dispatch for {selInv.invoice_number} ({selInv.customer_name})
                </CardTitle>
                <CardDescription>
                  Adjust quantities below to execute a partial dispatch (e.g. 100 of 150 pkts) or leave full remaining quantities.
                </CardDescription>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setSelectedInvoiceId(null)}>
                Cancel
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-4">
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">Transporter</label>
                  <Input value={transporter} onChange={(e) => setTransporter(e.target.value)} className="mt-1" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">Vehicle Number</label>
                  <Input value={vehicleNumber} onChange={(e) => setVehicleNumber(e.target.value)} className="mt-1" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">LR / Challan Ref</label>
                  <Input
                    value={lrNumber}
                    onChange={(e) => setLrNumber(e.target.value)}
                    placeholder="LR-2026-01"
                    className="mt-1"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">Packing Notes</label>
                  <Input value={packingRemarks} onChange={(e) => setPackingRemarks(e.target.value)} className="mt-1" />
                </div>
              </div>

              <div className="rounded-lg border overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-secondary/40 text-left text-xs uppercase text-muted-foreground">
                      <th className="px-4 py-2">Product SKU</th>
                      <th className="px-3 py-2 text-right">Invoiced</th>
                      <th className="px-3 py-2 text-right">Already Dispatched</th>
                      <th className="px-3 py-2 text-right">Remaining</th>
                      <th className="px-4 py-2 text-right">Dispatch Now (Pkts)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {selInv.items.map((it) => (
                      <tr key={it.id}>
                        <td className="px-4 py-2.5">
                          <div className="font-semibold">{it.description}</div>
                          <div className="font-mono text-xs text-muted-foreground">{it.sku_code}</div>
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{it.qty_pkts}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{it.dispatched_qty_pkts}</td>
                        <td className="px-3 py-2.5 text-right font-semibold tabular-nums">
                          {it.remaining_dispatch_qty_pkts}
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <Input
                            type="number"
                            min={0}
                            max={it.remaining_dispatch_qty_pkts}
                            className="ml-auto w-28 text-right h-8"
                            value={qtyByItem[it.id] ?? 0}
                            onChange={(e) =>
                              setQtyByItem((prev) => ({
                                ...prev,
                                [it.id]: Math.max(0, parseInt(e.target.value, 10) || 0),
                              }))
                            }
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3">
                <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
                  <input type="checkbox" checked={postNow} onChange={(e) => setPostNow(e.target.checked)} />
                  Post dispatch immediately &amp; deduct FG inventory (`DISPATCH_OUT`)
                </label>
                <Button disabled={createDspMutation.isPending} onClick={() => createDspMutation.mutate()}>
                  <CheckCircle2 className="h-4 w-4" />
                  {createDspMutation.isPending
                    ? "Processing..."
                    : postNow
                    ? "Create & Post Dispatch (Deduct Stock)"
                    : "Create Dispatch Draft"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Invoices Ready for Dispatch */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <PackageCheck className="h-4 w-4 text-primary" />
              Issued Invoices Ready for Dispatch ({data?.ready_invoices.length ?? 0})
            </CardTitle>
            <CardDescription>
              Only statutory ISSUED GST invoices can enter the dispatch queue. Remaining quantities reflect all prior partial dispatches.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-y bg-secondary/40 text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2.5">Invoice #</th>
                  <th className="px-3 py-2.5">Order #</th>
                  <th className="px-3 py-2.5">Customer</th>
                  <th className="px-3 py-2.5">Status</th>
                  <th className="px-3 py-2.5 text-right">Invoiced</th>
                  <th className="px-3 py-2.5 text-right">Dispatched</th>
                  <th className="px-3 py-2.5 text-right">Remaining</th>
                  <th className="px-3 py-2.5">FG Physical Stock</th>
                  <th className="px-4 py-2.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {(data?.ready_invoices ?? []).map((inv) => (
                  <tr key={inv.invoice_id} className="hover:bg-secondary/20">
                    <td className="px-4 py-3 font-mono text-xs font-bold">
                      <Link to={`/admin/billing/invoices/${inv.invoice_id}`} className="text-primary hover:underline">
                        {inv.invoice_number}
                      </Link>
                    </td>
                    <td className="px-3 py-3 font-mono text-xs">{inv.order_number}</td>
                    <td className="px-3 py-3 font-medium">{inv.customer_name}</td>
                    <td className="px-3 py-3">
                      <StatusBadge status={inv.dispatch_status} />
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">{inv.total_qty_pkts}</td>
                    <td className="px-3 py-3 text-right tabular-nums">{inv.dispatched_qty_pkts}</td>
                    <td className="px-3 py-3 text-right font-bold tabular-nums">{inv.remaining_qty_pkts}</td>
                    <td className="px-3 py-3">
                      {inv.fg_on_hand_sufficient ? (
                        <Badge variant="success">Covered</Badge>
                      ) : (
                        <Badge variant="destructive">Insufficient FG</Badge>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {canOperate ? (
                        <Button size="sm" onClick={() => setSelectedInvoiceId(inv.invoice_id)}>
                          <Truck className="h-3.5 w-3.5" />
                          Prepare Dispatch
                        </Button>
                      ) : (
                        <Badge variant="outline">View Only</Badge>
                      )}
                    </td>
                  </tr>
                ))}
                {(data?.ready_invoices ?? []).length === 0 && (
                  <tr>
                    <td colSpan={9} className="py-8 text-center text-muted-foreground">
                      No pending invoices awaiting dispatch.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {/* Dispatch & Delivery History Table */}
        <Card>
          <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <CardTitle className="text-base">All Dispatches &amp; Delivery Tracking</CardTitle>
            </div>
            <select
              className="flex h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">All Dispatch / Delivery States</option>
              <option value="CREATED">Created</option>
              <option value="READY_FOR_DISPATCH">Ready for Dispatch</option>
              <option value="DISPATCHED">Dispatched</option>
              <option value="IN_TRANSIT">In Transit</option>
              <option value="DELIVERED">Delivered</option>
              <option value="DELIVERY_EXCEPTION">Delivery Exception</option>
            </select>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-y bg-secondary/40 text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-2.5">Dispatch #</th>
                  <th className="px-3 py-2.5">Invoice &amp; Order</th>
                  <th className="px-3 py-2.5">Customer</th>
                  <th className="px-3 py-2.5">Vehicle / Transporter</th>
                  <th className="px-3 py-2.5 text-right">Dispatched</th>
                  <th className="px-3 py-2.5 text-right">Delivered Qty</th>
                  <th className="px-3 py-2.5">Status</th>
                  <th className="px-4 py-2.5 text-right">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {(data?.dispatches ?? []).map((dsp) => (
                  <tr key={dsp.id} className="hover:bg-secondary/20">
                    <td className="px-4 py-3 font-mono text-xs font-bold">
                      <Link to={`/admin/dispatch/${dsp.id}`} className="text-primary hover:underline">
                        {dsp.dispatch_number}
                      </Link>
                      <div className="font-sans font-normal text-muted-foreground">
                        {formatOrderDate(dsp.dispatch_date)}
                      </div>
                    </td>
                    <td className="px-3 py-3 font-mono text-xs">
                      <Link to={`/admin/billing/invoices/${dsp.invoice_id}`} className="hover:underline">
                        {dsp.invoice_number}
                      </Link>
                      <div className="text-muted-foreground">{dsp.order_number}</div>
                    </td>
                    <td className="px-3 py-3 font-medium">{dsp.customer_name}</td>
                    <td className="px-3 py-3 text-xs">
                      <div>{dsp.vehicle_number ?? "—"}</div>
                      <div className="text-muted-foreground">{dsp.transporter_name ?? "—"}</div>
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">{dsp.total_dispatched_pkts} pkts</td>
                    <td className="px-3 py-3 text-right tabular-nums">
                      {dsp.status === "DELIVERED" || dsp.status === "DELIVERY_EXCEPTION"
                        ? `${dsp.total_received_pkts} pkts`
                        : "—"}
                    </td>
                    <td className="px-3 py-3">
                      <StatusBadge status={dsp.status} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Button size="sm" variant="outline" asChild>
                        <Link to={`/admin/dispatch/${dsp.id}`}>Track / Manage</Link>
                      </Button>
                    </td>
                  </tr>
                ))}
                {(data?.dispatches ?? []).length === 0 && (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-muted-foreground">
                      No dispatches match this filter.
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

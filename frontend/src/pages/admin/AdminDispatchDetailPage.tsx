import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Clock, PackageCheck, Printer, Truck } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDateTimeIst, formatOrderDate } from "@/lib/money";

export function AdminDispatchDetailPage() {
  const { dispatchId } = useParams<{ dispatchId: string }>();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canOperate = user?.role_code === "FACTORY_ADMIN";

  const [transporter, setTransporter] = useState("");
  const [vehicleNo, setVehicleNo] = useState("");
  const [lrNo, setLrNo] = useState("");
  const [actionRemarks, setActionRemarks] = useState("");
  const [exceptionReason, setExceptionReason] = useState("");
  const [receivedByItem, setReceivedByItem] = useState<Record<number, number>>({});
  const [banner, setBanner] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  const dspQuery = useQuery({
    queryKey: ["dispatch-detail", dispatchId],
    queryFn: () => api.getDispatchDetail(Number(dispatchId)),
    enabled: Boolean(dispatchId),
    refetchInterval: 15_000,
  });

  useEffect(() => {
    const d = dspQuery.data;
    if (!d) return;
    setTransporter(d.transporter_name ?? "");
    setVehicleNo(d.vehicle_number ?? "");
    setLrNo(d.lr_number ?? "");
    const recMap: Record<number, number> = {};
    d.items.forEach((it) => {
      recMap[it.id] = it.received_qty_pkts ?? it.dispatched_qty_pkts;
    });
    setReceivedByItem(recMap);
  }, [dspQuery.data?.id, dspQuery.data?.version]);

  const readyMutation = useMutation({
    mutationFn: () =>
      api.markDispatchReady(Number(dispatchId), {
        remarks: actionRemarks.trim() || null,
        transporter_name: transporter.trim() || null,
        vehicle_number: vehicleNo.trim() || null,
        lr_number: lrNo.trim() || null,
        expected_version: dspQuery.data?.version,
      }),
    onSuccess: (d) => {
      queryClient.setQueryData(["dispatch-detail", dispatchId], d);
      queryClient.invalidateQueries({ queryKey: ["dispatch-dashboard"] });
      setBanner({ kind: "success", msg: `Dispatch ${d.dispatch_number} marked READY_FOR_DISPATCH.` });
    },
    onError: (err) => {
      setBanner({ kind: "error", msg: err instanceof ApiClientError ? err.message : "Failed to update dispatch." });
    },
  });

  const postMutation = useMutation({
    mutationFn: () =>
      api.postDispatch(Number(dispatchId), {
        remarks: actionRemarks.trim() || null,
        transporter_name: transporter.trim() || null,
        vehicle_number: vehicleNo.trim() || null,
        lr_number: lrNo.trim() || null,
        expected_version: dspQuery.data?.version,
      }),
    onSuccess: (d) => {
      queryClient.setQueryData(["dispatch-detail", dispatchId], d);
      queryClient.invalidateQueries({ queryKey: ["dispatch-dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-overview"] });
      queryClient.invalidateQueries({ queryKey: ["invoice-detail", String(d.invoice_id)] });
      setBanner({
        kind: "success",
        msg: `Dispatch ${d.dispatch_number} posted atomically; FG stock deducted via DISPATCH_OUT.`,
      });
    },
    onError: (err) => {
      setBanner({ kind: "error", msg: err instanceof ApiClientError ? err.message : "Failed to post dispatch." });
    },
  });

  const deliveryMutation = useMutation({
    mutationFn: (targetStatus: "IN_TRANSIT" | "DELIVERED" | "DELIVERY_EXCEPTION") => {
      const d = dspQuery.data!;
      return api.updateDeliveryStatus(d.id, {
        target_status: targetStatus,
        remarks: actionRemarks.trim() || null,
        exception_reason: targetStatus === "DELIVERY_EXCEPTION" ? exceptionReason.trim() : null,
        expected_version: d.version,
        items:
          targetStatus === "IN_TRANSIT"
            ? []
            : d.items.map((it) => ({
                dispatch_item_id: it.id,
                received_qty_pkts: Number(receivedByItem[it.id] ?? it.dispatched_qty_pkts),
              })),
      });
    },
    onSuccess: (d) => {
      queryClient.setQueryData(["dispatch-detail", dispatchId], d);
      queryClient.invalidateQueries({ queryKey: ["dispatch-dashboard"] });
      setBanner({ kind: "success", msg: `Delivery status updated to ${d.status}.` });
    },
    onError: (err) => {
      setBanner({ kind: "error", msg: err instanceof ApiClientError ? err.message : "Failed to update delivery." });
    },
  });

  const dsp = dspQuery.data;

  return (
    <DesktopAdminLayout
      title={dsp ? `Dispatch ${dsp.dispatch_number}` : "Dispatch & Delivery Detail"}
      subtitle={dsp ? `${dsp.customer_name} · Invoice ${dsp.invoice_number} · Order ${dsp.order_number}` : "Loading..."}
      actions={
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild>
            <Link to="/admin/dispatch">
              <ArrowLeft className="h-4 w-4" />
              Dispatch Queue
            </Link>
          </Button>
          {dsp && (
            <>
              <Button variant="outline" asChild>
                <Link to={`/admin/billing/invoices/${dsp.invoice_id}`}>Open Invoice {dsp.invoice_number}</Link>
              </Button>
              <Button variant="outline" onClick={() => window.print()}>
                <Printer className="h-4 w-4" />
                Print Challan
              </Button>
            </>
          )}
        </div>
      }
    >
      {dsp && (
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

          {/* Status & Transport Details */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Truck className="h-4 w-4 text-primary" />
                    Dispatch Metadata &amp; Lifecycle
                  </CardTitle>
                  <CardDescription>Dispatch Date: {formatOrderDate(dsp.dispatch_date)}</CardDescription>
                </div>
                <StatusBadge status={dsp.status} />
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-4">
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">Transporter</label>
                  <Input
                    value={transporter}
                    onChange={(e) => setTransporter(e.target.value)}
                    disabled={!canOperate || !["CREATED", "READY_FOR_DISPATCH"].includes(dsp.status)}
                    className="mt-1"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">Vehicle Number</label>
                  <Input
                    value={vehicleNo}
                    onChange={(e) => setVehicleNo(e.target.value)}
                    disabled={!canOperate || !["CREATED", "READY_FOR_DISPATCH"].includes(dsp.status)}
                    className="mt-1"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">LR / Challan Ref</label>
                  <Input
                    value={lrNo}
                    onChange={(e) => setLrNo(e.target.value)}
                    disabled={!canOperate || !["CREATED", "READY_FOR_DISPATCH"].includes(dsp.status)}
                    className="mt-1"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">Remarks</label>
                  <Input
                    value={actionRemarks}
                    onChange={(e) => setActionRemarks(e.target.value)}
                    placeholder="Packing / delivery confirmation note..."
                    className="mt-1"
                  />
                </div>
              </div>

              {canOperate && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {dsp.status === "CREATED" && (
                    <Button variant="outline" disabled={readyMutation.isPending} onClick={() => readyMutation.mutate()}>
                      <PackageCheck className="h-4 w-4" />
                      Verify Packing &amp; Mark Ready
                    </Button>
                  )}
                  {(dsp.status === "CREATED" || dsp.status === "READY_FOR_DISPATCH") && (
                    <Button disabled={postMutation.isPending} onClick={() => postMutation.mutate()}>
                      <CheckCircle2 className="h-4 w-4" />
                      {postMutation.isPending ? "Posting..." : "Post Dispatch & Deduct Stock"}
                    </Button>
                  )}
                  {dsp.status === "DISPATCHED" && (
                    <Button
                      variant="outline"
                      disabled={deliveryMutation.isPending}
                      onClick={() => deliveryMutation.mutate("IN_TRANSIT")}
                    >
                      Mark In Transit
                    </Button>
                  )}
                  {["DISPATCHED", "IN_TRANSIT", "DELIVERY_EXCEPTION"].includes(dsp.status) && (
                    <>
                      <Button disabled={deliveryMutation.isPending} onClick={() => deliveryMutation.mutate("DELIVERED")}>
                        <CheckCircle2 className="h-4 w-4" />
                        Confirm Delivered
                      </Button>
                      <div className="flex flex-wrap items-center gap-2 ml-auto">
                        <Input
                          value={exceptionReason}
                          onChange={(e) => setExceptionReason(e.target.value)}
                          placeholder="Exception reason (e.g. 5 pkts short/damaged)"
                          className="w-64 h-9"
                        />
                        <Button
                          variant="destructive"
                          size="sm"
                          disabled={!exceptionReason.trim() || deliveryMutation.isPending}
                          onClick={() => deliveryMutation.mutate("DELIVERY_EXCEPTION")}
                        >
                          Log Delivery Exception
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Items Table */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Dispatched Items &amp; Delivery Confirmation Quantities</CardTitle>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y bg-secondary/40 text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-2.5">SKU &amp; Product</th>
                    <th className="px-3 py-2.5">Batch / Lot Ref</th>
                    <th className="px-3 py-2.5 text-right">Dispatched Qty</th>
                    <th className="px-3 py-2.5 text-right">Received Qty</th>
                    <th className="px-4 py-2.5 text-right">Discrepancy</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {dsp.items.map((it) => (
                    <tr key={it.id}>
                      <td className="px-4 py-3">
                        <div className="font-semibold">{it.display_name}</div>
                        <div className="font-mono text-xs text-muted-foreground">{it.sku_code}</div>
                      </td>
                      <td className="px-3 py-3 font-mono text-xs">{it.batch_code_ref ?? "—"}</td>
                      <td className="px-3 py-3 text-right font-semibold tabular-nums">{it.dispatched_qty_pkts} pkts</td>
                      <td className="px-3 py-3 text-right tabular-nums">
                        {["DISPATCHED", "IN_TRANSIT", "DELIVERY_EXCEPTION"].includes(dsp.status) && canOperate ? (
                          <Input
                            type="number"
                            min={0}
                            max={it.dispatched_qty_pkts}
                            className="ml-auto w-24 text-right h-8"
                            value={receivedByItem[it.id] ?? it.dispatched_qty_pkts}
                            onChange={(e) =>
                              setReceivedByItem((p) => ({
                                ...p,
                                [it.id]: Math.max(0, parseInt(e.target.value, 10) || 0),
                              }))
                            }
                          />
                        ) : (
                          <span>{it.received_qty_pkts ?? "Pending"}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-xs">
                        {it.discrepancy_qty_pkts > 0 ? (
                          <span className="font-bold text-red-700">{it.discrepancy_qty_pkts} pkts short</span>
                        ) : (
                          "0"
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          {/* Status Timeline */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Clock className="h-4 w-4 text-primary" />
                Dispatch &amp; Delivery Audit Timeline
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              {dsp.status_history.map((h) => (
                <div key={h.id} className="flex items-start justify-between border-b pb-2 last:border-b-0">
                  <div>
                    <div className="flex items-center gap-2">
                      {h.from_status && <span className="font-mono text-muted-foreground">{h.from_status} →</span>}
                      <StatusBadge status={h.to_status} />
                      <span className="font-medium">{h.changed_by_name}</span>
                    </div>
                    {h.reason && <div className="mt-1 text-muted-foreground">{h.reason}</div>}
                  </div>
                  <span className="text-muted-foreground">{formatDateTimeIst(h.changed_at)}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </DesktopAdminLayout>
  );
}

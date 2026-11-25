import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  Clock,
  IndianRupee,
  XCircle,
} from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { formatDateTimeIst, formatInrFromPaisa } from "@/lib/money";

export function AdminDashboardPage() {
  const summaryQuery = useQuery({
    queryKey: ["admin-orders-summary"],
    queryFn: () => api.getAdminOrdersSummary(),
    refetchInterval: 10_000,
  });

  const ordersQuery = useQuery({
    queryKey: ["admin-dashboard-orders"],
    queryFn: () => api.getAdminOrders({ page: 1, pageSize: 10 }),
    refetchInterval: 10_000,
  });

  const summary = summaryQuery.data;
  const orders = ordersQuery.data?.items ?? [];

  return (
    <DesktopAdminLayout
      title="Factory Admin Dashboard"
      subtitle="Live overview of order verification queue, stock alerts, and approved commitments"
      actions={
        <Button asChild>
          <Link to="/admin/orders">
            Open Order Queue
            <ArrowRight className="h-4 w-4" />
          </Link>
        </Button>
      }
    >
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Link to="/admin/orders?tab=pending">
            <Card className="hover:border-primary/50 transition-colors h-full">
              <CardContent className="p-5 flex items-start justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Pending Verification
                  </p>
                  <p className="mt-2 text-2xl font-bold tabular-nums text-primary">
                    {summary?.pending_verification_count ?? 0}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground tabular-nums">
                    {summary?.submitted_count ?? 0} incoming · {summary?.under_review_count ?? 0} under review
                  </p>
                </div>
                <Clock className="h-5 w-5 text-primary" />
              </CardContent>
            </Card>
          </Link>

          <Link to="/admin/orders?tab=pending">
            <Card className="hover:border-amber-400 transition-colors h-full">
              <CardContent className="p-5 flex items-start justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Stock Shortage Alerts
                  </p>
                  <p className="mt-2 text-2xl font-bold tabular-nums text-amber-700">
                    {summary?.shortage_count ?? 0}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Orders exceeding available FG stock
                  </p>
                </div>
                <AlertTriangle className="h-5 w-5 text-amber-600" />
              </CardContent>
            </Card>
          </Link>

          <Link to="/admin/orders?tab=approved">
            <Card className="hover:border-emerald-400 transition-colors h-full">
              <CardContent className="p-5 flex items-start justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Approved Orders
                  </p>
                  <p className="mt-2 text-2xl font-bold tabular-nums text-emerald-700">
                    {summary?.approved_count ?? 0}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground tabular-nums">
                    {formatInrFromPaisa(summary?.approved_value_paisa ?? 0)} committed
                  </p>
                </div>
                <CheckCircle2 className="h-5 w-5 text-emerald-700" />
              </CardContent>
            </Card>
          </Link>

          <Link to="/admin/orders?tab=rejected">
            <Card className="hover:border-red-300 transition-colors h-full">
              <CardContent className="p-5 flex items-start justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Rejected / Total
                  </p>
                  <p className="mt-2 text-2xl font-bold tabular-nums">
                    {summary?.rejected_count ?? 0}{" "}
                    <span className="text-sm font-medium text-muted-foreground">
                      / {summary?.total_count ?? 0}
                    </span>
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground tabular-nums">
                    Pending val: {formatInrFromPaisa(summary?.pending_value_paisa ?? 0)}
                  </p>
                </div>
                {summary && summary.rejected_count > 0 ? (
                  <XCircle className="h-5 w-5 text-destructive" />
                ) : (
                  <IndianRupee className="h-5 w-5 text-accent" />
                )}
              </CardContent>
            </Card>
          </Link>
        </div>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="flex items-center gap-2">
                <ClipboardList className="h-4 w-4 text-primary" />
                Recent Sales Orders
              </CardTitle>
              <CardDescription>
                Orders from mobile salesmen sync directly here for stock check, revision, approval, or rejection.
              </CardDescription>
            </div>
            <Link to="/admin/orders" className="text-sm font-semibold text-primary hover:underline">
              Full Queue →
            </Link>
          </CardHeader>
          <CardContent>
            {ordersQuery.isLoading ? (
              <div className="h-32 animate-pulse rounded-lg bg-muted" />
            ) : orders.length === 0 ? (
              <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
                No orders submitted yet. Place an order from the mobile Salesman interface to see it
                appear live here.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      <th className="py-2.5 pr-4">Order #</th>
                      <th className="py-2.5 pr-4">Customer</th>
                      <th className="py-2.5 pr-4">Salesman</th>
                      <th className="py-2.5 pr-4 text-right">Qty</th>
                      <th className="py-2.5 pr-4 text-right">Est. Total</th>
                      <th className="py-2.5 pr-4">Stock</th>
                      <th className="py-2.5 pr-4">Status</th>
                      <th className="py-2.5 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {orders.slice(0, 8).map((ord) => (
                      <tr key={ord.id} className="hover:bg-secondary/40">
                        <td className="py-3 pr-4 font-mono text-xs font-bold">
                          <div>{ord.order_number}</div>
                          <div className="font-sans font-normal text-[11px] text-muted-foreground">
                            {formatDateTimeIst(ord.submitted_at)}
                          </div>
                        </td>
                        <td className="py-3 pr-4">
                          <div className="font-semibold">{ord.customer_name}</div>
                          <div className="text-xs text-muted-foreground">
                            {ord.place_of_supply_state_name} ({ord.place_of_supply_state_code})
                          </div>
                        </td>
                        <td className="py-3 pr-4">{ord.salesman_name}</td>
                        <td className="py-3 pr-4 text-right font-semibold tabular-nums">
                          {ord.total_packets} pkts
                        </td>
                        <td className="py-3 pr-4 text-right font-semibold tabular-nums">
                          {formatInrFromPaisa(ord.estimated_grand_total_paisa)}
                        </td>
                        <td className="py-3 pr-4">
                          {ord.status === "APPROVED" ? (
                            <Badge variant="success">Reserved</Badge>
                          ) : ord.has_shortage ? (
                            <Badge variant="warning">Shortage</Badge>
                          ) : (
                            <Badge variant="success">Covered</Badge>
                          )}
                        </td>
                        <td className="py-3 pr-4">
                          <StatusBadge status={ord.status} />
                        </td>
                        <td className="py-3 text-right">
                          <Button asChild size="sm" variant="outline">
                            <Link to={`/admin/orders/${ord.id}`}>
                              {ord.status === "SUBMITTED" || ord.status === "UNDER_REVIEW"
                                ? "Verify"
                                : "Inspect"}
                            </Link>
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </DesktopAdminLayout>
  );
}

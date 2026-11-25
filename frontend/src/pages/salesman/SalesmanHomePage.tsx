import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ArrowRight, ClipboardList, MapPin, PlusCircle, Store } from "lucide-react";
import { MobileSalesLayout } from "@/components/layouts/MobileSalesLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatInrFromPaisa, formatOrderDate } from "@/lib/money";

export function SalesmanHomePage() {
  const { user } = useAuth();

  const customersQuery = useQuery({
    queryKey: ["salesman-customers"],
    queryFn: () => api.getCustomers(),
  });

  const ordersQuery = useQuery({
    queryKey: ["salesman-orders", 1],
    queryFn: () => api.getMyOrders(1, 5),
  });

  const customers = customersQuery.data ?? [];
  const orders = ordersQuery.data?.items ?? [];

  return (
    <MobileSalesLayout
      title={`Welcome, ${user?.full_name ?? "Salesman"}`}
      subtitle="Select a shop or tap New Order to submit directly to the factory"
    >
      <div className="space-y-4">
        <Card className="border-primary/20 bg-primary text-primary-foreground shadow-md">
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-primary-foreground/80">
                Quick Field Entry
              </span>
              <span className="rounded-full bg-white/15 px-2.5 py-0.5 text-xs font-semibold tabular-nums">
                {ordersQuery.data?.total ?? 0} Submitted
              </span>
            </div>
            <p className="text-sm text-primary-foreground/90">
              Capture retailer &amp; distributor demand in under 1 minute with automatic price lookup.
            </p>
            <Button
              asChild
              variant="accent"
              size="lg"
              className="w-full justify-between font-bold"
            >
              <Link to="/salesman/new-order">
                <span className="flex items-center gap-2">
                  <PlusCircle className="h-5 w-5" />
                  Start New Order
                </span>
                <ArrowRight className="h-5 w-5" />
              </Link>
            </Button>
          </CardContent>
        </Card>

        <section className="space-y-2.5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-foreground">Assigned Customers</h2>
            <span className="text-xs text-muted-foreground">{customers.length} active</span>
          </div>
          {customersQuery.isLoading ? (
            <div className="h-20 animate-pulse rounded-xl bg-muted" />
          ) : customers.length === 0 ? (
            <Card>
              <CardContent className="p-4 text-sm text-muted-foreground">
                No customers assigned to your route yet.
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-2">
              {customers.map((c) => (
                <Link key={c.id} to={`/salesman/new-order?customerId=${c.id}`} className="block">
                  <Card className="transition-colors hover:border-primary/50">
                    <CardContent className="flex items-center justify-between p-4">
                      <div className="min-w-0 space-y-1">
                        <div className="flex items-center gap-2">
                          <Store className="h-4 w-4 text-primary shrink-0" />
                          <span className="font-semibold text-sm truncate">{c.name}</span>
                          <span className="rounded bg-secondary px-1.5 py-0.5 text-[10px] font-semibold uppercase text-secondary-foreground">
                            {c.customer_type}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                          <MapPin className="h-3.5 w-3.5 shrink-0" />
                          <span>
                            {c.default_shipping_address?.city
                              ? `${c.default_shipping_address.city}, `
                              : ""}
                            {c.primary_state_name} ({c.primary_state_code})
                          </span>
                        </div>
                      </div>
                      <ArrowRight className="h-4 w-4 text-muted-foreground shrink-0" />
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </section>

        <section className="space-y-2.5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-foreground">Recent Orders</h2>
            <Link to="/salesman/orders" className="text-xs font-semibold text-primary hover:underline">
              View all
            </Link>
          </div>
          {ordersQuery.isLoading ? (
            <div className="h-24 animate-pulse rounded-xl bg-muted" />
          ) : orders.length === 0 ? (
            <Card>
              <CardContent className="flex items-center gap-3 p-4 text-sm text-muted-foreground">
                <ClipboardList className="h-4 w-4 shrink-0" />
                <span>No orders submitted yet. Tap Start New Order above.</span>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-2">
              {orders.map((ord) => (
                <Link key={ord.id} to={`/salesman/orders/${ord.id}`} className="block">
                  <Card className="hover:border-primary/40">
                    <CardContent className="flex items-center justify-between p-4">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-bold">{ord.order_number}</span>
                          <StatusBadge status={ord.status} />
                        </div>
                        <div className="text-sm font-medium">{ord.customer_name}</div>
                        <div className="text-xs text-muted-foreground">
                          {formatOrderDate(ord.order_date)} ·{" "}
                          <span className="tabular-nums">{ord.total_packets} pkts</span>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-sm font-bold tabular-nums">
                          {formatInrFromPaisa(ord.estimated_grand_total_paisa)}
                        </div>
                        <div className="text-[11px] text-muted-foreground">Est. incl. GST</div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </section>
      </div>
    </MobileSalesLayout>
  );
}

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { AlertTriangle, ChevronRight, MessageSquare, RefreshCw, Search } from "lucide-react";
import { MobileSalesLayout } from "@/components/layouts/MobileSalesLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { formatDateTimeIst, formatInrFromPaisa } from "@/lib/money";

const STATUS_CHIPS = [
  { value: "", label: "All" },
  { value: "SUBMITTED", label: "Submitted" },
  { value: "UNDER_REVIEW", label: "Under Review" },
  { value: "CORRECTION_REQUESTED", label: "Correction" },
  { value: "APPROVED", label: "Approved" },
  { value: "REJECTED", label: "Rejected" },
  { value: "CANCELLED", label: "Cancelled" },
];

export function SalesmanOrdersPage() {
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [search, setSearch] = useState<string>("");

  const ordersQuery = useQuery({
    queryKey: ["salesman-orders", statusFilter, search],
    queryFn: () =>
      api.getMyOrders(1, 30, statusFilter || undefined, search.trim() || undefined),
    refetchInterval: 10_000,
    refetchOnWindowFocus: true,
  });

  const orders = ordersQuery.data?.items ?? [];

  return (
    <MobileSalesLayout
      title="My Orders"
      subtitle="Auto-syncs every 10s with factory verification decisions"
    >
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search order # or customer..."
              className="pl-9 h-10"
            />
          </div>
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() => ordersQuery.refetch()}
            aria-label="Refresh orders"
          >
            <RefreshCw className={`h-4 w-4 ${ordersQuery.isFetching ? "animate-spin" : ""}`} />
          </Button>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {STATUS_CHIPS.map((chip) => (
            <button
              key={chip.value}
              type="button"
              onClick={() => setStatusFilter(chip.value)}
              className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${
                statusFilter === chip.value
                  ? "border-primary bg-primary text-primary-foreground"
                  : "bg-card text-muted-foreground hover:bg-secondary"
              }`}
            >
              {chip.label}
            </button>
          ))}
        </div>

        {ordersQuery.isLoading ? (
          <div className="space-y-2.5">
            <div className="h-24 animate-pulse rounded-xl bg-muted" />
            <div className="h-24 animate-pulse rounded-xl bg-muted" />
          </div>
        ) : orders.length === 0 ? (
          <Card>
            <CardContent className="p-6 text-center space-y-2">
              <p className="text-sm text-muted-foreground">No orders found matching this filter.</p>
              <Button asChild size="sm">
                <Link to="/salesman/new-order">Place Order</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2.5">
            {orders.map((ord) => {
              const qtyAdjusted = ord.total_packets !== ord.ordered_total_packets;
              const decisionNote = ord.rejection_reason || ord.cancellation_reason || ord.admin_remarks;

              return (
                <Link key={ord.id} to={`/salesman/orders/${ord.id}`} className="block">
                  <Card className="hover:border-primary/50 transition-colors">
                    <CardContent className="p-4 space-y-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-xs font-bold text-primary">
                          {ord.order_number}
                        </span>
                        <div className="flex items-center gap-1.5">
                          {ord.has_shortage && ord.status !== "APPROVED" && ord.status !== "REJECTED" && (
                            <Badge variant="warning" className="gap-1">
                              <AlertTriangle className="h-3 w-3" />
                              Shortage
                            </Badge>
                          )}
                          <StatusBadge status={ord.status} />
                        </div>
                      </div>

                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="font-semibold text-sm truncate">{ord.customer_name}</div>
                          <div className="text-xs text-muted-foreground">
                            {formatDateTimeIst(ord.submitted_at)}
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5 text-right shrink-0">
                          <div>
                            <div className="font-bold text-sm tabular-nums">
                              {formatInrFromPaisa(ord.estimated_grand_total_paisa)}
                            </div>
                            <div className="text-xs text-muted-foreground tabular-nums">
                              {ord.total_packets} pkts
                              {qtyAdjusted && ` (ord ${ord.ordered_total_packets})`}
                            </div>
                          </div>
                          <ChevronRight className="h-4 w-4 text-muted-foreground" />
                        </div>
                      </div>

                      {decisionNote && (
                        <div className="flex items-start gap-1.5 rounded-lg bg-secondary/60 px-2.5 py-1.5 text-xs text-muted-foreground">
                          <MessageSquare className="h-3.5 w-3.5 shrink-0 mt-0.5 text-primary" />
                          <span className="line-clamp-2">{decisionNote}</span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </MobileSalesLayout>
  );
}

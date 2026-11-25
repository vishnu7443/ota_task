import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { AlertTriangle, CheckCircle2, RefreshCw, RotateCcw, Search } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { formatDateTimeIst, formatInrFromPaisa } from "@/lib/money";

type QueueTab = "all" | "incoming" | "pending" | "approved" | "rejected";

export function AdminIncomingOrdersPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialTab = (searchParams.get("tab") as QueueTab | null) ?? "all";

  const [activeTab, setActiveTab] = useState<QueueTab>(
    ["all", "incoming", "pending", "approved", "rejected"].includes(initialTab) ? initialTab : "all"
  );
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [customerId, setCustomerId] = useState<string>("");
  const [salesmanId, setSalesmanId] = useState<string>("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [shortageFilter, setShortageFilter] = useState<string>("all");

  const summaryQuery = useQuery({
    queryKey: ["admin-orders-summary"],
    queryFn: () => api.getAdminOrdersSummary(),
    refetchInterval: 10_000,
  });

  const customersQuery = useQuery({
    queryKey: ["admin-filter-customers"],
    queryFn: () => api.getCustomers(),
  });

  const salesmenQuery = useQuery({
    queryKey: ["admin-filter-salesmen"],
    queryFn: () => api.getSalesmen(),
  });

  const effectiveStatus =
    activeTab === "incoming"
      ? "SUBMITTED"
      : activeTab === "approved"
      ? "APPROVED"
      : activeTab === "rejected"
      ? "REJECTED"
      : statusFilter || undefined;

  const pendingVerification = activeTab === "pending" && !statusFilter;

  const hasShortage =
    shortageFilter === "short" ? true : shortageFilter === "covered" ? false : null;

  const ordersQuery = useQuery({
    queryKey: [
      "admin-orders",
      activeTab,
      page,
      search,
      effectiveStatus,
      pendingVerification,
      customerId,
      salesmanId,
      dateFrom,
      dateTo,
      shortageFilter,
    ],
    queryFn: () =>
      api.getAdminOrders({
        page,
        pageSize: 15,
        status: effectiveStatus,
        pendingVerification,
        customerId: customerId ? Number(customerId) : null,
        salesmanId: salesmanId ? Number(salesmanId) : null,
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        hasShortage,
        search: search.trim() || undefined,
      }),
    refetchInterval: 10_000,
  });

  const summary = summaryQuery.data;
  const data = ordersQuery.data;
  const orders = data?.items ?? [];

  const switchTab = (tab: QueueTab) => {
    setActiveTab(tab);
    setStatusFilter("");
    setPage(1);
    setSearchParams(tab === "all" ? {} : { tab });
  };

  const resetFilters = () => {
    setSearch("");
    setStatusFilter("");
    setCustomerId("");
    setSalesmanId("");
    setDateFrom("");
    setDateTo("");
    setShortageFilter("all");
    setPage(1);
  };

  const tabs: Array<{ id: QueueTab; label: string; count?: number }> = [
    { id: "pending", label: "Pending Verification", count: summary?.pending_verification_count },
    { id: "incoming", label: "Incoming", count: summary?.submitted_count },
    { id: "approved", label: "Approved", count: summary?.approved_count },
    { id: "rejected", label: "Rejected", count: summary?.rejected_count },
    { id: "all", label: "All Orders", count: summary?.total_count },
  ];

  return (
    <DesktopAdminLayout
      title="Order Management & Verification"
      subtitle="Search, filter, inspect live stock coverage, adjust quantities/prices, and approve or reject orders"
      actions={
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            summaryQuery.refetch();
            ordersQuery.refetch();
          }}
          disabled={ordersQuery.isFetching}
        >
          <RefreshCw className={`h-4 w-4 ${ordersQuery.isFetching ? "animate-spin" : ""}`} />
          Refresh Now
        </Button>
      }
    >
      <div className="space-y-4">
        {/* Lifecycle Tabs */}
        <div className="flex flex-wrap gap-2">
          {tabs.map((t) => {
            const active = activeTab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => switchTab(t.id)}
                className={`inline-flex items-center gap-2 rounded-lg border px-3.5 py-2 text-sm font-semibold transition-colors ${
                  active
                    ? "border-primary bg-primary text-primary-foreground shadow-sm"
                    : "bg-card text-muted-foreground hover:bg-secondary hover:text-foreground"
                }`}
              >
                <span>{t.label}</span>
                {t.count !== undefined && (
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs tabular-nums ${
                      active ? "bg-white/20 text-white" : "bg-secondary text-foreground"
                    }`}
                  >
                    {t.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Multi-criteria Filters */}
        <Card>
          <CardContent className="p-4 space-y-3">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
              <div className="relative lg:col-span-2">
                <Search className="absolute left-3 top-3.5 h-4 w-4 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(e) => {
                    setPage(1);
                    setSearch(e.target.value);
                  }}
                  placeholder="Order #, customer, salesman..."
                  className="pl-9"
                />
              </div>

              <select
                aria-label="Filter by customer"
                value={customerId}
                onChange={(e) => {
                  setPage(1);
                  setCustomerId(e.target.value);
                }}
                className="h-11 rounded-lg border border-input bg-card px-3 text-sm"
              >
                <option value="">All Customers</option>
                {(customersQuery.data ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.primary_state_code})
                  </option>
                ))}
              </select>

              <select
                aria-label="Filter by salesman"
                value={salesmanId}
                onChange={(e) => {
                  setPage(1);
                  setSalesmanId(e.target.value);
                }}
                className="h-11 rounded-lg border border-input bg-card px-3 text-sm"
              >
                <option value="">All Salesmen</option>
                {(salesmenQuery.data ?? []).map((s) => (
                  <option key={s.user_id} value={s.user_id}>
                    {s.full_name} ({s.employee_code})
                  </option>
                ))}
              </select>

              {(activeTab === "all" || activeTab === "pending") && (
                <select
                  aria-label="Filter by order status"
                  value={statusFilter}
                  onChange={(e) => {
                    setPage(1);
                    setStatusFilter(e.target.value);
                  }}
                  className="h-11 rounded-lg border border-input bg-card px-3 text-sm"
                >
                  <option value="">
                    {activeTab === "pending" ? "All Pending States" : "All Statuses"}
                  </option>
                  <option value="SUBMITTED">Submitted</option>
                  <option value="UNDER_REVIEW">Under Review</option>
                  <option value="CORRECTION_REQUESTED">Correction Requested</option>
                  {activeTab === "all" && (
                    <>
                      <option value="APPROVED">Approved</option>
                      <option value="REJECTED">Rejected</option>
                      <option value="CANCELLED">Cancelled</option>
                    </>
                  )}
                </select>
              )}

              <select
                aria-label="Filter by stock availability"
                value={shortageFilter}
                onChange={(e) => {
                  setPage(1);
                  setShortageFilter(e.target.value);
                }}
                className="h-11 rounded-lg border border-input bg-card px-3 text-sm"
              >
                <option value="all">All Stock States</option>
                <option value="short">Shortage Flagged</option>
                <option value="covered">Fully Covered</option>
              </select>
            </div>

            <div className="flex flex-wrap items-center gap-3 text-xs">
              <div className="flex items-center gap-2">
                <label htmlFor="date-from" className="font-semibold text-muted-foreground">
                  From Date
                </label>
                <Input
                  id="date-from"
                  type="date"
                  value={dateFrom}
                  onChange={(e) => {
                    setPage(1);
                    setDateFrom(e.target.value);
                  }}
                  className="h-9 w-auto text-xs"
                />
              </div>
              <div className="flex items-center gap-2">
                <label htmlFor="date-to" className="font-semibold text-muted-foreground">
                  To Date
                </label>
                <Input
                  id="date-to"
                  type="date"
                  value={dateTo}
                  onChange={(e) => {
                    setPage(1);
                    setDateTo(e.target.value);
                  }}
                  className="h-9 w-auto text-xs"
                />
              </div>
              <Button type="button" variant="ghost" size="sm" onClick={resetFilters}>
                <RotateCcw className="h-3.5 w-3.5" />
                Reset Filters
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Queue Table */}
        <Card>
          <CardContent className="p-0">
            {ordersQuery.isLoading ? (
              <div className="p-6 space-y-3">
                <div className="h-12 animate-pulse rounded-lg bg-muted" />
                <div className="h-12 animate-pulse rounded-lg bg-muted" />
              </div>
            ) : ordersQuery.error ? (
              <div className="p-6 text-sm text-destructive">
                Failed to load incoming orders from backend.
              </div>
            ) : orders.length === 0 ? (
              <div className="p-10 text-center text-sm text-muted-foreground">
                No orders match your current filters.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-secondary/40 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      <th className="px-5 py-3">Order #</th>
                      <th className="px-4 py-3">Submitted At (IST)</th>
                      <th className="px-4 py-3">Customer &amp; State</th>
                      <th className="px-4 py-3">Salesman</th>
                      <th className="px-4 py-3 text-right">Quantity</th>
                      <th className="px-4 py-3 text-right">Taxable</th>
                      <th className="px-4 py-3 text-right">Est. Total</th>
                      <th className="px-4 py-3">Stock Check</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-5 py-3 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {orders.map((ord) => (
                      <tr key={ord.id} className="hover:bg-secondary/30">
                        <td className="px-5 py-3.5 font-mono text-xs font-bold text-primary">
                          {ord.order_number}
                        </td>
                        <td className="px-4 py-3.5 text-xs text-muted-foreground">
                          {formatDateTimeIst(ord.submitted_at)}
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="font-semibold">{ord.customer_name}</div>
                          <div className="text-xs text-muted-foreground">
                            {ord.customer_type} · {ord.place_of_supply_state_name} (
                            {ord.place_of_supply_state_code})
                          </div>
                        </td>
                        <td className="px-4 py-3.5 font-medium">{ord.salesman_name}</td>
                        <td className="px-4 py-3.5 text-right font-semibold tabular-nums">
                          <div>{ord.total_packets} pkts</div>
                          {ord.total_packets !== ord.ordered_total_packets && (
                            <div className="text-[11px] font-normal text-amber-700">
                              ord {ord.ordered_total_packets}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3.5 text-right tabular-nums">
                          {formatInrFromPaisa(ord.taxable_total_paisa)}
                        </td>
                        <td className="px-4 py-3.5 text-right font-bold tabular-nums">
                          {formatInrFromPaisa(ord.estimated_grand_total_paisa)}
                        </td>
                        <td className="px-4 py-3.5">
                          {ord.status === "APPROVED" ? (
                            <Badge variant="success" className="gap-1">
                              <CheckCircle2 className="h-3 w-3" />
                              Reserved
                            </Badge>
                          ) : ord.has_shortage ? (
                            <Badge variant="warning" className="gap-1">
                              <AlertTriangle className="h-3 w-3" />
                              Shortage
                            </Badge>
                          ) : (
                            <Badge variant="success" className="gap-1">
                              <CheckCircle2 className="h-3 w-3" />
                              Covered
                            </Badge>
                          )}
                        </td>
                        <td className="px-4 py-3.5">
                          <StatusBadge status={ord.status} />
                        </td>
                        <td className="px-5 py-3.5 text-right">
                          <Button asChild size="sm">
                            <Link to={`/admin/orders/${ord.id}`}>Open Review</Link>
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {data && data.total_pages > 1 && (
              <div className="flex items-center justify-between border-t px-5 py-3 text-xs text-muted-foreground">
                <span>
                  Page {data.page} of {data.total_pages} ({data.total} orders)
                </span>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    Previous
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={page >= data.total_pages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </DesktopAdminLayout>
  );
}

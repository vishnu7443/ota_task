import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Boxes,
  IndianRupee,
  Package,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { formatInrFromPaisa } from "@/lib/money";
import { formatDisplayQty, formatQtyPair } from "@/lib/units";

const CATEGORY_TABS = [
  { key: "", label: "All Inventory" },
  { key: "RAW_MATERIAL", label: "Raw Materials" },
  { key: "PACKAGING_MATERIAL", label: "Packaging Materials" },
  { key: "FINISHED_GOOD", label: "Finished Goods" },
];

export function AdminInventoryDashboardPage() {
  const [category, setCategory] = useState("");
  const [lowStockOnly, setLowStockOnly] = useState(false);
  const [search, setSearch] = useState("");

  const overviewQuery = useQuery({
    queryKey: ["inventory-overview", category, lowStockOnly, search],
    queryFn: () =>
      api.getInventoryOverview({
        itemCategory: category || undefined,
        lowStockOnly,
        search: search.trim() || undefined,
      }),
    refetchInterval: 15_000,
  });

  const data = overviewQuery.data;
  const items = data?.items ?? [];

  return (
    <DesktopAdminLayout
      title="Inventory Dashboard"
      subtitle="Unified ledger-backed stock view across Raw Materials, Packaging, and Finished Goods"
      actions={
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link to="/admin/inventory/adjustments">
              <SlidersHorizontal className="h-4 w-4" />
              Adjustments
            </Link>
          </Button>
          <Button asChild>
            <Link to="/admin/purchasing/receipts">
              Record Goods Receipt
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
        </div>
      }
    >
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardContent className="p-5 flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Open FIFO Valuation
                </p>
                <p className="mt-2 text-2xl font-bold tabular-nums text-foreground">
                  {formatInrFromPaisa(data?.total_stock_value_paisa ?? 0)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Across {data?.total_items ?? 0} tracked SKUs &amp; materials
                </p>
              </div>
              <IndianRupee className="h-5 w-5 text-primary" />
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5 flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Materials &amp; Packaging
                </p>
                <p className="mt-2 text-2xl font-bold tabular-nums">
                  {(data?.raw_material_count ?? 0) + (data?.packaging_material_count ?? 0)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {data?.raw_material_count ?? 0} Raw · {data?.packaging_material_count ?? 0} Packaging
                </p>
              </div>
              <Boxes className="h-5 w-5 text-emerald-600" />
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-5 flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Low Stock Alerts
                </p>
                <p className="mt-2 text-2xl font-bold tabular-nums text-amber-700">
                  {data?.low_stock_count ?? 0}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Available stock &le; reorder level
                </p>
              </div>
              <AlertTriangle className="h-5 w-5 text-amber-600" />
            </CardContent>
          </Card>

          <Link to="/admin/inventory/adjustments">
            <Card className="hover:border-primary/50 transition-colors h-full">
              <CardContent className="p-5 flex items-start justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Pending Adjustments
                  </p>
                  <p className="mt-2 text-2xl font-bold tabular-nums text-primary">
                    {data?.pending_adjustments_count ?? 0}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Awaiting Factory Admin approval
                  </p>
                </div>
                <Package className="h-5 w-5 text-primary" />
              </CardContent>
            </Card>
          </Link>
        </div>

        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap gap-1.5">
            {CATEGORY_TABS.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setCategory(tab.key)}
                className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                  category === tab.key
                    ? "bg-primary text-primary-foreground"
                    : "bg-card border text-muted-foreground hover:text-foreground"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-xs font-semibold text-muted-foreground cursor-pointer">
              <input
                type="checkbox"
                checked={lowStockOnly}
                onChange={(e) => setLowStockOnly(e.target.checked)}
                className="h-4 w-4 rounded border-input"
              />
              Low Stock Alerts Only
            </label>
            <div className="relative w-64">
              <Search className="h-4 w-4 absolute left-3 top-2.5 text-muted-foreground" />
              <Input
                className="pl-9 h-9"
                placeholder="Search item code or name..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Current Stock &amp; Movement Summary</CardTitle>
            <CardDescription>
              Physical = Opening + Received - Issued - Dispatched + Adjusted · Available = Physical - Reserved
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="py-2 pr-3">Item</th>
                  <th className="py-2 pr-3 text-right">Opening</th>
                  <th className="py-2 pr-3 text-right">Received</th>
                  <th className="py-2 pr-3 text-right">Issued</th>
                  <th className="py-2 pr-3 text-right">Adjusted</th>
                  <th className="py-2 pr-3 text-right">Physical</th>
                  <th className="py-2 pr-3 text-right">Reserved</th>
                  <th className="py-2 pr-3 text-right">Available</th>
                  <th className="py-2 pr-3 text-right">Reorder</th>
                  <th className="py-2 pr-3 text-right">Lot Value</th>
                  <th className="py-2 text-right">Ledger</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {items.map((item) => {
                  const ledgerLink =
                    item.item_type === "MATERIAL"
                      ? `/admin/inventory/ledger?material_id=${item.item_id}`
                      : `/admin/inventory/ledger?pack_size_id=${item.item_id}`;
                  return (
                    <tr key={`${item.item_type}-${item.item_id}`} className="hover:bg-secondary/30">
                      <td className="py-3 pr-3">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground">{item.name}</span>
                          {item.is_low_stock && <Badge variant="warning">Low Stock</Badge>}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          <span className="font-mono">{item.code}</span> · {item.item_category.replaceAll("_", " ")}
                        </div>
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums text-xs">
                        {formatDisplayQty(item.opening_qty_base, item.display_uom, item.display_factor)}
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums text-xs text-emerald-700 font-medium">
                        {formatDisplayQty(item.received_qty_base, item.display_uom, item.display_factor)}
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums text-xs text-amber-700 font-medium">
                        {formatDisplayQty(item.issued_qty_base, item.display_uom, item.display_factor)}
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums text-xs">
                        {formatDisplayQty(item.adjusted_qty_base, item.display_uom, item.display_factor)}
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums">
                        <div className="font-semibold">
                          {formatDisplayQty(item.physical_qty_base, item.display_uom, item.display_factor)}
                        </div>
                        {item.display_uom !== item.base_uom && (
                          <div className="text-[11px] text-muted-foreground">
                            {formatQtyPair(
                              item.physical_qty_base,
                              item.display_uom,
                              item.display_factor,
                              item.base_uom
                            )
                              .split("(")[1]
                              ?.replace(")", "")}
                          </div>
                        )}
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums text-xs text-amber-700">
                        {formatDisplayQty(item.reserved_qty_base, item.display_uom, item.display_factor)}
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums font-bold text-primary">
                        {formatDisplayQty(item.available_qty_base, item.display_uom, item.display_factor)}
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums text-xs text-muted-foreground">
                        {formatDisplayQty(item.reorder_level_base, item.display_uom, item.display_factor)}
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums font-medium">
                        {formatInrFromPaisa(item.open_lot_value_paisa)}
                      </td>
                      <td className="py-3 text-right">
                        <Button size="sm" variant="ghost" asChild>
                          <Link to={ledgerLink}>
                            <BookOpen className="h-3.5 w-3.5" />
                          </Link>
                        </Button>
                      </td>
                    </tr>
                  );
                })}
                {items.length === 0 && (
                  <tr>
                    <td colSpan={11} className="py-8 text-center text-muted-foreground">
                      No inventory items match the current filters.
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

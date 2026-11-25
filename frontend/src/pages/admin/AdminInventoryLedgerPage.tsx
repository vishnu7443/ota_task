import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { BookOpen } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { formatDateTimeIst, formatInrFromPaisa } from "@/lib/money";
import { formatBaseQty, toNumber } from "@/lib/units";

const MOVEMENT_TYPES = [
  "",
  "OPENING",
  "PURCHASE_IN",
  "DAMAGE_WASTAGE",
  "SUPPLIER_RETURN",
  "ADJUSTMENT",
  "PROD_ISSUE_OUT",
  "PROD_OUTPUT_IN",
  "DISPATCH_OUT",
];

export function AdminInventoryLedgerPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialMaterialId = searchParams.get("material_id") ?? "";
  const initialPackSizeId = searchParams.get("pack_size_id") ?? "";

  const [itemFilter, setItemFilter] = useState(() => {
    if (initialMaterialId) return `MAT:${initialMaterialId}`;
    if (initialPackSizeId) return `PS:${initialPackSizeId}`;
    return "";
  });
  const [movementType, setMovementType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const overviewQuery = useQuery({
    queryKey: ["inventory-overview-all"],
    queryFn: () => api.getInventoryOverview(),
  });

  const parsedFilter = (() => {
    if (itemFilter.startsWith("MAT:")) return { materialId: Number(itemFilter.slice(4)), packSizeId: undefined };
    if (itemFilter.startsWith("PS:")) return { materialId: undefined, packSizeId: Number(itemFilter.slice(3)) };
    return { materialId: undefined, packSizeId: undefined };
  })();

  const ledgerQuery = useQuery({
    queryKey: ["inventory-ledger", itemFilter, movementType, dateFrom, dateTo],
    queryFn: () =>
      api.getInventoryLedger({
        materialId: parsedFilter.materialId,
        packSizeId: parsedFilter.packSizeId,
        movementType: movementType || undefined,
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        limit: 200,
      }),
    refetchInterval: 15_000,
  });

  const entries = ledgerQuery.data ?? [];
  const items = overviewQuery.data?.items ?? [];

  const handleItemChange = (val: string) => {
    setItemFilter(val);
    if (val.startsWith("MAT:")) {
      setSearchParams({ material_id: val.slice(4) });
    } else if (val.startsWith("PS:")) {
      setSearchParams({ pack_size_id: val.slice(3) });
    } else {
      setSearchParams({});
    }
  };

  return (
    <DesktopAdminLayout
      title="Immutable Inventory Ledger"
      subtitle="Chronological, append-only ledger tracking every stock-changing transaction with source traceability"
    >
      <div className="space-y-6">
        <Card>
          <CardContent className="p-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-muted-foreground">Filter by Item</label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={itemFilter}
                onChange={(e) => handleItemChange(e.target.value)}
              >
                <option value="">All Materials &amp; Finished Goods</option>
                {items.map((it) => {
                  const key = `${it.item_type === "MATERIAL" ? "MAT" : "PS"}:${it.item_id}`;
                  return (
                    <option key={key} value={key}>
                      {it.code} — {it.name}
                    </option>
                  );
                })}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-muted-foreground">Movement Type</label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={movementType}
                onChange={(e) => setMovementType(e.target.value)}
              >
                {MOVEMENT_TYPES.map((mt) => (
                  <option key={mt} value={mt}>
                    {mt || "All Movement Types"}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-muted-foreground">From Date</label>
              <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-muted-foreground">To Date</label>
              <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-primary" />
              Ledger Entries ({entries.length})
            </CardTitle>
            <CardDescription>
              Protected by PostgreSQL append-only mutation triggers (no silent updates or deletions permitted).
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="py-2 pr-3">Timestamp (IST)</th>
                  <th className="py-2 pr-3">Item</th>
                  <th className="py-2 pr-3">Type</th>
                  <th className="py-2 pr-3 text-right">Entered Qty</th>
                  <th className="py-2 pr-3 text-right">Base Delta</th>
                  <th className="py-2 pr-3 text-right">Total Value</th>
                  <th className="py-2 pr-3">Source Ref</th>
                  <th className="py-2">Actor &amp; Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {entries.map((entry) => {
                  const delta = toNumber(entry.signed_qty_base);
                  return (
                    <tr key={entry.id} className="hover:bg-secondary/30">
                      <td className="py-3 pr-3 text-xs text-muted-foreground whitespace-nowrap">
                        {formatDateTimeIst(entry.occurred_at)}
                      </td>
                      <td className="py-3 pr-3">
                        <div className="font-medium text-foreground">{entry.item_name}</div>
                        <div className="text-xs font-mono text-muted-foreground">{entry.item_code}</div>
                      </td>
                      <td className="py-3 pr-3">
                        <Badge variant={delta > 0 ? "success" : "warning"}>{entry.movement_type}</Badge>
                      </td>
                      <td className="py-3 pr-3 text-right text-xs tabular-nums">
                        {entry.entered_qty ? `${entry.entered_qty} ${entry.entered_uom ?? ""}` : "—"}
                      </td>
                      <td
                        className={`py-3 pr-3 text-right font-mono text-xs font-bold tabular-nums ${
                          delta > 0 ? "text-emerald-700" : "text-red-700"
                        }`}
                      >
                        {delta > 0 ? "+" : ""}
                        {formatBaseQty(entry.signed_qty_base, entry.base_uom)}
                      </td>
                      <td className="py-3 pr-3 text-right font-semibold tabular-nums text-xs">
                        {formatInrFromPaisa(entry.total_cost_paisa)}
                      </td>
                      <td className="py-3 pr-3 text-xs">
                        <div className="font-mono font-semibold">{entry.reference_code ?? "—"}</div>
                        <div className="text-[11px] text-muted-foreground">{entry.source_doc_type}</div>
                      </td>
                      <td className="py-3 text-xs">
                        <div className="font-medium">{entry.actor_name}</div>
                        <div className="text-muted-foreground max-w-xs truncate">{entry.notes ?? "—"}</div>
                      </td>
                    </tr>
                  );
                })}
                {entries.length === 0 && (
                  <tr>
                    <td colSpan={8} className="py-8 text-center text-muted-foreground">
                      No inventory movements match the selected filters.
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

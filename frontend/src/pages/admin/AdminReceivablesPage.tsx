import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { CalendarClock, Download, FileSpreadsheet, Search } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, financeApi } from "@/lib/api";
import { formatInrFromPaisa, formatOrderDate } from "@/lib/money";

function downloadCsv(filename: string, headers: string[], rows: Array<Array<string | number>>) {
  const esc = (v: string | number) => `"${String(v).replaceAll('"', '""')}"`;
  const csv = [headers.map(esc).join(","), ...rows.map((r) => r.map(esc).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function AdminReceivablesPage() {
  const [tab, setTab] = useState<"summary" | "ageing" | "statement">("summary");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [onlyOutstanding, setOnlyOutstanding] = useState(false);
  const [asOfDate, setAsOfDate] = useState("");
  const [statementCustId, setStatementCustId] = useState<string>("");
  const [stmtFrom, setStmtFrom] = useState("");
  const [stmtTo, setStmtTo] = useState("");

  const customersQuery = useQuery({
    queryKey: ["ar-customers-list"],
    queryFn: () => api.getCustomers(),
  });

  const arQuery = useQuery({
    queryKey: ["finance-receivables", page, search, onlyOutstanding, asOfDate],
    queryFn: () =>
      financeApi.getReceivables({
        page,
        pageSize: 20,
        search: search.trim() || undefined,
        onlyOutstanding,
        asOfDate: asOfDate || undefined,
      }),
    refetchInterval: 15_000,
  });

  const ageingQuery = useQuery({
    queryKey: ["finance-ageing", asOfDate, search, page],
    queryFn: () =>
      financeApi.getAgeingReport({
        asOfDate: asOfDate || undefined,
        search: search.trim() || undefined,
        page,
        pageSize: 25,
      }),
    enabled: tab === "ageing",
  });

  const stmtQuery = useQuery({
    queryKey: ["customer-statement", statementCustId, stmtFrom, stmtTo],
    queryFn: () =>
      financeApi.getCustomerStatement(Number(statementCustId), {
        dateFrom: stmtFrom || undefined,
        dateTo: stmtTo || undefined,
      }),
    enabled: tab === "statement" && Boolean(statementCustId),
  });

  const ar = arQuery.data;
  const ageing = ageingQuery.data;
  const stmt = stmtQuery.data;

  const handleExport = () => {
    if (tab === "summary" && ar) {
      downloadCsv(
        "customer-receivables-summary.csv",
        ["Code", "Customer", "Invoiced Rs", "Credited Rs", "Paid Rs", "Advance Rs", "Outstanding Rs", "Overdue Rs", "Pending Inv", "Overdue Inv"],
        ar.items.map((r) => [
          r.customer_code,
          r.customer_name,
          (r.total_invoiced_paisa / 100).toFixed(2),
          (r.total_credited_paisa / 100).toFixed(2),
          (r.total_payments_received_paisa / 100).toFixed(2),
          (r.advance_balance_paisa / 100).toFixed(2),
          (r.total_outstanding_paisa / 100).toFixed(2),
          (r.overdue_balance_paisa / 100).toFixed(2),
          r.pending_invoices_count,
          r.overdue_invoices_count,
        ])
      );
    } else if (tab === "ageing" && ageing) {
      downloadCsv(
        `ar-ageing-${ageing.as_of_date}.csv`,
        ["Invoice #", "Customer", "Invoice Date", "Due Date", "Days Past Due", "Bucket", "Total Rs", "Paid Rs", "Outstanding Rs"],
        ageing.invoices.map((i) => [
          i.invoice_number,
          i.customer_name,
          i.invoice_date,
          i.due_date,
          i.days_past_due,
          i.ageing_bucket,
          (i.original_paisa / 100).toFixed(2),
          (i.paid_paisa / 100).toFixed(2),
          (i.outstanding_paisa / 100).toFixed(2),
        ])
      );
    } else if (tab === "statement" && stmt) {
      downloadCsv(
        `statement-${stmt.customer_code}.csv`,
        ["Date", "Type", "Reference", "Description", "Debit Rs", "Credit Rs", "Running Balance Rs"],
        stmt.entries.map((e) => [
          e.entry_date,
          e.entry_type,
          e.reference_number,
          e.description,
          (e.debit_paisa / 100).toFixed(2),
          (e.credit_paisa / 100).toFixed(2),
          (e.running_balance_paisa / 100).toFixed(2),
        ])
      );
    }
  };

  return (
    <DesktopAdminLayout
      title="Accounts Receivable & Due-Date Ageing"
      subtitle="Customer-wise outstanding receivables, due-date ageing buckets (0-30, 31-60, 61-90, >90d), and chronological statements"
      actions={
        <Button variant="outline" onClick={handleExport}>
          <Download className="h-4 w-4" />
          Export CSV
        </Button>
      }
    >
      <div className="space-y-6">
        <Card>
          <CardContent className="p-4 flex flex-wrap items-end gap-3">
            <div className="flex gap-1.5">
              {[
                { key: "summary", label: "Customer Receivables" },
                { key: "ageing", label: "Invoice Ageing (By Due Date)" },
                { key: "statement", label: "Customer Statement" },
              ].map((t) => (
                <Button
                  key={t.key}
                  size="sm"
                  variant={tab === t.key ? "default" : "outline"}
                  onClick={() => {
                    setTab(t.key as typeof tab);
                    setPage(1);
                  }}
                >
                  {t.label}
                </Button>
              ))}
            </div>

            {tab !== "statement" && (
              <>
                <div className="relative flex-1 min-w-[200px]">
                  <Search className="h-4 w-4 absolute left-3 top-3 text-muted-foreground" />
                  <Input
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setPage(1);
                    }}
                    placeholder="Search customer or invoice..."
                    className="pl-9"
                  />
                </div>
                <div>
                  <label className="text-[11px] font-semibold text-muted-foreground">Reporting Date</label>
                  <Input
                    type="date"
                    value={asOfDate}
                    onChange={(e) => setAsOfDate(e.target.value)}
                    className="h-10"
                  />
                </div>
              </>
            )}

            {tab === "summary" && (
              <label className="flex items-center gap-2 text-xs font-medium cursor-pointer pb-2">
                <input
                  type="checkbox"
                  checked={onlyOutstanding}
                  onChange={(e) => setOnlyOutstanding(e.target.checked)}
                />
                Open balances only
              </label>
            )}
          </CardContent>
        </Card>

        {tab === "summary" && ar && (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs text-muted-foreground">Net Invoiced (Less CN)</div>
                  <div className="text-lg font-bold tabular-nums">{formatInrFromPaisa(ar.summary_total_invoiced_paisa)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs text-muted-foreground">Net Cash Received</div>
                  <div className="text-lg font-bold text-emerald-700 tabular-nums">{formatInrFromPaisa(ar.summary_total_received_paisa)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs text-muted-foreground">Total Outstanding</div>
                  <div className="text-lg font-bold text-amber-700 tabular-nums">{formatInrFromPaisa(ar.summary_total_outstanding_paisa)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs text-muted-foreground">Overdue (&gt; Due Date)</div>
                  <div className="text-lg font-bold text-red-700 tabular-nums">{formatInrFromPaisa(ar.summary_total_overdue_paisa)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <div className="text-xs text-muted-foreground">Unallocated Advances</div>
                  <div className="text-lg font-bold text-primary tabular-nums">{formatInrFromPaisa(ar.summary_total_advance_paisa)}</div>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <FileSpreadsheet className="h-4 w-4 text-primary" /> Customer-Wise Receivables Statement
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                      <th className="px-4 py-2.5">Customer</th>
                      <th className="px-3 py-2.5 text-right">Invoiced</th>
                      <th className="px-3 py-2.5 text-right">Payments Rec.</th>
                      <th className="px-3 py-2.5 text-right">Advance Bal.</th>
                      <th className="px-3 py-2.5 text-right">Outstanding</th>
                      <th className="px-3 py-2.5 text-right">Overdue</th>
                      <th className="px-3 py-2.5 text-center">Pending / Overdue</th>
                      <th className="px-4 py-2.5 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {ar.items.map((c) => (
                      <tr key={c.customer_id}>
                        <td className="px-4 py-2.5">
                          <div className="font-semibold">{c.customer_name}</div>
                          <div className="text-[11px] text-muted-foreground">
                            {c.customer_code} · Net {c.credit_days}d · {c.salesman_name ?? "Factory"}
                          </div>
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums">
                          {formatInrFromPaisa(c.total_invoiced_paisa - c.total_credited_paisa)}
                        </td>
                        <td className="px-3 py-2.5 text-right text-emerald-700 tabular-nums">
                          {formatInrFromPaisa(c.total_payments_received_paisa - c.total_refunded_paisa)}
                        </td>
                        <td className="px-3 py-2.5 text-right text-primary font-semibold tabular-nums">
                          {formatInrFromPaisa(c.advance_balance_paisa)}
                        </td>
                        <td className="px-3 py-2.5 text-right font-bold text-amber-700 tabular-nums">
                          {formatInrFromPaisa(c.total_outstanding_paisa)}
                        </td>
                        <td className="px-3 py-2.5 text-right font-bold text-red-700 tabular-nums">
                          {formatInrFromPaisa(c.overdue_balance_paisa)}
                        </td>
                        <td className="px-3 py-2.5 text-center">
                          <Badge variant={c.overdue_invoices_count > 0 ? "destructive" : "secondary"}>
                            {c.pending_invoices_count} / {c.overdue_invoices_count}
                          </Badge>
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setStatementCustId(String(c.customer_id));
                              setTab("statement");
                            }}
                          >
                            Statement
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </>
        )}

        {tab === "ageing" && ageing && (
          <>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
              <Card>
                <CardContent className="p-3.5">
                  <div className="text-[11px] uppercase text-muted-foreground">Not Yet Due</div>
                  <div className="text-base font-bold tabular-nums">{formatInrFromPaisa(ageing.not_due_paisa)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-3.5">
                  <div className="text-[11px] uppercase text-muted-foreground">0–30 Days Bucket</div>
                  <div className="text-base font-bold text-amber-700 tabular-nums">{formatInrFromPaisa(ageing.bucket_0_30_paisa)}</div>
                  <div className="text-[10px] text-muted-foreground">1–30d past due: {formatInrFromPaisa(ageing.overdue_1_30_paisa)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-3.5">
                  <div className="text-[11px] uppercase text-muted-foreground">31–60 Days Past Due</div>
                  <div className="text-base font-bold text-amber-800 tabular-nums">{formatInrFromPaisa(ageing.bucket_31_60_paisa)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-3.5">
                  <div className="text-[11px] uppercase text-muted-foreground">61–90 Days Past Due</div>
                  <div className="text-base font-bold text-red-700 tabular-nums">{formatInrFromPaisa(ageing.bucket_61_90_paisa)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-3.5">
                  <div className="text-[11px] uppercase text-muted-foreground">Above 90 Days</div>
                  <div className="text-base font-bold text-red-900 tabular-nums">{formatInrFromPaisa(ageing.bucket_90_plus_paisa)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-3.5">
                  <div className="text-[11px] uppercase text-muted-foreground">Total Overdue</div>
                  <div className="text-base font-bold text-destructive tabular-nums">{formatInrFromPaisa(ageing.overdue_total_paisa)}</div>
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <CalendarClock className="h-4 w-4 text-primary" /> Open Invoices by Due-Date Ageing (As of {formatOrderDate(ageing.as_of_date)})
                </CardTitle>
                <CardDescription>
                  Days overdue strictly calculated as (Reporting Date - Invoice Due Date).
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0 overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                      <th className="px-4 py-2.5">Invoice #</th>
                      <th className="px-3 py-2.5">Customer</th>
                      <th className="px-3 py-2.5">Invoice Date</th>
                      <th className="px-3 py-2.5">Due Date</th>
                      <th className="px-3 py-2.5 text-right">Days Past Due</th>
                      <th className="px-3 py-2.5">Bucket</th>
                      <th className="px-3 py-2.5 text-right">Paid</th>
                      <th className="px-4 py-2.5 text-right">Outstanding</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {ageing.invoices.map((i) => (
                      <tr key={i.invoice_id}>
                        <td className="px-4 py-2.5 font-mono font-bold">
                          <Link to={`/admin/billing/invoices/${i.invoice_id}`} className="text-primary hover:underline">
                            {i.invoice_number}
                          </Link>
                        </td>
                        <td className="px-3 py-2.5">{i.customer_name}</td>
                        <td className="px-3 py-2.5">{formatOrderDate(i.invoice_date)}</td>
                        <td className="px-3 py-2.5 font-semibold">{formatOrderDate(i.due_date)}</td>
                        <td className="px-3 py-2.5 text-right font-mono">{i.days_past_due}d</td>
                        <td className="px-3 py-2.5"><StatusBadge status={i.ageing_bucket} /></td>
                        <td className="px-3 py-2.5 text-right tabular-nums">{formatInrFromPaisa(i.paid_paisa)}</td>
                        <td className="px-4 py-2.5 text-right font-bold text-amber-700 tabular-nums">
                          {formatInrFromPaisa(i.outstanding_paisa)}
                        </td>
                      </tr>
                    ))}
                    {ageing.invoices.length === 0 && (
                      <tr>
                        <td colSpan={8} className="py-6 text-center text-muted-foreground">
                          No unpaid invoices as of {formatOrderDate(ageing.as_of_date)}.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </>
        )}

        {tab === "statement" && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Customer Ledger Statement</CardTitle>
              <CardDescription>Select a customer and optional date range to inspect full invoice, CN, payment & refund trail.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-3">
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">Customer</label>
                  <select
                    className="mt-1 flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    value={statementCustId}
                    onChange={(e) => setStatementCustId(e.target.value)}
                  >
                    <option value="">Select Customer...</option>
                    {(customersQuery.data ?? []).map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name} ({c.code})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">From Date</label>
                  <Input type="date" value={stmtFrom} onChange={(e) => setStmtFrom(e.target.value)} className="mt-1" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">To Date</label>
                  <Input type="date" value={stmtTo} onChange={(e) => setStmtTo(e.target.value)} className="mt-1" />
                </div>
              </div>

              {stmt && (
                <>
                  <div className="grid gap-3 sm:grid-cols-4 text-xs">
                    <div className="rounded border p-3">
                      <div className="text-muted-foreground">Gross Invoiced</div>
                      <div className="font-bold text-sm">{formatInrFromPaisa(stmt.total_invoiced_paisa)}</div>
                    </div>
                    <div className="rounded border p-3">
                      <div className="text-muted-foreground">Total Paid</div>
                      <div className="font-bold text-sm text-emerald-700">{formatInrFromPaisa(stmt.total_payments_received_paisa)}</div>
                    </div>
                    <div className="rounded border p-3">
                      <div className="text-muted-foreground">Open Advance</div>
                      <div className="font-bold text-sm text-primary">{formatInrFromPaisa(stmt.advance_balance_paisa)}</div>
                    </div>
                    <div className="rounded border p-3">
                      <div className="text-muted-foreground">Closing Outstanding Balance</div>
                      <div className="font-bold text-sm text-amber-700">{formatInrFromPaisa(stmt.total_outstanding_paisa)}</div>
                    </div>
                  </div>

                  <div className="overflow-x-auto rounded-lg border">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b bg-secondary/40 text-left uppercase text-muted-foreground">
                          <th className="px-3 py-2">Date</th>
                          <th className="px-3 py-2">Type</th>
                          <th className="px-3 py-2">Reference #</th>
                          <th className="px-3 py-2">Description</th>
                          <th className="px-3 py-2 text-right">Debit (Inv/Rev)</th>
                          <th className="px-3 py-2 text-right">Credit (Pay/CN)</th>
                          <th className="px-3 py-2 text-right">Running Balance</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {stmt.entries.map((e, idx) => (
                          <tr key={`${e.reference_number}-${idx}`}>
                            <td className="px-3 py-2">{formatOrderDate(e.entry_date)}</td>
                            <td className="px-3 py-2 font-mono">{e.entry_type}</td>
                            <td className="px-3 py-2 font-mono font-bold">{e.reference_number}</td>
                            <td className="px-3 py-2">{e.description}</td>
                            <td className="px-3 py-2 text-right tabular-nums">
                              {e.debit_paisa > 0 ? formatInrFromPaisa(e.debit_paisa) : "—"}
                            </td>
                            <td className="px-3 py-2 text-right text-emerald-700 tabular-nums">
                              {e.credit_paisa > 0 ? formatInrFromPaisa(e.credit_paisa) : "—"}
                            </td>
                            <td className="px-3 py-2 text-right font-bold tabular-nums">
                              {formatInrFromPaisa(e.running_balance_paisa)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </DesktopAdminLayout>
  );
}

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  Download,
  Eye,
  PlusCircle,
  RotateCcw,
  Search,
  Split,
  Undo2,
  Wallet,
} from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api, financeApi, type PaymentDetail } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDateTimeIst, formatInrFromPaisa, formatOrderDate } from "@/lib/money";

export function AdminPaymentsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const canOperate = user?.role_code === "FACTORY_ADMIN";

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [modeFilter, setModeFilter] = useState("");

  // Record Payment form
  const [showRecord, setShowRecord] = useState(false);
  const [customerId, setCustomerId] = useState<string>("");
  const [pmtDate, setPmtDate] = useState("");
  const [amountRs, setAmountRs] = useState("");
  const [pmtMode, setPmtMode] = useState("UPI");
  const [refNo, setRefNo] = useState("");
  const [remarks, setRemarks] = useState("");
  const [clientPmtId, setClientPmtId] = useState(() => crypto.randomUUID());
  const [allocInputs, setAllocInputs] = useState<Record<number, string>>({});

  // Detail / Action panel state
  const [selectedPmtId, setSelectedPmtId] = useState<number | null>(null);
  const [allocModalOpen, setAllocModalOpen] = useState(false);
  const [extraAllocInputs, setExtraAllocInputs] = useState<Record<number, string>>({});
  const [extraAllocNotes, setExtraAllocNotes] = useState("");
  const [reverseReason, setReverseReason] = useState("");
  const [showReverseForm, setShowReverseForm] = useState(false);
  const [showRefundForm, setShowRefundForm] = useState(false);
  const [refundRs, setRefundRs] = useState("");
  const [refundMode, setRefundMode] = useState("BANK_TRANSFER");
  const [refundRef, setRefundRef] = useState("");
  const [refundReason, setRefundReason] = useState("");
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [banner, setBanner] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  useEffect(() => {
    const qCust = searchParams.get("customer_id");
    if (qCust) {
      setCustomerId(qCust);
      setShowRecord(true);
    }
  }, [searchParams]);

  useEffect(() => {
    return () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    };
  }, [pdfUrl]);

  const customersQuery = useQuery({
    queryKey: ["finance-customers"],
    queryFn: () => api.getCustomers(),
  });

  const paymentsQuery = useQuery({
    queryKey: ["finance-payments", page, search, statusFilter, modeFilter],
    queryFn: () =>
      financeApi.getPayments({
        page,
        pageSize: 15,
        search: search.trim() || undefined,
        status: statusFilter || undefined,
        paymentMode: modeFilter || undefined,
      }),
    refetchInterval: 15_000,
  });

  const openInvRecordQuery = useQuery({
    queryKey: ["open-invoices-for-customer", customerId],
    queryFn: () => financeApi.getOpenInvoicesForCustomer(Number(customerId)),
    enabled: Boolean(customerId) && showRecord,
  });

  const detailQuery = useQuery({
    queryKey: ["finance-payment-detail", selectedPmtId],
    queryFn: () => financeApi.getPaymentDetail(selectedPmtId!),
    enabled: selectedPmtId !== null,
  });

  const selectedPmt: PaymentDetail | undefined = detailQuery.data;

  const openInvAllocQuery = useQuery({
    queryKey: ["open-invoices-for-alloc", selectedPmt?.customer_id],
    queryFn: () => financeApi.getOpenInvoicesForCustomer(selectedPmt!.customer_id),
    enabled: Boolean(selectedPmt?.customer_id) && allocModalOpen,
  });

  useEffect(() => {
    const qInv = searchParams.get("invoice_id");
    const invList = openInvRecordQuery.data ?? [];
    if (qInv && invList.length > 0) {
      const target = invList.find((x) => x.invoice_id === Number(qInv));
      if (target && !amountRs) {
        const rs = (target.outstanding_paisa / 100).toFixed(2);
        setAmountRs(rs);
        setAllocInputs({ [target.invoice_id]: rs });
      }
    }
  }, [openInvRecordQuery.data, searchParams]);

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["finance-payments"] });
    queryClient.invalidateQueries({ queryKey: ["finance-payment-detail"] });
    queryClient.invalidateQueries({ queryKey: ["finance-dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["finance-receivables"] });
    queryClient.invalidateQueries({ queryKey: ["finance-ageing"] });
    queryClient.invalidateQueries({ queryKey: ["open-invoices-for-customer"] });
    queryClient.invalidateQueries({ queryKey: ["open-invoices-for-alloc"] });
    queryClient.invalidateQueries({ queryKey: ["billing-dashboard"] });
    queryClient.invalidateQueries({ queryKey: ["invoice-detail"] });
  };

  const recordMutation = useMutation({
    mutationFn: () => {
      const amtPaisa = Math.round(Number(amountRs || 0) * 100);
      const allocations = Object.entries(allocInputs)
        .map(([iid, val]) => ({
          invoice_id: Number(iid),
          allocated_paisa: Math.round(Number(val || 0) * 100),
        }))
        .filter((a) => a.allocated_paisa > 0);
      return financeApi.recordPayment({
        customer_id: Number(customerId),
        payment_date: pmtDate || null,
        amount_paisa: amtPaisa,
        payment_mode: pmtMode,
        reference_no: refNo.trim() || null,
        remarks: remarks.trim() || null,
        client_payment_id: clientPmtId,
        allocations,
      });
    },
    onSuccess: (pmt) => {
      invalidateAll();
      setShowRecord(false);
      setAmountRs("");
      setRefNo("");
      setRemarks("");
      setAllocInputs({});
      setClientPmtId(crypto.randomUUID());
      setSelectedPmtId(pmt.id);
      setBanner({
        kind: "success",
        msg: `Recorded ${pmt.payment_number} for ${formatInrFromPaisa(pmt.amount_paisa)} (${pmt.status}).`,
      });
    },
    onError: (err) =>
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Failed to record customer payment.",
      }),
  });

  const allocateMutation = useMutation({
    mutationFn: () => {
      const allocations = Object.entries(extraAllocInputs)
        .map(([iid, val]) => ({
          invoice_id: Number(iid),
          allocated_paisa: Math.round(Number(val || 0) * 100),
        }))
        .filter((a) => a.allocated_paisa > 0);
      return financeApi.allocatePayment(selectedPmt!.id, {
        allocations,
        notes: extraAllocNotes.trim() || null,
        expected_version: selectedPmt?.version,
      });
    },
    onSuccess: (pmt) => {
      invalidateAll();
      setAllocModalOpen(false);
      setExtraAllocInputs({});
      setExtraAllocNotes("");
      setBanner({
        kind: "success",
        msg: `Allocated ${pmt.payment_number}; remaining unallocated: ${formatInrFromPaisa(pmt.unallocated_paisa)}.`,
      });
    },
    onError: (err) =>
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Allocation failed.",
      }),
  });

  const reverseMutation = useMutation({
    mutationFn: () =>
      financeApi.reversePayment(selectedPmt!.id, {
        reason: reverseReason.trim(),
        expected_version: selectedPmt?.version,
      }),
    onSuccess: (pmt) => {
      invalidateAll();
      setShowReverseForm(false);
      setReverseReason("");
      setBanner({ kind: "success", msg: `Reversed ${pmt.payment_number} and updated linked AR.` });
    },
    onError: (err) =>
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Reversal failed.",
      }),
  });

  const refundMutation = useMutation({
    mutationFn: () =>
      financeApi.refundPayment(selectedPmt!.id, {
        amount_paisa: Math.round(Number(refundRs || 0) * 100),
        refund_mode: refundMode,
        reference_no: refundRef.trim() || null,
        reason: refundReason.trim(),
        expected_version: selectedPmt?.version,
      }),
    onSuccess: (pmt) => {
      invalidateAll();
      setShowRefundForm(false);
      setRefundRs("");
      setRefundRef("");
      setRefundReason("");
      setBanner({
        kind: "success",
        msg: `Issued advance refund on ${pmt.payment_number}. Remaining unallocated: ${formatInrFromPaisa(pmt.unallocated_paisa)}.`,
      });
    },
    onError: (err) =>
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Refund failed.",
      }),
  });

  const reverseAllocMutation = useMutation({
    mutationFn: (allocId: number) =>
      financeApi.reverseAllocation(allocId, "Reallocated or corrected via Payment Desk"),
    onSuccess: () => {
      invalidateAll();
      setBanner({ kind: "success", msg: "Invoice allocation reversed cleanly back to unallocated advance." });
    },
    onError: (err) =>
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Failed to reverse allocation.",
      }),
  });

  const handleReceiptPdf = async (pmt: PaymentDetail, mode: "preview" | "download") => {
    try {
      const blob = await financeApi.fetchReceiptPdfBlob(pmt.id);
      const url = URL.createObjectURL(blob);
      if (mode === "preview") {
        if (pdfUrl) URL.revokeObjectURL(pdfUrl);
        setPdfUrl(url);
      } else {
        const a = document.createElement("a");
        a.href = url;
        a.download = `${pmt.payment_number.replaceAll("/", "-")}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch {
      setBanner({ kind: "error", msg: "Unable to load Payment Receipt PDF." });
    }
  };

  const openInvs = openInvRecordQuery.data ?? [];
  const pmtData = paymentsQuery.data;

  const handleExportPaymentsCsv = () => {
    const list = pmtData?.items ?? [];
    if (list.length === 0) return;
    const esc = (v: string | number) => `"${String(v).replaceAll('"', '""')}"`;
    const rows = [
      ["Receipt #", "Date", "Customer Code", "Customer Name", "Mode", "Reference", "Status", "Amount Rs", "Allocated Rs", "Refunded Rs", "Unallocated Rs"].map(esc).join(","),
      ...list.map((p) =>
        [
          p.payment_number,
          p.payment_date,
          p.customer_code,
          p.customer_name,
          p.payment_mode,
          p.reference_no ?? "",
          p.status,
          (p.amount_paisa / 100).toFixed(2),
          (p.allocated_paisa / 100).toFixed(2),
          (p.refunded_paisa / 100).toFixed(2),
          (p.unallocated_paisa / 100).toFixed(2),
        ]
          .map(esc)
          .join(",")
      ),
    ];
    const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "customer-payments-register.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <DesktopAdminLayout
      title="Customer Payments & Invoice Allocations"
      subtitle="Record cash/UPI/NEFT/cheque receipts, allocate across single or multiple invoices, hold advances, and print receipts"
      actions={
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={handleExportPaymentsCsv} disabled={!pmtData?.items.length}>
            <Download className="h-4 w-4" />
            Export CSV
          </Button>
          <Button variant="outline" asChild>
            <Link to="/admin/finance/receivables">AR &amp; Ageing →</Link>
          </Button>
          {canOperate && (
            <Button onClick={() => setShowRecord((s) => !s)}>
              <PlusCircle className="h-4 w-4" />
              {showRecord ? "Close Form" : "Record Payment"}
            </Button>
          )}
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

        {/* Record Customer Payment Wizard */}
        {showRecord && canOperate && (
          <Card className="border-primary/40">
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Wallet className="h-4 w-4 text-primary" />
                Record Customer Payment Receipt
              </CardTitle>
              <CardDescription>
                Leave invoice allocations at 0 to record an Advance Payment, or split across one or multiple open invoices atomically.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-5">
                <div className="md:col-span-2">
                  <label className="text-xs font-semibold text-muted-foreground">Customer</label>
                  <select
                    className="mt-1 flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    value={customerId}
                    onChange={(e) => {
                      setCustomerId(e.target.value);
                      setAllocInputs({});
                    }}
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
                  <label className="text-xs font-semibold text-muted-foreground">Amount Received (₹)</label>
                  <Input
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={amountRs}
                    onChange={(e) => setAmountRs(e.target.value)}
                    placeholder="4000.00"
                    className="mt-1"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">Payment Mode</label>
                  <select
                    className="mt-1 flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    value={pmtMode}
                    onChange={(e) => setPmtMode(e.target.value)}
                  >
                    <option value="UPI">UPI</option>
                    <option value="BANK_TRANSFER">Bank Transfer</option>
                    <option value="NEFT">NEFT</option>
                    <option value="RTGS">RTGS</option>
                    <option value="CASH">Cash</option>
                    <option value="CHEQUE">Cheque</option>
                    <option value="CARD">Card</option>
                    <option value="OTHER">Other</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">Payment Date</label>
                  <Input
                    type="date"
                    value={pmtDate}
                    onChange={(e) => setPmtDate(e.target.value)}
                    className="mt-1"
                  />
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">
                    UTR / Cheque / Transaction Reference
                  </label>
                  <Input
                    value={refNo}
                    onChange={(e) => setRefNo(e.target.value)}
                    placeholder="e.g. UPI-6319204589"
                    className="mt-1"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">Remarks</label>
                  <Input
                    value={remarks}
                    onChange={(e) => setRemarks(e.target.value)}
                    placeholder="Payment notes..."
                    className="mt-1"
                  />
                </div>
              </div>

              {customerId && (
                <div className="space-y-2 rounded-lg border p-3 bg-secondary/20">
                  <div className="flex items-center justify-between text-xs font-bold">
                    <span>Open Invoices for Allocation ({openInvs.length})</span>
                    {Number(amountRs) > 0 && openInvs.length > 0 && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        onClick={() => {
                          let rem = Math.round(Number(amountRs) * 100);
                          const next: Record<number, string> = {};
                          for (const oi of openInvs) {
                            if (rem <= 0) break;
                            const take = Math.min(rem, oi.outstanding_paisa);
                            next[oi.invoice_id] = (take / 100).toFixed(2);
                            rem -= take;
                          }
                          setAllocInputs(next);
                        }}
                      >
                        Auto-Fill FIFO By Due Date
                      </Button>
                    )}
                  </div>
                  {openInvs.length === 0 ? (
                    <div className="text-xs text-muted-foreground">
                      No open unpaid invoices; submitting will hold this receipt as an Unallocated Customer Advance.
                    </div>
                  ) : (
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b text-left text-muted-foreground">
                          <th className="py-1.5 pr-3">Invoice #</th>
                          <th className="py-1.5 pr-3">Due Date</th>
                          <th className="py-1.5 pr-3 text-right">Invoice Total</th>
                          <th className="py-1.5 pr-3 text-right">Outstanding</th>
                          <th className="py-1.5 text-right w-40">Allocate (₹)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {openInvs.map((oi) => (
                          <tr key={oi.invoice_id}>
                            <td className="py-2 pr-3 font-mono font-bold">{oi.invoice_number}</td>
                            <td className="py-2 pr-3">
                              {formatOrderDate(oi.due_date)}
                              {oi.is_overdue && (
                                <span className="ml-1 text-red-700 font-semibold">
                                  ({oi.days_past_due}d overdue)
                                </span>
                              )}
                            </td>
                            <td className="py-2 pr-3 text-right tabular-nums">
                              {formatInrFromPaisa(oi.grand_total_paisa)}
                            </td>
                            <td className="py-2 pr-3 text-right font-bold text-amber-700 tabular-nums">
                              {formatInrFromPaisa(oi.outstanding_paisa)}
                            </td>
                            <td className="py-1.5 text-right">
                              <Input
                                type="number"
                                min="0"
                                step="0.01"
                                max={(oi.outstanding_paisa / 100).toFixed(2)}
                                value={allocInputs[oi.invoice_id] ?? ""}
                                onChange={(e) =>
                                  setAllocInputs((prev) => ({
                                    ...prev,
                                    [oi.invoice_id]: e.target.value,
                                  }))
                                }
                                className="h-8 text-right tabular-nums"
                                placeholder="0.00"
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}

              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setShowRecord(false)}>
                  Cancel
                </Button>
                <Button
                  disabled={!customerId || !(Number(amountRs) > 0) || recordMutation.isPending}
                  onClick={() => recordMutation.mutate()}
                >
                  {recordMutation.isPending ? "Recording..." : "Save Customer Payment"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Filter Bar */}
        <Card>
          <CardContent className="p-4 flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="h-4 w-4 absolute left-3 top-3 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                placeholder="Search payment #, reference #, or customer..."
                className="pl-9"
              />
            </div>
            <select
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
              value={modeFilter}
              onChange={(e) => {
                setModeFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All Modes</option>
              <option value="CASH">Cash</option>
              <option value="UPI">UPI</option>
              <option value="BANK_TRANSFER">Bank Transfer</option>
              <option value="NEFT">NEFT</option>
              <option value="RTGS">RTGS</option>
              <option value="CHEQUE">Cheque</option>
            </select>
            <select
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All Statuses</option>
              <option value="RECORDED">Advance / Unallocated</option>
              <option value="PARTIALLY_ALLOCATED">Partially Allocated</option>
              <option value="ALLOCATED">Allocated</option>
              <option value="REVERSED">Reversed</option>
              <option value="REFUNDED">Refunded</option>
            </select>
          </CardContent>
        </Card>

        {/* Payment Register Table */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Payment History Register ({pmtData?.total ?? 0})</CardTitle>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-y bg-secondary/40 text-left uppercase text-muted-foreground">
                  <th className="px-4 py-2.5">Receipt #</th>
                  <th className="px-3 py-2.5">Date</th>
                  <th className="px-3 py-2.5">Customer</th>
                  <th className="px-3 py-2.5">Mode / Ref</th>
                  <th className="px-3 py-2.5 text-right">Amount</th>
                  <th className="px-3 py-2.5 text-right">Allocated</th>
                  <th className="px-3 py-2.5 text-right">Unallocated</th>
                  <th className="px-3 py-2.5">Status</th>
                  <th className="px-4 py-2.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {(pmtData?.items ?? []).map((p) => (
                  <tr key={p.id} className={selectedPmtId === p.id ? "bg-primary/5" : "hover:bg-secondary/30"}>
                    <td className="px-4 py-2.5 font-mono font-bold text-primary">{p.payment_number}</td>
                    <td className="px-3 py-2.5">{formatOrderDate(p.payment_date)}</td>
                    <td className="px-3 py-2.5 font-medium">{p.customer_name}</td>
                    <td className="px-3 py-2.5">
                      <div>{p.payment_mode}</div>
                      {p.reference_no && (
                        <div className="font-mono text-[11px] text-muted-foreground">{p.reference_no}</div>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right font-bold tabular-nums">
                      {formatInrFromPaisa(p.amount_paisa)}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-emerald-700">
                      {formatInrFromPaisa(p.allocated_paisa)}
                    </td>
                    <td className="px-3 py-2.5 text-right tabular-nums text-amber-700 font-semibold">
                      {formatInrFromPaisa(p.unallocated_paisa)}
                    </td>
                    <td className="px-3 py-2.5">
                      <StatusBadge status={p.status} />
                    </td>
                    <td className="px-4 py-2.5 text-right space-x-1 whitespace-nowrap">
                      <Button
                        size="sm"
                        variant={selectedPmtId === p.id ? "default" : "outline"}
                        onClick={() => {
                          setSelectedPmtId(p.id);
                          setAllocModalOpen(false);
                          setShowReverseForm(false);
                          setShowRefundForm(false);
                        }}
                      >
                        Manage
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => handleReceiptPdf(p, "download")}>
                        <Download className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
                {(pmtData?.items ?? []).length === 0 && (
                  <tr>
                    <td colSpan={9} className="py-8 text-center text-muted-foreground">
                      No payment records match current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </CardContent>
          {pmtData && pmtData.total_pages > 1 && (
            <div className="flex items-center justify-between border-t px-4 py-3 text-xs">
              <span>
                Page {pmtData.page} of {pmtData.total_pages}
              </span>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page >= pmtData.total_pages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </Button>
              </div>
            </div>
          )}
        </Card>

        {/* Selected Payment Inspection, Allocation, Refund & Reversal */}
        {selectedPmt && (
          <Card className="border-primary/40">
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle className="text-base">
                  {selectedPmt.payment_number} — {selectedPmt.customer_name}
                </CardTitle>
                <CardDescription>
                  Recorded by {selectedPmt.recorded_by_name} on {formatDateTimeIst(selectedPmt.recorded_at)}
                </CardDescription>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => handleReceiptPdf(selectedPmt, "preview")}>
                  <Eye className="h-3.5 w-3.5" /> Preview Receipt PDF
                </Button>
                <Button size="sm" variant="outline" onClick={() => handleReceiptPdf(selectedPmt, "download")}>
                  <Download className="h-3.5 w-3.5" /> Download PDF
                </Button>
                {canOperate && selectedPmt.unallocated_paisa > 0 && selectedPmt.status !== "REVERSED" && (
                  <>
                    <Button size="sm" onClick={() => setAllocModalOpen((s) => !s)}>
                      <Split className="h-3.5 w-3.5" /> Allocate Advance
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setShowRefundForm((s) => !s)}>
                      <Undo2 className="h-3.5 w-3.5" /> Refund Advance
                    </Button>
                  </>
                )}
                {canOperate && selectedPmt.status !== "REVERSED" && selectedPmt.refunded_paisa === 0 && (
                  <Button size="sm" variant="destructive" onClick={() => setShowReverseForm((s) => !s)}>
                    <RotateCcw className="h-3.5 w-3.5" /> Reverse Payment
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {pdfUrl && (
                <div className="rounded-lg border overflow-hidden">
                  <div className="flex justify-between items-center bg-secondary/40 px-3 py-1.5 text-xs font-semibold">
                    <span>Receipt PDF Preview</span>
                    <Button size="sm" variant="ghost" onClick={() => setPdfUrl(null)}>
                      Close
                    </Button>
                  </div>
                  <iframe title="Payment Receipt PDF" src={pdfUrl} className="h-[460px] w-full" />
                </div>
              )}

              {allocModalOpen && (
                <div className="rounded-lg border p-4 space-y-3 bg-secondary/20">
                  <div className="text-xs font-bold">
                    Allocate Available Advance ({formatInrFromPaisa(selectedPmt.unallocated_paisa)}) to Open Invoices
                  </div>
                  <div className="space-y-2">
                    {(openInvAllocQuery.data ?? []).map((oi) => (
                      <div key={oi.invoice_id} className="flex items-center justify-between gap-4 text-xs">
                        <div>
                          <span className="font-mono font-bold">{oi.invoice_number}</span> · Outstanding:{" "}
                          <span className="font-semibold text-amber-700">
                            {formatInrFromPaisa(oi.outstanding_paisa)}
                          </span>
                        </div>
                        <Input
                          type="number"
                          min="0"
                          step="0.01"
                          value={extraAllocInputs[oi.invoice_id] ?? ""}
                          onChange={(e) =>
                            setExtraAllocInputs((prev) => ({ ...prev, [oi.invoice_id]: e.target.value }))
                          }
                          placeholder="Amount ₹"
                          className="w-36 h-8 text-right"
                        />
                      </div>
                    ))}
                    {(openInvAllocQuery.data ?? []).length === 0 && (
                      <div className="text-xs text-muted-foreground">No open unpaid invoices for this customer.</div>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Input
                      value={extraAllocNotes}
                      onChange={(e) => setExtraAllocNotes(e.target.value)}
                      placeholder="Allocation notes..."
                      className="h-9"
                    />
                    <Button size="sm" disabled={allocateMutation.isPending} onClick={() => allocateMutation.mutate()}>
                      Apply Allocation
                    </Button>
                  </div>
                </div>
              )}

              {showRefundForm && (
                <div className="rounded-lg border border-amber-300 p-4 space-y-3 bg-amber-50/40">
                  <div className="text-xs font-bold">
                    Refund Unallocated Balance (Max {formatInrFromPaisa(selectedPmt.unallocated_paisa)})
                  </div>
                  <div className="grid gap-3 md:grid-cols-4">
                    <Input
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={refundRs}
                      onChange={(e) => setRefundRs(e.target.value)}
                      placeholder="Refund ₹"
                    />
                    <select
                      className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                      value={refundMode}
                      onChange={(e) => setRefundMode(e.target.value)}
                    >
                      <option value="BANK_TRANSFER">Bank Transfer</option>
                      <option value="UPI">UPI</option>
                      <option value="CASH">Cash</option>
                      <option value="CHEQUE">Cheque</option>
                    </select>
                    <Input value={refundRef} onChange={(e) => setRefundRef(e.target.value)} placeholder="Ref # (optional)" />
                    <Input value={refundReason} onChange={(e) => setRefundReason(e.target.value)} placeholder="Mandatory reason (min 5 chars)" />
                  </div>
                  <Button
                    size="sm"
                    disabled={refundReason.trim().length < 5 || !(Number(refundRs) > 0) || refundMutation.isPending}
                    onClick={() => refundMutation.mutate()}
                  >
                    Confirm Refund
                  </Button>
                </div>
              )}

              {showReverseForm && (
                <div className="rounded-lg border border-red-300 p-4 space-y-3 bg-red-50/40">
                  <div className="text-xs font-bold text-red-900">
                    Reverse Payment {selectedPmt.payment_number} (Unwinds all active invoice allocations atomically)
                  </div>
                  <div className="flex gap-2">
                    <Input
                      value={reverseReason}
                      onChange={(e) => setReverseReason(e.target.value)}
                      placeholder="Audit reason e.g. Cheque bounced / incorrect customer receipt (min 5 chars)..."
                    />
                    <Button
                      variant="destructive"
                      size="sm"
                      disabled={reverseReason.trim().length < 5 || reverseMutation.isPending}
                      onClick={() => reverseMutation.mutate()}
                    >
                      Confirm Reversal
                    </Button>
                  </div>
                </div>
              )}

              <div className="overflow-x-auto rounded-lg border">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b bg-secondary/40 text-left uppercase text-muted-foreground">
                      <th className="px-3 py-2">Invoice #</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2 text-right">Allocated</th>
                      <th className="px-3 py-2 text-right">Inv. Balance Due</th>
                      <th className="px-3 py-2">Timestamp</th>
                      <th className="px-3 py-2 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {selectedPmt.allocations.map((a) => (
                      <tr key={a.id}>
                        <td className="px-3 py-2 font-mono font-bold">
                          <Link to={`/admin/billing/invoices/${a.invoice_id}`} className="text-primary hover:underline">
                            {a.invoice_number}
                          </Link>
                        </td>
                        <td className="px-3 py-2">
                          <Badge variant={a.status === "ACTIVE" ? "success" : "destructive"}>{a.status}</Badge>
                        </td>
                        <td className="px-3 py-2 text-right font-bold tabular-nums">
                          {formatInrFromPaisa(a.allocated_paisa)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {formatInrFromPaisa(a.invoice_outstanding_paisa)}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {formatDateTimeIst(a.allocated_at)}
                          {a.reversal_reason && <div className="text-red-700">{a.reversal_reason}</div>}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {a.status === "ACTIVE" && canOperate && (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 text-destructive"
                              onClick={() => reverseAllocMutation.mutate(a.id)}
                            >
                              Unallocate
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {selectedPmt.allocations.length === 0 && (
                      <tr>
                        <td colSpan={6} className="py-5 text-center text-muted-foreground">
                          Unallocated advance balance ({formatInrFromPaisa(selectedPmt.unallocated_paisa)}).
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </DesktopAdminLayout>
  );
}

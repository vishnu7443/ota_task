import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  CheckCircle2,
  Download,
  Eye,
  FileClock,
  FileWarning,
  Mail,
  MessageCircle,
  ShieldCheck,
  Truck,
} from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDateTimeIst, formatInrFromPaisa, formatOrderDate } from "@/lib/money";

export function AdminInvoiceDetailPage() {
  const { invoiceId } = useParams<{ invoiceId: string }>();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canOperate = user?.role_code === "FACTORY_ADMIN";

  const [verifyRemarks, setVerifyRemarks] = useState("");
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const [showCnForm, setShowCnForm] = useState(false);
  const [cnReason, setCnReason] = useState("");
  const [cnNoteType, setCnNoteType] = useState<"INVOICE_CANCELLATION" | "SALES_RETURN" | "VALUE_ADJUSTMENT">(
    "INVOICE_CANCELLATION"
  );
  const [cnDisposition, setCnDisposition] = useState<
    "NONE_NOT_DISPATCHED" | "RESTOCK_SELLABLE" | "SCRAP_DAMAGED"
  >("NONE_NOT_DISPATCHED");
  const [banner, setBanner] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  useEffect(() => {
    return () => {
      if (pdfPreviewUrl) URL.revokeObjectURL(pdfPreviewUrl);
    };
  }, [pdfPreviewUrl]);

  const invQuery = useQuery({
    queryKey: ["invoice-detail", invoiceId],
    queryFn: () => api.getInvoiceDetail(Number(invoiceId)),
    enabled: Boolean(invoiceId),
    refetchInterval: 15_000,
  });

  const verifyMutation = useMutation({
    mutationFn: () =>
      api.verifyInvoice(Number(invoiceId), {
        remarks: verifyRemarks.trim() || null,
        expected_version: invQuery.data?.version,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["invoice-detail", invoiceId], updated);
      queryClient.invalidateQueries({ queryKey: ["billing-dashboard"] });
      setBanner({ kind: "success", msg: "Draft GST invoice verified and ready for issuance." });
    },
    onError: (err) => {
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Failed to verify invoice.",
      });
    },
  });

  const issueMutation = useMutation({
    mutationFn: () =>
      api.issueInvoice(Number(invoiceId), {
        verification_remarks: verifyRemarks.trim() || null,
        expected_version: invQuery.data?.version,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["invoice-detail", invoiceId], updated);
      queryClient.invalidateQueries({ queryKey: ["billing-dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["dispatch-dashboard"] });
      setBanner({
        kind: "success",
        msg: `Issued statutory invoice ${updated.invoice_number} (FY ${updated.financial_year}).`,
      });
    },
    onError: (err) => {
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Failed to issue invoice.",
      });
    },
  });

  const createCnMutation = useMutation({
    mutationFn: () => {
      const inv = invQuery.data!;
      return api.createCreditNote({
        original_invoice_id: inv.id,
        note_type: cnNoteType,
        reason: cnReason.trim(),
        cancel_original_invoice: cnNoteType === "INVOICE_CANCELLATION",
        issue_immediately: true,
        items: inv.items.map((it) => ({
          invoice_item_id: it.id,
          qty_pkts: it.qty_pkts,
          return_disposition: cnDisposition,
        })),
      });
    },
    onSuccess: (cn) => {
      queryClient.invalidateQueries({ queryKey: ["invoice-detail", invoiceId] });
      queryClient.invalidateQueries({ queryKey: ["billing-dashboard"] });
      queryClient.invalidateQueries({ queryKey: ["credit-notes"] });
      queryClient.invalidateQueries({ queryKey: ["inventory-overview"] });
      setShowCnForm(false);
      setCnReason("");
      setBanner({
        kind: "success",
        msg: `Issued Credit Note ${cn.cn_number} reversing ${formatInrFromPaisa(cn.total_reversed_paisa)}.`,
      });
    },
    onError: (err) => {
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Failed to issue Credit Note.",
      });
    },
  });

  const handlePdfAction = async (mode: "preview" | "download") => {
    try {
      const inv = invQuery.data!;
      const blob = await api.fetchInvoicePdfBlob(inv.id);
      const url = URL.createObjectURL(blob);
      if (mode === "preview") {
        if (pdfPreviewUrl) URL.revokeObjectURL(pdfPreviewUrl);
        setPdfPreviewUrl(url);
      } else {
        const a = document.createElement("a");
        a.href = url;
        a.download = `${(inv.invoice_number || inv.draft_ref).replaceAll("/", "-")}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Unable to load invoice PDF.",
      });
    }
  };

  const inv = invQuery.data;
  const shareSummaryText = inv
    ? `GST Tax Invoice ${inv.invoice_number ?? inv.draft_ref} (${formatOrderDate(inv.invoice_date)}) from ${inv.seller_legal_name} for ${inv.customer_name}. Order: ${inv.order_number}. Grand Total: ${formatInrFromPaisa(inv.grand_total_paisa)}. Balance Due: ${formatInrFromPaisa(inv.outstanding_paisa)}.`
    : "";

  return (
    <DesktopAdminLayout
      title={inv ? `Invoice ${inv.invoice_number ?? inv.draft_ref}` : "GST Invoice Details"}
      subtitle={
        inv
          ? `Order ${inv.order_number} · ${inv.customer_name} · FY ${inv.financial_year}`
          : "Loading invoice..."
      }
      actions={
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild>
            <Link to="/admin/billing">
              <ArrowLeft className="h-4 w-4" />
              Back to Billing
            </Link>
          </Button>
          {inv && (
            <>
              <Button variant="outline" onClick={() => handlePdfAction("preview")}>
                <Eye className="h-4 w-4" />
                Preview PDF
              </Button>
              <Button variant="outline" onClick={() => handlePdfAction("download")}>
                <Download className="h-4 w-4" />
                Download PDF
              </Button>
              {inv.doc_status === "ISSUED" && (
                <>
                  <Button variant="outline" asChild>
                    <a
                      href={`https://wa.me/?text=${encodeURIComponent(shareSummaryText)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <MessageCircle className="h-4 w-4" />
                      WhatsApp Share
                    </a>
                  </Button>
                  <Button variant="outline" asChild>
                    <a
                      href={`mailto:?subject=${encodeURIComponent(
                        `GST Invoice ${inv.invoice_number ?? inv.draft_ref} - ${inv.seller_legal_name}`
                      )}&body=${encodeURIComponent(shareSummaryText)}`}
                    >
                      <Mail className="h-4 w-4" />
                      Email
                    </a>
                  </Button>
                </>
              )}
            </>
          )}
          {inv?.doc_status === "ISSUED" && inv.outstanding_paisa > 0 && canOperate && (
            <Button asChild variant="outline">
              <Link to={`/admin/finance/payments?customer_id=${inv.customer_id}&invoice_id=${inv.id}`}>
                Record Payment
              </Link>
            </Button>
          )}
          {inv?.doc_status === "ISSUED" && inv.remaining_dispatch_qty_pkts > 0 && canOperate && (
            <Button asChild>
              <Link to={`/admin/dispatch?invoice_id=${inv.id}`}>
                <Truck className="h-4 w-4" />
                Create Dispatch ({inv.remaining_dispatch_qty_pkts} pkts left)
              </Link>
            </Button>
          )}
        </div>
      }
    >
      {inv && (
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

          {/* Status Strip + Lifecycle Controls */}
          <Card>
            <CardContent className="p-4 flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={inv.doc_status} />
                <StatusBadge status={inv.dispatch_status} />
                <StatusBadge status={inv.payment_status} />
                <StatusBadge status={inv.supply_type} />
                <Badge variant="outline">{inv.nature_of_supply}</Badge>
                {inv.verified_at && (
                  <Badge variant="success" className="gap-1">
                    <ShieldCheck className="h-3 w-3" />
                    Verified by {inv.verified_by_name}
                  </Badge>
                )}
              </div>

              {canOperate && (
                <div className="flex flex-wrap items-center gap-2">
                  {inv.doc_status === "DRAFT" && (
                    <>
                      <Input
                        value={verifyRemarks}
                        onChange={(e) => setVerifyRemarks(e.target.value)}
                        placeholder="Verification / issue remarks..."
                        className="w-60 h-9"
                      />
                      {!inv.verified_at && (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={verifyMutation.isPending}
                          onClick={() => verifyMutation.mutate()}
                        >
                          Verify Draft
                        </Button>
                      )}
                      <Button size="sm" disabled={issueMutation.isPending} onClick={() => issueMutation.mutate()}>
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        {issueMutation.isPending ? "Issuing..." : "Issue Statutory Invoice"}
                      </Button>
                    </>
                  )}
                  {inv.doc_status === "ISSUED" && (
                    <Button size="sm" variant="destructive" onClick={() => setShowCnForm((s) => !s)}>
                      <FileWarning className="h-3.5 w-3.5" />
                      Issue Credit Note / Cancel
                    </Button>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Credit Note Form Modal/Card */}
          {showCnForm && inv.doc_status === "ISSUED" && canOperate && (
            <Card className="border-red-300">
              <CardHeader>
                <CardTitle className="text-base text-red-900">
                  Issue GST Credit Note against {inv.invoice_number}
                </CardTitle>
                <CardDescription>
                  Issued invoices are never deleted or silently edited; Credit Notes create gap-free reversals (`CN/YYYY-YY/XXXX`).
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 md:grid-cols-3">
                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Credit Note Type</label>
                    <select
                      className="mt-1 flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                      value={cnNoteType}
                      onChange={(e) => setCnNoteType(e.target.value as typeof cnNoteType)}
                    >
                      <option value="INVOICE_CANCELLATION">Full Invoice Cancellation</option>
                      <option value="SALES_RETURN">Sales Return</option>
                      <option value="VALUE_ADJUSTMENT">Value / Rate Adjustment</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Stock Return Disposition</label>
                    <select
                      className="mt-1 flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                      value={cnDisposition}
                      onChange={(e) => setCnDisposition(e.target.value as typeof cnDisposition)}
                    >
                      <option value="NONE_NOT_DISPATCHED">None (Not Dispatched / Value Only)</option>
                      <option value="RESTOCK_SELLABLE">Restock Sellable Goods (CREDIT_RETURN_IN)</option>
                      <option value="SCRAP_DAMAGED">Damaged / Spoiled Return (Do Not Restock)</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Statutory Reason (min 5 chars)</label>
                    <Input
                      className="mt-1"
                      value={cnReason}
                      onChange={(e) => setCnReason(e.target.value)}
                      placeholder="e.g. Customer cancelled prior to truck dispatch"
                    />
                  </div>
                </div>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => setShowCnForm(false)}>
                    Close
                  </Button>
                  <Button
                    variant="destructive"
                    disabled={cnReason.trim().length < 5 || createCnMutation.isPending}
                    onClick={() => createCnMutation.mutate()}
                  >
                    {createCnMutation.isPending ? "Issuing Credit Note..." : "Confirm & Issue Credit Note"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Embedded PDF Preview Modal Card */}
          {pdfPreviewUrl && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between py-3">
                <CardTitle className="text-sm">Statutory PDF Preview (Rendered from Persisted DB Record)</CardTitle>
                <Button size="sm" variant="ghost" onClick={() => setPdfPreviewUrl(null)}>
                  Close Preview
                </Button>
              </CardHeader>
              <CardContent className="p-0">
                <iframe
                  title="Invoice PDF Preview"
                  src={pdfPreviewUrl}
                  className="h-[620px] w-full border-t"
                />
              </CardContent>
            </Card>
          )}

          {/* Seller / Customer / Place-of-Supply Metadata */}
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">Supplier</CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-1">
                <div className="font-bold">{inv.seller_legal_name}</div>
                <div className="font-mono text-xs">GSTIN: {inv.seller_gstin}</div>
                <div className="text-xs text-muted-foreground">
                  State: {inv.seller_state_name} ({inv.seller_state_code})
                </div>
                <div className="text-xs text-muted-foreground">{inv.seller_address}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
                  Customer &amp; Place of Supply
                </CardTitle>
              </CardHeader>
              <CardContent className="text-sm space-y-1">
                <div className="font-bold">
                  {inv.customer_name} ({inv.customer_type})
                </div>
                <div className="font-mono text-xs">GSTIN: {inv.buyer_gstin ?? "Unregistered"}</div>
                <div className="text-xs font-semibold text-primary">
                  POS: {inv.place_of_supply_state_name} ({inv.place_of_supply_state_code})
                </div>
                <div className="text-xs text-muted-foreground">Bill: {inv.billing_address_snapshot}</div>
                <div className="text-xs text-muted-foreground">Ship: {inv.shipping_address_snapshot}</div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs uppercase tracking-wider text-muted-foreground">
                  Dates, Terms &amp; Legal Rule
                </CardTitle>
              </CardHeader>
              <CardContent className="text-xs space-y-1.5">
                <div>
                  <span className="text-muted-foreground">Invoice Date:</span>{" "}
                  <strong>{formatOrderDate(inv.invoice_date)}</strong> · Due:{" "}
                  <strong>{formatOrderDate(inv.due_date)}</strong>
                </div>
                <div>
                  <span className="text-muted-foreground">Payment Terms:</span> {inv.payment_terms}
                </div>
                <div className="rounded bg-secondary/60 p-2 text-[11px] leading-relaxed">
                  {String(inv.tax_calculation_snapshot.rule_rationale ?? "")}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Line Items & GST Breakdown */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Line Items &amp; Persisted GST Calculation</CardTitle>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y bg-secondary/40 text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-2.5">Description</th>
                    <th className="px-3 py-2.5">HSN</th>
                    <th className="px-3 py-2.5 text-right">Qty</th>
                    <th className="px-3 py-2.5 text-right">Dispatched</th>
                    <th className="px-3 py-2.5 text-right">Rate</th>
                    <th className="px-3 py-2.5 text-right">Discount</th>
                    <th className="px-3 py-2.5 text-right">Taxable</th>
                    <th className="px-3 py-2.5 text-right">CGST</th>
                    <th className="px-3 py-2.5 text-right">SGST</th>
                    <th className="px-3 py-2.5 text-right">IGST</th>
                    <th className="px-4 py-2.5 text-right">Line Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {inv.items.map((it) => (
                    <tr key={it.id}>
                      <td className="px-4 py-3">
                        <div className="font-semibold">{it.description}</div>
                        <div className="font-mono text-xs text-muted-foreground">{it.sku_code}</div>
                      </td>
                      <td className="px-3 py-3 font-mono text-xs">{it.hsn_code}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{it.qty_pkts}</td>
                      <td className="px-3 py-3 text-right tabular-nums text-xs">
                        {it.dispatched_qty_pkts} / {it.qty_pkts}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums">{formatInrFromPaisa(it.unit_price_paisa)}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{formatInrFromPaisa(it.discount_paisa)}</td>
                      <td className="px-3 py-3 text-right tabular-nums font-medium">
                        {formatInrFromPaisa(it.taxable_paisa)}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums text-xs">
                        {formatInrFromPaisa(it.cgst_paisa)}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums text-xs">
                        {formatInrFromPaisa(it.sgst_paisa)}
                      </td>
                      <td className="px-3 py-3 text-right tabular-nums text-xs">
                        {formatInrFromPaisa(it.igst_paisa)}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums font-bold">
                        {formatInrFromPaisa(it.line_total_paisa)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="border-t bg-secondary/20 p-4 grid gap-4 md:grid-cols-2">
                <div className="space-y-1 text-xs">
                  <div className="font-semibold uppercase text-muted-foreground">Amount in Words</div>
                  <div className="font-semibold text-sm">{inv.amount_in_words}</div>
                  <div className="text-muted-foreground pt-1">{inv.legal_declaration}</div>
                </div>
                <div className="space-y-1.5 text-sm">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Taxable Total</span>
                    <span className="tabular-nums">{formatInrFromPaisa(inv.taxable_total_paisa)}</span>
                  </div>
                  {inv.supply_type === "INTRA_STATE" ? (
                    <>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">CGST</span>
                        <span className="tabular-nums">{formatInrFromPaisa(inv.cgst_total_paisa)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-muted-foreground">SGST</span>
                        <span className="tabular-nums">{formatInrFromPaisa(inv.sgst_total_paisa)}</span>
                      </div>
                    </>
                  ) : (
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">IGST</span>
                      <span className="tabular-nums">{formatInrFromPaisa(inv.igst_total_paisa)}</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Round Off</span>
                    <span className="tabular-nums">{formatInrFromPaisa(inv.round_off_paisa)}</span>
                  </div>
                  <div className="flex justify-between border-t pt-2 text-base font-bold">
                    <span>Grand Total</span>
                    <span className="text-primary tabular-nums">{formatInrFromPaisa(inv.grand_total_paisa)}</span>
                  </div>
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>Credited by CN: {formatInrFromPaisa(inv.credited_paisa)}</span>
                    <span>Outstanding Balance: {formatInrFromPaisa(inv.outstanding_paisa)}</span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Dispatches & Credit Notes */}
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Linked Dispatches ({inv.dispatches.length})</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                {inv.dispatches.map((d) => (
                  <Link
                    key={d.id}
                    to={`/admin/dispatch/${d.id}`}
                    className="block rounded-lg border p-3 hover:border-primary/50"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-primary">{d.dispatch_number}</span>
                      <StatusBadge status={d.status} />
                    </div>
                    <div className="mt-1 text-muted-foreground">
                      {d.total_dispatched_pkts} pkts · {formatOrderDate(d.dispatch_date)}
                      {d.vehicle_number ? ` · Vehicle ${d.vehicle_number}` : ""}
                    </div>
                  </Link>
                ))}
                {inv.dispatches.length === 0 && (
                  <p className="text-muted-foreground">No dispatches recorded for this invoice yet.</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Linked Credit Notes ({inv.credit_notes.length})</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-xs">
                {inv.credit_notes.map((cn) => (
                  <div key={cn.id} className="rounded-lg border p-3 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold">{cn.cn_number ?? cn.draft_ref}</span>
                      <StatusBadge status={cn.status} />
                    </div>
                    <div className="font-semibold text-red-700">
                      Reversed: {formatInrFromPaisa(cn.total_reversed_paisa)} ({cn.note_type})
                    </div>
                    <div className="text-muted-foreground">{cn.reason}</div>
                  </div>
                ))}
                {inv.credit_notes.length === 0 && (
                  <p className="text-muted-foreground">No credit notes issued against this invoice.</p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Payment Allocations */}
        {inv?.doc_status === "ISSUED" && (
          <Card>
            <CardHeader className="pb-2 flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-base">Payment Settlements</CardTitle>
              <div className="flex items-center gap-2 text-xs">
                <StatusBadge status={inv.payment_status} />
                <span className="font-semibold tabular-nums">
                  Paid {formatInrFromPaisa(inv.paid_paisa)} / Outstanding{" "}
                  {formatInrFromPaisa(inv.outstanding_paisa)}
                </span>
              </div>
            </CardHeader>
            <CardContent>
              {(inv.allocations ?? []).length === 0 ? (
                <div className="text-xs text-muted-foreground">
                  No customer payment allocations recorded against this invoice yet.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b text-left uppercase text-muted-foreground">
                        <th className="py-2 pr-3">Payment #</th>
                        <th className="py-2 pr-3">Payment Date</th>
                        <th className="py-2 pr-3">Mode / Ref</th>
                        <th className="py-2 pr-3">Status</th>
                        <th className="py-2 text-right">Amount</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {(inv.allocations ?? []).map((alloc) => (
                        <tr key={alloc.id}>
                          <td className="py-2 pr-3 font-mono font-semibold text-primary">
                            <Link to={`/admin/finance/payments?search=${alloc.payment_number}`}>
                              {alloc.payment_number}
                            </Link>
                          </td>
                          <td className="py-2 pr-3">{alloc.payment_date}</td>
                          <td className="py-2 pr-3">
                            {alloc.payment_mode}
                            {alloc.reference_no ? ` · ${alloc.reference_no}` : ""}
                          </td>
                          <td className="py-2 pr-3">
                            <StatusBadge status={alloc.status} />
                          </td>
                          <td className="py-2 text-right font-semibold tabular-nums">
                            {formatInrFromPaisa(alloc.allocated_paisa)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Audit Trail */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FileClock className="h-4 w-4 text-primary" />
                Financial &amp; Dispatch Audit Trail
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-y bg-secondary/40 text-left uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-2">Time (IST)</th>
                    <th className="px-3 py-2">Actor</th>
                    <th className="px-3 py-2">Action</th>
                    <th className="px-4 py-2">Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {inv.audit_trail.map((lg) => (
                    <tr key={lg.id}>
                      <td className="px-4 py-2 whitespace-nowrap text-muted-foreground">
                        {formatDateTimeIst(lg.occurred_at)}
                      </td>
                      <td className="px-3 py-2">
                        {lg.actor_name} ({lg.actor_role})
                      </td>
                      <td className="px-3 py-2 font-mono font-bold text-primary">{lg.action}</td>
                      <td className="px-4 py-2">{lg.reason ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </div>
      )}
    </DesktopAdminLayout>
  );
}

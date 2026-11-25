# Phase 8 — Deterministic Tax Invoice PDF Generation

## Implementation

Invoice PDF generation is implemented in [`pdf_generator.py`](file:///d:/mac/ota/backend/app/modules/billing/pdf_generator.py) (`render_invoice_pdf`) and served via `GET /api/v1/billing/invoices/{invoice_id}/pdf`.

---

## Design Guarantees

1. **Zero Independent Recalculation:**
   - `render_invoice_pdf` renders **only** from persisted columns of `billing.invoices`, `billing.invoice_items`, and `billing.invoice_tax_components`.
   - Changes to live product prices or GST master tables never alter PDFs generated for historical invoices.
2. **Valid ISO 32000-1 PDF 1.4 Binary:**
   - Pure-Python A4 page layout (`MediaBox [0 0 595 842]`) using `Helvetica` and `Helvetica-Bold` Type1 fonts with `WinAnsiEncoding`, exact byte-offset cross-reference (`xref`) table, and `%%EOF` trailer—no external native binary dependencies.
   - Currencies are formatted cleanly (`Rs. 7,875.00`) in Indian comma grouping.
3. **Mandatory Statutory Sections Rendered:**
   - Dynamic title banner: `"TAX INVOICE"` (`ISSUED`), `"DRAFT PROFORMA INVOICE (NOT STATUTORY)"` (`DRAFT`), or `"TAX INVOICE (CANCELLED BY CREDIT NOTE)"` (`CANCELLED_BY_CN`).
   - Invoice Number / Draft Ref, Financial Year, Invoice Date, Status.
   - Seller Legal Name, Seller GSTIN, State & Code, Address.
   - Document & Tax Metadata (Sales Order Ref, Payment Terms & Due Date, Place of Supply state & code, Supply Type, Nature of Supply, Dispatch Status).
   - Bill To & Ship To blocks (Customer Name, Type, Customer GSTIN or `Unregistered (B2C)`, persisted addresses).
   - Itemized table (`#`, Description & SKU, HSN, Qty, Rate, Taxable, GST Split, Line Total).
   - HSN / Tax Component Breakdown (`CGST` + `SGST` or `IGST`), Taxable Value, Tax Totals, Round-Off Adjustment, Grand Total, Indian Amount in Words (`amount_in_words`), Legal Declaration, Payment Status, and Outstanding Amount.
4. **Access Control:**
   - `FACTORY_ADMIN`, `ACCOUNTANT_AUDITOR`, `OWNER` can download any invoice PDF.
   - `SALESMAN` can download PDFs only for **issued/cancelled** invoices linked to their own Sales Orders (`403 AuthorizationError` on other salesmen's orders or unissued `DRAFT` invoices).
   - `PRODUCTION_SUPERVISOR` is blocked (`403`).

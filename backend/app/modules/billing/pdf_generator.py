"""Deterministic pure-Python PDF 1.4 Tax Invoice renderer using persisted Invoice DB records.

Never recalculates independent totals; renders strictly from persisted Invoice, items,
and tax component snapshots so PDF output matches PostgreSQL & UI to the exact paisa.
"""

from app.modules.billing.models import Invoice


def _fmt_inr(paisa: int) -> str:
    sign = "-" if paisa < 0 else ""
    val = abs(paisa)
    rupees = val // 100
    p = val % 100
    s = str(rupees)
    if len(s) > 3:
        last3 = s[-3:]
        rest = s[:-3]
        groups: list[str] = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        formatted = ",".join(groups) + "," + last3
    else:
        formatted = s
    return f"{sign}Rs. {formatted}.{p:02d}"


def _fmt_rate_pct(bps: int) -> str:
    pct = bps / 100
    if bps % 100 == 0:
        return f"{int(pct)}%"
    return f"{pct:.2f}%"


def _pdf_escape(text: str) -> str:
    safe = (
        text.replace("₹", "Rs. ")
        .replace("—", "-")
        .replace("–", "-")
        .replace("·", "|")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_text(text: str, max_chars: int) -> list[str]:
    words = text.replace("\n", " ").split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur = f"{cur} {w}"
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def render_invoice_pdf(invoice: Invoice, *, order_number: str) -> bytes:
    """Render statutory GST Tax Invoice PDF directly from persisted Invoice model."""
    cmds: list[str] = []

    def rect(x: float, y: float, w: float, h: float, fill_gray: float | None = None) -> None:
        if fill_gray is not None:
            cmds.append(f"q {fill_gray:.2f} g {x:.1f} {y:.1f} {w:.1f} {h:.1f} re f Q")
        cmds.append(f"0.4 w 0.15 0.15 0.20 RG {x:.1f} {y:.1f} {w:.1f} {h:.1f} re S")

    def line(x1: float, y1: float, x2: float, y2: float) -> None:
        cmds.append(f"0.4 w 0.65 0.68 0.72 RG {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")

    def txt(x: float, y: float, content: str, *, bold: bool = False, size: float = 9.0, align_right: bool = False) -> None:
        font = "/F2" if bold else "/F1"
        est_x = x - (len(content) * size * 0.50) if align_right else x
        cmds.append(
            f"BT {font} {size:.1f} Tf 0.08 0.09 0.12 rg {est_x:.1f} {y:.1f} Td ({_pdf_escape(content)}) Tj ET"
        )

    # Top Title Banner
    rect(36, 766, 523, 42, fill_gray=0.95)
    inv_title = "TAX INVOICE"
    if invoice.doc_status == "DRAFT":
        inv_title = "DRAFT PROFORMA INVOICE (NOT STATUTORY)"
    elif invoice.doc_status == "CANCELLED_BY_CN":
        inv_title = "TAX INVOICE (CANCELLED BY CREDIT NOTE)"
    txt(46, 788, inv_title, bold=True, size=13)
    inv_no_display = invoice.invoice_number or invoice.draft_ref
    txt(549, 790, f"Invoice No: {inv_no_display}", bold=True, size=10.5, align_right=True)
    txt(
        549,
        774,
        f"FY: {invoice.financial_year}  |  Date: {invoice.invoice_date.isoformat()}  |  Status: {invoice.doc_status}",
        size=8.5,
        align_right=True,
    )

    # Seller Box
    rect(36, 686, 260, 74)
    txt(44, 746, "SUPPLIER DETAILS", bold=True, size=8.0)
    txt(44, 732, invoice.seller_legal_name, bold=True, size=10.0)
    txt(44, 720, f"GSTIN: {invoice.seller_gstin}", bold=True, size=8.5)
    txt(
        44,
        708,
        f"State: {invoice.seller_state_name} (Code: {invoice.seller_state_code})",
        size=8.5,
    )
    addr_lines = _wrap_text(invoice.seller_address, 50)
    for idx, ln in enumerate(addr_lines[:2]):
        txt(44, 696 - (idx * 9), ln, size=7.8)

    # Invoice Metadata Box
    rect(302, 686, 257, 74)
    txt(310, 746, "DOCUMENT & TAX METADATA", bold=True, size=8.0)
    txt(310, 732, f"Sales Order Ref: {order_number}", size=8.5)
    txt(310, 720, f"Payment Terms: {invoice.payment_terms} (Due: {invoice.due_date.isoformat()})", size=8.5)
    txt(
        310,
        708,
        f"Place of Supply: {invoice.place_of_supply_state_name} ({invoice.place_of_supply_state_code})",
        bold=True,
        size=8.5,
    )
    txt(
        310,
        696,
        f"Supply: {invoice.supply_type} ({invoice.nature_of_supply})  |  Dispatch: {invoice.dispatch_status}",
        size=8.2,
    )

    # Customer Billing & Shipping Boxes
    rect(36, 610, 260, 70)
    txt(44, 666, "BILL TO (CUSTOMER)", bold=True, size=8.0)
    txt(44, 653, f"{invoice.customer_name} ({invoice.customer_type})", bold=True, size=9.5)
    txt(44, 641, f"GSTIN: {invoice.buyer_gstin or 'Unregistered (B2C)'}", size=8.5)
    for idx, ln in enumerate(_wrap_text(invoice.billing_address_snapshot, 48)[:2]):
        txt(44, 629 - (idx * 10), ln, size=8.0)

    rect(302, 610, 257, 70)
    txt(310, 666, "SHIP TO (DELIVERY ADDRESS)", bold=True, size=8.0)
    txt(310, 653, invoice.customer_name, bold=True, size=9.5)
    txt(310, 641, f"POS State Code: {invoice.place_of_supply_state_code}", size=8.5)
    for idx, ln in enumerate(_wrap_text(invoice.shipping_address_snapshot, 48)[:2]):
        txt(310, 629 - (idx * 10), ln, size=8.0)

    # Line Items Table
    y_top = 598.0
    row_h = 20.0
    table_h = row_h * (len(invoice.items) + 1) + 6
    y_bottom = y_top - table_h
    rect(36, y_bottom, 523, table_h)
    rect(36, y_top - row_h, 523, row_h, fill_gray=0.93)

    txt(42, y_top - 13, "#", bold=True, size=8.2)
    txt(60, y_top - 13, "Description & SKU", bold=True, size=8.2)
    txt(222, y_top - 13, "HSN", bold=True, size=8.2)
    txt(285, y_top - 13, "Qty", bold=True, size=8.2, align_right=True)
    txt(342, y_top - 13, "Rate", bold=True, size=8.2, align_right=True)
    txt(408, y_top - 13, "Taxable", bold=True, size=8.2, align_right=True)
    txt(486, y_top - 13, "GST Split", bold=True, size=8.2, align_right=True)
    txt(553, y_top - 13, "Line Total", bold=True, size=8.2, align_right=True)

    cur_y = y_top - row_h
    for idx, item in enumerate(invoice.items, start=1):
        cur_y -= row_h
        if idx > 1:
            line(36, cur_y + row_h, 559, cur_y + row_h)
        gst_lbl = (
            f"C+S {_fmt_rate_pct(item.cgst_rate_bps + item.sgst_rate_bps)}"
            if invoice.supply_type == "INTRA_STATE"
            else f"IGST {_fmt_rate_pct(item.igst_rate_bps)}"
        )
        txt(42, cur_y + 7, str(idx), size=8.2)
        txt(60, cur_y + 7, f"{item.description} [{item.sku_code}]"[:34], size=8.2)
        txt(222, cur_y + 7, item.hsn_code, size=8.2)
        txt(285, cur_y + 7, f"{item.qty_pkts} pkt", size=8.2, align_right=True)
        txt(342, cur_y + 7, _fmt_inr(int(item.unit_price_paisa)), size=8.2, align_right=True)
        txt(408, cur_y + 7, _fmt_inr(int(item.taxable_paisa)), size=8.2, align_right=True)
        txt(486, cur_y + 7, gst_lbl, size=8.0, align_right=True)
        txt(553, cur_y + 7, _fmt_inr(int(item.line_total_paisa)), bold=True, size=8.2, align_right=True)

    # Tax Breakdown + Totals Summary
    summary_top = y_bottom - 12
    rect(36, summary_top - 108, 286, 108)
    txt(44, summary_top - 15, "HSN / TAX COMPONENT BREAKDOWN", bold=True, size=8.2)
    comp_y = summary_top - 30
    for comp in invoice.tax_components[:5]:
        txt(
            44,
            comp_y,
            f"HSN {comp.hsn_code} | {comp.tax_type} @ {_fmt_rate_pct(comp.rate_bps)} on {_fmt_inr(int(comp.taxable_base_paisa))}",
            size=8.0,
        )
        txt(314, comp_y, _fmt_inr(int(comp.tax_amount_paisa)), bold=True, size=8.0, align_right=True)
        comp_y -= 13

    rect(330, summary_top - 108, 229, 108)
    txt(340, summary_top - 16, "Taxable Value:", size=8.8)
    txt(551, summary_top - 16, _fmt_inr(int(invoice.taxable_total_paisa)), size=8.8, align_right=True)
    if invoice.supply_type == "INTRA_STATE":
        txt(340, summary_top - 32, "CGST Total:", size=8.8)
        txt(551, summary_top - 32, _fmt_inr(int(invoice.cgst_total_paisa)), size=8.8, align_right=True)
        txt(340, summary_top - 47, "SGST Total:", size=8.8)
        txt(551, summary_top - 47, _fmt_inr(int(invoice.sgst_total_paisa)), size=8.8, align_right=True)
    else:
        txt(340, summary_top - 32, "IGST Total:", size=8.8)
        txt(551, summary_top - 32, _fmt_inr(int(invoice.igst_total_paisa)), size=8.8, align_right=True)
    txt(340, summary_top - 62, "Round-Off Adjustment:", size=8.8)
    txt(551, summary_top - 62, _fmt_inr(int(invoice.round_off_paisa)), size=8.8, align_right=True)
    line(330, summary_top - 72, 559, summary_top - 72)
    rect(330, summary_top - 108, 229, 34, fill_gray=0.94)
    txt(340, summary_top - 93, "GRAND TOTAL:", bold=True, size=10.0)
    txt(551, summary_top - 93, _fmt_inr(int(invoice.grand_total_paisa)), bold=True, size=10.5, align_right=True)

    # Amount in Words & Declaration
    words_top = summary_top - 120
    rect(36, words_top - 38, 523, 38)
    txt(44, words_top - 14, "AMOUNT IN WORDS:", bold=True, size=8.0)
    txt(44, words_top - 28, invoice.amount_in_words, bold=True, size=8.8)

    decl_top = words_top - 46
    rect(36, decl_top - 58, 523, 58)
    txt(44, decl_top - 13, "DECLARATION & TERMS:", bold=True, size=8.0)
    for idx, ln in enumerate(_wrap_text(invoice.legal_declaration, 80)[:2]):
        txt(44, decl_top - 25 - (idx * 10), ln, size=7.8)
    txt(44, decl_top - 49, f"Payment Status: {invoice.payment_status}  |  Outstanding: {_fmt_inr(int(invoice.outstanding_paisa))}", size=8.0)
    txt(549, decl_top - 49, f"For {invoice.seller_legal_name}", bold=True, size=8.0, align_right=True)

    stream_bytes = "\n".join(cmds).encode("latin-1", "replace")

    # Assemble valid ISO 32000-1 PDF 1.4 binary with exact byte-offset xref table
    objects: list[bytes] = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>\nendobj\n"
        ),
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\nendobj\n",
        (
            f"6 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("ascii")
            + stream_bytes
            + b"\nendstream\nendobj\n"
        ),
    ]

    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    buf = bytearray(header)
    offsets: list[int] = [0]
    for obj in objects:
        offsets.append(len(buf))
        buf.extend(obj)

    xref_pos = len(buf)
    buf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    buf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        buf.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    buf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode(
            "ascii"
        )
    )
    return bytes(buf)

"""Deterministic pure-Python PDF 1.4 Payment Receipt renderer from persisted DB records."""

from app.modules.billing.gst_engine import amount_in_words_inr
from app.modules.finance.models import Payment, PaymentAllocation
from app.modules.iam.models import CompanyProfile
from app.modules.sales.models import Customer


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


def render_payment_receipt_pdf(
    payment: Payment,
    *,
    company: CompanyProfile,
    customer: Customer,
    allocations: list[tuple[PaymentAllocation, str, int, int]],
) -> bytes:
    """Render official Customer Payment Receipt PDF (A4) directly from persisted DB rows."""
    cmds: list[str] = []

    def rect(x: float, y: float, w: float, h: float, fill_gray: float | None = None) -> None:
        if fill_gray is not None:
            cmds.append(f"q {fill_gray:.2f} g {x:.1f} {y:.1f} {w:.1f} {h:.1f} re f Q")
        cmds.append(f"0.4 w 0.15 0.15 0.20 RG {x:.1f} {y:.1f} {w:.1f} {h:.1f} re S")

    def line(x1: float, y1: float, x2: float, y2: float) -> None:
        cmds.append(f"0.4 w 0.65 0.68 0.72 RG {x1:.1f} {y1:.1f} m {x2:.1f} {y2:.1f} l S")

    def txt(
        x: float,
        y: float,
        content: str,
        *,
        bold: bool = False,
        size: float = 9.0,
        align_right: bool = False,
    ) -> None:
        font = "/F2" if bold else "/F1"
        est_x = x - (len(content) * size * 0.50) if align_right else x
        cmds.append(
            f"BT {font} {size:.1f} Tf 0.08 0.09 0.12 rg {est_x:.1f} {y:.1f} Td ({_pdf_escape(content)}) Tj ET"
        )

    # Banner
    rect(36, 766, 523, 42, fill_gray=0.95)
    title = "CUSTOMER PAYMENT RECEIPT" if payment.status != "REVERSED" else "PAYMENT RECEIPT (REVERSED)"
    txt(46, 788, title, bold=True, size=13)
    txt(549, 790, f"Receipt No: {payment.payment_number}", bold=True, size=10.5, align_right=True)
    txt(
        549,
        774,
        f"FY: {payment.financial_year}  |  Date: {payment.payment_date.isoformat()}  |  Status: {payment.status}",
        size=8.5,
        align_right=True,
    )

    # Company & Receipt Info
    rect(36, 684, 260, 74)
    txt(44, 744, "RECEIVED BY (COMPANY)", bold=True, size=8.0)
    txt(44, 730, company.legal_name, bold=True, size=10.0)
    txt(44, 718, f"GSTIN: {company.gstin}", bold=True, size=8.5)
    for idx, ln in enumerate(_wrap_text(company.address, 48)[:2]):
        txt(44, 704 - (idx * 10), ln, size=8.0)

    rect(302, 684, 257, 74)
    txt(310, 744, "RECEIVED FROM (CUSTOMER)", bold=True, size=8.0)
    txt(310, 730, f"{customer.name} ({customer.code})", bold=True, size=9.8)
    txt(310, 718, f"GSTIN: {customer.gstin or 'Unregistered'}", size=8.5)
    txt(310, 706, f"State: {customer.primary_state_name} ({customer.primary_state_code})", size=8.5)

    # Payment Summary Strip
    rect(36, 608, 523, 68, fill_gray=0.98)
    txt(46, 661, "TRANSACTION DETAILS", bold=True, size=8.0)
    txt(46, 646, f"Payment Mode: {payment.payment_mode}", bold=True, size=9.2)
    txt(46, 632, f"Transaction Ref: {payment.reference_no or 'N/A'}", size=8.8)
    txt(46, 618, f"Remarks: {(payment.remarks or '-')[:55]}", size=8.2)

    txt(549, 656, f"Amount Received: {_fmt_inr(int(payment.amount_paisa))}", bold=True, size=10.5, align_right=True)
    txt(549, 640, f"Allocated to Invoices: {_fmt_inr(int(payment.allocated_paisa))}", size=8.8, align_right=True)
    txt(549, 626, f"Unallocated Advance: {_fmt_inr(int(payment.unallocated_paisa))}", bold=True, size=8.8, align_right=True)
    if int(payment.refunded_paisa) > 0:
        txt(549, 613, f"Refunded: {_fmt_inr(int(payment.refunded_paisa))}", size=8.2, align_right=True)

    # Amount in words
    rect(36, 562, 523, 38)
    txt(44, 586, "AMOUNT RECEIVED IN WORDS:", bold=True, size=8.0)
    txt(44, 572, amount_in_words_inr(int(payment.amount_paisa)), bold=True, size=8.8)

    # Invoice Allocation Table
    y_top = 548.0
    row_h = 20.0
    display_rows = allocations[:12]
    table_rows = max(1, len(display_rows))
    table_h = row_h * (table_rows + 1) + 8
    y_bottom = y_top - table_h
    rect(36, y_bottom, 523, table_h)
    rect(36, y_top - row_h, 523, row_h, fill_gray=0.93)

    txt(44, y_top - 13, "Invoice #", bold=True, size=8.5)
    txt(210, y_top - 13, "Status", bold=True, size=8.5)
    txt(325, y_top - 13, "Invoice Total", bold=True, size=8.5, align_right=True)
    txt(438, y_top - 13, "Allocated Now", bold=True, size=8.5, align_right=True)
    txt(548, y_top - 13, "Balance Due", bold=True, size=8.5, align_right=True)

    cur_y = y_top - row_h
    if not display_rows:
        cur_y -= row_h
        txt(44, cur_y + 7, "No invoice allocations applied yet (held as Customer Advance Balance).", size=8.5)
    else:
        for idx, (alloc, inv_no, inv_total, inv_out) in enumerate(display_rows, start=1):
            cur_y -= row_h
            if idx > 1:
                line(36, cur_y + row_h, 559, cur_y + row_h)
            txt(44, cur_y + 7, inv_no, bold=True, size=8.5)
            txt(210, cur_y + 7, alloc.status, size=8.2)
            txt(325, cur_y + 7, _fmt_inr(inv_total), size=8.5, align_right=True)
            txt(438, cur_y + 7, _fmt_inr(int(alloc.allocated_paisa)), bold=True, size=8.5, align_right=True)
            txt(548, cur_y + 7, _fmt_inr(inv_out), size=8.5, align_right=True)

    if payment.reversal_reason:
        rev_top = y_bottom - 14
        rect(36, rev_top - 36, 523, 36)
        txt(44, rev_top - 13, "REVERSAL AUDIT REASON:", bold=True, size=8.0)
        txt(44, rev_top - 26, payment.reversal_reason[:88], size=8.2)
        sig_y = rev_top - 64
    else:
        sig_y = y_bottom - 34

    txt(44, sig_y, "System-generated receipt verified against persisted ledger entries.", size=8.0)
    txt(549, sig_y, f"For {company.legal_name}", bold=True, size=8.5, align_right=True)

    stream_bytes = "\n".join(cmds).encode("latin-1", "replace")
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

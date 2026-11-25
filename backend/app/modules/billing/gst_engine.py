"""Reusable GST Calculation Engine & Indian Financial Year utilities.

Guarantees exact Decimal (`ROUND_HALF_UP`) and integer-paisa calculations with zero
binary floating-point arithmetic, explicit Place-of-Supply validation, and persisted
audit snapshots.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.core.exceptions import DomainValidationError

_GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_STATE_CODE_RE = re.compile(r"^[0-9]{2}$")
_HSN_RE = re.compile(r"^[0-9]{4,8}$")


def get_indian_financial_year(doc_date: date) -> str:
    """Return Indian Financial Year string (`YYYY-YY`, Apr 1 to Mar 31) for a date."""
    start_year = doc_date.year if doc_date.month >= 4 else doc_date.year - 1
    end_two = (start_year + 1) % 100
    return f"{start_year}-{end_two:02d}"


def round_half_up_bps(amount_paisa: int, rate_bps: int) -> int:
    """Compute tax paisa from taxable paisa and basis points using exact Decimal ROUND_HALF_UP."""
    if amount_paisa < 0 or rate_bps < 0:
        raise DomainValidationError("Taxable amount and GST rate basis points cannot be negative.")
    raw = (Decimal(amount_paisa) * Decimal(rate_bps)) / Decimal(10000)
    return int(raw.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _num_to_words_under_1000(n: int) -> str:
    ones = [
        "",
        "One",
        "Two",
        "Three",
        "Four",
        "Five",
        "Six",
        "Seven",
        "Eight",
        "Nine",
        "Ten",
        "Eleven",
        "Twelve",
        "Thirteen",
        "Fourteen",
        "Fifteen",
        "Sixteen",
        "Seventeen",
        "Eighteen",
        "Nineteen",
    ]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    parts: list[str] = []
    if n >= 100:
        parts.append(f"{ones[n // 100]} Hundred")
        n %= 100
    if n >= 20:
        word = tens[n // 10]
        if n % 10:
            word = f"{word} {ones[n % 10]}"
        parts.append(word)
    elif n > 0:
        parts.append(ones[n])
    return " ".join(parts)


def integer_to_indian_words(n: int) -> str:
    """Convert non-negative integer to Indian numbering words (Crore, Lakh, Thousand)."""
    if n == 0:
        return "Zero"
    parts: list[str] = []
    crore = n // 10_000_000
    n %= 10_000_000
    if crore:
        parts.append(f"{integer_to_indian_words(crore)} Crore")
    lakh = n // 100_000
    n %= 100_000
    if lakh:
        parts.append(f"{_num_to_words_under_1000(lakh)} Lakh")
    thousand = n // 1_000
    n %= 1_000
    if thousand:
        parts.append(f"{_num_to_words_under_1000(thousand)} Thousand")
    if n:
        parts.append(_num_to_words_under_1000(n))
    return " ".join(parts)


def amount_in_words_inr(paisa: int) -> str:
    """Render exact paisa amount in Indian statutory Rupees & Paise words."""
    if paisa < 0:
        raise DomainValidationError("Invoice total cannot be negative.")
    rupees = paisa // 100
    rem_paise = paisa % 100
    if rem_paise == 0:
        return f"Rupees {integer_to_indian_words(rupees)} Only"
    return (
        f"Rupees {integer_to_indian_words(rupees)} and "
        f"{integer_to_indian_words(rem_paise)} Paise Only"
    )


@dataclass(frozen=True)
class TaxLineInput:
    sales_order_item_id: int
    pack_size_id: int
    sku_code: str
    product_name: str
    description: str
    hsn_code: str
    qty_pkts: int
    unit_price_paisa: int
    gst_rate_bps: int
    discount_paisa: int = 0


@dataclass(frozen=True)
class ComputedTaxLine:
    sales_order_item_id: int
    pack_size_id: int
    sku_code: str
    product_name: str
    description: str
    hsn_code: str
    qty_pkts: int
    unit_price_paisa: int
    discount_paisa: int
    taxable_paisa: int
    gst_rate_bps: int
    cgst_rate_bps: int
    sgst_rate_bps: int
    igst_rate_bps: int
    cgst_paisa: int
    sgst_paisa: int
    igst_paisa: int
    line_total_paisa: int


@dataclass(frozen=True)
class ComputedTaxComponent:
    hsn_code: str
    tax_type: str
    rate_bps: int
    taxable_base_paisa: int
    tax_amount_paisa: int


@dataclass(frozen=True)
class GstCalculationResult:
    seller_state_code: str
    seller_state_name: str
    place_of_supply_state_code: str
    place_of_supply_state_name: str
    nature_of_supply: str
    supply_type: str
    rule_rationale: str
    discount_total_paisa: int
    taxable_total_paisa: int
    cgst_total_paisa: int
    sgst_total_paisa: int
    igst_total_paisa: int
    round_off_paisa: int
    grand_total_paisa: int
    amount_in_words: str
    lines: list[ComputedTaxLine]
    components: list[ComputedTaxComponent]
    snapshot: dict[str, Any]


def validate_tax_conditions_and_calculate_gst(
    *,
    seller_gstin: str,
    seller_state_code: str,
    seller_state_name: str,
    buyer_gstin: str | None,
    customer_state_code: str,
    place_of_supply_state_code: str,
    place_of_supply_state_name: str,
    lines: list[TaxLineInput],
    apply_round_off: bool = False,
) -> GstCalculationResult:
    """Validate supplier, customer, POS, HSN, and GST conditions, then calculate exact GST breakdown."""
    if not _STATE_CODE_RE.match(seller_state_code) or not _GSTIN_RE.match(seller_gstin):
        raise DomainValidationError("Invalid supplier GSTIN or state code configuration on Company Profile.")
    if seller_gstin[:2] != seller_state_code:
        raise DomainValidationError(
            f"Supplier GSTIN state prefix ({seller_gstin[:2]}) does not match Company state code ({seller_state_code})."
        )

    if not _STATE_CODE_RE.match(customer_state_code) or not _STATE_CODE_RE.match(place_of_supply_state_code):
        raise DomainValidationError("Customer and Place-of-Supply state codes must be valid 2-digit Indian GST state codes.")

    clean_buyer_gstin = buyer_gstin.strip().upper() if buyer_gstin else None
    if clean_buyer_gstin:
        if not _GSTIN_RE.match(clean_buyer_gstin):
            raise DomainValidationError(f"Invalid customer GSTIN '{clean_buyer_gstin}'.")
        if clean_buyer_gstin[:2] != customer_state_code:
            raise DomainValidationError(
                f"Customer GSTIN state prefix ({clean_buyer_gstin[:2]}) mismatches customer registration state ({customer_state_code})."
            )
        nature_of_supply = "B2B"
    else:
        nature_of_supply = "B2C"

    if not lines:
        raise DomainValidationError("At least one positive line item is required for GST calculation.")

    if seller_state_code == place_of_supply_state_code:
        supply_type = "INTRA_STATE"
        rule_rationale = (
            f"Supplier state code {seller_state_code} ({seller_state_name}) matches Place of Supply "
            f"{place_of_supply_state_code} ({place_of_supply_state_name}); intra-state CGST + SGST applies under IGST/CGST Act."
        )
    else:
        supply_type = "INTER_STATE"
        rule_rationale = (
            f"Supplier state code {seller_state_code} ({seller_state_name}) differs from Place of Supply "
            f"{place_of_supply_state_code} ({place_of_supply_state_name}); inter-state IGST applies under Section 7 of IGST Act."
        )

    computed_lines: list[ComputedTaxLine] = []
    comp_map: dict[tuple[str, str, int], list[int]] = {}  # (hsn, type, bps) -> [base, tax]

    discount_total = 0
    taxable_total = 0
    cgst_total = 0
    sgst_total = 0
    igst_total = 0

    for item in lines:
        if item.qty_pkts <= 0:
            raise DomainValidationError(f"Line item {item.sku_code} must have positive quantity.")
        if item.unit_price_paisa < 0:
            raise DomainValidationError(f"Line item {item.sku_code} cannot have negative unit price.")
        if not _HSN_RE.match(item.hsn_code):
            raise DomainValidationError(f"Product HSN code '{item.hsn_code}' is missing or invalid (must be 4-8 digits).")
        if item.gst_rate_bps < 0 or item.gst_rate_bps > 2800:
            raise DomainValidationError(f"Product GST rate {item.gst_rate_bps} bps is outside supported range [0..2800].")

        gross_paisa = item.qty_pkts * item.unit_price_paisa
        if item.discount_paisa < 0 or item.discount_paisa > gross_paisa:
            raise DomainValidationError(
                f"Discount ({item.discount_paisa} paise) on {item.sku_code} cannot be negative or exceed gross value ({gross_paisa} paise)."
            )

        taxable_paisa = gross_paisa - item.discount_paisa
        if supply_type == "INTRA_STATE":
            if item.gst_rate_bps % 2 != 0:
                raise DomainValidationError(
                    f"GST rate {item.gst_rate_bps} bps on HSN {item.hsn_code} cannot be evenly split between CGST and SGST."
                )
            cgst_bps = item.gst_rate_bps // 2
            sgst_bps = cgst_bps
            igst_bps = 0
            cgst_paisa = round_half_up_bps(taxable_paisa, cgst_bps)
            sgst_paisa = cgst_paisa
            igst_paisa = 0
            if cgst_paisa > 0 or cgst_bps > 0:
                for tax_type, bps, amt in (("CGST", cgst_bps, cgst_paisa), ("SGST", sgst_bps, sgst_paisa)):
                    key = (item.hsn_code, tax_type, bps)
                    cur = comp_map.setdefault(key, [0, 0])
                    cur[0] += taxable_paisa
                    cur[1] += amt
        else:
            cgst_bps = 0
            sgst_bps = 0
            igst_bps = item.gst_rate_bps
            cgst_paisa = 0
            sgst_paisa = 0
            igst_paisa = round_half_up_bps(taxable_paisa, igst_bps)
            if igst_paisa > 0 or igst_bps > 0:
                key = (item.hsn_code, "IGST", igst_bps)
                cur = comp_map.setdefault(key, [0, 0])
                cur[0] += taxable_paisa
                cur[1] += igst_paisa

        line_total = taxable_paisa + cgst_paisa + sgst_paisa + igst_paisa
        discount_total += item.discount_paisa
        taxable_total += taxable_paisa
        cgst_total += cgst_paisa
        sgst_total += sgst_paisa
        igst_total += igst_paisa

        computed_lines.append(
            ComputedTaxLine(
                sales_order_item_id=item.sales_order_item_id,
                pack_size_id=item.pack_size_id,
                sku_code=item.sku_code,
                product_name=item.product_name,
                description=item.description,
                hsn_code=item.hsn_code,
                qty_pkts=item.qty_pkts,
                unit_price_paisa=item.unit_price_paisa,
                discount_paisa=item.discount_paisa,
                taxable_paisa=taxable_paisa,
                gst_rate_bps=item.gst_rate_bps,
                cgst_rate_bps=cgst_bps,
                sgst_rate_bps=sgst_bps,
                igst_rate_bps=igst_bps,
                cgst_paisa=cgst_paisa,
                sgst_paisa=sgst_paisa,
                igst_paisa=igst_paisa,
                line_total_paisa=line_total,
            )
        )

    pre_round_total = taxable_total + cgst_total + sgst_total + igst_total
    round_off_paisa = 0
    if apply_round_off:
        rounded_rupees = (Decimal(pre_round_total) / Decimal(100)).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
        round_off_paisa = int(rounded_rupees * Decimal(100)) - pre_round_total

    grand_total = pre_round_total + round_off_paisa
    words = amount_in_words_inr(grand_total)

    components = [
        ComputedTaxComponent(
            hsn_code=hsn,
            tax_type=t_type,
            rate_bps=bps,
            taxable_base_paisa=vals[0],
            tax_amount_paisa=vals[1],
        )
        for (hsn, t_type, bps), vals in sorted(comp_map.items())
    ]

    snapshot: dict[str, Any] = {
        "seller_gstin": seller_gstin,
        "seller_state_code": seller_state_code,
        "seller_state_name": seller_state_name,
        "buyer_gstin": clean_buyer_gstin,
        "customer_state_code": customer_state_code,
        "place_of_supply_state_code": place_of_supply_state_code,
        "place_of_supply_state_name": place_of_supply_state_name,
        "nature_of_supply": nature_of_supply,
        "supply_type": supply_type,
        "rule_rationale": rule_rationale,
        "apply_round_off": apply_round_off,
        "pre_round_total_paisa": pre_round_total,
        "round_off_paisa": round_off_paisa,
        "grand_total_paisa": grand_total,
        "line_breakdown": [
            {
                "sku_code": ln.sku_code,
                "hsn_code": ln.hsn_code,
                "qty_pkts": ln.qty_pkts,
                "unit_price_paisa": ln.unit_price_paisa,
                "discount_paisa": ln.discount_paisa,
                "taxable_paisa": ln.taxable_paisa,
                "gst_rate_bps": ln.gst_rate_bps,
                "cgst_paisa": ln.cgst_paisa,
                "sgst_paisa": ln.sgst_paisa,
                "igst_paisa": ln.igst_paisa,
                "line_total_paisa": ln.line_total_paisa,
            }
            for ln in computed_lines
        ],
    }

    return GstCalculationResult(
        seller_state_code=seller_state_code,
        seller_state_name=seller_state_name,
        place_of_supply_state_code=place_of_supply_state_code,
        place_of_supply_state_name=place_of_supply_state_name,
        nature_of_supply=nature_of_supply,
        supply_type=supply_type,
        rule_rationale=rule_rationale,
        discount_total_paisa=discount_total,
        taxable_total_paisa=taxable_total,
        cgst_total_paisa=cgst_total,
        sgst_total_paisa=sgst_total,
        igst_total_paisa=igst_total,
        round_off_paisa=round_off_paisa,
        grand_total_paisa=grand_total,
        amount_in_words=words,
        lines=computed_lines,
        components=components,
        snapshot=snapshot,
    )

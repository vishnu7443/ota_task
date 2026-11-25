# Phase 8 — GST Calculation Engine

## Overview

Tax computation is centralized in the pure, reusable Python module [`gst_engine.py`](file:///d:/mac/ota/backend/app/modules/billing/gst_engine.py) (`validate_tax_conditions_and_calculate_gst` and `round_half_up_bps`). No tax totals, rates, or splits are accepted from client requests.

---

## Core Arithmetic Rules

1. **Integer Paisa & `Decimal` `ROUND_HALF_UP`:**
   - Zero binary floating-point (`float`) arithmetic is used.
   - All rates are stored in integer basis points (`gst_rate_bps`, e.g., `500` bps = `5.00%`, `250` bps = `2.50%`, range `0..2800`).
   - Line gross value = `qty_pkts * unit_price_paisa`.
   - Line discount bounds check: `0 <= discount_paisa <= gross_paisa`.
   - Line taxable value = `gross_paisa - discount_paisa`.
   - Tax computation:

     ```python
     raw = (Decimal(amount_paisa) * Decimal(rate_bps)) / Decimal(10000)
     tax_paisa = int(raw.quantize(Decimal(1), rounding=ROUND_HALF_UP))
     ```

2. **Symmetric Intra-State Split (CGST + SGST):**
   - For `INTRA_STATE`, `gst_rate_bps` must be evenly divisible by `2`.
   - `cgst_rate_bps = sgst_rate_bps = gst_rate_bps // 2`.
   - `cgst_paisa = round_half_up_bps(taxable_paisa, cgst_rate_bps)` and `sgst_paisa = cgst_paisa`, ensuring DB constraint `inv_gst_split` (`cgst_total_paisa = sgst_total_paisa AND igst_total_paisa = 0`) always holds symmetrically (e.g., `₹51.00 @ 5%`: half of `₹51.00 * 2.5% = 127.5` paise rounds `ROUND_HALF_UP` to `128` paise each = `₹1.28 CGST + ₹1.28 SGST`).

3. **Inter-State IGST:**
   - For `INTER_STATE`, `igst_rate_bps = gst_rate_bps`, `cgst_rate_bps = sgst_rate_bps = 0`, `igst_paisa = round_half_up_bps(taxable_paisa, igst_rate_bps)`, satisfying DB constraint `inv_gst_split` (`cgst_total_paisa = 0 AND sgst_total_paisa = 0`).

4. **Optional Whole-Rupee Commercial Round-Off:**
   - When `apply_round_off=True`, `(Decimal(pre_round_total) / Decimal(100)).quantize(Decimal(1), rounding=ROUND_HALF_UP)` determines the rounded rupee target; `round_off_paisa = int(rounded_rupees * Decimal(100)) - pre_round_total`, constrained in PostgreSQL to `[-100, +100]` (`inv_round_off_bounds`).
   - Example verified in tests: `1 pkt × ₹50.00 = ₹50.00 + ₹2.50 tax = ₹52.50` -> `+₹0.50` round-off -> `₹53.00` (`5300` paise).

5. **HSN & Rate Bucket Aggregation + Amount in Words:**
   - Aggregates tax bases and tax amounts by `(hsn_code, tax_type, rate_bps)` into persisted `billing.invoice_tax_components` rows (`uq_itc_bucket`).
   - Formats exact integer totals using Indian numbering words (`amount_in_words_inr`, Crore / Lakh / Thousand / Rupees / Paise).

---

## Pre-Calculation Condition Validation

Before computing any rupees/paise, `validate_tax_conditions_and_calculate_gst` enforces:
- Valid 15-char GSTIN regex (`^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$`) and 2-digit Indian state codes (`^[0-9]{2}$`).
- `seller_gstin[:2] == seller_state_code`.
- When customer has GSTIN: `clean_buyer_gstin[:2] == customer_state_code` -> sets `nature_of_supply = "B2B"`; otherwise `"B2C"`.
- Product HSN must match `^[0-9]{4,8}$` and `0 <= gst_rate_bps <= 2800`.

---

## Historical Snapshot Immutability

At invoice creation, tax inputs, calculation rationale, HSN, rates, per-line breakdown, and totals are written as immutable columns and a JSONB `tax_calculation_snapshot` on `billing.invoices`. Subsequent changes to master product pricing or `sales.products.gst_rate_bps` do not alter previously generated or issued invoices or their PDFs.

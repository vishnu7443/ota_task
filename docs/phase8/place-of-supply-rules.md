# Phase 8 — Place of Supply & Tax Treatment Rules

## Design Principle

CGST+SGST vs. IGST classification is **never hardcoded** by customer name or static lookup flags. Every invoice evaluates legal supply conditions dynamically from persisted seller, customer, and shipping/place-of-supply master attributes.

---

## Evaluation Inputs

Implemented in `validate_tax_conditions_and_calculate_gst` ([`gst_engine.py`](file:///d:/mac/ota/backend/app/modules/billing/gst_engine.py)) and `_resolve_customer_addresses` ([`service.py`](file:///d:/mac/ota/backend/app/modules/billing/service.py)):

1. **Supplier Origin Location:** `iam.company_profile.gstin`, `state_code`, and `state_name` (`33` — Tamil Nadu for `Kaveri Traditional Snacks Pvt. Ltd.`).
2. **Customer Registration State & GSTIN:** `sales.customers.primary_state_code` and `sales.customers.gstin`.
   - Registered `buyer_gstin` present -> `nature_of_supply = 'B2B'`.
   - Unregistered (`buyer_gstin IS NULL`) -> `nature_of_supply = 'B2C'`.
   - GSTIN state prefix mismatch (`buyer_gstin[:2] != customer_state_code`) is rejected with `422 DomainValidationError`.
3. **Place of Supply (POS) Resolution Priority:**
   - First, uses `sales.sales_orders.place_of_supply_state_code` / customer shipping address state (`order.shipping_address_id` or default `SHIPPING` / `BILLING` address in `sales.customer_addresses`).
   - Caller may supply `place_of_supply_state_code` override on draft creation only where matching legal state validation (`^[0-9]{2}$`).
4. **Intra-State vs. Inter-State Rule:**
   - `seller_state_code == place_of_supply_state_code` -> `supply_type = 'INTRA_STATE'` (`CGST + SGST`).
   - `seller_state_code != place_of_supply_state_code` -> `supply_type = 'INTER_STATE'` (`IGST` under Section 7 of the IGST Act).
5. **Audit Rationale Persistence:**
   - Every calculation records a human-readable `rule_rationale` string inside `tax_calculation_snapshot`, surfaced in the UI GST Calculation Audit panel and Audit Trail.

---

## Benchmark Proof Cases

| Customer | Supplier State | Customer GSTIN | POS State | Nature | Supply Type | Tax Applied |
| --- | --- | --- | --- | --- | --- | --- |
| `Retailer A` (`CUST-RET-A`) | `33` (Tamil Nadu) | `33AAACR9999K1Z2` | `33` (Tamil Nadu) | `B2B` | `INTRA_STATE` | `2.5% CGST + 2.5% SGST` |
| `Distributor B` (`CUST-DIST-B`) | `33` (Tamil Nadu) | `29AAACD8888M1Z9` | `29` (Karnataka) | `B2B` | `INTER_STATE` | `5.0% IGST` |
| Unregistered local buyer | `33` (Tamil Nadu) | `None` | `33` (Tamil Nadu) | `B2C` | `INTRA_STATE` | `2.5% CGST + 2.5% SGST` |

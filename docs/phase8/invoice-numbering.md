# Phase 8 — Numbering Series & Indian Financial Year Rollover

## Implementation

Transaction-safe sequential document numbering lives in [`billing.fiscal_sequences`](file:///d:/mac/ota/backend/app/modules/billing/models.py) and `allocate_fiscal_sequence` in [`repository.py`](file:///d:/mac/ota/backend/app/modules/billing/repository.py).

---

## Indian Financial Year Derivation

`get_indian_financial_year(doc_date)` computes the April 1 – March 31 Indian fiscal year:
- If `doc_date.month >= 4`: `"{year}-{(year + 1) % 100:02d}"` (e.g., `2027-04-01` -> `"2027-28"`).
- If `doc_date.month < 4`: `"{year - 1}-{year % 100:02d}"` (e.g., `2027-03-31` -> `"2026-27"`).

---

## Document Formats

| Document Type (`doc_type`) | Prefix | Format Pattern | Allocated When |
| --- | --- | --- | --- |
| `INVOICE` | `INV` | `INV/YYYY-YY/NNNN` (e.g. `INV/2026-27/0001`) | Strictly upon **Issuance** (`DRAFT -> ISSUED`), never on Draft creation |
| `CREDIT_NOTE` | `CN` | `CN/YYYY-YY/NNNN` (e.g. `CN/2026-27/0001`) | Strictly upon **Issuance** (`DRAFT -> ISSUED`) |
| `DISPATCH` | `DSP` | `DSP/YYYY-YY/NNNN` (e.g. `DSP/2026-27/0001`) | Upon Dispatch Note creation |

Draft invoices hold a temporary non-statutory `draft_ref` (`DRF-INV-...`), enforced at database level by `chk_invoices_inv_issued_number_required`:
- `doc_status = 'DRAFT' => invoice_number IS NULL`
- `doc_status IN ('ISSUED', 'CANCELLED_BY_CN') => invoice_number IS NOT NULL`

---

## Concurrency & Gapless Serialization

`allocate_fiscal_sequence`:
1. Executes PostgreSQL `INSERT INTO billing.fiscal_sequences ... ON CONFLICT (doc_type, financial_year) DO NOTHING` (`pg_insert(...).on_conflict_do_nothing`).
2. Acquires an exclusive row lock via `SELECT ... FROM billing.fiscal_sequences WHERE doc_type = :doc_type AND financial_year = :fy FOR UPDATE`.
3. Increments `last_seq_no += 1`, flushes inside the enclosing DB transaction, and returns `f"{row.prefix}/{row.financial_year}/{row.last_seq_no:04d}"`.
4. If the transaction rolls back on an error later in issuance, the sequence increment rolls back atomically with it—preventing phantom number gaps on failed transactions.

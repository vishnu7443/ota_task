# Phase 10 — Audit, Reconciliation & Management Intelligence Overview

## Purpose

Phase 10 delivers the final enterprise governance, verification, and executive analytics layer for the NIT Tiruchirappalli CDI Winter Internship 2026 **Order-to-Audit Management System (`Kaveri Traditional Snacks Pvt. Ltd.`)**.

Rather than building a disconnected reporting clone, Phase 10 integrates directly with all operational and financial ledgers established across Phases 1–9:
- **Centralized Audit Explorer (`audit.audit_logs`):** Enhances the append-only audit backbone with request-level correlation tracking (`REQ-...`), sanitized JSON metadata, pagination, CSV export, security monitoring (`LOGIN_FAILED`, `ACCESS_DENIED`), and per-user activity reporting.
- **IAM User & Role Governance (`iam.users`, `iam.roles`):** Adds Factory Admin / Owner endpoints (`/iam/roles`, `/iam/users`) to provision accounts, change roles, or deactivate access with mandatory audit reasons and zero credential exposure.
- **Cross-Module Reconciliation Engine (`reconciliation` + `audit.reconciliation_*`):** Deterministically verifies data parity across Inventory, Purchasing, Sales Orders, GST Invoices, Credit Notes, Payments, Customer Receivables, Dispatches, Production Execution, and Batch Costing without modifying balances silently.
- **Controlled Discrepancy Workflow (`audit.reconciliation_runs`, `reconciliation_discrepancies`, `reconciliation_events`):** Guides exceptions through `OPEN -> UNDER_REVIEW -> ACTION_PROPOSED -> APPROVED -> RESOLVED / DISMISSED -> CLOSED` with explicit Maker-Checker approvals and authorized `StockAdjustment` ledger postings.
- **Management Intelligence Dashboard (`/intelligence`):** Consolidates real-time Net Sales (excl. GST), GST Collected, FIFO Stock Valuation, Batch Yield & Unit Costing, Collections, Due-Date AR Ageing, Gross Profit Margin (distinct from Net Profit), and Operational Watchlists.

---

## Core Architectural Principles Enforced

1. **Zero Silent Overwrites:** Discrepancy resolution never silently updates `inventory.inventory_balances`, historical invoices, or payment totals. Physical stock differences flow strictly through authorized `inventory.stock_adjustments` (`COUNT_CORRECTION`), creating immutable `inventory.inventory_movements` ledger rows.
2. **Backend Authoritative Telemetry:** All correlation IDs (`REQ-<uuid8>` via Python `contextvars`), audit state diffs, and reconciliation comparisons execute exclusively on the backend within PostgreSQL ACID transactions.
3. **Immutable Audit & Reconciliation History:** PostgreSQL `BEFORE UPDATE OR DELETE` triggers lock `audit.audit_logs`, `audit.reconciliation_events`, and `CLOSED` `audit.reconciliation_runs`.
4. **Strict 5-Role Segregation of Duties:**
   - `SALESMAN`: Blocked (`403`) from Audit, Reconciliation, Intelligence, and User Governance.
   - `PRODUCTION_SUPERVISOR`: Restricted strictly to `INVENTORY`, `PURCHASING`, and `PRODUCTION` reconciliation views/investigations; blocked from Commercial/Financial domains, Audit Logs, IAM Users, and Management Intelligence.
   - `ACCOUNTANT_AUDITOR`: Full read-only visibility + CSV exports across Audit Logs, all Reconciliation domains, IAM Directory, and Intelligence; blocked (`403`) from all state-changing mutations.
   - `FACTORY_ADMIN` & `OWNER`: Full oversight and governance approvals; only `FACTORY_ADMIN` executes operational ledger resolutions (`STOCK_ADJUSTMENT`).

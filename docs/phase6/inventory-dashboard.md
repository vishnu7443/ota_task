# Inventory Dashboard & Frontend Screens (`docs/phase6/inventory-dashboard.md`)

## Implemented Desktop UI Routes (React + TypeScript + Tailwind)
All Phase 6 screens live cleanly inside `DesktopAdminLayout.tsx`, role-scoped via `RequireRole` in `App.tsx`:

1. **`/admin/purchasing/suppliers` (`AdminSuppliersPage.tsx`):**
   - Search active/inactive vendors, create/edit suppliers (Factory Admin), view GSTIN state consistency, inspect PO/GRN totals and chronological supplier purchase history.
2. **`/admin/purchasing/orders` (`AdminPurchaseOrdersPage.tsx`):**
   - Multi-line PO creation mixing Raw Materials and Packaging Materials with dimension-filtered UOM selectors and live ₹ subtotal + GST preview.
   - Full Draft -> Submit -> Approve / Reject / Cancel action bar and deep link to record Goods Receipts against Approved/Partially Received POs.
3. **`/admin/purchasing/receipts` (`AdminGoodsReceiptsPage.tsx`):**
   - Pre-loads remaining open lines from selected Approved POs, records Received vs Damaged/Rejected quantities (mandatory rejection reason), batch codes, expiry dates, and explicit excess opt-in.
   - Enforces Draft -> Submit -> Verify -> Post to Inventory step-by-step confirmation.
4. **`/admin/inventory` (`AdminInventoryDashboardPage.tsx`):**
   - KPI summary cards (Open FIFO Valuation ₹, Raw/Packaging SKU counts, Low Stock Alerts count, Pending Adjustments count).
   - Category filter tabs (`All`, `Raw Materials`, `Packaging Materials`, `Finished Goods`), Low-Stock toggle, search input, and clean movement breakdown (`Opening`, `Received`, `Adjusted`, `Physical`, `Reserved`, `Available`, `Reorder`, `Lot Value`) with unit-aware display + canonical base unit sublabels.
5. **`/admin/inventory/ledger` (`AdminInventoryLedgerPage.tsx`):**
   - Filterable immutable ledger timeline by Item (Raw Material / Packaging / Finished Good SKU), Movement Type, and Date Range (`GET /api/v1/inventory/ledger`).
6. **`/admin/inventory/adjustments` (`AdminStockAdjustmentsPage.tsx`):**
   - Reason-logged adjustment request form with role-aware `Approve & Post immediately` toggle (Admin only), plus Admin Pending Approval queue & historical audit register.
7. **`/admin/inventory/reports` (`AdminStockReportsPage.tsx`):**
   - Four report views powered by `/api/v1/inventory/reports/summary` (Current Stock, Low Stock Alerts, Purchase Receipts, Stock Adjustments) with client-side CSV download.

## Role Routing Notes
- `FACTORY_ADMIN`: full access to Sales Orders + Purchasing + Inventory workflows.
- `PRODUCTION_SUPERVISOR`: automatically routed to `/admin/inventory`; Sales Order links & views are hidden/blocked (`403`) while Purchasing & Inventory screens operate within Supervisor RBAC permissions.
- `ACCOUNTANT_AUDITOR` & `OWNER`: full read-only visibility across dashboards, ledgers, and reports (all write/mutation controls disabled/rejected with `403`).
- `SALESMAN`: strictly restricted to mobile field order routes (`/salesman*`).

import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/lib/auth-context";
import { LoginPage } from "@/pages/LoginPage";
import { AdminDashboardPage } from "@/pages/admin/AdminDashboardPage";
import { AdminBomPage } from "@/pages/admin/AdminBomPage";
import { AdminGoodsReceiptsPage } from "@/pages/admin/AdminGoodsReceiptsPage";
import { AdminIncomingOrdersPage } from "@/pages/admin/AdminIncomingOrdersPage";
import { AdminInventoryDashboardPage } from "@/pages/admin/AdminInventoryDashboardPage";
import { AdminInventoryLedgerPage } from "@/pages/admin/AdminInventoryLedgerPage";
import { AdminOrderDetailPage } from "@/pages/admin/AdminOrderDetailPage";
import { AdminProductionDashboardPage } from "@/pages/admin/AdminProductionDashboardPage";
import { AdminProductionRunDetailPage } from "@/pages/admin/AdminProductionRunDetailPage";
import { AdminProductionVarianceReportPage } from "@/pages/admin/AdminProductionVarianceReportPage";
import { AdminPurchaseOrdersPage } from "@/pages/admin/AdminPurchaseOrdersPage";
import { AdminStockAdjustmentsPage } from "@/pages/admin/AdminStockAdjustmentsPage";
import { AdminStockReportsPage } from "@/pages/admin/AdminStockReportsPage";
import { AdminSuppliersPage } from "@/pages/admin/AdminSuppliersPage";
import { NewOrderPage } from "@/pages/salesman/NewOrderPage";
import { SalesmanHomePage } from "@/pages/salesman/SalesmanHomePage";
import { SalesmanOrderDetailPage } from "@/pages/salesman/SalesmanOrderDetailPage";
import { SalesmanOrdersPage } from "@/pages/salesman/SalesmanOrdersPage";

function homeForRole(roleCode: string): string {
  if (roleCode === "SALESMAN") return "/salesman";
  if (roleCode === "PRODUCTION_SUPERVISOR") return "/admin/inventory";
  return "/admin";
}

function RequireRole({
  allowedRoles,
  children,
}: {
  allowedRoles: string[];
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
        Loading session...
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (!allowedRoles.includes(user.role_code)) {
    return <Navigate to={homeForRole(user.role_code)} replace />;
  }
  return <>{children}</>;
}

function RootRedirect() {
  const { user, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
        Loading...
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={homeForRole(user.role_code)} replace />;
}

export function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginPage />} />

      {/* Mobile-first Salesman routes */}
      <Route
        path="/salesman"
        element={
          <RequireRole allowedRoles={["SALESMAN"]}>
            <SalesmanHomePage />
          </RequireRole>
        }
      />
      <Route
        path="/salesman/new-order"
        element={
          <RequireRole allowedRoles={["SALESMAN"]}>
            <NewOrderPage />
          </RequireRole>
        }
      />
      <Route
        path="/salesman/orders"
        element={
          <RequireRole allowedRoles={["SALESMAN"]}>
            <SalesmanOrdersPage />
          </RequireRole>
        }
      />
      <Route
        path="/salesman/orders/:orderId"
        element={
          <RequireRole allowedRoles={["SALESMAN"]}>
            <SalesmanOrderDetailPage />
          </RequireRole>
        }
      />
      <Route
        path="/salesman/orders/:orderId/confirmation"
        element={
          <RequireRole allowedRoles={["SALESMAN"]}>
            <SalesmanOrderDetailPage />
          </RequireRole>
        }
      />

      {/* Desktop-first Admin & Oversight routes */}
      <Route
        path="/admin"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminDashboardPage />
          </RequireRole>
        }
      />
      <Route
        path="/admin/orders"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminIncomingOrdersPage />
          </RequireRole>
        }
      />
      <Route
        path="/admin/orders/:orderId"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminOrderDetailPage />
          </RequireRole>
        }
      />

      {/* Phase 6: Purchasing & Inventory Routes */}
      <Route
        path="/admin/purchasing/suppliers"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminSuppliersPage />
          </RequireRole>
        }
      />
      <Route
        path="/admin/purchasing/orders"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminPurchaseOrdersPage />
          </RequireRole>
        }
      />
      <Route
        path="/admin/purchasing/receipts"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminGoodsReceiptsPage />
          </RequireRole>
        }
      />
      <Route
        path="/admin/inventory"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminInventoryDashboardPage />
          </RequireRole>
        }
      />
      <Route
        path="/admin/inventory/ledger"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminInventoryLedgerPage />
          </RequireRole>
        }
      />
      <Route
        path="/admin/inventory/adjustments"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminStockAdjustmentsPage />
          </RequireRole>
        }
      />
      <Route
        path="/admin/inventory/reports"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminStockReportsPage />
          </RequireRole>
        }
      />

      {/* Phase 7: BOM & Production Management Routes */}
      <Route
        path="/admin/production"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminProductionDashboardPage />
          </RequireRole>
        }
      />
      <Route
        path="/admin/production/boms"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminBomPage />
          </RequireRole>
        }
      />
      <Route
        path="/admin/production/runs/:runId"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminProductionRunDetailPage />
          </RequireRole>
        }
      />
      <Route
        path="/admin/production/variances"
        element={
          <RequireRole allowedRoles={["FACTORY_ADMIN", "PRODUCTION_SUPERVISOR", "OWNER", "ACCOUNTANT_AUDITOR"]}>
            <AdminProductionVarianceReportPage />
          </RequireRole>
        }
      />

      <Route path="*" element={<RootRedirect />} />
    </Routes>
  );
}

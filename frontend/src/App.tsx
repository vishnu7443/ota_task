import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/lib/auth-context";
import { LoginPage } from "@/pages/LoginPage";
import { AdminDashboardPage } from "@/pages/admin/AdminDashboardPage";
import { AdminIncomingOrdersPage } from "@/pages/admin/AdminIncomingOrdersPage";
import { AdminOrderDetailPage } from "@/pages/admin/AdminOrderDetailPage";
import { NewOrderPage } from "@/pages/salesman/NewOrderPage";
import { SalesmanHomePage } from "@/pages/salesman/SalesmanHomePage";
import { SalesmanOrderDetailPage } from "@/pages/salesman/SalesmanOrderDetailPage";
import { SalesmanOrdersPage } from "@/pages/salesman/SalesmanOrdersPage";

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
    return <Navigate to={user.role_code === "SALESMAN" ? "/salesman" : "/admin"} replace />;
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
  return <Navigate to={user.role_code === "SALESMAN" ? "/salesman" : "/admin"} replace />;
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

      <Route path="*" element={<RootRedirect />} />
    </Routes>
  );
}

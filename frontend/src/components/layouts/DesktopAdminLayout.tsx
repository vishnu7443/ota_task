import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  BookOpen,
  Boxes,
  Calculator,
  ClipboardCheck,
  Factory,
  FileSpreadsheet,
  FileText,
  IndianRupee,
  Layers,
  LayoutDashboard,
  LogOut,
  PackageCheck,
  Receipt,
  TrendingUp,
  Truck,
  Users,
  Wallet,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

function SidebarLink({
  to,
  end = false,
  icon: Icon,
  label,
}: {
  to: string;
  end?: boolean;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
}) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
          isActive
            ? "bg-primary/10 text-primary"
            : "text-muted-foreground hover:bg-secondary hover:text-foreground"
        )
      }
    >
      <Icon className="h-4 w-4 shrink-0" />
      <span>{label}</span>
    </NavLink>
  );
}

export function DesktopAdminLayout({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
}) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const canViewSalesOrders =
    user?.role_code === "FACTORY_ADMIN" ||
    user?.role_code === "OWNER" ||
    user?.role_code === "ACCOUNTANT_AUDITOR";

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-background flex flex-col md:flex-row">
      <aside className="w-full border-b bg-card md:w-64 md:shrink-0 md:border-b-0 md:border-r">
        <div className="flex h-full flex-col justify-between p-4">
          <div className="space-y-5">
            <div className="flex items-center gap-2.5 px-2 pb-4 pt-1 border-b">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Factory className="h-5 w-5" />
              </div>
              <div>
                <div className="text-sm font-bold leading-tight">Kaveri Snacks</div>
                <div className="text-[11px] font-medium text-muted-foreground">
                  Factory Control Desk
                </div>
              </div>
            </div>

            {canViewSalesOrders && (
              <>
                <div>
                  <p className="px-3 mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Sales &amp; Oversight
                  </p>
                  <nav className="space-y-1">
                    <SidebarLink to="/admin" end icon={LayoutDashboard} label="Dashboard" />
                    <SidebarLink to="/admin/orders" icon={ClipboardCheck} label="Incoming Orders" />
                  </nav>
                </div>

                <div>
                  <p className="px-3 mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    GST Billing &amp; Dispatch
                  </p>
                  <nav className="space-y-1">
                    <SidebarLink to="/admin/billing" end icon={Receipt} label="Billing & Invoices" />
                    <SidebarLink to="/admin/billing/credit-notes" icon={FileSpreadsheet} label="Credit Notes" />
                    <SidebarLink to="/admin/dispatch" icon={Truck} label="Dispatch & Delivery" />
                    <SidebarLink to="/admin/billing/reports" icon={BarChart3} label="GST & Sales Reports" />
                  </nav>
                </div>
              </>
            )}

            <div>
              <p className="px-3 mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Purchasing
              </p>
              <nav className="space-y-1">
                <SidebarLink to="/admin/purchasing/suppliers" icon={Users} label="Suppliers" />
                <SidebarLink to="/admin/purchasing/orders" icon={Receipt} label="Purchase Orders" />
                <SidebarLink
                  to="/admin/purchasing/receipts"
                  icon={PackageCheck}
                  label="Goods Receipts"
                />
              </nav>
            </div>

            <div>
              <p className="px-3 mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Inventory &amp; Ledger
              </p>
              <nav className="space-y-1">
                <SidebarLink to="/admin/inventory" end icon={Boxes} label="Stock Overview" />
                <SidebarLink
                  to="/admin/inventory/ledger"
                  icon={BookOpen}
                  label="Inventory Ledger"
                />
                <SidebarLink
                  to="/admin/inventory/adjustments"
                  icon={AlertTriangle}
                  label="Stock Adjustments"
                />
                <SidebarLink to="/admin/inventory/reports" icon={FileText} label="Stock Reports" />
              </nav>
            </div>

            <div>
              <p className="px-3 mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Production &amp; BOM
              </p>
              <nav className="space-y-1">
                <SidebarLink to="/admin/production" end icon={Activity} label="Production Runs" />
                  <SidebarLink to="/admin/production/boms" icon={Layers} label="BOM & Recipes" />
                <SidebarLink
                  to="/admin/production/variances"
                  icon={BarChart3}
                  label="Variance Report"
                />
                <SidebarLink to="/admin/costing" icon={Calculator} label="Product Costing" />
              </nav>
            </div>

            {canViewSalesOrders && (
              <div>
                <p className="px-3 mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Finance, AR &amp; Margins
                </p>
                <nav className="space-y-1">
                  <SidebarLink to="/admin/finance" end icon={IndianRupee} label="Financial Overview" />
                  <SidebarLink to="/admin/finance/payments" icon={Wallet} label="Payments & Receipts" />
                  <SidebarLink to="/admin/finance/receivables" icon={FileSpreadsheet} label="Receivables & Ageing" />
                  <SidebarLink to="/admin/finance/profitability" icon={TrendingUp} label="Profitability & COGS" />
                </nav>
              </div>
            )}
          </div>

          <div className="mt-6 border-t pt-4">
            <div className="mb-3 px-2">
              <div className="text-sm font-semibold text-foreground">{user?.full_name}</div>
              <div className="text-xs text-muted-foreground">{user?.role_name}</div>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="flex w-full items-center justify-center gap-2 rounded-lg border px-3 py-2 text-xs font-semibold text-muted-foreground hover:bg-secondary hover:text-foreground"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      </aside>

      <div className="flex-1 min-w-0">
        <header className="border-b bg-card px-6 py-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-foreground">{title}</h1>
            {subtitle && <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>}
          </div>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
        <main className="p-6 max-w-7xl mx-auto">{children}</main>
      </div>
    </div>
  );
}

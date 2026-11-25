import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import {
  BarChart3,
  ClipboardCheck,
  Factory,
  FileSpreadsheet,
  LayoutDashboard,
  LogOut,
  Package,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { cn } from "@/lib/utils";

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

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen bg-background flex flex-col md:flex-row">
      <aside className="w-full border-b bg-card md:w-64 md:shrink-0 md:border-b-0 md:border-r">
        <div className="flex h-full flex-col justify-between p-4">
          <div>
            <div className="flex items-center gap-2.5 px-2 pb-5 pt-1 border-b">
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

            <nav className="mt-5 space-y-1">
              <NavLink
                to="/admin"
                end
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                  )
                }
              >
                <LayoutDashboard className="h-4 w-4" />
                <span>Dashboard</span>
              </NavLink>
              <NavLink
                to="/admin/orders"
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                  )
                }
              >
                <ClipboardCheck className="h-4 w-4" />
                <span>Incoming Orders</span>
              </NavLink>
            </nav>

            <div className="mt-8 border-t pt-4">
              <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Upcoming Phases
              </p>
              <div className="mt-2 space-y-1 opacity-55">
                <div className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground">
                  <FileSpreadsheet className="h-4 w-4" />
                  <span>GST Invoicing &amp; AR</span>
                </div>
                <div className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground">
                  <Package className="h-4 w-4" />
                  <span>BOM &amp; Stock Ledger</span>
                </div>
                <div className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium text-muted-foreground">
                  <BarChart3 className="h-4 w-4" />
                  <span>Audit Exports</span>
                </div>
              </div>
            </div>
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
        <header className="border-b bg-card/80 backdrop-blur">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-4">
            <div>
              <h1 className="text-xl font-bold tracking-tight text-foreground">{title}</h1>
              {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
            </div>
            {actions && <div className="flex items-center gap-2.5">{actions}</div>}
          </div>
        </header>
        <main className="mx-auto max-w-6xl p-6">{children}</main>
      </div>
    </div>
  );
}

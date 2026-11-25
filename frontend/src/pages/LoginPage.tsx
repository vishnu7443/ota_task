import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Factory, Lock, Smartphone, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

function routeForRole(roleCode: string): string {
  if (roleCode === "SALESMAN") return "/salesman";
  if (roleCode === "PRODUCTION_SUPERVISOR") return "/admin/inventory";
  if (roleCode === "OWNER") return "/admin/intelligence";
  return "/admin";
}

export function LoginPage() {
  const { user, login, logout } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const loggedUser = await login(username.trim(), password);
      navigate(routeForRole(loggedUser.role_code), { replace: true });
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError("Login failed. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-2">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-sm">
            <Factory className="h-6 w-6" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Kaveri Traditional Snacks
          </h1>
          <p className="text-sm text-muted-foreground">
            Order-to-Audit Factory Management System
          </p>
        </div>

        <Card className="border-border/80 shadow-md">
          <CardHeader>
            <CardTitle className="text-lg">Sign in to your workspace</CardTitle>
            <CardDescription>
              Field salesmen open mobile order capture; factory staff open desktop verification.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {user && (
              <div className="mb-4 flex items-center justify-between gap-2 rounded-lg border bg-secondary/60 px-3 py-2 text-xs">
                <span className="text-muted-foreground">
                  Active session: <strong className="text-foreground">{user.full_name}</strong> ({user.role_code})
                </span>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => navigate(routeForRole(user.role_code), { replace: true })}
                    className="font-semibold text-primary hover:underline"
                  >
                    Continue
                  </button>
                  <button
                    type="button"
                    onClick={logout}
                    className="text-muted-foreground hover:text-foreground hover:underline"
                  >
                    Sign out
                  </button>
                </div>
              </div>
            )}
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div
                  role="alert"
                  className="rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm font-medium text-red-700"
                >
                  {error}
                </div>
              )}

              <div className="space-y-1.5">
                <label htmlFor="username" className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Username
                </label>
                <Input
                  id="username"
                  name="username"
                  autoComplete="username"
                  placeholder="e.g. salesman_a or admin"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="password" className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Password
                </label>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  placeholder="Enter password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>

              <Button type="submit" size="lg" className="w-full" disabled={submitting}>
                <Lock className="h-4 w-4" />
                {submitting ? "Signing in..." : "Sign In"}
              </Button>
            </form>

            {import.meta.env.DEV && (
              <div className="mt-5 rounded-xl border bg-secondary/50 p-3.5 space-y-2">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Development Test Accounts
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setUsername("salesman_a");
                      setPassword("SalesA@2026!");
                    }}
                    className="flex items-center gap-2 rounded-lg border bg-card px-2.5 py-2 text-left text-xs hover:bg-secondary"
                  >
                    <Smartphone className="h-3.5 w-3.5 text-primary shrink-0" />
                    <div>
                      <div className="font-semibold">Salesman A</div>
                      <div className="text-[10px] text-muted-foreground">salesman_a</div>
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setUsername("admin");
                      setPassword("Admin@2026!");
                    }}
                    className="flex items-center gap-2 rounded-lg border bg-card px-2.5 py-2 text-left text-xs hover:bg-secondary"
                  >
                    <ShieldCheck className="h-3.5 w-3.5 text-accent shrink-0" />
                    <div>
                      <div className="font-semibold">Factory Admin</div>
                      <div className="text-[10px] text-muted-foreground">admin</div>
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setUsername("supervisor");
                      setPassword("Prod@2026!");
                    }}
                    className="flex items-center gap-2 rounded-lg border bg-card px-2.5 py-2 text-left text-xs hover:bg-secondary col-span-2"
                  >
                    <Factory className="h-3.5 w-3.5 text-amber-600 shrink-0" />
                    <div>
                      <div className="font-semibold">Production Supervisor</div>
                      <div className="text-[10px] text-muted-foreground">supervisor (Purchasing &amp; Inventory)</div>
                    </div>
                  </button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

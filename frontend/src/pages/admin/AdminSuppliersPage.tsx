import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Edit3, Plus, Search, X } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api, type Supplier } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatInrFromPaisa, formatOrderDate } from "@/lib/money";

export function AdminSuppliersPage() {
  const { user } = useAuth();
  const isAdmin = user?.role_code === "FACTORY_ADMIN";
  const queryClient = useQueryClient();

  const [search, setSearch] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [editingSupplier, setEditingSupplier] = useState<Supplier | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [banner, setBanner] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  const [formCode, setFormCode] = useState("");
  const [formName, setFormName] = useState("");
  const [formContact, setFormContact] = useState("");
  const [formPhone, setFormPhone] = useState("");
  const [formEmail, setFormEmail] = useState("");
  const [formGstin, setFormGstin] = useState("");
  const [formStateName, setFormStateName] = useState("Tamil Nadu");
  const [formStateCode, setFormStateCode] = useState("33");
  const [formAddress, setFormAddress] = useState("");
  const [formActive, setFormActive] = useState(true);

  const suppliersQuery = useQuery({
    queryKey: ["purchasing-suppliers", activeOnly, search],
    queryFn: () => api.getSuppliers({ activeOnly, search: search.trim() || undefined }),
  });

  const detailQuery = useQuery({
    queryKey: ["purchasing-supplier-detail", selectedId],
    queryFn: () => api.getSupplierDetail(Number(selectedId)),
    enabled: Boolean(selectedId),
  });

  const resetForm = () => {
    setFormCode("");
    setFormName("");
    setFormContact("");
    setFormPhone("");
    setFormEmail("");
    setFormGstin("");
    setFormStateName("Tamil Nadu");
    setFormStateCode("33");
    setFormAddress("");
    setFormActive(true);
    setEditingSupplier(null);
    setShowCreateForm(false);
  };

  const openEdit = (sup: Supplier) => {
    setEditingSupplier(sup);
    setShowCreateForm(true);
    setFormCode(sup.code);
    setFormName(sup.name);
    setFormContact(sup.contact_person ?? "");
    setFormPhone(sup.phone ?? "");
    setFormEmail(sup.email ?? "");
    setFormGstin(sup.gstin ?? "");
    setFormStateName(sup.state_name);
    setFormStateCode(sup.state_code);
    setFormAddress(sup.address);
    setFormActive(sup.is_active);
    setBanner(null);
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (editingSupplier) {
        return api.updateSupplier(editingSupplier.id, {
          name: formName,
          contact_person: formContact || null,
          phone: formPhone || null,
          email: formEmail || null,
          gstin: formGstin || null,
          state_name: formStateName,
          state_code: formStateCode,
          address: formAddress,
          is_active: formActive,
        });
      }
      return api.createSupplier({
        code: formCode,
        name: formName,
        contact_person: formContact || null,
        phone: formPhone || null,
        email: formEmail || null,
        gstin: formGstin || null,
        state_name: formStateName,
        state_code: formStateCode,
        address: formAddress,
        is_active: formActive,
      });
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ["purchasing-suppliers"] });
      queryClient.invalidateQueries({ queryKey: ["purchasing-supplier-detail", saved.id] });
      setBanner({
        kind: "success",
        msg: `Supplier ${saved.code} (${saved.name}) saved cleanly.`,
      });
      setSelectedId(saved.id);
      resetForm();
    },
    onError: (err) => {
      const msg = err instanceof ApiClientError ? err.message : "Failed to save supplier.";
      setBanner({ kind: "error", msg });
    },
  });

  const suppliers = suppliersQuery.data ?? [];
  const detail = detailQuery.data;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setBanner(null);
    saveMutation.mutate();
  };

  return (
    <DesktopAdminLayout
      title="Suppliers"
      subtitle="Manage raw material & packaging vendors, GSTIN records, and purchase history"
      actions={
        isAdmin ? (
          <Button
            onClick={() => {
              if (showCreateForm) {
                resetForm();
              } else {
                resetForm();
                setShowCreateForm(true);
              }
            }}
          >
            {showCreateForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
            {showCreateForm ? "Close Form" : "Add Supplier"}
          </Button>
        ) : undefined
      }
    >
      <div className="space-y-6">
        {banner && (
          <div
            className={`rounded-xl border px-4 py-3 text-sm font-medium ${
              banner.kind === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-red-200 bg-red-50 text-red-800"
            }`}
          >
            {banner.msg}
          </div>
        )}

        {showCreateForm && isAdmin && (
          <Card className="border-primary/30 shadow-sm">
            <CardHeader>
              <CardTitle className="text-base">
                {editingSupplier ? `Edit Supplier ${editingSupplier.code}` : "Register New Supplier"}
              </CardTitle>
              <CardDescription>
                Validate GSTIN state prefix matches the supplier's 2-digit GST state code.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Supplier Code</label>
                  <Input
                    value={formCode}
                    onChange={(e) => setFormCode(e.target.value)}
                    disabled={Boolean(editingSupplier)}
                    placeholder="e.g. SUP-002"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Legal Name</label>
                  <Input
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="Supplier business name"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Contact Person</label>
                  <Input
                    value={formContact}
                    onChange={(e) => setFormContact(e.target.value)}
                    placeholder="Primary coordinator"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Phone</label>
                  <Input
                    value={formPhone}
                    onChange={(e) => setFormPhone(e.target.value)}
                    placeholder="+91..."
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Email</label>
                  <Input
                    type="email"
                    value={formEmail}
                    onChange={(e) => setFormEmail(e.target.value)}
                    placeholder="orders@supplier.example"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">GSTIN (15-char optional)</label>
                  <Input
                    value={formGstin}
                    onChange={(e) => setFormGstin(e.target.value.toUpperCase())}
                    placeholder="33AAAAA0000A1Z5"
                    maxLength={15}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">State Name</label>
                  <Input
                    value={formStateName}
                    onChange={(e) => setFormStateName(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">GST State Code</label>
                  <Input
                    value={formStateCode}
                    onChange={(e) => setFormStateCode(e.target.value)}
                    maxLength={2}
                    required
                  />
                </div>
                <div className="space-y-1 flex items-end pb-1">
                  <label className="flex items-center gap-2 text-sm font-medium cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formActive}
                      onChange={(e) => setFormActive(e.target.checked)}
                      className="h-4 w-4 rounded border-input"
                    />
                    Active for Purchase Orders
                  </label>
                </div>
                <div className="space-y-1 sm:col-span-2 lg:col-span-3">
                  <label className="text-xs font-semibold text-muted-foreground">Address</label>
                  <Input
                    value={formAddress}
                    onChange={(e) => setFormAddress(e.target.value)}
                    placeholder="Street, industrial estate, city, pincode"
                    required
                  />
                </div>
                <div className="sm:col-span-2 lg:col-span-3 flex gap-2">
                  <Button type="submit" disabled={saveMutation.isPending}>
                    {saveMutation.isPending ? "Saving..." : editingSupplier ? "Update Supplier" : "Create Supplier"}
                  </Button>
                  <Button type="button" variant="outline" onClick={resetForm}>
                    Cancel
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative flex-1 max-w-sm">
            <Search className="h-4 w-4 absolute left-3 top-3 text-muted-foreground" />
            <Input
              className="pl-9"
              placeholder="Search code, name, or GSTIN..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={(e) => setActiveOnly(e.target.checked)}
              className="h-4 w-4 rounded border-input"
            />
            Show Active Only
          </label>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">Registered Suppliers ({suppliers.length})</CardTitle>
              <CardDescription>Click a supplier row to inspect PO &amp; receipt history</CardDescription>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="py-2 pr-3">Code</th>
                    <th className="py-2 pr-3">Supplier &amp; GSTIN</th>
                    <th className="py-2 pr-3">State</th>
                    <th className="py-2 pr-3 text-right">POs / GRNs</th>
                    <th className="py-2 pr-3 text-right">Posted Purchases</th>
                    <th className="py-2">Status</th>
                    {isAdmin && <th className="py-2 text-right">Edit</th>}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {suppliers.map((sup) => (
                    <tr
                      key={sup.id}
                      onClick={() => setSelectedId(sup.id)}
                      className={`cursor-pointer hover:bg-secondary/40 ${
                        selectedId === sup.id ? "bg-primary/5" : ""
                      }`}
                    >
                      <td className="py-3 pr-3 font-mono text-xs font-semibold">{sup.code}</td>
                      <td className="py-3 pr-3">
                        <div className="font-semibold text-foreground">{sup.name}</div>
                        <div className="text-xs text-muted-foreground">
                          {sup.gstin ?? "Unregistered"} · {sup.phone ?? "No phone"}
                        </div>
                      </td>
                      <td className="py-3 pr-3 text-xs">
                        {sup.state_name} ({sup.state_code})
                      </td>
                      <td className="py-3 pr-3 text-right tabular-nums text-xs">
                        {sup.po_count} / {sup.receipt_count}
                      </td>
                      <td className="py-3 pr-3 text-right font-semibold tabular-nums">
                        {formatInrFromPaisa(sup.total_purchased_paisa)}
                      </td>
                      <td className="py-3">
                        <Badge variant={sup.is_active ? "success" : "secondary"}>
                          {sup.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </td>
                      {isAdmin && (
                        <td className="py-3 text-right" onClick={(e) => e.stopPropagation()}>
                          <Button size="sm" variant="ghost" onClick={() => openEdit(sup)}>
                            <Edit3 className="h-3.5 w-3.5" />
                          </Button>
                        </td>
                      )}
                    </tr>
                  ))}
                  {suppliers.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-8 text-center text-muted-foreground">
                        No matching suppliers found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Building2 className="h-4 w-4 text-primary" />
                Supplier Profile &amp; History
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!detail ? (
                <p className="text-sm text-muted-foreground py-6 text-center">
                  Select a supplier from the table to inspect contact details, purchase orders, and posted receipts.
                </p>
              ) : (
                <div className="space-y-4 text-sm">
                  <div className="rounded-lg bg-secondary/40 p-3 space-y-1">
                    <div className="font-bold text-foreground">{detail.name}</div>
                    <div className="text-xs text-muted-foreground font-mono">{detail.code}</div>
                    <p className="text-xs text-muted-foreground pt-1">{detail.address}</p>
                    <p className="text-xs text-muted-foreground">
                      Contact: {detail.contact_person ?? "—"} · {detail.email ?? "—"}
                    </p>
                  </div>

                  <div>
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                      Recent Purchase Orders ({detail.purchase_orders.length})
                    </h4>
                    <div className="space-y-2 max-h-48 overflow-y-auto">
                      {detail.purchase_orders.map((po) => (
                        <div key={po.id} className="flex items-center justify-between border rounded-lg p-2 text-xs">
                          <div>
                            <div className="font-semibold">{po.po_number}</div>
                            <div className="text-muted-foreground">{formatOrderDate(po.order_date)}</div>
                          </div>
                          <div className="text-right space-y-1">
                            <div className="font-semibold tabular-nums">{formatInrFromPaisa(po.total_paisa)}</div>
                            <StatusBadge status={po.status} />
                          </div>
                        </div>
                      ))}
                      {detail.purchase_orders.length === 0 && (
                        <p className="text-xs text-muted-foreground">No purchase orders yet.</p>
                      )}
                    </div>
                  </div>

                  <div>
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                      Goods Receipts ({detail.purchase_receipts.length})
                    </h4>
                    <div className="space-y-2 max-h-48 overflow-y-auto">
                      {detail.purchase_receipts.map((gr) => (
                        <div key={gr.id} className="flex items-center justify-between border rounded-lg p-2 text-xs">
                          <div>
                            <div className="font-semibold">{gr.receipt_number}</div>
                            <div className="text-muted-foreground">
                              {formatOrderDate(gr.receipt_date)} · {gr.supplier_bill_ref ?? "No bill ref"}
                            </div>
                          </div>
                          <div className="text-right space-y-1">
                            <div className="font-semibold tabular-nums">{formatInrFromPaisa(gr.total_paisa)}</div>
                            <StatusBadge status={gr.status} />
                          </div>
                        </div>
                      ))}
                      {detail.purchase_receipts.length === 0 && (
                        <p className="text-xs text-muted-foreground">No goods receipts yet.</p>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </DesktopAdminLayout>
  );
}

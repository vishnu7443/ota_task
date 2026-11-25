import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Plus,
  RefreshCw,
  Search,
  Store,
  Tag,
  UserPlus,
} from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  api,
  ApiClientError,
  type CustomerSummary,
  type ProductPack,
  type SalesmanOption,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatInrFromPaisa } from "@/lib/money";

const INDIAN_GST_STATES: Array<{ code: string; name: string }> = [
  { code: "33", name: "Tamil Nadu" },
  { code: "29", name: "Karnataka" },
  { code: "32", name: "Kerala" },
  { code: "37", name: "Andhra Pradesh" },
  { code: "36", name: "Telangana" },
  { code: "27", name: "Maharashtra" },
  { code: "07", name: "Delhi" },
  { code: "24", name: "Gujarat" },
  { code: "09", name: "Uttar Pradesh" },
  { code: "19", name: "West Bengal" },
  { code: "34", name: "Puducherry" },
];

export function AdminCatalogPage() {
  const { user } = useAuth();
  const canWrite = user?.role_code === "FACTORY_ADMIN";

  const [customers, setCustomers] = useState<CustomerSummary[]>([]);
  const [products, setProducts] = useState<ProductPack[]>([]);
  const [salesmen, setSalesmen] = useState<SalesmanOption[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  // Create customer modal/panel state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [submittingCustomer, setSubmittingCustomer] = useState(false);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [customerType, setCustomerType] = useState<"RETAILER" | "DISTRIBUTOR">("RETAILER");
  const [gstin, setGstin] = useState("");
  const [stateCode, setStateCode] = useState("33");
  const [stateName, setStateName] = useState("Tamil Nadu");
  const [phone, setPhone] = useState("");
  const [assignedSalesmanId, setAssignedSalesmanId] = useState<string>("");
  const [creditDays, setCreditDays] = useState("15");
  const [addressLine1, setAddressLine1] = useState("");
  const [city, setCity] = useState("");
  const [pincode, setPincode] = useState("");

  // Inline pack-size price editor state
  const [editingPackId, setEditingPackId] = useState<number | null>(null);
  const [priceInrInput, setPriceInrInput] = useState("");
  const [priceReason, setPriceReason] = useState("");
  const [savingPrice, setSavingPrice] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [custList, prodList, salesmanList] = await Promise.all([
        api.getCustomers(),
        api.getProducts(),
        canWrite ? api.getSalesmen() : Promise.resolve([] as SalesmanOption[]),
      ]);
      setCustomers(custList);
      setProducts(prodList);
      setSalesmen(salesmanList);
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Failed to load catalog data.");
    } finally {
      setLoading(false);
    }
  }, [canWrite]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const salesmanMap = useMemo(() => {
    const map = new Map<number, string>();
    for (const s of salesmen) {
      map.set(s.user_id, `${s.full_name} (${s.employee_code})`);
    }
    return map;
  }, [salesmen]);

  const filteredCustomers = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return customers;
    return customers.filter(
      (c) =>
        c.code.toLowerCase().includes(q) ||
        c.name.toLowerCase().includes(q) ||
        (c.gstin ?? "").toLowerCase().includes(q) ||
        c.primary_state_name.toLowerCase().includes(q)
    );
  }, [customers, search]);

  const handleStateSelect = (selectedCode: string) => {
    setStateCode(selectedCode);
    const match = INDIAN_GST_STATES.find((s) => s.code === selectedCode);
    if (match) {
      setStateName(match.name);
    }
  };

  const handleCreateCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canWrite) return;
    setError(null);
    setBanner(null);

    const trimmedCode = code.trim().toUpperCase();
    const trimmedName = name.trim();
    const trimmedAddress = addressLine1.trim();
    const trimmedCity = city.trim();
    const trimmedPin = pincode.trim();

    if (!trimmedCode || !trimmedName || !trimmedAddress || !trimmedCity || !trimmedPin) {
      setError("Code, Name, Address Line 1, City, and 6-digit Pincode are required.");
      return;
    }

    setSubmittingCustomer(true);
    try {
      const created = await api.createCustomer({
        code: trimmedCode,
        name: trimmedName,
        customer_type: customerType,
        gstin: gstin.trim() ? gstin.trim().toUpperCase() : null,
        primary_state_name: stateName.trim(),
        primary_state_code: stateCode.trim(),
        phone: phone.trim() || null,
        assigned_salesman_id: assignedSalesmanId ? Number(assignedSalesmanId) : null,
        credit_days: Math.max(0, Number(creditDays) || 0),
        address_line1: trimmedAddress,
        city: trimmedCity,
        pincode: trimmedPin,
      });
      setBanner(`Customer ${created.code} (${created.name}) created with default billing & shipping addresses.`);
      setShowCreateForm(false);
      setCode("");
      setName("");
      setGstin("");
      setPhone("");
      setAddressLine1("");
      setCity("");
      setPincode("");
      setAssignedSalesmanId("");
      await loadData();
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Failed to create customer.");
    } finally {
      setSubmittingCustomer(false);
    }
  };

  const openPriceEditor = (pack: ProductPack) => {
    setEditingPackId(pack.pack_size_id);
    setPriceInrInput((pack.selling_price_paisa / 100).toFixed(2));
    setPriceReason("");
    setError(null);
    setBanner(null);
  };

  const handleSavePrice = async (pack: ProductPack) => {
    if (!canWrite) return;
    const numericInr = Number(priceInrInput);
    if (!Number.isFinite(numericInr) || numericInr <= 0) {
      setError("Unit selling price must be greater than ₹0.00.");
      return;
    }
    const reason = priceReason.trim();
    if (reason.length < 3) {
      setError("Provide a short audit reason (minimum 3 characters) for the price change.");
      return;
    }

    const paisa = Math.round(numericInr * 100);
    setSavingPrice(true);
    setError(null);
    setBanner(null);
    try {
      const updated = await api.updatePackSizePrice(pack.pack_size_id, {
        unit_price_paisa: paisa,
        reason,
      });
      setProducts((prev) =>
        prev.map((item) => (item.pack_size_id === updated.pack_size_id ? updated : item))
      );
      setEditingPackId(null);
      setPriceReason("");
      setBanner(
        `Updated ${updated.sku_code} selling price to ${formatInrFromPaisa(updated.selling_price_paisa)} (audited).`
      );
    } catch (err) {
      setError(err instanceof ApiClientError ? err.message : "Failed to update SKU selling price.");
    } finally {
      setSavingPrice(false);
    }
  };

  return (
    <DesktopAdminLayout
      title="Customers & SKU Pricing"
      subtitle="Manage retailer/distributor master data, GST state codes, salesman mapping, and finished SKU selling prices."
    >
      <div className="space-y-6">
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {banner && (
          <div className="flex items-start gap-2 rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900">
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-700" />
            <span>{banner}</span>
          </div>
        )}

        {/* Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="relative w-full max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search customers by code, name, GSTIN, state..."
              className="pl-9"
            />
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => void loadData()} disabled={loading}>
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
            {canWrite && (
              <Button size="sm" onClick={() => setShowCreateForm((v) => !v)}>
                <UserPlus className="h-4 w-4" />
                {showCreateForm ? "Cancel New Customer" : "Add Customer"}
              </Button>
            )}
          </div>
        </div>

        {/* Create Customer Panel (FACTORY_ADMIN only) */}
        {canWrite && showCreateForm && (
          <Card className="border-primary/25 bg-primary/[0.02]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Plus className="h-4 w-4 text-primary" />
                New Customer Master Record
              </CardTitle>
              <CardDescription>
                Creates the customer with matching primary BILLING &amp; SHIPPING addresses and records an audited CUSTOMER_CREATED event.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreateCustomer} className="grid gap-4 md:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Customer Code *
                  </label>
                  <Input
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="e.g. CUST-RET-C"
                    required
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Legal / Trade Name *
                  </label>
                  <Input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Cauvery Super Market"
                    required
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Customer Type *
                  </label>
                  <select
                    value={customerType}
                    onChange={(e) => setCustomerType(e.target.value as "RETAILER" | "DISTRIBUTOR")}
                    className="flex h-11 w-full rounded-lg border border-input bg-card px-3 text-sm"
                  >
                    <option value="RETAILER">RETAILER</option>
                    <option value="DISTRIBUTOR">DISTRIBUTOR</option>
                  </select>
                </div>

                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    State (Place of Supply) *
                  </label>
                  <select
                    value={stateCode}
                    onChange={(e) => handleStateSelect(e.target.value)}
                    className="flex h-11 w-full rounded-lg border border-input bg-card px-3 text-sm"
                  >
                    {INDIAN_GST_STATES.map((s) => (
                      <option key={s.code} value={s.code}>
                        {s.code} - {s.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    GSTIN (15 chars, leave blank if unregistered)
                  </label>
                  <Input
                    value={gstin}
                    onChange={(e) => setGstin(e.target.value)}
                    placeholder="e.g. 33AABCC1234D1Z5"
                    maxLength={15}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Assigned Salesman
                  </label>
                  <select
                    value={assignedSalesmanId}
                    onChange={(e) => setAssignedSalesmanId(e.target.value)}
                    className="flex h-11 w-full rounded-lg border border-input bg-card px-3 text-sm"
                  >
                    <option value="">Unassigned / Any</option>
                    {salesmen.map((s) => (
                      <option key={s.user_id} value={String(s.user_id)}>
                        {s.full_name} ({s.employee_code})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    Address Line 1 *
                  </label>
                  <Input
                    value={addressLine1}
                    onChange={(e) => setAddressLine1(e.target.value)}
                    placeholder="Street / Market Road"
                    required
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    City *
                  </label>
                  <Input
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    placeholder="e.g. Tiruchirappalli"
                    required
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">
                      Pincode *
                    </label>
                    <Input
                      value={pincode}
                      onChange={(e) => setPincode(e.target.value)}
                      placeholder="620001"
                      maxLength={6}
                      required
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">
                      Credit Days
                    </label>
                    <Input
                      type="number"
                      min={0}
                      max={365}
                      value={creditDays}
                      onChange={(e) => setCreditDays(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-muted-foreground">
                      Phone
                    </label>
                    <Input
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder="9876543210"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2 md:col-span-3">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setShowCreateForm(false)}
                    disabled={submittingCustomer}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={submittingCustomer}>
                    {submittingCustomer ? "Saving Customer..." : "Create Customer"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Customers Directory */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Store className="h-5 w-5 text-primary" />
              Customer Master ({filteredCustomers.length})
            </CardTitle>
            <CardDescription>
              Customer tax profile determines INTRA-STATE (CGST + SGST) vs INTER-STATE (IGST) treatment against supplier state code 33.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            {loading ? (
              <p className="py-6 text-sm text-muted-foreground">Loading customers...</p>
            ) : filteredCustomers.length === 0 ? (
              <p className="py-6 text-sm text-muted-foreground">No customers match your filter.</p>
            ) : (
              <table className="w-full min-w-[780px] text-left text-sm">
                <thead>
                  <tr className="border-b text-xs uppercase text-muted-foreground">
                    <th className="py-2.5 pr-4">Code</th>
                    <th className="py-2.5 pr-4">Customer</th>
                    <th className="py-2.5 pr-4">Type</th>
                    <th className="py-2.5 pr-4">State / Place of Supply</th>
                    <th className="py-2.5 pr-4">GSTIN</th>
                    <th className="py-2.5 pr-4">Salesman</th>
                    <th className="py-2.5">Contact</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {filteredCustomers.map((c) => (
                    <tr key={c.id} className="hover:bg-secondary/30">
                      <td className="py-3 pr-4 font-mono text-xs font-semibold">{c.code}</td>
                      <td className="py-3 pr-4">
                        <div className="font-medium">{c.name}</div>
                        {c.default_shipping_address && (
                          <div className="text-xs text-muted-foreground">
                            {c.default_shipping_address.city}, {c.default_shipping_address.pincode}
                          </div>
                        )}
                      </td>
                      <td className="py-3 pr-4">
                        <Badge variant={c.customer_type === "DISTRIBUTOR" ? "default" : "secondary"}>
                          {c.customer_type}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4">
                        {c.primary_state_name} ({c.primary_state_code})
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs">
                        {c.gstin ? c.gstin : <span className="text-muted-foreground">Unregistered</span>}
                      </td>
                      <td className="py-3 pr-4 text-xs text-muted-foreground">
                        {c.assigned_salesman_id
                          ? salesmanMap.get(c.assigned_salesman_id) ?? `User #${c.assigned_salesman_id}`
                          : "Any Salesman"}
                      </td>
                      <td className="py-3 text-xs text-muted-foreground">{c.phone ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>

        {/* Finished SKU Catalog & Price List */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Tag className="h-5 w-5 text-primary" />
              Finished Goods Catalog &amp; Active Price List ({products.length})
            </CardTitle>
            <CardDescription>
              Authoritative backend prices used for new sales orders and GST invoicing. Updating a price logs an audit event and never mutates issued invoices.
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            {loading ? (
              <p className="py-6 text-sm text-muted-foreground">Loading SKU catalog...</p>
            ) : products.length === 0 ? (
              <p className="py-6 text-sm text-muted-foreground">No active pack sizes found.</p>
            ) : (
              <table className="w-full min-w-[780px] text-left text-sm">
                <thead>
                  <tr className="border-b text-xs uppercase text-muted-foreground">
                    <th className="py-2.5 pr-4">SKU</th>
                    <th className="py-2.5 pr-4">Product Description</th>
                    <th className="py-2.5 pr-4">HSN &amp; GST</th>
                    <th className="py-2.5 pr-4">Live Stock (Avail / On-Hand)</th>
                    <th className="py-2.5 pr-4">Selling Price</th>
                    {canWrite && <th className="py-2.5 text-right">Action</th>}
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {products.map((p) => {
                    const isEditing = editingPackId === p.pack_size_id;
                    return (
                      <tr key={p.pack_size_id} className="hover:bg-secondary/30">
                        <td className="py-3 pr-4 font-mono text-xs font-semibold">{p.sku_code}</td>
                        <td className="py-3 pr-4">
                          <div className="font-medium">{p.display_name}</div>
                          <div className="text-xs text-muted-foreground">
                            {p.pack_weight_g}g · {p.packets_per_carton} pkts/carton
                          </div>
                        </td>
                        <td className="py-3 pr-4 font-mono text-xs">
                          HSN {p.hsn_code} · {(p.gst_rate_bps / 100).toFixed(2)}%
                        </td>
                        <td className="py-3 pr-4">
                          <span className="font-semibold">{p.available_stock_pkts}</span>
                          <span className="text-xs text-muted-foreground">
                            {" "}
                            / {p.on_hand_stock_pkts} pkts
                          </span>
                        </td>
                        <td className="py-3 pr-4">
                          {isEditing ? (
                            <div className="flex flex-col gap-2">
                              <div className="flex items-center gap-1.5">
                                <span className="text-xs text-muted-foreground">₹</span>
                                <Input
                                  type="number"
                                  step="0.01"
                                  min="0.01"
                                  value={priceInrInput}
                                  onChange={(e) => setPriceInrInput(e.target.value)}
                                  className="h-8 w-28 text-xs"
                                />
                              </div>
                              <Input
                                value={priceReason}
                                onChange={(e) => setPriceReason(e.target.value)}
                                placeholder="Audit reason for price update"
                                className="h-8 w-56 text-xs"
                              />
                            </div>
                          ) : (
                            <span className="font-semibold">
                              {formatInrFromPaisa(p.selling_price_paisa)}
                            </span>
                          )}
                        </td>
                        {canWrite && (
                          <td className="py-3 text-right">
                            {isEditing ? (
                              <div className="inline-flex items-center gap-1.5">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() => setEditingPackId(null)}
                                  disabled={savingPrice}
                                >
                                  Cancel
                                </Button>
                                <Button
                                  size="sm"
                                  onClick={() => void handleSavePrice(p)}
                                  disabled={savingPrice}
                                >
                                  {savingPrice ? "Saving..." : "Save"}
                                </Button>
                              </div>
                            ) : (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => openPriceEditor(p)}
                              >
                                Edit Price
                              </Button>
                            )}
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </CardContent>
        </Card>
      </div>
    </DesktopAdminLayout>
  );
}

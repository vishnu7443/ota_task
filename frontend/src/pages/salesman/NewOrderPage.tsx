import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  Minus,
  Package,
  Plus,
  Search,
  ShoppingBag,
  Store,
} from "lucide-react";
import { MobileSalesLayout } from "@/components/layouts/MobileSalesLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api, type CustomerSummary, type ProductPack } from "@/lib/api";
import { formatInrFromPaisa } from "@/lib/money";

const DRAFT_STORAGE_KEY = "ota_salesman_order_draft_v1";

interface LocalOrderDraft {
  clientOrderId: string;
  customerId: number | null;
  quantities: Record<number, number>;
  notes: string;
}

function createFreshDraft(preselectedCustomerId: number | null): LocalOrderDraft {
  return {
    clientOrderId: crypto.randomUUID(),
    customerId: preselectedCustomerId,
    quantities: {},
    notes: "",
  };
}

export function NewOrderPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const preselectedCustomerId = Number(searchParams.get("customerId")) || null;

  const [draft, setDraft] = useState<LocalOrderDraft>(() => {
    try {
      const saved = localStorage.getItem(DRAFT_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as LocalOrderDraft;
        if (parsed.clientOrderId) {
          return preselectedCustomerId
            ? { ...parsed, customerId: preselectedCustomerId }
            : parsed;
        }
      }
    } catch {
      // Ignore corrupt local draft
    }
    return createFreshDraft(preselectedCustomerId);
  });

  const [step, setStep] = useState<"customer" | "products" | "review">(
    preselectedCustomerId ? "products" : draft.customerId ? "products" : "customer"
  );
  const [customerSearch, setCustomerSearch] = useState("");
  const [cartonHelperForSku, setCartonHelperForSku] = useState<number | null>(null);
  const [cartonsInput, setCartonsInput] = useState("0");
  const [looseInput, setLooseInput] = useState("0");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isNetworkRetryable, setIsNetworkRetryable] = useState(false);

  useEffect(() => {
    localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
  }, [draft]);

  const customersQuery = useQuery({
    queryKey: ["salesman-customers", customerSearch],
    queryFn: () => api.getCustomers(customerSearch || undefined),
  });

  const allCustomersQuery = useQuery({
    queryKey: ["salesman-customers", "all"],
    queryFn: () => api.getCustomers(),
  });

  const selectedCustomer: CustomerSummary | undefined = useMemo(
    () => (allCustomersQuery.data ?? []).find((c) => c.id === draft.customerId),
    [allCustomersQuery.data, draft.customerId]
  );

  const productsQuery = useQuery({
    queryKey: ["salesman-products", draft.customerId],
    queryFn: () => api.getProducts(draft.customerId ?? undefined),
    enabled: draft.customerId !== null,
  });

  const products = productsQuery.data ?? [];

  const cartLines = useMemo(() => {
    return products
      .map((p) => ({
        product: p,
        qty: draft.quantities[p.pack_size_id] ?? 0,
      }))
      .filter((line) => line.qty > 0);
  }, [products, draft.quantities]);

  const totalPackets = cartLines.reduce((acc, l) => acc + l.qty, 0);
  const estimatedTaxablePaisa = cartLines.reduce(
    (acc, l) => acc + l.qty * l.product.selling_price_paisa,
    0
  );
  const estimatedGstPaisa = cartLines.reduce((acc, l) => {
    const lineTaxable = l.qty * l.product.selling_price_paisa;
    return acc + Math.floor((lineTaxable * l.product.gst_rate_bps + 5000) / 10000);
  }, 0);
  const estimatedGrandTotalPaisa = estimatedTaxablePaisa + estimatedGstPaisa;
  const isIntraState = selectedCustomer?.primary_state_code === "33";

  const submitMutation = useMutation({
    mutationFn: () => {
      if (!draft.customerId) {
        throw new Error("Please select a customer.");
      }
      if (cartLines.length === 0) {
        throw new Error("Please add at least one product.");
      }
      return api.submitOrder({
        customer_id: draft.customerId,
        client_order_id: draft.clientOrderId,
        notes: draft.notes.trim() || null,
        items: cartLines.map((l) => ({
          pack_size_id: l.product.pack_size_id,
          ordered_qty_pkts: l.qty,
        })),
      });
    },
    onSuccess: (createdOrder) => {
      localStorage.removeItem(DRAFT_STORAGE_KEY);
      queryClient.invalidateQueries({ queryKey: ["salesman-orders"] });
      navigate(`/salesman/orders/${createdOrder.id}/confirmation`, {
        state: { order: createdOrder, justSubmitted: true },
        replace: true,
      });
    },
    onError: (err) => {
      if (err instanceof ApiClientError) {
        setIsNetworkRetryable(err.status === 0);
        setSubmitError(err.message);
      } else if (err instanceof Error) {
        setIsNetworkRetryable(false);
        setSubmitError(err.message);
      } else {
        setSubmitError("Order submission failed.");
      }
    },
  });

  const setSkuQty = (packSizeId: number, rawQty: number) => {
    const safeQty = Math.max(0, Math.min(1_000_000, Math.floor(rawQty)));
    setDraft((prev) => ({
      ...prev,
      quantities: {
        ...prev.quantities,
        [packSizeId]: safeQty,
      },
    }));
  };

  const openCartonHelper = (p: ProductPack) => {
    const current = draft.quantities[p.pack_size_id] ?? 0;
    const cartons = Math.floor(current / p.packets_per_carton);
    const loose = current % p.packets_per_carton;
    setCartonsInput(String(cartons));
    setLooseInput(String(loose));
    setCartonHelperForSku(p.pack_size_id);
  };

  const applyCartonHelper = (p: ProductPack) => {
    const c = Math.max(0, parseInt(cartonsInput || "0", 10) || 0);
    const l = Math.max(0, parseInt(looseInput || "0", 10) || 0);
    setSkuQty(p.pack_size_id, c * p.packets_per_carton + l);
    setCartonHelperForSku(null);
  };

  return (
    <MobileSalesLayout
      title={
        step === "customer"
          ? "1. Select Customer"
          : step === "products"
          ? "2. Select Products"
          : "3. Order Summary & Cart"
      }
      subtitle={selectedCustomer ? `${selectedCustomer.name} · ${selectedCustomer.primary_state_name}` : "New Factory Order"}
    >
      <div className="space-y-4">
        {/* Stepper pills */}
        <div className="grid grid-cols-3 gap-1.5 rounded-xl bg-secondary p-1 text-xs font-semibold">
          <button
            type="button"
            onClick={() => setStep("customer")}
            className={`rounded-lg py-2 transition-colors ${
              step === "customer" ? "bg-card text-primary shadow-sm" : "text-muted-foreground"
            }`}
          >
            1. Customer
          </button>
          <button
            type="button"
            disabled={!draft.customerId}
            onClick={() => draft.customerId && setStep("products")}
            className={`rounded-lg py-2 transition-colors disabled:opacity-45 ${
              step === "products" ? "bg-card text-primary shadow-sm" : "text-muted-foreground"
            }`}
          >
            2. Products
          </button>
          <button
            type="button"
            disabled={!draft.customerId || cartLines.length === 0}
            onClick={() => draft.customerId && cartLines.length > 0 && setStep("review")}
            className={`rounded-lg py-2 transition-colors disabled:opacity-45 ${
              step === "review" ? "bg-card text-primary shadow-sm" : "text-muted-foreground"
            }`}
          >
            3. Summary ({totalPackets})
          </button>
        </div>

        {/* STEP 1: CUSTOMER SELECTION */}
        {step === "customer" && (
          <div className="space-y-3">
            <div className="relative">
              <Search className="absolute left-3.5 top-3.5 h-4 w-4 text-muted-foreground" />
              <Input
                value={customerSearch}
                onChange={(e) => setCustomerSearch(e.target.value)}
                placeholder="Search customer name, code, or state..."
                className="pl-10"
              />
            </div>

            {customersQuery.isLoading ? (
              <div className="h-24 animate-pulse rounded-xl bg-muted" />
            ) : (
              <div className="space-y-2">
                {(customersQuery.data ?? []).map((cust) => {
                  const active = cust.id === draft.customerId;
                  return (
                    <Card
                      key={cust.id}
                      className={`cursor-pointer transition-all ${
                        active ? "border-primary ring-2 ring-primary/20" : "hover:border-primary/40"
                      }`}
                      onClick={() => {
                        setDraft((prev) => ({ ...prev, customerId: cust.id }));
                        setStep("products");
                      }}
                    >
                      <CardContent className="flex items-center justify-between p-4">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <Store className="h-4 w-4 text-primary" />
                            <span className="font-semibold text-sm">{cust.name}</span>
                            <Badge variant="secondary">{cust.customer_type}</Badge>
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {cust.primary_state_name} ({cust.primary_state_code})
                            {cust.gstin ? ` · GSTIN: ${cust.gstin}` : ""}
                          </div>
                        </div>
                        {active ? (
                          <Check className="h-5 w-5 text-primary" />
                        ) : (
                          <ArrowRight className="h-4 w-4 text-muted-foreground" />
                        )}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* STEP 2: PRODUCT SELECTION & QUANTITY ENTRY */}
        {step === "products" && (
          <div className="space-y-3">
            {selectedCustomer && (
              <div className="flex items-center justify-between rounded-xl border bg-card px-3.5 py-2.5 text-xs">
                <div>
                  <span className="font-semibold">{selectedCustomer.name}</span>{" "}
                  <span className="text-muted-foreground">
                    ({selectedCustomer.primary_state_name})
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setStep("customer")}
                  className="font-semibold text-primary hover:underline"
                >
                  Change
                </button>
              </div>
            )}

            {productsQuery.isLoading ? (
              <div className="h-32 animate-pulse rounded-xl bg-muted" />
            ) : (
              <div className="space-y-3">
                {products.map((prod) => {
                  const qty = draft.quantities[prod.pack_size_id] ?? 0;
                  const shortBy = Math.max(0, qty - prod.available_stock_pkts);

                  return (
                    <Card key={prod.pack_size_id} className={qty > 0 ? "border-primary/60" : ""}>
                      <CardContent className="p-4 space-y-3">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <div className="flex items-center gap-2">
                              <Package className="h-4 w-4 text-primary shrink-0" />
                              <span className="font-bold text-base">{prod.display_name}</span>
                            </div>
                            <div className="mt-0.5 text-xs text-muted-foreground">
                              SKU: <span className="font-mono">{prod.sku_code}</span> ·{" "}
                              {prod.packets_per_carton} pkts/carton · GST {(prod.gst_rate_bps / 100).toFixed(0)}%
                            </div>
                          </div>
                          <div className="text-right">
                            <div className="text-base font-bold tabular-nums text-primary">
                              {formatInrFromPaisa(prod.selling_price_paisa)}
                            </div>
                            <div className="text-[11px] text-muted-foreground">per packet</div>
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <Badge variant={prod.available_stock_pkts > 0 ? "success" : "warning"}>
                            Factory Stock: {prod.available_stock_pkts} pkts
                          </Badge>
                          <button
                            type="button"
                            onClick={() =>
                              cartonHelperForSku === prod.pack_size_id
                                ? setCartonHelperForSku(null)
                                : openCartonHelper(prod)
                            }
                            className="text-xs font-semibold text-primary hover:underline"
                          >
                            {cartonHelperForSku === prod.pack_size_id
                              ? "Hide Carton Calc"
                              : "Enter in Cartons"}
                          </button>
                        </div>

                        {cartonHelperForSku === prod.pack_size_id && (
                          <div className="rounded-lg border bg-secondary/40 p-3 space-y-2">
                            <div className="grid grid-cols-2 gap-2">
                              <div>
                                <label className="text-[11px] font-medium text-muted-foreground">
                                  Cartons (×{prod.packets_per_carton})
                                </label>
                                <Input
                                  type="number"
                                  min={0}
                                  inputMode="numeric"
                                  value={cartonsInput}
                                  onChange={(e) => setCartonsInput(e.target.value)}
                                  className="h-9"
                                />
                              </div>
                              <div>
                                <label className="text-[11px] font-medium text-muted-foreground">
                                  Loose Packets
                                </label>
                                <Input
                                  type="number"
                                  min={0}
                                  inputMode="numeric"
                                  value={looseInput}
                                  onChange={(e) => setLooseInput(e.target.value)}
                                  className="h-9"
                                />
                              </div>
                            </div>
                            <Button
                              type="button"
                              size="sm"
                              className="w-full"
                              onClick={() => applyCartonHelper(prod)}
                            >
                              Apply Quantity
                            </Button>
                          </div>
                        )}

                        <div className="flex items-center gap-2">
                          <Button
                            type="button"
                            variant="outline"
                            size="icon"
                            aria-label={`Decrease ${prod.display_name}`}
                            onClick={() => setSkuQty(prod.pack_size_id, qty - 10)}
                          >
                            <Minus className="h-4 w-4" />
                          </Button>
                          <Input
                            type="number"
                            min={0}
                            inputMode="numeric"
                            aria-label={`Quantity for ${prod.display_name}`}
                            value={qty === 0 ? "" : qty}
                            placeholder="0 packets"
                            onChange={(e) =>
                              setSkuQty(
                                prod.pack_size_id,
                                e.target.value === "" ? 0 : parseInt(e.target.value, 10) || 0
                              )
                            }
                            className="text-center text-base font-bold tabular-nums"
                          />
                          <Button
                            type="button"
                            variant="outline"
                            size="icon"
                            aria-label={`Increase ${prod.display_name}`}
                            onClick={() => setSkuQty(prod.pack_size_id, qty + 10)}
                          >
                            <Plus className="h-4 w-4" />
                          </Button>
                        </div>

                        {/* Quick preset packet chips for sub-minute tap speed */}
                        <div className="flex flex-wrap gap-1.5">
                          {[20, 50, 100, 150].map((preset) => (
                            <button
                              key={preset}
                              type="button"
                              onClick={() => setSkuQty(prod.pack_size_id, preset)}
                              className="rounded-md border bg-secondary/50 px-2.5 py-1 text-xs font-semibold tabular-nums hover:bg-secondary"
                            >
                              {preset} pkts
                            </button>
                          ))}
                        </div>

                        {qty > 0 && (
                          <div className="flex items-center justify-between border-t pt-2.5 text-xs">
                            <span className="text-muted-foreground">Line subtotal (excl. GST)</span>
                            <span className="font-bold tabular-nums text-foreground">
                              {formatInrFromPaisa(qty * prod.selling_price_paisa)}
                            </span>
                          </div>
                        )}

                        {shortBy > 0 && (
                          <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-800">
                            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
                            <span>
                              Requested <strong>{qty}</strong> pkts exceeds current stock (
                              <strong>{prod.available_stock_pkts}</strong> avail). You can still
                              submit; Admin will review stock shortfall ({shortBy} pkts).
                            </span>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}

            {cartLines.length > 0 && (
              <div className="sticky bottom-16 z-20 pt-2">
                <Button
                  type="button"
                  size="lg"
                  className="w-full justify-between shadow-lg"
                  onClick={() => setStep("review")}
                >
                  <span className="flex items-center gap-2">
                    <ShoppingBag className="h-5 w-5" />
                    <span className="tabular-nums">{totalPackets} Packets in Cart</span>
                  </span>
                  <span className="flex items-center gap-1 tabular-nums">
                    {formatInrFromPaisa(estimatedTaxablePaisa)}
                    <ArrowRight className="h-4 w-4" />
                  </span>
                </Button>
              </div>
            )}
          </div>
        )}

        {/* STEP 3: ORDER CART & SUMMARY -> SUBMIT */}
        {step === "review" && selectedCustomer && (
          <div className="space-y-4">
            <Card>
              <CardContent className="p-4 space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Customer &amp; Place of Supply
                  </span>
                  <Badge variant="outline">
                    {isIntraState ? "CGST + SGST (Intra-State)" : "IGST (Inter-State)"}
                  </Badge>
                </div>
                <div className="font-bold text-base">{selectedCustomer.name}</div>
                <div className="text-xs text-muted-foreground">
                  {selectedCustomer.primary_state_name} ({selectedCustomer.primary_state_code})
                  {selectedCustomer.gstin ? ` · GSTIN: ${selectedCustomer.gstin}` : ""}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Order Items ({cartLines.length})
                  </span>
                  <button
                    type="button"
                    onClick={() => setStep("products")}
                    className="text-xs font-semibold text-primary hover:underline"
                  >
                    Edit Items
                  </button>
                </div>

                {cartLines.map(({ product, qty }) => (
                  <div
                    key={product.pack_size_id}
                    className="flex items-center justify-between border-b pb-2.5 last:border-b-0 last:pb-0 text-sm"
                  >
                    <div>
                      <div className="font-semibold">{product.display_name}</div>
                      <div className="text-xs text-muted-foreground tabular-nums">
                        {qty} pkts × {formatInrFromPaisa(product.selling_price_paisa)}
                      </div>
                    </div>
                    <div className="font-bold tabular-nums">
                      {formatInrFromPaisa(qty * product.selling_price_paisa)}
                    </div>
                  </div>
                ))}

                <div className="border-t pt-3 space-y-1.5 text-sm">
                  <div className="flex justify-between text-muted-foreground">
                    <span>Taxable Subtotal</span>
                    <span className="tabular-nums">{formatInrFromPaisa(estimatedTaxablePaisa)}</span>
                  </div>
                  <div className="flex justify-between text-muted-foreground">
                    <span>Est. GST ({isIntraState ? "2.5% CGST + 2.5% SGST" : "5% IGST"})</span>
                    <span className="tabular-nums">{formatInrFromPaisa(estimatedGstPaisa)}</span>
                  </div>
                  <div className="flex justify-between text-base font-bold pt-1 border-t">
                    <span>Estimated Order Total</span>
                    <span className="tabular-nums text-primary">
                      {formatInrFromPaisa(estimatedGrandTotalPaisa)}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <div className="space-y-1.5">
              <label htmlFor="order-notes" className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Delivery / Floor Notes (Optional)
              </label>
              <Input
                id="order-notes"
                value={draft.notes}
                onChange={(e) => setDraft((prev) => ({ ...prev, notes: e.target.value }))}
                placeholder="e.g. Morning dispatch vehicle"
              />
            </div>

            {submitError && (
              <div
                role="alert"
                className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 space-y-1"
              >
                <div className="font-semibold">{submitError}</div>
                {isNetworkRetryable && (
                  <div className="text-xs">
                    Draft preserved safely with idempotency key{" "}
                    <span className="font-mono">{draft.clientOrderId.slice(0, 8)}</span>. Retrying
                    will never create a duplicate order.
                  </div>
                )}
              </div>
            )}

            <div className="grid grid-cols-3 gap-2">
              <Button type="button" variant="outline" size="lg" onClick={() => setStep("products")}>
                <ArrowLeft className="h-4 w-4" />
                Back
              </Button>
              <Button
                type="button"
                variant="default"
                size="lg"
                className="col-span-2"
                disabled={submitMutation.isPending}
                onClick={() => submitMutation.mutate()}
              >
                {submitMutation.isPending
                  ? "Submitting..."
                  : isNetworkRetryable
                  ? "Retry Submit Order"
                  : "Submit Order to Factory"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </MobileSalesLayout>
  );
}

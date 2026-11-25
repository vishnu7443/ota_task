import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  ArrowRight,
  Calculator,
  CheckCircle2,
  History,
  Layers,
  Lock,
  Plus,
  Trash2,
} from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiClientError, api, type BomComponent, type MaterialSummary } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatDateTimeIst, formatOrderDate } from "@/lib/money";
import { compatibleUomsForMaterial, formatDisplayQty } from "@/lib/units";

interface DraftBomLine {
  rowKey: number;
  material_id: string;
  input_role: "COOKING_RAW" | "PACKAGING";
  display_qty: string;
  display_uom: string;
}

export function AdminBomPage() {
  const { user } = useAuth();
  const canEdit = user?.role_code === "FACTORY_ADMIN" || user?.role_code === "PRODUCTION_SUPERVISOR";
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const [selectedPackSizeId, setSelectedPackSizeId] = useState<number>(0);
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);
  const [banner, setBanner] = useState<{ kind: "success" | "error"; msg: string } | null>(null);

  // Calculator state
  const [calcMode, setCalcMode] = useState<"batch" | "target">("batch");
  const [batchScale, setBatchScale] = useState("1.0");
  const [targetPackets, setTargetPackets] = useState("200");

  // New version composer modal
  const [showNewVersion, setShowNewVersion] = useState(false);
  const [newYieldPkts, setNewYieldPkts] = useState("200");
  const [newEffectiveDate, setNewEffectiveDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [newNotes, setNewNotes] = useState("");
  const [activateOnSave, setActivateOnSave] = useState(true);
  const [newLines, setNewLines] = useState<DraftBomLine[]>([]);

  // Quick Add Pack Size modal (e.g. Murukku 500 g)
  const [showAddPack, setShowAddPack] = useState(false);
  const [psProductId, setPsProductId] = useState("");
  const [psSkuCode, setPsSkuCode] = useState("MRK-500G");
  const [psDisplayName, setPsDisplayName] = useState("Murukku 500 g");
  const [psWeightG, setPsWeightG] = useState("500");
  const [psCartonPkts, setPsCartonPkts] = useState("10");

  const catalogQuery = useQuery({
    queryKey: ["production-catalog"],
    queryFn: () => api.getProductionCatalog(),
  });

  const bomsQuery = useQuery({
    queryKey: ["production-boms"],
    queryFn: () => api.getBoms(),
  });

  const materialsQuery = useQuery({
    queryKey: ["inventory-materials"],
    queryFn: () => api.getMaterials(),
  });

  const boms = bomsQuery.data ?? [];
  const catalog = catalogQuery.data;
  const materials = materialsQuery.data ?? [];

  const materialsMap = useMemo(() => {
    const map: Record<number, MaterialSummary> = {};
    materials.forEach((m) => {
      map[m.id] = m;
    });
    return map;
  }, [materials]);

  useEffect(() => {
    if (boms.length > 0 && selectedPackSizeId === 0) {
      setSelectedPackSizeId(boms[0].pack_size_id);
    }
  }, [boms, selectedPackSizeId]);

  const currentBom = useMemo(
    () => boms.find((b) => b.pack_size_id === selectedPackSizeId) ?? boms[0],
    [boms, selectedPackSizeId]
  );

  useEffect(() => {
    if (currentBom) {
      const defVer = currentBom.active_version ?? currentBom.all_versions[0] ?? null;
      setSelectedVersionId(defVer ? defVer.id : null);
    }
  }, [currentBom?.pack_size_id, currentBom?.active_version_id]);

  const viewedVersion = useMemo(() => {
    if (!currentBom) return null;
    return (
      currentBom.all_versions.find((v) => v.id === selectedVersionId) ??
      currentBom.active_version ??
      currentBom.all_versions[0] ??
      null
    );
  }, [currentBom, selectedVersionId]);

  const calcQuery = useQuery({
    queryKey: [
      "bom-calculate",
      currentBom?.pack_size_id,
      calcMode,
      batchScale,
      targetPackets,
      viewedVersion?.id,
    ],
    queryFn: () =>
      api.calculateBom({
        pack_size_id: currentBom!.pack_size_id,
        batch_multiplier: calcMode === "batch" && Number(batchScale) > 0 ? batchScale : null,
        target_output_pkts:
          calcMode === "target" && Number(targetPackets) > 0 ? Number(targetPackets) : null,
        bom_version_id: viewedVersion?.id ?? null,
      }),
    enabled: Boolean(currentBom?.pack_size_id && viewedVersion?.id),
  });

  const openNewVersionModal = () => {
    const src = viewedVersion;
    setNewYieldPkts(String(src?.expected_yield_pkts ?? 200));
    setNewNotes("");
    setActivateOnSave(true);
    if (src && src.components.length > 0) {
      setNewLines(
        src.components.map((c: BomComponent, idx) => ({
          rowKey: idx + 1,
          material_id: String(c.material_id),
          input_role: c.input_role as "COOKING_RAW" | "PACKAGING",
          display_qty: String(Number(c.display_qty)),
          display_uom: c.display_uom,
        }))
      );
    } else if (materials.length > 0) {
      setNewLines([
        {
          rowKey: 1,
          material_id: String(materials[0].id),
          input_role: materials[0].material_category === "RAW_MATERIAL" ? "COOKING_RAW" : "PACKAGING",
          display_qty: "1",
          display_uom: materials[0].display_uom,
        },
      ]);
    }
    setShowNewVersion(true);
  };

  const createVersionMutation = useMutation({
    mutationFn: () =>
      api.createBomVersion({
        pack_size_id: currentBom!.pack_size_id,
        recipe_template_id: viewedVersion?.recipe_template_id ?? catalog?.recipe_templates[0]?.id ?? null,
        expected_yield_pkts: Number(newYieldPkts),
        effective_date: newEffectiveDate || null,
        notes: newNotes.trim() || null,
        activate: activateOnSave,
        components: newLines.map((l) => ({
          material_id: Number(l.material_id),
          input_role: l.input_role,
          display_qty: l.display_qty,
          display_uom: l.display_uom,
        })),
      }),
    onSuccess: (ver) => {
      queryClient.invalidateQueries({ queryKey: ["production-boms"] });
      queryClient.invalidateQueries({ queryKey: ["bom-calculate"] });
      setSelectedVersionId(ver.id);
      setShowNewVersion(false);
      setBanner({
        kind: "success",
        msg: `Created BOM v${ver.version_no} (${ver.status}). Historical versions remain preserved.`,
      });
    },
    onError: (err) => {
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Failed to create BOM version.",
      });
    },
  });

  const activateMutation = useMutation({
    mutationFn: (versionId: number) => api.activateBomVersion(versionId),
    onSuccess: (ver) => {
      queryClient.invalidateQueries({ queryKey: ["production-boms"] });
      queryClient.invalidateQueries({ queryKey: ["bom-calculate"] });
      setSelectedVersionId(ver.id);
      setBanner({
        kind: "success",
        msg: `BOM v${ver.version_no} is now ACTIVE. Previous active version marked SUPERSEDED.`,
      });
    },
    onError: (err) => {
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Activation failed.",
      });
    },
  });

  const addPackSizeMutation = useMutation({
    mutationFn: () =>
      api.createPackSize({
        product_id: Number(psProductId || catalog?.products[0]?.id),
        sku_code: psSkuCode.trim().toUpperCase(),
        display_name: psDisplayName.trim(),
        pack_weight_g: Number(psWeightG),
        packets_per_carton: Number(psCartonPkts),
      }),
    onSuccess: (ps) => {
      queryClient.invalidateQueries({ queryKey: ["production-catalog"] });
      queryClient.invalidateQueries({ queryKey: ["production-boms"] });
      setSelectedPackSizeId(ps.id);
      setShowAddPack(false);
      setBanner({ kind: "success", msg: `Added pack size ${ps.display_name} (${ps.sku_code}). Create its BOM v1 next.` });
    },
    onError: (err) => {
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Could not add pack size.",
      });
    },
  });

  const planRunFromCalcMutation = useMutation({
    mutationFn: () =>
      api.createProductionRun({
        pack_size_id: currentBom!.pack_size_id,
        batch_multiplier: calcQuery.data!.batch_multiplier,
        run_date: new Date().toISOString().slice(0, 10),
        notes: `Planned via BOM Calculator (${calcQuery.data!.expected_output_pkts} pkts)`,
        plan_immediately: true,
      }),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["production-dashboard"] });
      navigate(`/admin/production/runs/${run.id}`);
    },
    onError: (err) => {
      setBanner({
        kind: "error",
        msg: err instanceof ApiClientError ? err.message : "Could not create production plan.",
      });
    },
  });

  const calc = calcQuery.data;

  return (
    <DesktopAdminLayout
      title="Bill of Materials & Recipe Calculator"
      subtitle="Versioned cooking formulas, packaging ratios, and decimal material scaling"
      actions={
        <div className="flex gap-2">
          {canEdit && (
            <>
              <Button variant="outline" onClick={() => {
                setPsProductId(String(catalog?.products[0]?.id ?? ""));
                setShowAddPack(true);
              }}>
                <Plus className="h-4 w-4" />
                Add Pack Size
              </Button>
              {currentBom && (
                <Button onClick={openNewVersionModal}>
                  <Plus className="h-4 w-4" />
                  New BOM Version
                </Button>
              )}
            </>
          )}
        </div>
      }
    >
      <div className="space-y-6">
        {banner && (
          <div
            className={`rounded-lg border px-4 py-3 text-sm font-medium ${
              banner.kind === "success"
                ? "border-emerald-200 bg-emerald-50 text-emerald-900"
                : "border-red-200 bg-red-50 text-red-900"
            }`}
          >
            {banner.msg}
          </div>
        )}

        {/* Pack Size Tabs */}
        <div className="flex flex-wrap gap-2">
          {boms.map((b) => (
            <button
              key={b.pack_size_id}
              type="button"
              onClick={() => setSelectedPackSizeId(b.pack_size_id)}
              className={`rounded-lg border px-4 py-2 text-left transition-colors ${
                currentBom?.pack_size_id === b.pack_size_id
                  ? "border-primary bg-primary/10 text-primary"
                  : "bg-card text-muted-foreground hover:text-foreground"
              }`}
            >
              <div className="text-sm font-bold">{b.display_name}</div>
              <div className="text-[11px] font-mono">
                {b.sku_code} ·{" "}
                {b.active_version ? `Active v${b.active_version.version_no}` : "No Active BOM"}
              </div>
            </button>
          ))}
        </div>

        {/* Modals */}
        {showAddPack && (
          <Card className="border-primary/40">
            <CardHeader>
              <CardTitle className="text-base">Add New Pack Size Variant</CardTitle>
              <CardDescription>
                Supports multi-pack sizing (e.g. Murukku 500 g) sharing an existing product family.
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <div className="space-y-1">
                <label className="text-xs font-semibold">Base Product</label>
                <select
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                  value={psProductId}
                  onChange={(e) => setPsProductId(e.target.value)}
                >
                  {(catalog?.products ?? []).map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.product_code})
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold">SKU Code</label>
                <Input value={psSkuCode} onChange={(e) => setPsSkuCode(e.target.value)} />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold">Display Name</label>
                <Input value={psDisplayName} onChange={(e) => setPsDisplayName(e.target.value)} />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold">Pack Weight (g)</label>
                <Input type="number" value={psWeightG} onChange={(e) => setPsWeightG(e.target.value)} />
              </div>
              <div className="space-y-1">
                <label className="text-xs font-semibold">Packets / Carton</label>
                <Input type="number" value={psCartonPkts} onChange={(e) => setPsCartonPkts(e.target.value)} />
              </div>
              <div className="sm:col-span-2 lg:col-span-5 flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowAddPack(false)}>
                  Cancel
                </Button>
                <Button onClick={() => addPackSizeMutation.mutate()} disabled={addPackSizeMutation.isPending}>
                  {addPackSizeMutation.isPending ? "Saving..." : "Save Pack Size"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {showNewVersion && currentBom && (
          <Card className="border-primary/40">
            <CardHeader>
              <CardTitle className="text-base">
                Create New BOM Version for {currentBom.display_name}
              </CardTitle>
              <CardDescription>
                Historical versions are never edited in place. Saving creates a new immutable version number.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="space-y-1">
                  <label className="text-xs font-semibold">Expected Yield (packets / batch)</label>
                  <Input
                    type="number"
                    min="1"
                    value={newYieldPkts}
                    onChange={(e) => setNewYieldPkts(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold">Effective Date</label>
                  <Input
                    type="date"
                    value={newEffectiveDate}
                    onChange={(e) => setNewEffectiveDate(e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-semibold">Version Notes</label>
                  <Input
                    placeholder="e.g., Adjusted flour ratio for festive batch"
                    value={newNotes}
                    onChange={(e) => setNewNotes(e.target.value)}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    BOM Components (1 Standard Batch)
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const first = materials[0];
                      if (!first) return;
                      setNewLines((prev) => [
                        ...prev,
                        {
                          rowKey: Date.now() + Math.random(),
                          material_id: String(first.id),
                          input_role:
                            first.material_category === "RAW_MATERIAL" ? "COOKING_RAW" : "PACKAGING",
                          display_qty: "1",
                          display_uom: first.display_uom,
                        },
                      ]);
                    }}
                  >
                    <Plus className="h-3.5 w-3.5" /> Add Component
                  </Button>
                </div>
                {newLines.map((line) => {
                  const mat = materialsMap[Number(line.material_id)];
                  const uoms = mat ? compatibleUomsForMaterial(mat.unit_dimension) : ["kg", "g", "L", "ml", "piece"];
                  return (
                    <div key={line.rowKey} className="grid gap-2 sm:grid-cols-12 items-center">
                      <select
                        className="sm:col-span-5 flex h-9 rounded-md border border-input bg-background px-2 text-sm"
                        value={line.material_id}
                        onChange={(e) => {
                          const m = materialsMap[Number(e.target.value)];
                          setNewLines((prev) =>
                            prev.map((p) =>
                              p.rowKey === line.rowKey
                                ? {
                                    ...p,
                                    material_id: e.target.value,
                                    input_role:
                                      m?.material_category === "RAW_MATERIAL"
                                        ? "COOKING_RAW"
                                        : "PACKAGING",
                                    display_uom: m?.display_uom ?? p.display_uom,
                                  }
                                : p
                            )
                          );
                        }}
                      >
                        {materials.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name} ({m.code}) — {m.material_category === "RAW_MATERIAL" ? "Raw" : "Packaging"}
                          </option>
                        ))}
                      </select>
                      <Input
                        type="number"
                        step="0.001"
                        className="sm:col-span-3 h-9"
                        value={line.display_qty}
                        onChange={(e) =>
                          setNewLines((prev) =>
                            prev.map((p) =>
                              p.rowKey === line.rowKey ? { ...p, display_qty: e.target.value } : p
                            )
                          )
                        }
                      />
                      <select
                        className="sm:col-span-2 flex h-9 rounded-md border border-input bg-background px-2 text-sm"
                        value={line.display_uom}
                        onChange={(e) =>
                          setNewLines((prev) =>
                            prev.map((p) =>
                              p.rowKey === line.rowKey ? { ...p, display_uom: e.target.value } : p
                            )
                          )
                        }
                      >
                        {uoms.map((u) => (
                          <option key={u} value={u}>
                            {u}
                          </option>
                        ))}
                      </select>
                      <div className="sm:col-span-2 flex justify-end">
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={newLines.length <= 1}
                          onClick={() =>
                            setNewLines((prev) => prev.filter((p) => p.rowKey !== line.rowKey))
                          }
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t">
                <label className="flex items-center gap-2 text-xs font-medium cursor-pointer">
                  <input
                    type="checkbox"
                    checked={activateOnSave}
                    onChange={(e) => setActivateOnSave(e.target.checked)}
                    className="h-4 w-4"
                  />
                  Activate this BOM version immediately (superseding current active)
                </label>
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => setShowNewVersion(false)}>
                    Cancel
                  </Button>
                  <Button
                    onClick={() => createVersionMutation.mutate()}
                    disabled={createVersionMutation.isPending}
                  >
                    {createVersionMutation.isPending ? "Saving..." : "Save New BOM Version"}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {currentBom && (
          <div className="grid gap-6 lg:grid-cols-12">
            {/* Version History Column */}
            <Card className="lg:col-span-4">
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <History className="h-4 w-4 text-primary" />
                  BOM Versions ({currentBom.all_versions.length})
                </CardTitle>
                <CardDescription>
                  Click a version to inspect or activate. Used versions are permanently locked.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2.5">
                {currentBom.all_versions.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-4 text-center">
                    No BOM versions created yet for {currentBom.display_name}.
                  </p>
                ) : (
                  currentBom.all_versions.map((v) => (
                    <div
                      key={v.id}
                      onClick={() => setSelectedVersionId(v.id)}
                      className={`rounded-lg border p-3 cursor-pointer transition-colors ${
                        viewedVersion?.id === v.id
                          ? "border-primary bg-primary/5"
                          : "hover:bg-secondary/40"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-sm">Version v{v.version_no}</span>
                          {v.is_locked && <Lock className="h-3 w-3 text-muted-foreground" />}
                        </div>
                        <StatusBadge status={v.status} />
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        Expected Yield: <strong>{v.expected_yield_pkts} pkts</strong> · Runs:{" "}
                        <strong>{v.run_count}</strong>
                      </div>
                      <div className="mt-0.5 text-[11px] text-muted-foreground">
                        Effective: {v.effective_date ? formatOrderDate(v.effective_date) : "—"} · By{" "}
                        {v.created_by_name}
                      </div>
                      {v.notes && <p className="mt-1 text-xs italic text-muted-foreground">{v.notes}</p>}
                      {canEdit && v.status !== "ACTIVE" && (
                        <div className="mt-2 pt-2 border-t flex justify-end">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(e) => {
                              e.stopPropagation();
                              activateMutation.mutate(v.id);
                            }}
                            disabled={activateMutation.isPending}
                          >
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            Activate v{v.version_no}
                          </Button>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            {/* Active Recipe + BOM Calculator */}
            <div className="lg:col-span-8 space-y-6">
              {viewedVersion && (
                <Card>
                  <CardHeader>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <CardTitle className="text-base flex items-center gap-2">
                          <Layers className="h-4 w-4 text-primary" />
                          {currentBom.display_name} — Recipe v{viewedVersion.version_no}
                        </CardTitle>
                        <CardDescription>
                          1 Standard Batch = {viewedVersion.expected_yield_pkts} expected packets ·{" "}
                          {viewedVersion.activated_at
                            ? `Activated ${formatDateTimeIst(viewedVersion.activated_at)} by ${viewedVersion.activated_by_name}`
                            : "Draft / Inactive"}
                        </CardDescription>
                      </div>
                      <StatusBadge status={viewedVersion.status} />
                    </div>
                  </CardHeader>
                  <CardContent className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                          <th className="py-2 pr-3">Material</th>
                          <th className="py-2 pr-3">Role</th>
                          <th className="py-2 pr-3 text-right">Standard Qty / Batch</th>
                          <th className="py-2 text-right">Canonical Base Qty</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {viewedVersion.components.map((c) => (
                          <tr key={c.id}>
                            <td className="py-2.5 pr-3">
                              <div className="font-medium">{c.material_name}</div>
                              <div className="text-xs font-mono text-muted-foreground">{c.material_code}</div>
                            </td>
                            <td className="py-2.5 pr-3">
                              <Badge variant={c.input_role === "COOKING_RAW" ? "secondary" : "outline"}>
                                {c.input_role === "COOKING_RAW" ? "Raw Material" : "Packaging"}
                              </Badge>
                            </td>
                            <td className="py-2.5 pr-3 text-right font-semibold tabular-nums">
                              {Number(c.display_qty)} {c.display_uom}
                            </td>
                            <td className="py-2.5 text-right font-mono text-xs text-muted-foreground tabular-nums">
                              {Number(c.std_qty_base).toLocaleString("en-IN")} {c.base_uom}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </CardContent>
                </Card>
              )}

              {/* BOM Calculator */}
              {viewedVersion && (
                <Card>
                  <CardHeader>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <CardTitle className="text-base flex items-center gap-2">
                          <Calculator className="h-4 w-4 text-primary" />
                          BOM Requirement &amp; Availability Calculator
                        </CardTitle>
                        <CardDescription>
                          Exact decimal scaling with ceiling rounding for indivisible packaging units &amp; live warehouse stock
                        </CardDescription>
                      </div>
                      {canEdit && calc && (
                        <Button
                          size="sm"
                          onClick={() => planRunFromCalcMutation.mutate()}
                          disabled={planRunFromCalcMutation.isPending}
                        >
                          Plan Production Run
                          <ArrowRight className="h-3.5 w-3.5" />
                        </Button>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid gap-3 sm:grid-cols-3 items-end">
                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-muted-foreground">Scale By</label>
                        <select
                          className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                          value={calcMode}
                          onChange={(e) => setCalcMode(e.target.value as "batch" | "target")}
                        >
                          <option value="batch">Batch Multiplier</option>
                          <option value="target">Target Output Packets</option>
                        </select>
                      </div>
                      {calcMode === "batch" ? (
                        <div className="space-y-1">
                          <label className="text-xs font-semibold text-muted-foreground">Batch Scale (1 = standard)</label>
                          <Input
                            type="number"
                            step="0.25"
                            min="0.1"
                            value={batchScale}
                            onChange={(e) => setBatchScale(e.target.value)}
                          />
                        </div>
                      ) : (
                        <div className="space-y-1">
                          <label className="text-xs font-semibold text-muted-foreground">Target Packets</label>
                          <Input
                            type="number"
                            min="1"
                            value={targetPackets}
                            onChange={(e) => setTargetPackets(e.target.value)}
                          />
                        </div>
                      )}
                      {calc && (
                        <div className="rounded-lg border bg-secondary/40 px-3 py-2 text-xs">
                          <div>
                            Batch Scale: <strong>{Number(calc.batch_multiplier)}×</strong>
                          </div>
                          <div>
                            Expected Output: <strong>{calc.expected_output_pkts} packets</strong>
                          </div>
                        </div>
                      )}
                    </div>

                    {calc && (
                      <>
                        {calc.has_shortages ? (
                          <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4 shrink-0" />
                            <span>
                              <strong>Material Shortage Detected:</strong> {calc.shortage_summary}
                            </span>
                          </div>
                        ) : (
                          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900 flex items-center gap-2">
                            <CheckCircle2 className="h-4 w-4 shrink-0" />
                            <span>All required raw &amp; packaging materials are available in stock.</span>
                          </div>
                        )}

                        <div className="overflow-x-auto">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="border-b text-left text-xs uppercase tracking-wider text-muted-foreground">
                                <th className="py-2 pr-3">Material</th>
                                <th className="py-2 pr-3 text-right">Required Qty</th>
                                <th className="py-2 pr-3 text-right">Available</th>
                                <th className="py-2 pr-3 text-right">Reserved</th>
                                <th className="py-2 text-right">Additional Needed</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y">
                              {calc.requirements.map((r) => (
                                <tr key={r.material_id} className={r.is_shortage ? "bg-red-50/40" : ""}>
                                  <td className="py-2.5 pr-3">
                                    <div className="font-medium">{r.material_name}</div>
                                    {r.was_rounded_up && r.rounding_note && (
                                      <div className="text-[11px] text-amber-700">{r.rounding_note}</div>
                                    )}
                                  </td>
                                  <td className="py-2.5 pr-3 text-right font-semibold tabular-nums">
                                    {formatDisplayQty(r.standard_qty_base, r.display_uom, r.display_factor)}
                                  </td>
                                  <td className="py-2.5 pr-3 text-right tabular-nums text-emerald-700">
                                    {formatDisplayQty(r.available_qty_base, r.display_uom, r.display_factor)}
                                  </td>
                                  <td className="py-2.5 pr-3 text-right tabular-nums text-xs text-muted-foreground">
                                    {formatDisplayQty(r.reserved_qty_base, r.display_uom, r.display_factor)}
                                  </td>
                                  <td className="py-2.5 text-right tabular-nums">
                                    {r.is_shortage ? (
                                      <Badge variant="destructive">
                                        Short {formatDisplayQty(r.additional_required_base, r.display_uom, r.display_factor)}
                                      </Badge>
                                    ) : (
                                      <span className="text-xs text-muted-foreground">0</span>
                                    )}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        )}
      </div>
    </DesktopAdminLayout>
  );
}

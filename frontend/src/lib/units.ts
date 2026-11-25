export function toNumber(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === "") return 0;
  const n = Number(val);
  return Number.isNaN(n) ? 0 : n;
}

export function formatNumber(val: number, maxDecimals = 3): string {
  return new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: maxDecimals,
  }).format(val);
}

export function formatDisplayQty(
  baseQty: string | number,
  displayUom: string,
  displayFactor: string | number
): string {
  const base = toNumber(baseQty);
  const factor = toNumber(displayFactor) || 1;
  const converted = base / factor;
  const decimals = Math.abs(converted % 1) < 1e-6 ? 0 : 2;
  return `${formatNumber(converted, decimals)} ${displayUom}`;
}

export function formatBaseQty(baseQty: string | number, baseUom: string): string {
  const base = toNumber(baseQty);
  const decimals = Math.abs(base % 1) < 1e-6 ? 0 : 3;
  return `${formatNumber(base, decimals)} ${baseUom}`;
}

export function formatQtyPair(
  baseQty: string | number,
  displayUom: string,
  displayFactor: string | number,
  baseUom: string
): string {
  const disp = formatDisplayQty(baseQty, displayUom, displayFactor);
  if (displayUom === baseUom) return disp;
  return `${disp} (${formatBaseQty(baseQty, baseUom)})`;
}

export function compatibleUomsForMaterial(dimension: string): string[] {
  if (dimension === "MASS") return ["kg", "g"];
  if (dimension === "VOLUME") return ["L", "ml"];
  return ["piece"];
}

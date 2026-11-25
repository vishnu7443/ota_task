import { Badge } from "@/components/ui/badge";

const STATUS_VARIANTS: Record<string, { label: string; variant: "default" | "secondary" | "warning" | "destructive" | "success" | "outline" }> = {
  DRAFT: { label: "Draft", variant: "secondary" },
  SUBMITTED: { label: "Submitted", variant: "default" },
  UNDER_REVIEW: { label: "Under Review", variant: "warning" },
  CORRECTION_REQUESTED: { label: "Correction Requested", variant: "warning" },
  APPROVED: { label: "Approved", variant: "success" },
  REJECTED: { label: "Rejected", variant: "destructive" },
  INVOICED: { label: "Invoiced", variant: "success" },
  PARTIALLY_DISPATCHED: { label: "Partial Dispatch", variant: "warning" },
  DISPATCHED: { label: "Dispatched", variant: "success" },
  CANCELLED: { label: "Cancelled", variant: "destructive" },
};

export function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_VARIANTS[status] ?? { label: status, variant: "outline" as const };
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}

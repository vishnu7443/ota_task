import { Badge } from "@/components/ui/badge";

const STATUS_VARIANTS: Record<string, { label: string; variant: "default" | "secondary" | "warning" | "destructive" | "success" | "outline" }> = {
  DRAFT: { label: "Draft", variant: "secondary" },
  PLANNED: { label: "Planned", variant: "default" },
  IN_PROGRESS: { label: "In Progress", variant: "warning" },
  COMPLETED: { label: "Completed", variant: "default" },
  ACTIVE: { label: "Active", variant: "success" },
  SUPERSEDED: { label: "Superseded", variant: "outline" },
  OPEN: { label: "Open Alert", variant: "warning" },
  ACKNOWLEDGED: { label: "Acknowledged", variant: "secondary" },
  SUBMITTED: { label: "Submitted", variant: "default" },
  PENDING_APPROVAL: { label: "Pending Approval", variant: "warning" },
  UNDER_REVIEW: { label: "Under Review", variant: "warning" },
  CORRECTION_REQUESTED: { label: "Correction Requested", variant: "warning" },
  VERIFIED: { label: "Verified", variant: "default" },
  APPROVED: { label: "Approved", variant: "success" },
  PARTIALLY_RECEIVED: { label: "Partially Received", variant: "warning" },
  RECEIVED: { label: "Received", variant: "success" },
  POSTED: { label: "Posted", variant: "success" },
  CLOSED: { label: "Closed", variant: "outline" },
  REJECTED: { label: "Rejected", variant: "destructive" },
  INVOICED: { label: "Invoiced", variant: "success" },
  PARTIALLY_DISPATCHED: { label: "Partial Dispatch", variant: "warning" },
  DISPATCHED: { label: "Dispatched", variant: "success" },
  CANCELLED: { label: "Cancelled", variant: "destructive" },
  ISSUED: { label: "Issued", variant: "success" },
  CANCELLED_BY_CN: { label: "Cancelled by CN", variant: "destructive" },
  UNPAID: { label: "Unpaid", variant: "warning" },
  PARTIALLY_PAID: { label: "Partially Paid", variant: "default" },
  PAID: { label: "Paid", variant: "success" },
  CREDITED: { label: "Credited", variant: "outline" },
  PENDING: { label: "Pending", variant: "secondary" },
  PARTIAL: { label: "Partial", variant: "warning" },
  CREATED: { label: "Created", variant: "secondary" },
  READY_FOR_DISPATCH: { label: "Ready for Dispatch", variant: "default" },
  IN_TRANSIT: { label: "In Transit", variant: "warning" },
  DELIVERED: { label: "Delivered", variant: "success" },
  DELIVERY_EXCEPTION: { label: "Delivery Exception", variant: "destructive" },
  INTRA_STATE: { label: "Intra-State (CGST+SGST)", variant: "secondary" },
  INTER_STATE: { label: "Inter-State (IGST)", variant: "default" },
};

export function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_VARIANTS[status] ?? { label: status, variant: "outline" as const };
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
}

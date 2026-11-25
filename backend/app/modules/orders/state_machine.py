"""Explicit Sales Order lifecycle state machine for Phase 5."""

from app.core.exceptions import ConflictError


class OrderStatus:
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    CORRECTION_REQUESTED = "CORRECTION_REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INVOICED = "INVOICED"
    PARTIALLY_DISPATCHED = "PARTIALLY_DISPATCHED"
    DISPATCHED = "DISPATCHED"
    CANCELLED = "CANCELLED"


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.DRAFT: {OrderStatus.SUBMITTED, OrderStatus.CANCELLED},
    OrderStatus.SUBMITTED: {
        OrderStatus.UNDER_REVIEW,
        OrderStatus.CORRECTION_REQUESTED,
        OrderStatus.APPROVED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.UNDER_REVIEW: {
        OrderStatus.CORRECTION_REQUESTED,
        OrderStatus.APPROVED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.CORRECTION_REQUESTED: {
        OrderStatus.SUBMITTED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.APPROVED: {
        # Billing / dispatch belong to Phase 6; in Phase 5 only pre-invoice cancellation is permitted.
        OrderStatus.CANCELLED,
    },
    OrderStatus.REJECTED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.INVOICED: set(),
    OrderStatus.PARTIALLY_DISPATCHED: set(),
    OrderStatus.DISPATCHED: set(),
}

ADMIN_EDITABLE_STATUSES: set[str] = {OrderStatus.SUBMITTED, OrderStatus.UNDER_REVIEW}
SALESMAN_EDITABLE_STATUSES: set[str] = {OrderStatus.CORRECTION_REQUESTED}
SALESMAN_CANCELLABLE_STATUSES: set[str] = {OrderStatus.SUBMITTED, OrderStatus.CORRECTION_REQUESTED}
PENDING_VERIFICATION_STATUSES: list[str] = [
    OrderStatus.SUBMITTED,
    OrderStatus.UNDER_REVIEW,
    OrderStatus.CORRECTION_REQUESTED,
]


def assert_transition_allowed(
    current_status: str, target_status: str, *, order_number: str
) -> None:
    """Enforce explicit state transitions and block repeats, reversals, or post-terminal edits."""
    if current_status == target_status:
        raise ConflictError(
            f"Order {order_number} is already in '{current_status}' status; repeated transition is not permitted.",
            error_code="INVALID_STATE_TRANSITION",
            details={"current_status": current_status, "target_status": target_status},
        )
    allowed = ALLOWED_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise ConflictError(
            f"Order {order_number} cannot transition from '{current_status}' to '{target_status}'.",
            error_code="INVALID_STATE_TRANSITION",
            details={
                "current_status": current_status,
                "target_status": target_status,
                "allowed_targets": sorted(allowed),
            },
        )

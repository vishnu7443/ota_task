"""Phase 9 Finance Service — Payments, Invoice Allocation Engine, Refunds, AR, Ageing & Profitability."""

import math
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from app.modules.audit.service import record_audit_log
from app.modules.billing import repository as billing_repo
from app.modules.billing.gst_engine import get_indian_financial_year
from app.modules.billing.models import (
    CreditNote,
    CreditNoteItem,
    Dispatch,
    DispatchItem,
    Invoice,
)
from app.modules.costing.models import ProductionCostSummary
from app.modules.finance import repository as finance_repo
from app.modules.finance.models import (
    CustomerReceivable,
    Payment,
    PaymentAllocation,
    PaymentRefund,
)
from app.modules.finance.pdf_generator import render_payment_receipt_pdf
from app.modules.finance.schemas import (
    AgeingCustomerRow,
    AgeingInvoiceRow,
    AgeingReportOut,
    AllocatePaymentRequest,
    CostingSummaryCardRow,
    CustomerArSummaryRow,
    CustomerProfitabilityRow,
    CustomerStatementEntry,
    CustomerStatementOut,
    DateProfitabilityRow,
    FinanceDashboardOut,
    OpenInvoiceForAllocationOut,
    OrderProfitabilityRow,
    PaginatedCustomerArOut,
    PaginatedPaymentsOut,
    PaymentAllocationOut,
    PaymentOut,
    PaymentRefundOut,
    PaymentTrendRow,
    ProductProfitabilityRow,
    ProfitabilityReportOut,
    RecordPaymentRequest,
    RefundPaymentRequest,
    ReverseAllocationRequest,
    ReversePaymentRequest,
    SalesmanCustomerArOut,
)
from app.modules.iam.models import CompanyProfile, User
from app.modules.iam.schemas import CurrentActor
from app.modules.inventory.models import CostLot, CostLotConsumption, InventoryMovement
from app.modules.orders.models import SalesOrder
from app.modules.production.models import ProductionRun
from app.modules.sales.models import Customer, PackSize

IST = ZoneInfo("Asia/Kolkata")
_FINANCE_OPERATOR_ROLES = {"FACTORY_ADMIN"}
_FINANCE_VIEWER_ROLES = {"FACTORY_ADMIN", "ACCOUNTANT_AUDITOR", "OWNER"}


def _require_finance_operator(actor: CurrentActor, action: str) -> None:
    if actor.role_code not in _FINANCE_OPERATOR_ROLES:
        raise AuthorizationError(f"Only Factory Admin is permitted to {action}.")


def _require_finance_viewer(actor: CurrentActor, action: str) -> None:
    if actor.role_code not in _FINANCE_VIEWER_ROLES:
        raise AuthorizationError(f"Your role is not permitted to {action}.")


def _get_company(db: Session) -> CompanyProfile:
    cp = db.execute(select(CompanyProfile).limit(1)).scalar_one_or_none()
    if cp is None:
        raise DomainValidationError("Company profile is not configured.")
    return cp


def _users_map(db: Session, ids: set[int]) -> dict[int, User]:
    clean = {i for i in ids if i is not None}
    if not clean:
        return {}
    return {u.id: u for u in db.execute(select(User).where(User.id.in_(clean))).scalars().all()}


def _customers_map(db: Session, ids: set[int]) -> dict[int, Customer]:
    if not ids:
        return {}
    return {c.id: c for c in db.execute(select(Customer).where(Customer.id.in_(ids))).scalars().all()}


def _invoices_map(db: Session, ids: set[int]) -> dict[int, Invoice]:
    if not ids:
        return {}
    return {i.id: i for i in db.execute(select(Invoice).where(Invoice.id.in_(ids))).scalars().all()}


def derive_invoice_payment_status(inv: Invoice) -> str:
    """Strictly derive invoice payment_status from persisted credits, active payments, and doc_status."""
    grand = int(inv.grand_total_paisa)
    cred = int(inv.credited_paisa)
    paid = int(inv.paid_paisa)
    if inv.doc_status == "CANCELLED_BY_CN" or cred >= grand:
        return "CREDITED"
    if paid <= 0:
        return "UNPAID"
    if paid + cred >= grand:
        return "PAID"
    return "PARTIALLY_PAID"


def derive_payment_status(pmt: Payment) -> str:
    """Strictly derive Payment status from allocated & refunded paisa balances."""
    if pmt.status == "REVERSED":
        return "REVERSED"
    amt = int(pmt.amount_paisa)
    alloc = int(pmt.allocated_paisa)
    ref = int(pmt.refunded_paisa)
    rem = amt - alloc - ref
    if ref >= amt and alloc == 0:
        return "REFUNDED"
    if alloc > 0:
        return "ALLOCATED" if rem == 0 else "PARTIALLY_ALLOCATED"
    if ref > 0:
        return "PARTIALLY_REFUNDED"
    return "RECORDED"


def _sync_invoice_and_ar_settlement(
    db: Session, *, invoice: Invoice, receivable: CustomerReceivable
) -> None:
    """Recompute authoritative invoice paid_paisa, AR paid/credited, and derived payment_status."""
    active_paid = finance_repo.sum_active_allocations_for_invoice(db, invoice.id)
    invoice.paid_paisa = active_paid
    receivable.credited_paisa = int(invoice.credited_paisa)
    receivable.paid_paisa = active_paid
    invoice.payment_status = derive_invoice_payment_status(invoice)
    invoice.version += 1


def _hydrate_payment(
    db: Session,
    pmt: Payment,
    *,
    cust_map: dict[int, Customer],
    inv_map: dict[int, Invoice],
    users: dict[int, User],
) -> PaymentOut:
    cust = cust_map[pmt.customer_id]
    alloc_outs = []
    for a in pmt.allocations:
        inv = inv_map[a.invoice_id]
        alloc_outs.append(
            PaymentAllocationOut(
                id=a.id,
                payment_id=pmt.id,
                payment_number=pmt.payment_number,
                invoice_id=inv.id,
                invoice_number=inv.invoice_number or inv.draft_ref,
                invoice_date=inv.invoice_date,
                due_date=inv.due_date,
                invoice_grand_total_paisa=int(inv.grand_total_paisa),
                invoice_outstanding_paisa=int(inv.outstanding_paisa),
                allocated_paisa=int(a.allocated_paisa),
                status=a.status,
                allocated_by_name=users[a.allocated_by].full_name if a.allocated_by in users else "System",
                allocated_at=a.allocated_at,
                reversed_by_name=(
                    users[a.reversed_by].full_name if a.reversed_by and a.reversed_by in users else None
                ),
                reversed_at=a.reversed_at,
                reversal_reason=a.reversal_reason,
                notes=a.notes,
            )
        )

    ref_outs = [
        PaymentRefundOut(
            id=r.id,
            refund_number=r.refund_number,
            financial_year=r.financial_year,
            payment_id=r.payment_id,
            customer_id=r.customer_id,
            refund_date=r.refund_date,
            amount_paisa=int(r.amount_paisa),
            refund_mode=r.refund_mode,
            reference_no=r.reference_no,
            reason=r.reason,
            status=r.status,
            refunded_by_name=users[r.refunded_by].full_name if r.refunded_by in users else "System",
            refunded_at=r.refunded_at,
        )
        for r in pmt.refunds
    ]

    return PaymentOut(
        id=pmt.id,
        payment_number=pmt.payment_number,
        financial_year=pmt.financial_year,
        customer_id=pmt.customer_id,
        customer_code=cust.code,
        customer_name=cust.name,
        payment_date=pmt.payment_date,
        amount_paisa=int(pmt.amount_paisa),
        allocated_paisa=int(pmt.allocated_paisa),
        refunded_paisa=int(pmt.refunded_paisa),
        unallocated_paisa=int(pmt.unallocated_paisa),
        payment_mode=pmt.payment_mode,
        reference_no=pmt.reference_no,
        remarks=pmt.remarks,
        is_advance=pmt.is_advance,
        idempotency_key=pmt.idempotency_key,
        status=pmt.status,
        reversal_reason=pmt.reversal_reason,
        reversed_by_name=(
            users[pmt.reversed_by].full_name if pmt.reversed_by and pmt.reversed_by in users else None
        ),
        reversed_at=pmt.reversed_at,
        recorded_by_name=users[pmt.recorded_by].full_name if pmt.recorded_by in users else "System",
        recorded_at=pmt.recorded_at,
        version=pmt.version,
        allocations=alloc_outs,
        refunds=ref_outs,
    )


def _hydrate_payment_list(db: Session, rows: list[Payment]) -> list[PaymentOut]:
    if not rows:
        return []
    cids = {p.customer_id for p in rows}
    iids = {a.invoice_id for p in rows for a in p.allocations}
    uids: set[int] = set()
    for p in rows:
        uids.add(p.recorded_by)
        if p.reversed_by:
            uids.add(p.reversed_by)
        for a in p.allocations:
            uids.add(a.allocated_by)
            if a.reversed_by:
                uids.add(a.reversed_by)
        for r in p.refunds:
            uids.add(r.refunded_by)
    return [
        _hydrate_payment(
            db,
            p,
            cust_map=_customers_map(db, cids),
            inv_map=_invoices_map(db, iids),
            users=_users_map(db, uids),
        )
        for p in rows
    ]


def _apply_allocations_internal(
    db: Session,
    *,
    pmt: Payment,
    lines: list[tuple[int, int]],
    actor: CurrentActor,
    notes: str | None = None,
) -> None:
    """Validate and apply allocation lines deterministically inside an active transaction."""
    if pmt.status in {"REVERSED", "REFUNDED"}:
        raise ConflictError(
            f"Payment {pmt.payment_number} is in status '{pmt.status}' and cannot be allocated.",
            error_code="PAYMENT_NOT_ALLOCATABLE",
        )

    seen_invoices: set[int] = set()
    total_requested = 0
    for inv_id, alloc_amt in lines:
        if inv_id in seen_invoices:
            raise DomainValidationError(
                f"Duplicate invoice {inv_id} in a single allocation submission."
            )
        seen_invoices.add(inv_id)
        if alloc_amt <= 0:
            raise DomainValidationError("Allocated amount must be strictly greater than zero.")
        total_requested += alloc_amt

    avail_pmt = int(pmt.amount_paisa) - int(pmt.allocated_paisa) - int(pmt.refunded_paisa)
    if total_requested > avail_pmt:
        raise ConflictError(
            f"Requested allocation ({total_requested} paise) exceeds available unallocated payment balance ({avail_pmt} paise).",
            error_code="OVER_ALLOCATION",
        )

    inv_map, ar_map = finance_repo.lock_invoices_for_settlement(db, list(seen_invoices))
    for inv_id, alloc_amt in lines:
        inv = inv_map.get(inv_id)
        if inv is None:
            raise NotFoundError(f"Invoice {inv_id} was not found.")
        if inv.customer_id != pmt.customer_id:
            raise DomainValidationError(
                f"Invoice {inv.invoice_number or inv.draft_ref} belongs to another customer."
            )
        if inv.doc_status != "ISSUED":
            raise ConflictError(
                f"Invoice {inv.invoice_number or inv.draft_ref} is in status '{inv.doc_status}' and cannot receive payments.",
                error_code="INVALID_STATE_TRANSITION",
            )
        ar = ar_map[inv.id]
        rem_inv = int(ar.original_paisa) - int(ar.credited_paisa) - int(ar.paid_paisa)
        if alloc_amt > rem_inv:
            raise ConflictError(
                f"Allocation ({alloc_amt} paise) exceeds remaining outstanding balance ({rem_inv} paise) on {inv.invoice_number}.",
                error_code="EXCEEDS_INVOICE_OUTSTANDING",
            )

        db.add(
            PaymentAllocation(
                payment_id=pmt.id,
                invoice_id=inv.id,
                allocated_paisa=alloc_amt,
                status="ACTIVE",
                allocated_by=actor.user_id,
                notes=notes.strip() if notes else None,
            )
        )
        db.flush()
        _sync_invoice_and_ar_settlement(db, invoice=inv, receivable=ar)

    pmt.allocated_paisa = finance_repo.sum_active_allocations_for_payment(db, pmt.id)
    pmt.status = derive_payment_status(pmt)
    pmt.version += 1
    db.flush()

    record_audit_log(
        db,
        actor_user_id=actor.user_id,
        actor_role=actor.role_code,
        action="PAYMENT_ALLOCATED",
        entity_schema="finance",
        entity_table="payments",
        entity_id=pmt.id,
        after_state={
            "payment_number": pmt.payment_number,
            "customer_id": pmt.customer_id,
            "allocated_paisa": int(pmt.allocated_paisa),
            "unallocated_paisa": int(pmt.amount_paisa) - int(pmt.allocated_paisa) - int(pmt.refunded_paisa),
            "status": pmt.status,
            "allocations": [
                {"invoice_id": iid, "invoice_number": inv_map[iid].invoice_number, "allocated_paisa": amt}
                for iid, amt in lines
            ],
        },
        reason=notes or f"Allocated {pmt.payment_number} to invoices",
    )


def record_customer_payment(
    db: Session, actor: CurrentActor, payload: RecordPaymentRequest
) -> PaymentOut:
    """Record a customer receipt (direct invoice settlement, multi-invoice split, or advance)."""
    _require_finance_operator(actor, "record customer payments")

    # 1. Idempotency check
    existing_idem = finance_repo.get_payment_by_idempotency(db, payload.client_payment_id)
    if existing_idem is not None:
        if (
            existing_idem.customer_id != payload.customer_id
            or int(existing_idem.amount_paisa) != payload.amount_paisa
            or existing_idem.payment_mode != payload.payment_mode
        ):
            raise ConflictError(
                "Duplicate payment idempotency key used with mismatched payment details.",
                error_code="IDEMPOTENCY_CONFLICT",
            )
        return _hydrate_payment_list(db, [existing_idem])[0]

    pmt_date = payload.payment_date or datetime.now(IST).date()
    ref_clean = payload.reference_no.strip() if payload.reference_no and payload.reference_no.strip() else None

    try:
        cust = db.execute(select(Customer).where(Customer.id == payload.customer_id)).scalar_one_or_none()
        if cust is None or not cust.is_active:
            raise NotFoundError(f"Active customer {payload.customer_id} was not found.")

        # Duplicate transaction guard when UTR/cheque reference matches active payment
        if ref_clean is not None:
            dup_ref = finance_repo.find_duplicate_payment_ref(
                db,
                customer_id=cust.id,
                payment_date=pmt_date,
                amount_paisa=payload.amount_paisa,
                reference_no=ref_clean,
            )
            if dup_ref is not None:
                raise ConflictError(
                    f"Duplicate transaction detected: payment {dup_ref.payment_number} already recorded with same customer, date, amount, and reference '{ref_clean}'.",
                    error_code="DUPLICATE_PAYMENT_REFERENCE",
                )

        fy = get_indian_financial_year(pmt_date)
        pmt_no = billing_repo.allocate_fiscal_sequence(
            db, doc_type="PAYMENT", financial_year=fy, prefix="PMT"
        )
        pmt = Payment(
            payment_number=pmt_no,
            financial_year=fy,
            customer_id=cust.id,
            payment_date=pmt_date,
            amount_paisa=payload.amount_paisa,
            allocated_paisa=0,
            refunded_paisa=0,
            payment_mode=payload.payment_mode,
            reference_no=ref_clean,
            remarks=payload.remarks.strip() if payload.remarks else None,
            is_advance=(len(payload.allocations) == 0),
            idempotency_key=payload.client_payment_id,
            status="RECORDED",
            recorded_by=actor.user_id,
        )
        db.add(pmt)
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PAYMENT_RECORDED",
            entity_schema="finance",
            entity_table="payments",
            entity_id=pmt.id,
            after_state={
                "payment_number": pmt_no,
                "customer_id": cust.id,
                "payment_date": pmt_date.isoformat(),
                "amount_paisa": int(pmt.amount_paisa),
                "payment_mode": pmt.payment_mode,
                "reference_no": pmt.reference_no,
                "is_advance": pmt.is_advance,
            },
            reason=pmt.remarks or f"Recorded {pmt.payment_mode} receipt {pmt_no} from {cust.name}",
        )

        if payload.allocations:
            _apply_allocations_internal(
                db,
                pmt=pmt,
                lines=[(ln.invoice_id, ln.allocated_paisa) for ln in payload.allocations],
                actor=actor,
                notes=pmt.remarks,
            )

        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError(
            "Duplicate or constraint-violating payment transaction rejected.",
            error_code="DUPLICATE_PAYMENT",
        ) from exc
    except Exception:
        db.rollback()
        raise

    created = finance_repo.get_payment(db, pmt.id)
    assert created is not None
    return _hydrate_payment_list(db, [created])[0]


def allocate_payment(
    db: Session, actor: CurrentActor, payment_id: int, payload: AllocatePaymentRequest
) -> PaymentOut:
    """Allocate unallocated advance/payment funds across one or multiple open invoices atomically."""
    _require_finance_operator(actor, "allocate customer payments")
    try:
        pmt = finance_repo.get_payment(db, payment_id, for_update=True)
        if pmt is None:
            raise NotFoundError(f"Payment {payment_id} was not found.")
        if payload.expected_version is not None and pmt.version != payload.expected_version:
            raise ConflictError("Payment changed concurrently; refresh and retry.", error_code="VERSION_CONFLICT")

        _apply_allocations_internal(
            db,
            pmt=pmt,
            lines=[(ln.invoice_id, ln.allocated_paisa) for ln in payload.allocations],
            actor=actor,
            notes=payload.notes,
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("Allocation exceeds invoice or payment limit.", error_code="OVER_ALLOCATION") from exc
    except Exception:
        db.rollback()
        raise

    refreshed = finance_repo.get_payment(db, payment_id)
    assert refreshed is not None
    return _hydrate_payment_list(db, [refreshed])[0]


def reverse_allocation(
    db: Session, actor: CurrentActor, allocation_id: int, payload: ReverseAllocationRequest
) -> PaymentOut:
    """Audit-logged reversal of a single active invoice allocation returning balance to Customer Advance."""
    _require_finance_operator(actor, "reverse invoice allocations")
    try:
        alloc = finance_repo.get_allocation(db, allocation_id, for_update=True)
        if alloc is None:
            raise NotFoundError(f"Allocation {allocation_id} was not found.")
        if alloc.status == "REVERSED":
            raise ConflictError("Allocation is already reversed.", error_code="ALREADY_REVERSED")

        pmt = finance_repo.get_payment(db, alloc.payment_id, for_update=True)
        assert pmt is not None
        if pmt.status == "REVERSED":
            raise ConflictError("Parent payment is already reversed.", error_code="ALREADY_REVERSED")

        inv_map, ar_map = finance_repo.lock_invoices_for_settlement(db, [alloc.invoice_id])
        inv = inv_map[alloc.invoice_id]
        ar = ar_map[alloc.invoice_id]

        now_utc = datetime.now(UTC)
        alloc.status = "REVERSED"
        alloc.reversed_by = actor.user_id
        alloc.reversed_at = now_utc
        alloc.reversal_reason = payload.reason
        db.flush()

        _sync_invoice_and_ar_settlement(db, invoice=inv, receivable=ar)
        pmt.allocated_paisa = finance_repo.sum_active_allocations_for_payment(db, pmt.id)
        pmt.status = derive_payment_status(pmt)
        pmt.version += 1
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="ALLOCATION_REVERSED",
            entity_schema="finance",
            entity_table="payment_allocations",
            entity_id=alloc.id,
            after_state={
                "payment_id": pmt.id,
                "invoice_id": inv.id,
                "reversed_paisa": int(alloc.allocated_paisa),
                "payment_status": pmt.status,
                "invoice_payment_status": inv.payment_status,
            },
            reason=payload.reason,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = finance_repo.get_payment(db, pmt.id)
    assert refreshed is not None
    return _hydrate_payment_list(db, [refreshed])[0]


def reverse_payment(
    db: Session, actor: CurrentActor, payment_id: int, payload: ReversePaymentRequest
) -> PaymentOut:
    """Reverse an entire customer payment (bounced cheque / erroneous entry) unwinding all invoice AR cleanly."""
    _require_finance_operator(actor, "reverse customer payments")
    try:
        pmt = finance_repo.get_payment(db, payment_id, for_update=True)
        if pmt is None:
            raise NotFoundError(f"Payment {payment_id} was not found.")
        if payload.expected_version is not None and pmt.version != payload.expected_version:
            raise ConflictError("Payment changed concurrently.", error_code="VERSION_CONFLICT")
        if pmt.status == "REVERSED":
            raise ConflictError("Payment is already reversed.", error_code="ALREADY_REVERSED")
        if int(pmt.refunded_paisa) > 0:
            raise ConflictError(
                "Payment already has posted refunds and cannot be fully reversed.",
                error_code="HAS_REFUNDS",
            )

        active_allocs = [a for a in pmt.allocations if a.status == "ACTIVE"]
        affected_inv_ids = [a.invoice_id for a in active_allocs]
        inv_map, ar_map = finance_repo.lock_invoices_for_settlement(db, affected_inv_ids)

        now_utc = datetime.now(UTC)
        for a in active_allocs:
            a.status = "REVERSED"
            a.reversed_by = actor.user_id
            a.reversed_at = now_utc
            a.reversal_reason = f"Payment {pmt.payment_number} reversed: {payload.reason}"
        db.flush()

        for iid in sorted(set(affected_inv_ids)):
            _sync_invoice_and_ar_settlement(db, invoice=inv_map[iid], receivable=ar_map[iid])

        prev_status = pmt.status
        pmt.allocated_paisa = 0
        pmt.status = "REVERSED"
        pmt.reversal_reason = payload.reason
        pmt.reversed_by = actor.user_id
        pmt.reversed_at = now_utc
        pmt.version += 1
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PAYMENT_REVERSED",
            entity_schema="finance",
            entity_table="payments",
            entity_id=pmt.id,
            before_state={"status": prev_status, "allocated_paisa": int(pmt.amount_paisa)},
            after_state={
                "status": "REVERSED",
                "reversed_allocations": len(active_allocs),
                "affected_invoices": affected_inv_ids,
            },
            reason=payload.reason,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = finance_repo.get_payment(db, payment_id)
    assert refreshed is not None
    return _hydrate_payment_list(db, [refreshed])[0]


def refund_payment(
    db: Session, actor: CurrentActor, payment_id: int, payload: RefundPaymentRequest
) -> PaymentOut:
    """Refund available unallocated customer advance balance cleanly without modifying invoices."""
    _require_finance_operator(actor, "issue customer refunds")
    try:
        pmt = finance_repo.get_payment(db, payment_id, for_update=True)
        if pmt is None:
            raise NotFoundError(f"Payment {payment_id} was not found.")
        if payload.expected_version is not None and pmt.version != payload.expected_version:
            raise ConflictError("Payment changed concurrently.", error_code="VERSION_CONFLICT")
        if pmt.status in {"REVERSED", "REFUNDED"}:
            raise ConflictError(
                f"Cannot refund payment in status '{pmt.status}'.",
                error_code="INVALID_STATE_TRANSITION",
            )

        avail_adv = int(pmt.amount_paisa) - int(pmt.allocated_paisa) - int(pmt.refunded_paisa)
        if payload.amount_paisa > avail_adv:
            raise ConflictError(
                f"Refund ({payload.amount_paisa} paise) exceeds available unallocated balance ({avail_adv} paise).",
                error_code="EXCEEDS_UNALLOCATED_BALANCE",
            )

        rfd_date = payload.refund_date or datetime.now(IST).date()
        fy = get_indian_financial_year(rfd_date)
        rfd_no = billing_repo.allocate_fiscal_sequence(
            db, doc_type="REFUND", financial_year=fy, prefix="RFD"
        )
        rfd = PaymentRefund(
            refund_number=rfd_no,
            financial_year=fy,
            payment_id=pmt.id,
            customer_id=pmt.customer_id,
            refund_date=rfd_date,
            amount_paisa=payload.amount_paisa,
            refund_mode=payload.refund_mode,
            reference_no=payload.reference_no.strip() if payload.reference_no else None,
            reason=payload.reason,
            status="POSTED",
            refunded_by=actor.user_id,
        )
        db.add(rfd)
        pmt.refunded_paisa = int(pmt.refunded_paisa) + payload.amount_paisa
        pmt.status = derive_payment_status(pmt)
        pmt.version += 1
        db.flush()

        record_audit_log(
            db,
            actor_user_id=actor.user_id,
            actor_role=actor.role_code,
            action="PAYMENT_REFUNDED",
            entity_schema="finance",
            entity_table="payment_refunds",
            entity_id=rfd.id,
            after_state={
                "refund_number": rfd_no,
                "payment_id": pmt.id,
                "payment_number": pmt.payment_number,
                "amount_paisa": int(rfd.amount_paisa),
                "payment_status": pmt.status,
            },
            reason=payload.reason,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    refreshed = finance_repo.get_payment(db, payment_id)
    assert refreshed is not None
    return _hydrate_payment_list(db, [refreshed])[0]


def get_payment_detail(db: Session, actor: CurrentActor, payment_id: int) -> PaymentOut:
    _require_finance_viewer(actor, "view payment details")
    pmt = finance_repo.get_payment(db, payment_id)
    if pmt is None:
        raise NotFoundError(f"Payment {payment_id} was not found.")
    return _hydrate_payment_list(db, [pmt])[0]


def list_payments_paginated(
    db: Session,
    actor: CurrentActor,
    *,
    customer_id: int | None = None,
    status: str | None = None,
    payment_mode: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedPaymentsOut:
    _require_finance_viewer(actor, "list customer payments")
    offset = (page - 1) * page_size
    rows, total = finance_repo.list_payments(
        db,
        customer_id=customer_id,
        status=status,
        payment_mode=payment_mode,
        date_from=date_from,
        date_to=date_to,
        search=search,
        offset=offset,
        limit=page_size,
    )
    items = _hydrate_payment_list(db, rows)
    total_pages = max(1, math.ceil(total / page_size))
    return PaginatedPaymentsOut(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


def generate_payment_receipt_pdf(
    db: Session, actor: CurrentActor, payment_id: int
) -> tuple[bytes, str]:
    _require_finance_viewer(actor, "download payment receipt PDFs")
    pmt = finance_repo.get_payment(db, payment_id)
    if pmt is None:
        raise NotFoundError(f"Payment {payment_id} was not found.")
    company = _get_company(db)
    cust = db.execute(select(Customer).where(Customer.id == pmt.customer_id)).scalar_one()
    inv_map = _invoices_map(db, {a.invoice_id for a in pmt.allocations})
    alloc_tuples = [
        (
            a,
            inv_map[a.invoice_id].invoice_number or inv_map[a.invoice_id].draft_ref,
            int(inv_map[a.invoice_id].grand_total_paisa),
            int(inv_map[a.invoice_id].outstanding_paisa),
        )
        for a in pmt.allocations
    ]
    pdf_bytes = render_payment_receipt_pdf(
        pmt, company=company, customer=cust, allocations=alloc_tuples
    )
    safe_no = pmt.payment_number.replace("/", "-")
    return pdf_bytes, f"{safe_no}.pdf"


def list_open_invoices_for_customer(
    db: Session,
    actor: CurrentActor,
    customer_id: int,
    *,
    as_of_date: date | None = None,
) -> list[OpenInvoiceForAllocationOut]:
    _require_finance_viewer(actor, "view open customer invoices")
    ref_date = as_of_date or datetime.now(IST).date()
    invs = (
        db.execute(
            select(Invoice)
            .where(
                Invoice.customer_id == customer_id,
                Invoice.doc_status == "ISSUED",
                Invoice.outstanding_paisa > 0,
            )
            .order_by(Invoice.due_date.asc(), Invoice.invoice_date.asc(), Invoice.id.asc())
        )
        .scalars()
        .all()
    )
    ord_ids = {i.sales_order_id for i in invs}
    ord_map = (
        {o.id: o.order_number for o in db.execute(select(SalesOrder).where(SalesOrder.id.in_(ord_ids))).scalars().all()}
        if ord_ids
        else {}
    )
    return [
        OpenInvoiceForAllocationOut(
            invoice_id=inv.id,
            invoice_number=inv.invoice_number or inv.draft_ref,
            order_number=ord_map.get(inv.sales_order_id, "-"),
            invoice_date=inv.invoice_date,
            due_date=inv.due_date,
            grand_total_paisa=int(inv.grand_total_paisa),
            credited_paisa=int(inv.credited_paisa),
            paid_paisa=int(inv.paid_paisa),
            outstanding_paisa=int(inv.outstanding_paisa),
            payment_status=inv.payment_status,
            days_past_due=max(0, (ref_date - inv.due_date).days),
            is_overdue=ref_date > inv.due_date,
        )
        for inv in invs
    ]


# ── Accounts Receivable, Ageing & Customer Statements ───────────────────────


def _ageing_bucket_for_days(days_past_due: int, is_overdue: bool) -> str:
    if not is_overdue:
        return "NOT_DUE"
    if days_past_due <= 30:
        return "0_30"
    if days_past_due <= 60:
        return "31_60"
    if days_past_due <= 90:
        return "61_90"
    return "ABOVE_90"


def get_customer_receivables_summary(
    db: Session,
    actor: CurrentActor,
    *,
    as_of_date: date | None = None,
    customer_id: int | None = None,
    search: str | None = None,
    only_outstanding: bool = False,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedCustomerArOut:
    _require_finance_viewer(actor, "view customer accounts receivable")
    ref_date = as_of_date or datetime.now(IST).date()

    cust_stmt = select(Customer).where(Customer.is_active.is_(True))
    if customer_id is not None:
        cust_stmt = cust_stmt.where(Customer.id == customer_id)
    if search and search.strip():
        pat = f"%{search.strip()}%"
        cust_stmt = cust_stmt.where(Customer.name.ilike(pat) | Customer.code.ilike(pat))
    customers = list(db.execute(cust_stmt.order_by(Customer.name.asc())).scalars().all())

    cids = {c.id for c in customers}
    sids = {c.assigned_salesman_id for c in customers if c.assigned_salesman_id is not None}
    users = _users_map(db, sids)

    invs = (
        db.execute(
            select(Invoice).where(
                Invoice.customer_id.in_(cids), Invoice.doc_status.in_(["ISSUED", "CANCELLED_BY_CN"])
            )
        )
        .scalars()
        .all()
        if cids
        else []
    )
    pmts = (
        db.execute(
            select(Payment).where(Payment.customer_id.in_(cids), Payment.status != "REVERSED")
        )
        .scalars()
        .all()
        if cids
        else []
    )

    inv_by_c: dict[int, list[Invoice]] = {}
    for i in invs:
        inv_by_c.setdefault(i.customer_id, []).append(i)
    pmt_by_c: dict[int, list[Payment]] = {}
    for p in pmts:
        pmt_by_c.setdefault(p.customer_id, []).append(p)

    all_rows: list[CustomerArSummaryRow] = []
    for c in customers:
        c_invs = inv_by_c.get(c.id, [])
        c_pmts = pmt_by_c.get(c.id, [])

        tot_inv = sum(int(i.grand_total_paisa) for i in c_invs)
        tot_cred = sum(int(i.credited_paisa) for i in c_invs)
        tot_paid = sum(int(p.amount_paisa) for p in c_pmts)
        tot_ref = sum(int(p.refunded_paisa) for p in c_pmts)
        tot_alloc = sum(int(p.allocated_paisa) for p in c_pmts)
        tot_adv = sum(int(p.unallocated_paisa) for p in c_pmts)

        open_invs = [i for i in c_invs if i.doc_status == "ISSUED" and int(i.outstanding_paisa) > 0]
        tot_out = sum(int(i.outstanding_paisa) for i in open_invs)
        overdue_invs = [i for i in open_invs if ref_date > i.due_date]
        overdue_bal = sum(int(i.outstanding_paisa) for i in overdue_invs)
        net_ar = max(0, tot_out - tot_adv)

        if only_outstanding and tot_out == 0 and tot_adv == 0:
            continue

        all_rows.append(
            CustomerArSummaryRow(
                customer_id=c.id,
                customer_code=c.code,
                customer_name=c.name,
                customer_type=c.customer_type,
                gstin=c.gstin,
                state_name=c.primary_state_name,
                credit_days=c.credit_days,
                salesman_name=(
                    users[c.assigned_salesman_id].full_name
                    if c.assigned_salesman_id and c.assigned_salesman_id in users
                    else None
                ),
                total_invoiced_paisa=tot_inv,
                total_credited_paisa=tot_cred,
                total_payments_received_paisa=tot_paid,
                total_refunded_paisa=tot_ref,
                total_allocated_paisa=tot_alloc,
                advance_balance_paisa=tot_adv,
                total_outstanding_paisa=tot_out,
                net_receivable_paisa=net_ar,
                overdue_balance_paisa=overdue_bal,
                pending_invoices_count=len(open_invs),
                overdue_invoices_count=len(overdue_invs),
            )
        )

    all_rows.sort(key=lambda r: (-r.total_outstanding_paisa, r.customer_name))
    total = len(all_rows)
    total_pages = max(1, math.ceil(total / page_size))
    start = (page - 1) * page_size
    return PaginatedCustomerArOut(
        items=all_rows[start : start + page_size],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        summary_total_invoiced_paisa=sum(r.total_invoiced_paisa - r.total_credited_paisa for r in all_rows),
        summary_total_received_paisa=sum(r.total_payments_received_paisa - r.total_refunded_paisa for r in all_rows),
        summary_total_outstanding_paisa=sum(r.total_outstanding_paisa for r in all_rows),
        summary_total_overdue_paisa=sum(r.overdue_balance_paisa for r in all_rows),
        summary_total_advance_paisa=sum(r.advance_balance_paisa for r in all_rows),
    )


def get_ageing_report(
    db: Session,
    actor: CurrentActor,
    *,
    as_of_date: date | None = None,
    customer_id: int | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> AgeingReportOut:
    """Calculate due-date based AR ageing (0-30, 31-60, 61-90, >90 days) as of reporting date."""
    _require_finance_viewer(actor, "view invoice ageing report")
    ref_date = as_of_date or datetime.now(IST).date()

    stmt = (
        select(Invoice, Customer)
        .join(Customer, Customer.id == Invoice.customer_id)
        .where(
            Invoice.doc_status == "ISSUED",
            Invoice.outstanding_paisa > 0,
            Invoice.invoice_date <= ref_date,
        )
    )
    if customer_id is not None:
        stmt = stmt.where(Invoice.customer_id == customer_id)
    if search and search.strip():
        pat = f"%{search.strip()}%"
        stmt = stmt.where(Invoice.invoice_number.ilike(pat) | Customer.name.ilike(pat))
    stmt = stmt.order_by(Invoice.due_date.asc(), Invoice.id.asc())

    rows = db.execute(stmt).all()
    not_due_sum = 0
    over_1_30_sum = 0
    b_0_30_sum = 0
    b_31_60_sum = 0
    b_61_90_sum = 0
    b_90_plus_sum = 0

    cust_buckets: dict[int, dict[str, Any]] = {}
    invoice_rows: list[AgeingInvoiceRow] = []

    for inv, cust in rows:
        out_amt = int(inv.outstanding_paisa)
        raw_days = (ref_date - inv.due_date).days
        is_overdue = raw_days > 0
        days_past_due = max(0, raw_days)
        bucket = _ageing_bucket_for_days(days_past_due, is_overdue)

        cb = cust_buckets.setdefault(
            cust.id,
            {
                "customer_id": cust.id,
                "customer_code": cust.code,
                "customer_name": cust.name,
                "not_due_paisa": 0,
                "overdue_1_30_paisa": 0,
                "bucket_0_30_paisa": 0,
                "bucket_31_60_paisa": 0,
                "bucket_61_90_paisa": 0,
                "bucket_90_plus_paisa": 0,
                "total_outstanding_paisa": 0,
                "overdue_total_paisa": 0,
            },
        )
        cb["total_outstanding_paisa"] += out_amt
        if bucket == "NOT_DUE":
            not_due_sum += out_amt
            b_0_30_sum += out_amt
            cb["not_due_paisa"] += out_amt
            cb["bucket_0_30_paisa"] += out_amt
        elif bucket == "0_30":
            over_1_30_sum += out_amt
            b_0_30_sum += out_amt
            cb["overdue_1_30_paisa"] += out_amt
            cb["bucket_0_30_paisa"] += out_amt
            cb["overdue_total_paisa"] += out_amt
        elif bucket == "31_60":
            b_31_60_sum += out_amt
            cb["bucket_31_60_paisa"] += out_amt
            cb["overdue_total_paisa"] += out_amt
        elif bucket == "61_90":
            b_61_90_sum += out_amt
            cb["bucket_61_90_paisa"] += out_amt
            cb["overdue_total_paisa"] += out_amt
        else:
            b_90_plus_sum += out_amt
            cb["bucket_90_plus_paisa"] += out_amt
            cb["overdue_total_paisa"] += out_amt

        invoice_rows.append(
            AgeingInvoiceRow(
                invoice_id=inv.id,
                invoice_number=inv.invoice_number or inv.draft_ref,
                customer_id=cust.id,
                customer_name=cust.name,
                invoice_date=inv.invoice_date,
                due_date=inv.due_date,
                days_past_due=days_past_due,
                is_overdue=is_overdue,
                ageing_bucket=bucket,
                original_paisa=int(inv.grand_total_paisa),
                credited_paisa=int(inv.credited_paisa),
                paid_paisa=int(inv.paid_paisa),
                outstanding_paisa=out_amt,
                payment_status=inv.payment_status,
            )
        )

    tot_out = b_0_30_sum + b_31_60_sum + b_61_90_sum + b_90_plus_sum
    overdue_tot = over_1_30_sum + b_31_60_sum + b_61_90_sum + b_90_plus_sum
    total_inv_cnt = len(invoice_rows)
    total_pages = max(1, math.ceil(total_inv_cnt / page_size))
    start = (page - 1) * page_size

    return AgeingReportOut(
        as_of_date=ref_date,
        not_due_paisa=not_due_sum,
        overdue_1_30_paisa=over_1_30_sum,
        bucket_0_30_paisa=b_0_30_sum,
        bucket_31_60_paisa=b_31_60_sum,
        bucket_61_90_paisa=b_61_90_sum,
        bucket_90_plus_paisa=b_90_plus_sum,
        total_outstanding_paisa=tot_out,
        overdue_total_paisa=overdue_tot,
        customers=[
            AgeingCustomerRow(**v)
            for v in sorted(cust_buckets.values(), key=lambda x: (-x["total_outstanding_paisa"], x["customer_name"]))
        ],
        invoices=invoice_rows[start : start + page_size],
        total_invoices=total_inv_cnt,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def get_customer_statement(
    db: Session,
    actor: CurrentActor,
    customer_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> CustomerStatementOut:
    _require_finance_viewer(actor, "view customer statement")
    cust = db.execute(select(Customer).where(Customer.id == customer_id)).scalar_one_or_none()
    if cust is None:
        raise NotFoundError(f"Customer {customer_id} was not found.")

    invs = (
        db.execute(
            select(Invoice)
            .where(Invoice.customer_id == cust.id, Invoice.doc_status.in_(["ISSUED", "CANCELLED_BY_CN"]))
            .order_by(Invoice.invoice_date.asc(), Invoice.id.asc())
        )
        .scalars()
        .all()
    )
    cns = (
        db.execute(
            select(CreditNote)
            .where(CreditNote.customer_id == cust.id, CreditNote.status == "ISSUED")
            .order_by(CreditNote.issue_date.asc(), CreditNote.id.asc())
        )
        .scalars()
        .all()
    )
    pmts = (
        db.execute(
            select(Payment)
            .where(Payment.customer_id == cust.id)
            .order_by(Payment.payment_date.asc(), Payment.id.asc())
        )
        .scalars()
        .all()
    )
    rfds = (
        db.execute(
            select(PaymentRefund)
            .where(PaymentRefund.customer_id == cust.id)
            .order_by(PaymentRefund.refund_date.asc(), PaymentRefund.id.asc())
        )
        .scalars()
        .all()
    )

    events: list[tuple[date, datetime, str, str, str, int, int, int | None, int | None]] = []
    for i in invs:
        events.append((
            i.invoice_date,
            i.issued_at or i.created_at,
            "INVOICE",
            i.invoice_number or i.draft_ref,
            f"Tax Invoice ({i.supply_type})",
            int(i.grand_total_paisa),
            0,
            i.id,
            None,
        ))
    for cn in cns:
        events.append((
            cn.issue_date,
            cn.issued_at or cn.created_at,
            "CREDIT_NOTE",
            cn.cn_number or cn.draft_ref,
            f"{cn.note_type}: {cn.reason}",
            0,
            int(cn.total_reversed_paisa),
            cn.original_invoice_id,
            None,
        ))
    for p in pmts:
        events.append((
            p.payment_date,
            p.recorded_at,
            "PAYMENT",
            p.payment_number,
            f"{p.payment_mode} receipt" + (f" (Ref: {p.reference_no})" if p.reference_no else ""),
            0,
            int(p.amount_paisa),
            None,
            p.id,
        ))
        if p.status == "REVERSED" and p.reversed_at is not None:
            events.append((
                p.reversed_at.astimezone(IST).date(),
                p.reversed_at,
                "PAYMENT_REVERSAL",
                p.payment_number,
                f"Reversed: {p.reversal_reason}",
                int(p.amount_paisa),
                0,
                None,
                p.id,
            ))
    for r in rfds:
        events.append((
            r.refund_date,
            r.refunded_at,
            "REFUND",
            r.refund_number,
            f"Advance refund ({r.refund_mode}): {r.reason}",
            int(r.amount_paisa),
            0,
            None,
            r.payment_id,
        ))

    events.sort(key=lambda e: (e[0], e[1]))
    running = 0
    entries: list[CustomerStatementEntry] = []
    for e_date, occ, e_type, ref_no, desc, deb, cred, inv_id, pmt_id in events:
        running = running + deb - cred
        if date_from is not None and e_date < date_from:
            continue
        if date_to is not None and e_date > date_to:
            continue
        entries.append(
            CustomerStatementEntry(
                entry_date=e_date,
                occurred_at=occ,
                entry_type=e_type,
                reference_number=ref_no,
                description=desc,
                debit_paisa=deb,
                credit_paisa=cred,
                running_balance_paisa=running,
                linked_invoice_id=inv_id,
                linked_payment_id=pmt_id,
            )
        )

    active_pmts = [p for p in pmts if p.status != "REVERSED"]
    tot_invoiced = sum(int(i.grand_total_paisa) for i in invs)
    tot_credited = sum(int(i.credited_paisa) for i in invs)
    tot_paid = sum(int(p.amount_paisa) for p in active_pmts)
    tot_refunded = sum(int(p.refunded_paisa) for p in active_pmts)
    tot_adv = sum(int(p.unallocated_paisa) for p in active_pmts)
    tot_out = sum(
        int(i.outstanding_paisa) for i in invs if i.doc_status == "ISSUED" and int(i.outstanding_paisa) > 0
    )
    open_invs = list_open_invoices_for_customer(db, actor, cust.id)

    return CustomerStatementOut(
        customer_id=cust.id,
        customer_code=cust.code,
        customer_name=cust.name,
        gstin=cust.gstin,
        state_name=cust.primary_state_name,
        credit_days=cust.credit_days,
        total_invoiced_paisa=tot_invoiced,
        total_credited_paisa=tot_credited,
        total_payments_received_paisa=tot_paid,
        total_refunded_paisa=tot_refunded,
        advance_balance_paisa=tot_adv,
        total_outstanding_paisa=tot_out,
        net_balance_paisa=tot_out - tot_adv,
        open_invoices=open_invs,
        entries=entries,
    )


def get_salesman_customer_receivables(db: Session, actor: CurrentActor) -> list[SalesmanCustomerArOut]:
    """Read-only customer AR snapshot scoped strictly to Salesman's assigned customers."""
    if actor.role_code != "SALESMAN":
        raise AuthorizationError("This endpoint is scoped for Field Salesmen.")
    customers = (
        db.execute(
            select(Customer)
            .where(Customer.assigned_salesman_id == actor.user_id, Customer.is_active.is_(True))
            .order_by(Customer.name.asc())
        )
        .scalars()
        .all()
    )
    if not customers:
        return []
    cids = {c.id for c in customers}
    ref_date = datetime.now(IST).date()

    invs = (
        db.execute(
            select(Invoice).where(Invoice.customer_id.in_(cids), Invoice.doc_status == "ISSUED")
        )
        .scalars()
        .all()
    )
    pmts = (
        db.execute(select(Payment).where(Payment.customer_id.in_(cids), Payment.status != "REVERSED"))
        .scalars()
        .all()
    )
    ord_ids = {i.sales_order_id for i in invs}
    ord_map = (
        {o.id: o.order_number for o in db.execute(select(SalesOrder).where(SalesOrder.id.in_(ord_ids))).scalars().all()}
        if ord_ids
        else {}
    )

    out: list[SalesmanCustomerArOut] = []
    for c in customers:
        ci = [i for i in invs if i.customer_id == c.id]
        cp = [p for p in pmts if p.customer_id == c.id]
        open_rows = [
            OpenInvoiceForAllocationOut(
                invoice_id=inv.id,
                invoice_number=inv.invoice_number or inv.draft_ref,
                order_number=ord_map.get(inv.sales_order_id, "-"),
                invoice_date=inv.invoice_date,
                due_date=inv.due_date,
                grand_total_paisa=int(inv.grand_total_paisa),
                credited_paisa=int(inv.credited_paisa),
                paid_paisa=int(inv.paid_paisa),
                outstanding_paisa=int(inv.outstanding_paisa),
                payment_status=inv.payment_status,
                days_past_due=max(0, (ref_date - inv.due_date).days),
                is_overdue=ref_date > inv.due_date,
            )
            for inv in ci
            if int(inv.outstanding_paisa) > 0
        ]
        out.append(
            SalesmanCustomerArOut(
                customer_id=c.id,
                customer_code=c.code,
                customer_name=c.name,
                total_invoiced_paisa=sum(int(i.grand_total_paisa) - int(i.credited_paisa) for i in ci),
                total_paid_paisa=sum(int(p.amount_paisa) - int(p.refunded_paisa) for p in cp),
                advance_balance_paisa=sum(int(p.unallocated_paisa) for p in cp),
                total_outstanding_paisa=sum(r.outstanding_paisa for r in open_rows),
                open_invoices=open_rows,
            )
        )
    return out


# ── Profitability & Financial Dashboard ─────────────────────────────────────


def _build_lot_full_unit_cost_resolver(db: Session):
    """Map CostLot -> effective full cost/pkt without modifying immutable InventoryMovements."""
    pcs_rows = (
        db.execute(
            select(ProductionCostSummary).where(ProductionCostSummary.is_current.is_(True))
        )
        .scalars()
        .all()
    )
    pcs_by_run = {p.production_run_id: p for p in pcs_rows}
    latest_pcs_by_sku: dict[int, Decimal] = {}
    run_rows = db.execute(select(ProductionRun.id, ProductionRun.pack_size_id).order_by(ProductionRun.id.desc())).all()
    for rid, psid in run_rows:
        if psid not in latest_pcs_by_sku and rid in pcs_by_run and pcs_by_run[rid].exact_cost_per_packet_paisa:
            latest_pcs_by_sku[psid] = Decimal(pcs_by_run[rid].exact_cost_per_packet_paisa)

    open_fg_lots = (
        db.execute(
            select(CostLot)
            .where(CostLot.pack_size_id.is_not(None), CostLot.remaining_qty_base > 0)
            .order_by(CostLot.expiry_date.asc().nullslast(), CostLot.received_at.asc(), CostLot.id.asc())
        )
        .scalars()
        .all()
    )
    open_lot_rate_by_sku: dict[int, Decimal] = {}
    for lot in open_fg_lots:
        if lot.pack_size_id and lot.pack_size_id not in open_lot_rate_by_sku:
            if lot.source_doc_type == "PRODUCTION_RUN" and lot.source_doc_id in pcs_by_run:
                pcs = pcs_by_run[lot.source_doc_id]
                if pcs.exact_cost_per_packet_paisa is not None:
                    open_lot_rate_by_sku[lot.pack_size_id] = Decimal(pcs.exact_cost_per_packet_paisa)
                    continue
            open_lot_rate_by_sku[lot.pack_size_id] = Decimal(lot.unit_cost_paisa_per_base)

    def resolve_lot_unit_cost(lot: CostLot) -> Decimal:
        if lot.source_doc_type == "PRODUCTION_RUN" and lot.source_doc_id in pcs_by_run:
            pcs = pcs_by_run[lot.source_doc_id]
            if pcs.exact_cost_per_packet_paisa is not None:
                return Decimal(pcs.exact_cost_per_packet_paisa)
        return Decimal(lot.unit_cost_paisa_per_base)

    def resolve_pending_sku_cost(pack_size_id: int) -> Decimal:
        if pack_size_id in open_lot_rate_by_sku:
            return open_lot_rate_by_sku[pack_size_id]
        return latest_pcs_by_sku.get(pack_size_id, Decimal(0))

    return resolve_lot_unit_cost, resolve_pending_sku_cost


def get_profitability_report(
    db: Session,
    actor: CurrentActor,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    customer_id: int | None = None,
    pack_size_id: int | None = None,
) -> ProfitabilityReportOut:
    """Compute Product, Customer, Order & Date profitability separating Revenue, GST, COGS & Cash."""
    _require_finance_viewer(actor, "view profitability reports")

    inv_stmt = (
        select(Invoice)
        .options(selectinload(Invoice.items), selectinload(Invoice.credit_notes).selectinload(CreditNote.items))
        .where(Invoice.doc_status.in_(["ISSUED", "CANCELLED_BY_CN"]))
    )
    if date_from is not None:
        inv_stmt = inv_stmt.where(Invoice.invoice_date >= date_from)
    if date_to is not None:
        inv_stmt = inv_stmt.where(Invoice.invoice_date <= date_to)
    if customer_id is not None:
        inv_stmt = inv_stmt.where(Invoice.customer_id == customer_id)
    invs = list(db.execute(inv_stmt.order_by(Invoice.invoice_date.desc(), Invoice.id.desc())).scalars().all())

    if pack_size_id is not None:
        invs = [i for i in invs if any(it.pack_size_id == pack_size_id for it in i.items)]

    resolve_lot_cost, resolve_pending_cost = _build_lot_full_unit_cost_resolver(db)

    inv_ids = [i.id for i in invs]
    inv_item_ids = [it.id for i in invs for it in i.items]
    cni_ids = [ci.id for i in invs for cn in i.credit_notes if cn.status == "ISSUED" for ci in cn.items]

    # Map dispatched qty & actual CostLotConsumption per invoice_item_id
    dispatched_qty_by_inv_item: dict[int, int] = {}
    dispatched_cogs_by_inv_item: dict[int, Decimal] = {}
    if inv_ids:
        dsp_rows = db.execute(
            select(DispatchItem, InventoryMovement)
            .join(Dispatch, Dispatch.id == DispatchItem.dispatch_id)
            .outerjoin(InventoryMovement, InventoryMovement.dispatch_item_id == DispatchItem.id)
            .where(
                Dispatch.invoice_id.in_(inv_ids),
                Dispatch.status.in_(["DISPATCHED", "IN_TRANSIT", "DELIVERED", "DELIVERY_EXCEPTION"]),
            )
        ).all()
        mov_to_inv_item: dict[int, int] = {}
        for di, mov in dsp_rows:
            dispatched_qty_by_inv_item[di.invoice_item_id] = (
                dispatched_qty_by_inv_item.get(di.invoice_item_id, 0) + di.dispatched_qty_pkts
            )
            if mov is not None:
                mov_to_inv_item[mov.id] = di.invoice_item_id

        if mov_to_inv_item:
            clcs = db.execute(
                select(CostLotConsumption, CostLot)
                .join(CostLot, CostLot.id == CostLotConsumption.cost_lot_id)
                .where(CostLotConsumption.inventory_movement_id.in_(list(mov_to_inv_item.keys())))
            ).all()
            for clc, lot in clcs:
                ii_id = mov_to_inv_item[clc.inventory_movement_id]
                eff_uc = resolve_lot_cost(lot)
                dispatched_cogs_by_inv_item[ii_id] = (
                    dispatched_cogs_by_inv_item.get(ii_id, Decimal(0))
                    + Decimal(clc.consumed_qty_base) * eff_uc
                )

    # Subtract COGS of sellable returns restored via CREDIT_RETURN_IN
    return_cogs_credit_by_inv_item: dict[int, Decimal] = {}
    if cni_ids:
        ret_rows = db.execute(
            select(CreditNoteItem, InventoryMovement)
            .join(InventoryMovement, InventoryMovement.credit_note_item_id == CreditNoteItem.id)
            .where(
                CreditNoteItem.id.in_(cni_ids),
                InventoryMovement.movement_type == "CREDIT_RETURN_IN",
            )
        ).all()
        for cni, mov in ret_rows:
            return_cogs_credit_by_inv_item[cni.invoice_item_id] = (
                return_cogs_credit_by_inv_item.get(cni.invoice_item_id, Decimal(0))
                + Decimal(mov.total_cost_paisa)
            )

    # Credit Note reversals aggregated per invoice_item_id & invoice_id
    cn_rev_by_inv_item: dict[int, tuple[int, int, int]] = {}  # item_id -> (qty_ret, taxable, gst)
    for inv in invs:
        for cn in inv.credit_notes:
            if cn.status != "ISSUED":
                continue
            for ci in cn.items:
                prev_q, prev_t, prev_g = cn_rev_by_inv_item.get(ci.invoice_item_id, (0, 0, 0))
                cn_rev_by_inv_item[ci.invoice_item_id] = (
                    prev_q + (ci.qty_pkts if ci.return_disposition == "RESTOCK_SELLABLE" else 0),
                    prev_t + int(ci.taxable_reversed_paisa),
                    prev_g + int(ci.cgst_reversed_paisa) + int(ci.sgst_reversed_paisa) + int(ci.igst_reversed_paisa),
                )

    cust_map = _customers_map(db, {i.customer_id for i in invs})
    ord_ids = {i.sales_order_id for i in invs}
    ord_map = (
        {o.id: o for o in db.execute(select(SalesOrder).where(SalesOrder.id.in_(ord_ids))).scalars().all()}
        if ord_ids
        else {}
    )
    ps_ids = {it.pack_size_id for i in invs for it in i.items}
    ps_map = (
        {p.id: p for p in db.execute(select(PackSize).where(PackSize.id.in_(ps_ids))).scalars().all()}
        if ps_ids
        else {}
    )

    # Payments collected on date range (kept strictly separate from Revenue!)
    pmt_stmt = select(Payment).where(Payment.status != "REVERSED")
    if date_from is not None:
        pmt_stmt = pmt_stmt.where(Payment.payment_date >= date_from)
    if date_to is not None:
        pmt_stmt = pmt_stmt.where(Payment.payment_date <= date_to)
    if customer_id is not None:
        pmt_stmt = pmt_stmt.where(Payment.customer_id == customer_id)
    pmts_in_range = list(db.execute(pmt_stmt).scalars().all())
    cash_by_date: dict[date, int] = {}
    for p in pmts_in_range:
        cash_by_date[p.payment_date] = cash_by_date.get(p.payment_date, 0) + (
            int(p.amount_paisa) - int(p.refunded_paisa)
        )

    tot_gross_rev = 0
    tot_cred_rev = 0
    tot_gst = 0
    tot_disp_cogs = 0
    tot_pend_cogs = 0
    tot_cash_inv = 0
    tot_out_inv = 0

    prod_agg: dict[int, dict[str, Any]] = {}
    cust_agg: dict[int, dict[str, Any]] = {}
    ord_rows: list[OrderProfitabilityRow] = []
    date_agg: dict[date, dict[str, Any]] = {}

    for inv in invs:
        inv_net_rev = 0
        inv_gst = 0
        inv_disp_cogs = 0
        inv_pend_cogs = 0

        for it in inv.items:
            if pack_size_id is not None and it.pack_size_id != pack_size_id:
                continue
            item_gross_rev = int(it.taxable_paisa)
            item_gross_gst = int(it.cgst_paisa) + int(it.sgst_paisa) + int(it.igst_paisa)
            ret_q, cred_tax, cred_gst = cn_rev_by_inv_item.get(it.id, (0, 0, 0))
            item_net_rev = item_gross_rev - cred_tax
            item_net_gst = item_gross_gst - cred_gst

            disp_q = dispatched_qty_by_inv_item.get(it.id, 0)
            raw_disp_cogs = dispatched_cogs_by_inv_item.get(it.id, Decimal(0))
            ret_cogs_credit = return_cogs_credit_by_inv_item.get(it.id, Decimal(0))
            net_disp_cogs = max(
                0,
                int((raw_disp_cogs - ret_cogs_credit).quantize(Decimal(1), rounding=ROUND_HALF_UP)),
            )

            # Only estimate unshipped COGS if invoice is active ISSUED (cancelled pre-dispatch has 0 COGS)
            pend_q = max(0, it.qty_pkts - disp_q) if inv.doc_status == "ISSUED" else 0
            pend_rate = resolve_pending_cost(it.pack_size_id)
            pend_cogs = (
                int((Decimal(pend_q) * pend_rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                if pend_q > 0
                else 0
            )
            item_total_cogs = net_disp_cogs + pend_cogs

            tot_gross_rev += item_gross_rev
            tot_cred_rev += cred_tax
            tot_gst += item_net_gst
            tot_disp_cogs += net_disp_cogs
            tot_pend_cogs += pend_cogs

            inv_net_rev += item_net_rev
            inv_gst += item_net_gst
            inv_disp_cogs += net_disp_cogs
            inv_pend_cogs += pend_cogs

            ps = ps_map[it.pack_size_id]
            pa = prod_agg.setdefault(
                it.pack_size_id,
                {
                    "pack_size_id": it.pack_size_id,
                    "sku_code": it.sku_code,
                    "display_name": ps.display_name,
                    "hsn_code": it.hsn_code,
                    "invoiced_qty_pkts": 0,
                    "returned_qty_pkts": 0,
                    "gross_revenue_paisa": 0,
                    "credited_revenue_paisa": 0,
                    "net_revenue_paisa": 0,
                    "gst_collected_paisa": 0,
                    "dispatched_cogs_paisa": 0,
                    "pending_dispatch_estimated_cogs_paisa": 0,
                    "total_cogs_paisa": 0,
                },
            )
            pa["invoiced_qty_pkts"] += it.qty_pkts if inv.doc_status == "ISSUED" else 0
            pa["returned_qty_pkts"] += ret_q
            pa["gross_revenue_paisa"] += item_gross_rev
            pa["credited_revenue_paisa"] += cred_tax
            pa["net_revenue_paisa"] += item_net_rev
            pa["gst_collected_paisa"] += item_net_gst
            pa["dispatched_cogs_paisa"] += net_disp_cogs
            pa["pending_dispatch_estimated_cogs_paisa"] += pend_cogs
            pa["total_cogs_paisa"] += item_total_cogs

        inv_cogs = inv_disp_cogs + inv_pend_cogs
        inv_gp = inv_net_rev - inv_cogs
        inv_gm = (
            ((Decimal(inv_gp) / Decimal(inv_net_rev)) * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if inv_net_rev > 0
            else Decimal("0.00")
        )
        inv_paid = int(inv.paid_paisa)
        inv_out = int(inv.outstanding_paisa) if inv.doc_status == "ISSUED" else 0
        tot_cash_inv += inv_paid
        tot_out_inv += inv_out

        cust = cust_map[inv.customer_id]
        ca = cust_agg.setdefault(
            cust.id,
            {
                "customer_id": cust.id,
                "customer_code": cust.code,
                "customer_name": cust.name,
                "customer_type": cust.customer_type,
                "invoice_count": 0,
                "net_revenue_paisa": 0,
                "gst_collected_paisa": 0,
                "total_cogs_paisa": 0,
                "cash_received_paisa": 0,
                "outstanding_receivables_paisa": 0,
            },
        )
        ca["invoice_count"] += 1
        ca["net_revenue_paisa"] += inv_net_rev
        ca["gst_collected_paisa"] += inv_gst
        ca["total_cogs_paisa"] += inv_cogs
        ca["cash_received_paisa"] += inv_paid
        ca["outstanding_receivables_paisa"] += inv_out

        ord_obj = ord_map[inv.sales_order_id]
        ord_rows.append(
            OrderProfitabilityRow(
                sales_order_id=ord_obj.id,
                order_number=ord_obj.order_number,
                order_date=ord_obj.order_date,
                invoice_id=inv.id,
                invoice_number=inv.invoice_number or inv.draft_ref,
                invoice_date=inv.invoice_date,
                customer_name=cust.name,
                doc_status=inv.doc_status,
                net_revenue_paisa=inv_net_rev,
                gst_collected_paisa=inv_gst,
                total_cogs_paisa=inv_cogs,
                gross_profit_paisa=inv_gp,
                gross_margin_pct=inv_gm,
                cash_received_paisa=inv_paid,
                outstanding_paisa=inv_out,
            )
        )

        da = date_agg.setdefault(
            inv.invoice_date,
            {
                "period_date": inv.invoice_date,
                "invoice_count": 0,
                "net_revenue_paisa": 0,
                "gst_collected_paisa": 0,
                "total_cogs_paisa": 0,
            },
        )
        da["invoice_count"] += 1
        da["net_revenue_paisa"] += inv_net_rev
        da["gst_collected_paisa"] += inv_gst
        da["total_cogs_paisa"] += inv_cogs

    net_rev = tot_gross_rev - tot_cred_rev
    tot_cogs = tot_disp_cogs + tot_pend_cogs
    tot_gp = net_rev - tot_cogs
    tot_gm = (
        ((Decimal(tot_gp) / Decimal(net_rev)) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if net_rev > 0
        else Decimal("0.00")
    )

    by_product = []
    for p in sorted(prod_agg.values(), key=lambda x: -x["net_revenue_paisa"]):
        gp = p["net_revenue_paisa"] - p["total_cogs_paisa"]
        gm = (
            ((Decimal(gp) / Decimal(p["net_revenue_paisa"])) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if p["net_revenue_paisa"] > 0
            else Decimal("0.00")
        )
        by_product.append(
            ProductProfitabilityRow(
                **p,
                net_sold_qty_pkts=max(0, p["invoiced_qty_pkts"] - p["returned_qty_pkts"]),
                gross_profit_paisa=gp,
                gross_margin_pct=gm,
            )
        )

    by_customer = []
    for c in sorted(cust_agg.values(), key=lambda x: -x["net_revenue_paisa"]):
        gp = c["net_revenue_paisa"] - c["total_cogs_paisa"]
        gm = (
            ((Decimal(gp) / Decimal(c["net_revenue_paisa"])) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if c["net_revenue_paisa"] > 0
            else Decimal("0.00")
        )
        by_customer.append(CustomerProfitabilityRow(**c, gross_profit_paisa=gp, gross_margin_pct=gm))

    all_dates = sorted(set(date_agg.keys()) | set(cash_by_date.keys()), reverse=True)
    by_date = []
    for d in all_dates:
        de = date_agg.get(
            d, {"period_date": d, "invoice_count": 0, "net_revenue_paisa": 0, "gst_collected_paisa": 0, "total_cogs_paisa": 0}
        )
        gp = de["net_revenue_paisa"] - de["total_cogs_paisa"]
        gm = (
            ((Decimal(gp) / Decimal(de["net_revenue_paisa"])) * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if de["net_revenue_paisa"] > 0
            else Decimal("0.00")
        )
        by_date.append(
            DateProfitabilityRow(
                **de,
                gross_profit_paisa=gp,
                gross_margin_pct=gm,
                cash_collected_on_date_paisa=cash_by_date.get(d, 0),
            )
        )

    _ = inv_item_ids
    return ProfitabilityReportOut(
        gross_revenue_paisa=tot_gross_rev,
        credited_revenue_paisa=tot_cred_rev,
        net_revenue_paisa=net_rev,
        gst_collected_paisa=tot_gst,
        dispatched_cogs_paisa=tot_disp_cogs,
        pending_dispatch_estimated_cogs_paisa=tot_pend_cogs,
        total_cogs_paisa=tot_cogs,
        gross_profit_paisa=tot_gp,
        gross_margin_pct=tot_gm,
        cash_received_paisa=sum(cash_by_date.values()),
        outstanding_receivables_paisa=tot_out_inv,
        disclaimer=(
            "Gross Profit = Net Revenue (excl. GST) - COGS (Materials + Packaging + Configured Production Overheads). "
            "GST collected is a tax liability excluded from revenue; customer payments settle AR and are not double-counted as revenue; "
            "Net Profit is not claimed because non-production SG&A operating expenses are outside system scope."
        ),
        by_product=by_product,
        by_customer=by_customer,
        by_order=ord_rows,
        by_date=by_date,
    )


def get_financial_dashboard(
    db: Session,
    actor: CurrentActor,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> FinanceDashboardOut:
    _require_finance_viewer(actor, "view financial dashboard")
    ref_date = date_to or datetime.now(IST).date()

    prof = get_profitability_report(db, actor, date_from=date_from, date_to=date_to)
    ar_summary = get_customer_receivables_summary(db, actor, as_of_date=ref_date, page=1, page_size=500)
    ageing = get_ageing_report(db, actor, as_of_date=ref_date, page=1, page_size=10)

    # All non-reversed payments inside filter window
    pmt_stmt = select(Payment).where(Payment.status != "REVERSED")
    if date_from is not None:
        pmt_stmt = pmt_stmt.where(Payment.payment_date >= date_from)
    if date_to is not None:
        pmt_stmt = pmt_stmt.where(Payment.payment_date <= date_to)
    pmts = list(db.execute(pmt_stmt.order_by(Payment.payment_date.desc(), Payment.id.desc())).scalars().all())

    recent_pmts_rows, _ = finance_repo.list_payments(
        db, date_from=date_from, date_to=date_to, offset=0, limit=8
    )
    recent_payments = _hydrate_payment_list(db, recent_pmts_rows)

    trends_map: dict[date, list[int]] = {}
    for p in pmts:
        cur = trends_map.setdefault(p.payment_date, [0, 0])
        cur[0] += 1
        cur[1] += int(p.amount_paisa) - int(p.refunded_paisa)
    payment_trends = [
        PaymentTrendRow(payment_date=d, payment_count=vals[0], total_received_paisa=vals[1])
        for d, vals in sorted(trends_map.items())
    ]

    # Product costing cards
    pcs_rows = db.execute(
        select(ProductionCostSummary, ProductionRun, PackSize)
        .join(ProductionRun, ProductionRun.id == ProductionCostSummary.production_run_id)
        .join(PackSize, PackSize.id == ProductionRun.pack_size_id)
        .where(ProductionCostSummary.is_current.is_(True))
        .order_by(ProductionRun.run_date.desc(), ProductionRun.id.desc())
        .limit(8)
    ).all()
    costing_summary = [
        CostingSummaryCardRow(
            production_run_id=run.id,
            run_number=run.run_number,
            sku_code=ps.sku_code,
            display_name=ps.display_name,
            cost_status=pcs.cost_status,
            good_packets=pcs.good_packets,
            total_cost_paisa=int(pcs.total_cost_paisa),
            cost_per_packet_paisa=int(pcs.cost_per_packet_paisa) if pcs.cost_per_packet_paisa is not None else None,
            gross_margin_per_pkt_paisa=(
                int(pcs.gross_margin_per_pkt_paisa) if pcs.gross_margin_per_pkt_paisa is not None else None
            ),
            gross_margin_pct=Decimal(pcs.gross_margin_pct) if pcs.gross_margin_pct is not None else None,
        )
        for pcs, run, ps in pcs_rows
    ]

    tot_paid = sum(int(p.amount_paisa) for p in pmts)
    tot_refunded = sum(int(p.refunded_paisa) for p in pmts)

    return FinanceDashboardOut(
        total_invoiced_taxable_paisa=prof.gross_revenue_paisa,
        total_gst_collected_paisa=prof.gst_collected_paisa,
        total_invoiced_gross_paisa=prof.gross_revenue_paisa + prof.gst_collected_paisa + prof.credited_revenue_paisa,
        total_credited_paisa=prof.credited_revenue_paisa,
        net_invoiced_sales_paisa=prof.net_revenue_paisa,
        payments_received_paisa=tot_paid,
        total_refunded_paisa=tot_refunded,
        net_cash_collected_paisa=tot_paid - tot_refunded,
        customer_advances_paisa=ar_summary.summary_total_advance_paisa,
        outstanding_receivables_paisa=ar_summary.summary_total_outstanding_paisa,
        overdue_receivables_paisa=ar_summary.summary_total_overdue_paisa,
        total_cogs_paisa=prof.total_cogs_paisa,
        gross_profit_paisa=prof.gross_profit_paisa,
        gross_margin_pct=prof.gross_margin_pct,
        profitability_disclaimer=prof.disclaimer,
        recent_payments=recent_payments,
        recent_outstanding_invoices=ageing.invoices[:8],
        payment_trends=payment_trends,
        product_profitability=prof.by_product,
        costing_summary=costing_summary,
    )

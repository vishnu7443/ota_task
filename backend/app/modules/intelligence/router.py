"""Phase 10 Management Intelligence & Executive Reporting API router."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import CurrentActor
from app.modules.intelligence import service as intel_service
from app.modules.intelligence.schemas import ManagementIntelligenceDashboardOut

router = APIRouter(prefix="/intelligence", tags=["Management Intelligence & Executive Reports"])

_IntelViewer = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN", "OWNER", "ACCOUNTANT_AUDITOR")),
]


@router.get("/dashboard", response_model=ManagementIntelligenceDashboardOut)
def get_intelligence_dashboard(
    actor: _IntelViewer,
    db: Annotated[Session, Depends(get_db)],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    as_of_date: Annotated[date | None, Query()] = None,
) -> ManagementIntelligenceDashboardOut:
    return intel_service.get_management_intelligence_dashboard(
        db, actor, date_from=date_from, date_to=date_to, as_of_date=as_of_date
    )


@router.get("/reports/export/csv")
def export_intelligence_csv(
    actor: _IntelViewer,
    db: Annotated[Session, Depends(get_db)],
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    as_of_date: Annotated[date | None, Query()] = None,
) -> Response:
    csv_text = intel_service.export_executive_intelligence_csv(
        db, actor, date_from=date_from, date_to=date_to, as_of_date=as_of_date
    )
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="management_intelligence_report.csv"'},
    )

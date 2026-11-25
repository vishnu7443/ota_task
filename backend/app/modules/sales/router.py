from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.iam import service as iam_service
from app.modules.iam.schemas import CurrentActor
from app.modules.sales import service as sales_service
from app.modules.sales.schemas import CustomerSummary, ProductPackResponse, SalesmanOption

router = APIRouter(prefix="/sales", tags=["Sales Catalog"])

_CatalogActor = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("SALESMAN", "FACTORY_ADMIN", "OWNER", "ACCOUNTANT_AUDITOR")),
]
_AdminViewerActor = Annotated[
    CurrentActor,
    Depends(iam_service.require_roles("FACTORY_ADMIN", "OWNER", "ACCOUNTANT_AUDITOR")),
]


@router.get("/customers", response_model=list[CustomerSummary])
def list_customers(
    actor: _CatalogActor,
    db: Annotated[Session, Depends(get_db)],
    search: Annotated[str | None, Query(max_length=80)] = None,
) -> list[CustomerSummary]:
    return sales_service.list_accessible_customers(db, actor, search=search)


@router.get("/products", response_model=list[ProductPackResponse])
def list_products(
    actor: _CatalogActor,
    db: Annotated[Session, Depends(get_db)],
    customer_id: Annotated[int | None, Query(gt=0)] = None,
) -> list[ProductPackResponse]:
    return sales_service.list_active_products(db, actor, customer_id=customer_id)


@router.get("/salesmen", response_model=list[SalesmanOption])
def list_salesmen(
    _actor: _AdminViewerActor,
    db: Annotated[Session, Depends(get_db)],
) -> list[SalesmanOption]:
    return sales_service.list_salesmen_options(db)

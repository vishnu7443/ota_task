"""Production-safe idempotent bootstrap (roles, company profile, metric units, optional admin).

Safe to run with ENVIRONMENT=production and ENABLE_DEV_SEED=false: never seeds default dev passwords.
"""

import logging
import os
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.modules.audit import models as _audit_models  # noqa: F401
from app.modules.billing import models as _billing_models  # noqa: F401
from app.modules.costing import models as _costing_models  # noqa: F401
from app.modules.finance import models as _finance_models  # noqa: F401
from app.modules.iam.models import CompanyProfile, Role, User
from app.modules.inventory.models import UnitConversion
from app.modules.orders import models as _orders_models  # noqa: F401
from app.modules.production import models as _production_models  # noqa: F401
from app.modules.purchasing import models as _purchasing_models  # noqa: F401
from app.modules.sales import models as _sales_models  # noqa: F401

logger = logging.getLogger(__name__)


def run_production_bootstrap(db: Session) -> None:
    """Ensure singleton company profile, 5 RBAC roles, unit conversions, and optional admin exist."""
    company = db.execute(select(CompanyProfile).limit(1)).scalar_one_or_none()
    if company is None:
        db.add(
            CompanyProfile(
                legal_name="Kaveri Traditional Snacks Pvt. Ltd.",
                gstin="33AABCK1234F1Z5",
                state_name="Tamil Nadu",
                state_code="33",
                address="Plot 14, SIDCO Industrial Estate, Tiruchirappalli, Tamil Nadu - 620015",
                variance_tolerance_pct=Decimal("3.00"),
                valuation_method="FIFO",
                is_singleton=True,
            )
        )
        db.flush()

    role_defs = [
        ("SALESMAN", "Field Salesman", "Mobile field order capture and own sales tracking"),
        ("FACTORY_ADMIN", "Factory Admin", "Order verification, billing, dispatch, and collections"),
        ("PRODUCTION_SUPERVISOR", "Production Supervisor", "Raw material intake, BOM runs, output & wastage"),
        ("ACCOUNTANT_AUDITOR", "Accountant / Auditor", "Read-only financial, GST, stock, and audit reports"),
        ("OWNER", "Factory Owner", "Executive KPIs, variance alerts, and governance"),
    ]
    roles_map: dict[str, Role] = {}
    for code, name, desc in role_defs:
        role = db.execute(select(Role).where(Role.code == code)).scalar_one_or_none()
        if role is None:
            role = Role(code=code, name=name, description=desc)
            db.add(role)
            db.flush()
        roles_map[code] = role

    uom_defs = [
        ("kg", "g", "MASS", Decimal("1000.000000")),
        ("g", "g", "MASS", Decimal("1.000000")),
        ("L", "ml", "VOLUME", Decimal("1000.000000")),
        ("ml", "ml", "VOLUME", Decimal("1.000000")),
        ("piece", "piece", "COUNT", Decimal("1.000000")),
        ("packet", "packet", "COUNT", Decimal("1.000000")),
    ]
    for from_uom, to_base_uom, dim, mult in uom_defs:
        existing_uom = db.execute(
            select(UnitConversion).where(
                UnitConversion.from_uom == from_uom,
                UnitConversion.to_base_uom == to_base_uom,
            )
        ).scalar_one_or_none()
        if existing_uom is None:
            db.add(
                UnitConversion(
                    from_uom=from_uom,
                    to_base_uom=to_base_uom,
                    unit_dimension=dim,
                    multiplier=mult,
                )
            )
            db.flush()

    admin_password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "").strip()
    admin_username = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "factory_admin").strip()
    if admin_password and len(admin_password) >= 8 and admin_username:
        existing_admin = db.execute(select(User).where(User.username == admin_username)).scalar_one_or_none()
        if existing_admin is None:
            db.add(
                User(
                    role_id=roles_map["FACTORY_ADMIN"].id,
                    username=admin_username,
                    phone=None,
                    full_name="Factory Admin",
                    password_hash=hash_password(admin_password),
                    is_active=True,
                )
            )
            db.flush()
            logger.info("Bootstrapped initial FACTORY_ADMIN user '%s'.", admin_username)

    db.commit()


def main() -> None:
    with SessionLocal() as db:
        run_production_bootstrap(db)
        logger.info("Production bootstrap completed cleanly.")


if __name__ == "__main__":
    main()

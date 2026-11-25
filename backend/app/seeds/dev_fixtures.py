"""Optional development sandbox fixture helper (kept strictly separate from official benchmark_seed.py).

Allows controlled Phase 5 testing of both sufficient-stock approval and shortage scenarios in local
development WITHOUT fabricating fake production runs or altering the Section 5 50-pkt benchmark baseline.
"""

import argparse
import logging
from datetime import date

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.modules.iam.models import User
from app.modules.inventory import service as inventory_service
from app.modules.sales.models import PackSize

logger = logging.getLogger(__name__)


def seed_controlled_dev_fg_stock(*, batch_ref: str = "DEV-PHASE5-TEST-STOCK", add_pkts: int = 150) -> None:
    settings = get_settings()
    if not settings.ENABLE_DEV_SEED:
        raise RuntimeError("ENABLE_DEV_SEED must be true to load dev fixtures.")

    with SessionLocal() as db:
        admin = db.execute(select(User).where(User.username == "admin")).scalar_one()
        mrk = db.execute(select(PackSize).where(PackSize.sku_code == "MRK-200G")).scalar_one()
        inventory_service.seed_opening_finished_goods(
            db,
            batch_ref=batch_ref,
            pack_size_id=mrk.id,
            opening_qty_pkts=add_pkts,
            unit_cost_paisa=2885,
            as_of_date=date(2026, 11, 25),
            created_by=admin.id,
        )
        db.commit()
        avail = inventory_service.get_pack_size_availability_map(db, [mrk.id])[mrk.id]
        logger.info("Controlled dev FG fixture ensured (%s). Current MRK-200G balance: %s", batch_ref, avail)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load optional isolated dev stock fixture.")
    parser.add_argument("--add-pkts", type=int, default=150)
    args = parser.parse_args()
    seed_controlled_dev_fg_stock(add_pkts=args.add_pkts)


if __name__ == "__main__":
    main()

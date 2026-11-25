"""Deterministic unit conversion helper across MASS (g/kg), VOLUME (ml/L), and COUNT (piece/packet/carton)."""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import DomainValidationError
from app.modules.inventory.models import UnitConversion

_CANONICAL_UOM_ALIASES: dict[str, str] = {
    "g": "g",
    "gm": "g",
    "gms": "g",
    "gram": "g",
    "grams": "g",
    "kg": "kg",
    "kgs": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "ml": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "milliliter": "ml",
    "l": "L",
    "ltr": "L",
    "litre": "L",
    "litres": "L",
    "liter": "L",
    "liters": "L",
    "pc": "piece",
    "pcs": "piece",
    "piece": "piece",
    "pieces": "piece",
    "pkt": "packet",
    "pkts": "packet",
    "packet": "packet",
    "packets": "packet",
    "ctn": "carton",
    "carton": "carton",
    "cartons": "carton",
}

_BUILTIN_FACTORS: dict[str, tuple[str, str, Decimal]] = {
    "g": ("g", "MASS", Decimal("1.000000")),
    "kg": ("g", "MASS", Decimal("1000.000000")),
    "ml": ("ml", "VOLUME", Decimal("1.000000")),
    "L": ("ml", "VOLUME", Decimal("1000.000000")),
    "piece": ("piece", "COUNT", Decimal("1.000000")),
    "packet": ("packet", "COUNT", Decimal("1.000000")),
}


def normalize_uom(raw_uom: str) -> str:
    cleaned = raw_uom.strip().lower()
    if cleaned not in _CANONICAL_UOM_ALIASES:
        raise DomainValidationError(f"Unsupported unit of measure '{raw_uom}'.")
    return _CANONICAL_UOM_ALIASES[cleaned]


def convert_to_base_qty(
    db: Session,
    *,
    entered_qty: Decimal,
    entered_uom: str,
    expected_dimension: str,
    expected_base_uom: str,
    packets_per_carton: int | None = None,
) -> tuple[Decimal, Decimal, str]:
    """Convert entered quantity to canonical base quantity (`g`, `ml`, `piece`, or `packet`).

    Strictly prevents cross-dimension mixing (e.g., L on MASS, kg on VOLUME).
    Returns `(base_qty_3dp, multiplier_6dp, normalized_uom)`.
    """
    uom = normalize_uom(entered_uom)

    if uom == "carton":
        if expected_dimension != "COUNT" or packets_per_carton is None or packets_per_carton <= 0:
            raise DomainValidationError(
                f"Unit 'carton' requires a COUNT item with a valid carton ratio (not compatible with {expected_dimension})."
            )
        multiplier = Decimal(packets_per_carton).quantize(Decimal("0.000001"))
        base_qty = (entered_qty * multiplier).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        return base_qty, multiplier, uom

    conv_row = db.execute(
        select(UnitConversion).where(
            UnitConversion.from_uom == uom,
            UnitConversion.to_base_uom == expected_base_uom,
        )
    ).scalar_one_or_none()

    if conv_row is not None:
        if conv_row.unit_dimension != expected_dimension:
            raise DomainValidationError(
                f"Incompatible unit '{uom}' ({conv_row.unit_dimension}) for item requiring {expected_dimension}."
            )
        multiplier = Decimal(conv_row.multiplier).quantize(Decimal("0.000001"))
    else:
        builtin = _BUILTIN_FACTORS.get(uom)
        if builtin is None:
            raise DomainValidationError(
                f"Unit '{uom}' cannot be converted to '{expected_base_uom}' ({expected_dimension})."
            )
        to_base, dim, builtin_mult = builtin
        if dim != expected_dimension or (dim != "COUNT" and to_base != expected_base_uom):
            raise DomainValidationError(
                f"Incompatible unit '{uom}' ({dim}) for item requiring {expected_dimension} ({expected_base_uom})."
            )
        multiplier = builtin_mult

    base_qty = (entered_qty * multiplier).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return base_qty, multiplier, uom


def unit_rate_to_base_cost(entered_rate_paisa: int, multiplier: Decimal) -> Decimal:
    """Convert rate per entered UOM (e.g., 4500 paise/kg) to paise per base unit (4.500000 paise/g)."""
    return (Decimal(entered_rate_paisa) / multiplier).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )

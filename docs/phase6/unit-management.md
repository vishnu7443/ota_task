# Unit Management & Conversions (`docs/phase6/unit-management.md`)

## Dimension-Safe Storage Strategy
All physical quantities in `inventory.inventory_balances`, `inventory.inventory_movements`, `inventory.cost_lots`, `inventory.opening_balances`, `inventory.stock_adjustments`, and PO/GRN base columns are normalized into canonical base units per dimension (`NUMERIC(18,3)`):

| Unit Dimension | Canonical Base Unit | Accepted Input Units (`uom.py`) | Conversion Multiplier |
|---|---|---|---|
| `MASS` | `g` | `g` (`gm`, `grams`), `kg` (`kgs`, `kilograms`) | `1`, `1000` |
| `VOLUME` | `ml` | `ml` (`millilitre`), `L` (`l`, `ltr`, `litre`, `litres`) | `1`, `1000` |
| `COUNT` | `piece` (Materials) / `packet` (FG SKUs) | `piece` (`pc`, `pcs`), `packet` (`pkt`, `pkts`), `carton` (`ctn`, FG only) | `1`, `1`, `packets_per_carton` (`20`) |

## Cross-Dimension Guard (EC-11)
- `convert_to_base_qty` validates input unit aliases against the item's `unit_dimension` and queries `production.unit_conversions` first (falling back to verified canonical constants).
- Supplying a `VOLUME` unit (`L`) on a `MASS` item (`MAT-FLR`), or `MASS` (`kg`) on a `VOLUME` item (`MAT-OIL`), immediately fails with `422 DomainValidationError`.

## Rate-to-Base Cost Normalization (`NUMERIC(18,6)`)
When purchasing in macro units (e.g., `60 kg` Flour at `4500` paise / `kg` = ₹45.00/kg):
$$\text{unit\_cost\_paisa\_per\_base} = \frac{4500}{1000} = 4.500000 \text{ paise / g}$$
Total value: `60,000 g * 4.500000 paise/g = 270,000 paise` (`₹2,700.00`), preserving exact INR arithmetic with zero floating-point drift.

"""Phase 5 gate: CSV parsing + label slugification."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.menu import _slugify  # noqa: E402


def test_slugify():
    assert _slugify("Mineral Water 500ml") == "mineral_water_500ml"
    assert _slugify("Coca-Cola Can") == "coca_cola_can"
    assert _slugify("100 Plus!!!") == "100_plus"
    assert _slugify("   ") == "item"


def test_sample_csv_parses():
    """Verify sample_menu.csv has 15 rows and each has a valid price."""
    import csv
    path = Path(__file__).resolve().parent.parent / "sample_menu.csv"
    with path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 15, f"expected 15 rows, got {len(rows)}"
    for r in rows:
        assert r["name"]
        assert float(r["price"]) > 0

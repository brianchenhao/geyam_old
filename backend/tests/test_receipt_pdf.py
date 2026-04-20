"""Phase 9 gate: receipt PDF renders without crashing and is a real PDF."""
import sys
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import receipt_pdf  # noqa: E402


def test_render_creates_pdf():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "r.pdf"
        receipt_pdf.render(
            out_path=out,
            shop_name="Demo Shop",
            tx_number="GY20260420-0042",
            created_at=datetime(2026, 4, 20, 13, 0, 0),
            items=[
                {"name": "Mineral Water 500ml", "qty": 2, "unit_price": Decimal("2.00")},
                {"name": "Oreo Original", "qty": 1, "unit_price": Decimal("4.50")},
            ],
            total=Decimal("8.50"),
            footer="Thank you!\nGoods sold are not refundable.",
            contact_phone="+60 12-345 6789",
            contact_email="shop@example.com",
        )
        data = out.read_bytes()
        assert data.startswith(b"%PDF-"), "not a PDF"
        assert len(data) > 500

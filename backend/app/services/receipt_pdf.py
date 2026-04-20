"""Receipt PDF renderer. 80mm thermal-style layout using reportlab."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import mm
from reportlab.lib.units import mm as mm_unit
from reportlab.pdfgen import canvas


def render(
    *,
    out_path: Path,
    shop_name: str,
    tx_number: str,
    created_at: datetime,
    items: list[dict],      # {name, qty, unit_price}
    total: Decimal,
    footer: str,
    contact_email: str | None = None,
    contact_phone: str | None = None,
    logo_abs_path: Path | None = None,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    width = 80 * mm
    # Dynamic height: header + one line per item + footer block
    line_h = 4.5 * mm_unit
    height = (50 + 6 * len(items) + 50) * mm_unit / 10  # placeholder; expand below
    # Simpler: compute exactly.
    top_pad = 10 * mm_unit
    header_h = 30 * mm_unit + (20 * mm_unit if logo_abs_path and logo_abs_path.exists() else 0)
    items_h = (len(items) + 2) * line_h
    footer_h = 30 * mm_unit
    height = top_pad + header_h + items_h + footer_h

    c = canvas.Canvas(str(out_path), pagesize=(width, height))
    y = height - top_pad

    if logo_abs_path and logo_abs_path.exists():
        try:
            c.drawImage(
                str(logo_abs_path), (width - 30 * mm_unit) / 2, y - 20 * mm_unit,
                width=30 * mm_unit, height=20 * mm_unit, preserveAspectRatio=True, mask="auto",
            )
            y -= 22 * mm_unit
        except Exception:
            pass

    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(width / 2, y, shop_name)
    y -= 6 * mm_unit

    c.setFont("Helvetica", 8)
    c.drawCentredString(width / 2, y, tx_number)
    y -= 4 * mm_unit
    c.drawCentredString(width / 2, y, created_at.strftime("%Y-%m-%d %H:%M:%S"))
    y -= 6 * mm_unit
    c.line(4 * mm_unit, y, width - 4 * mm_unit, y)
    y -= 4 * mm_unit

    c.setFont("Helvetica", 9)
    for it in items:
        name = it["name"]
        qty = it["qty"]
        line_total = Decimal(str(it["unit_price"])) * qty
        # Left: "2x Mineral Water 500ml". Right: "RM 4.00".
        left = f"{qty}x {name[:28]}"
        right = f"RM {line_total:.2f}"
        c.drawString(4 * mm_unit, y, left)
        c.drawRightString(width - 4 * mm_unit, y, right)
        y -= line_h

    y -= 2 * mm_unit
    c.line(4 * mm_unit, y, width - 4 * mm_unit, y)
    y -= 5 * mm_unit

    c.setFont("Helvetica-Bold", 11)
    c.drawString(4 * mm_unit, y, "TOTAL")
    c.drawRightString(width - 4 * mm_unit, y, f"RM {Decimal(str(total)):.2f}")
    y -= 10 * mm_unit

    c.setFont("Helvetica-Oblique", 8)
    for line in footer.splitlines():
        c.drawCentredString(width / 2, y, line[:44])
        y -= 3.5 * mm_unit
    if contact_email or contact_phone:
        y -= 2 * mm_unit
        if contact_phone:
            c.drawCentredString(width / 2, y, contact_phone)
            y -= 3.5 * mm_unit
        if contact_email:
            c.drawCentredString(width / 2, y, contact_email)

    c.showPage()
    c.save()

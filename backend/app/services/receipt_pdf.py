"""ReportLab receipt generator — logo + header + itemized + total + footer."""
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image as RLImage, Paragraph, SimpleDocTemplate,
                                 Spacer, Table, TableStyle)


def render_receipt(
    *,
    tx_number: str,
    paid_at: Optional[str],
    cashier: str,
    customer: Optional[str],
    shop_name: str,
    shop_email: Optional[str],
    shop_phone: Optional[str],
    logo_path: Optional[Path],
    line_items: list[dict],  # {name, qty, unit_price, total}
    total: Decimal,
    payment: str,
    footer: str,
    out_path: Path,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out_path), pagesize=A5, leftMargin=12 * mm,
                             rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=13)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, leading=10, textColor=colors.grey)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=14, leading=16, spaceAfter=2)

    elems = []
    if logo_path and logo_path.exists():
        try:
            elems.append(RLImage(str(logo_path), width=30 * mm, height=30 * mm, kind="proportional"))
        except Exception:
            pass
    elems.append(Paragraph(shop_name, h1))
    contact_bits = [b for b in [shop_email, shop_phone] if b]
    if contact_bits:
        elems.append(Paragraph(" · ".join(contact_bits), small))
    elems.append(Spacer(1, 6))

    elems.append(Paragraph(f"<b>TX {tx_number}</b>", body))
    if paid_at:
        elems.append(Paragraph(f"Paid: {paid_at}", small))
    elems.append(Paragraph(f"Cashier: {cashier}", small))
    elems.append(Paragraph(f"Customer: {customer or 'Walk-in'}", small))
    elems.append(Spacer(1, 8))

    data = [["Item", "Qty", "Unit", "Total"]]
    for li in line_items:
        data.append([li["name"], str(li["qty"]), f"{li['unit_price']:.2f}", f"{li['total']:.2f}"])
    data.append(["", "", "TOTAL", f"RM {total:.2f}"])
    data.append(["", "", "Payment", payment])

    t = Table(data, colWidths=[75 * mm, 15 * mm, 20 * mm, 25 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("LINEABOVE", (0, 1), (-1, 1), 0.5, colors.black),
        ("LINEABOVE", (0, -2), (-1, -2), 0.5, colors.black),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.grey),
    ]))
    elems.append(t)
    elems.append(Spacer(1, 12))
    elems.append(Paragraph(footer, small))

    doc.build(elems)
    return out_path

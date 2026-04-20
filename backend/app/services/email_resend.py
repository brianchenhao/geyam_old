"""Resend email client. Returns the resend message id or raises."""
import base64
import os
from pathlib import Path

import resend


class ResendDisabled(Exception):
    pass


def send_receipt(
    *, to_email: str, subject: str, html: str, pdf_path: Path,
) -> str:
    key = os.getenv("RESEND_API_KEY")
    if not key:
        raise ResendDisabled("RESEND_API_KEY not set")
    resend.api_key = key
    from_addr = os.getenv("RESEND_FROM", "noreply@geyam.com")
    attachment = {
        "filename": pdf_path.name,
        "content": base64.b64encode(pdf_path.read_bytes()).decode("ascii"),
    }
    resp = resend.Emails.send({
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "html": html,
        "attachments": [attachment],
    })
    return resp.get("id", "")

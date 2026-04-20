"""Thin Resend client. Real API if RESEND_API_KEY and not RESEND_SKIP, else no-op."""
import os
from pathlib import Path
from typing import Optional


def send_receipt_email(*, to: str, subject: str, html: str,
                        attachment_path: Optional[Path] = None,
                        filename: str = "receipt.pdf") -> Optional[str]:
    """Returns Resend message id on success, None if skipped/failed."""
    if os.environ.get("RESEND_SKIP", "") == "1":
        return "skipped"
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        return None
    try:
        import resend
        resend.api_key = api_key
        payload: dict = {
            "from": os.environ.get("RESEND_FROM", "noreply@geyam.com"),
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if attachment_path is not None and attachment_path.exists():
            import base64
            payload["attachments"] = [{
                "filename": filename,
                "content": base64.b64encode(attachment_path.read_bytes()).decode(),
            }]
        resp = resend.Emails.send(payload)
        if isinstance(resp, dict):
            return resp.get("id") or resp.get("data", {}).get("id")
        return str(resp)
    except Exception as e:
        return f"error:{type(e).__name__}"

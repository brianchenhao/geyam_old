"""Stage C — OpenAI gpt-4o-mini vision, pHash-cached, quota-capped."""
import base64
import json
import os
from datetime import date
from io import BytesIO
from typing import Optional

from PIL import Image
from rapidfuzz import fuzz
from redis import Redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.openai_usage import OpenAIUsage
from app.models.tenant import Tenant
from app.models.tenant_settings import TenantSettings
from app.services.plan_enforcement import PLAN_LIMITS, UNLIMITED


PROMPT = (
    "You see packaged food or drink items on a tray or counter. "
    "Return a strict JSON array (no prose, no markdown) of items you are confident "
    "about: [{\"name\": str, \"brand\": optional str, \"type\": str}]. "
    "Only include items you can name clearly."
)


def _redis() -> Optional[Redis]:
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        r = Redis.from_url(url)
        r.ping()
        return r
    except Exception:
        return None


def _cache_key(tenant_id: int, phash: str) -> str:
    return f"cv:{tenant_id}:{phash}"


def _image_to_data_url(img: Image.Image) -> str:
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def _fuzzy_match(openai_name: str, menu_items: list[dict]) -> Optional[dict]:
    if not menu_items:
        return None
    best: tuple[int, Optional[dict]] = (0, None)
    for m in menu_items:
        if not m.get("is_active"):
            continue
        score = fuzz.partial_ratio(openai_name.lower(), m["name"].lower())
        if score > best[0]:
            best = (score, m)
    return best[1] if best[0] >= 80 else None


def run_openai(
    *,
    tenant_id: int,
    phash: str,
    img: Image.Image,
    menu_items: list[dict],
    sync_session: Session,
    settings: TenantSettings,
) -> tuple[list[dict], Optional[str]]:
    """Returns (matches, error). matches: list with source='openai', needs_confirm=True."""
    if os.environ.get("OPENAI_SKIP", "") == "1":
        return [], "openai_skipped"

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return [], "no_api_key"

    # pHash cache lookup
    r = _redis()
    if r is not None:
        try:
            cached = r.get(_cache_key(tenant_id, phash))
            if cached is not None:
                cached_names = json.loads(cached)
                return _names_to_matches(cached_names, menu_items), None
        except Exception:
            pass

    # Quota check — per-day TenantSettings cap AND per-month plan cap both apply.
    today = date.today()
    usage = sync_session.query(OpenAIUsage).filter(
        OpenAIUsage.tenant_id == tenant_id, OpenAIUsage.day == today
    ).first()
    calls = usage.calls if usage else 0
    limit = settings.openai_daily_limit or 50
    if calls >= limit:
        return [], "quota_exceeded"

    # Phase 9: plan-tier monthly cap. tenants.plan is mirrored from the Stripe
    # webhook; defaults to 'free' for tenants with no subscription row.
    tenant = sync_session.query(Tenant).filter(Tenant.id == tenant_id).first()
    plan_name = tenant.plan if tenant else "free"
    monthly_cap = PLAN_LIMITS.get(plan_name, PLAN_LIMITS["free"]).openai_monthly
    if monthly_cap != UNLIMITED:
        month_start = today.replace(day=1)
        monthly_used = sync_session.execute(
            select(func.coalesce(func.sum(OpenAIUsage.calls), 0))
            .where(OpenAIUsage.tenant_id == tenant_id, OpenAIUsage.day >= month_start)
        ).scalar() or 0
        if int(monthly_used) >= monthly_cap:
            return [], "plan_quota_exceeded"

    # Call OpenAI
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": _image_to_data_url(img)}},
                ]},
            ],
            max_tokens=400,
            temperature=0.1,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
        data = json.loads(raw)
        if not isinstance(data, list):
            data = []
        names = [str(d.get("name", "")).strip() for d in data if d.get("name")]
    except Exception as e:
        return [], f"openai_error: {type(e).__name__}"

    # Increment usage counter
    if usage is None:
        sync_session.add(OpenAIUsage(tenant_id=tenant_id, day=today, calls=1))
    else:
        usage.calls = calls + 1
    sync_session.commit()

    # Cache names against pHash (7 days)
    if r is not None:
        try:
            r.setex(_cache_key(tenant_id, phash), 7 * 24 * 3600, json.dumps(names))
        except Exception:
            pass

    return _names_to_matches(names, menu_items), None


def _names_to_matches(names: list[str], menu_items: list[dict]) -> list[dict]:
    out: list[dict] = []
    for n in names:
        m = _fuzzy_match(n, menu_items)
        if m is not None:
            out.append({
                "label": m["label"],
                "menu_item_id": m["id"],
                "name": m["name"],
                "price": m.get("price", 0),
                "confidence": 0.5,
                "source": "openai",
                "needs_confirm": True,
            })
    return out

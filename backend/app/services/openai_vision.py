"""OpenAI GPT-4o-mini vision, constrained to the tenant's menu.

Quota + pHash cache live in the DB. A call path:
    cascade asks → cache hit?  return cached
                 → quota exceeded?  raise QuotaExceeded
                 → call OpenAI, persist cache, bump quota
"""
import base64
import json
import os
from datetime import date

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OpenAIUsage, PHashCache
from app.services import phash as phash_mod


class QuotaExceeded(Exception):
    pass


class OpenAIDisabled(Exception):
    pass


def _client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise OpenAIDisabled("OPENAI_API_KEY not set")
    return OpenAI(api_key=key)


async def detect(
    session: AsyncSession,
    *,
    tenant_id: int,
    image_bytes: bytes,
    menu_names: list[str],
    daily_limit: int = 50,
) -> tuple[list[str], str]:
    """Return (list_of_menu_names_found, source).
    source is 'openai.cache' or 'openai.fresh'."""
    ph = phash_mod.compute(image_bytes)

    cached = await session.scalar(
        select(PHashCache).where(PHashCache.phash == ph)
    )
    if cached is not None:
        try:
            return json.loads(cached.result_json), "openai.cache"
        except Exception:
            pass  # malformed cache row — re-fetch

    today = date.today()
    usage = await session.scalar(
        select(OpenAIUsage).where(OpenAIUsage.day == today)
    )
    if usage and usage.calls >= daily_limit:
        raise QuotaExceeded(f"daily limit {daily_limit} reached")

    client = _client()
    b64 = base64.b64encode(image_bytes).decode("ascii")
    prompt = (
        "Identify packaged food items in this tray image. "
        f"Only return names from this exact list: {menu_names}. "
        'Respond as JSON: {"items": ["name1", "name2", ...]}'
    )
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        response_format={"type": "json_object"},
        max_tokens=300,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw).get("items", [])
    except json.JSONDecodeError:
        parsed = []
    found = [n for n in parsed if n in menu_names]

    if usage is None:
        session.add(OpenAIUsage(tenant_id=tenant_id, day=today, calls=1))
    else:
        usage.calls += 1
    session.add(
        PHashCache(tenant_id=tenant_id, phash=ph, result_json=json.dumps(found))
    )
    return found, "openai.fresh"

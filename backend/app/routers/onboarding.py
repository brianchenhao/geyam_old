"""Phase 10 — self-serve onboarding wizard state.

The wizard advances through 4 steps after signup:
  1 = shop + logo
  2 = first cashier
  3 = sample items
  4 = billing intro
  5 = done (terminal)

`POST /onboarding/step/{n}` is idempotent — marking step 2 done when already at
step 3 is a no-op (the `done` flag stays true, the step counter doesn't roll
back). Lets the Flutter wizard fire-and-forget without coordination.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_session, get_tenant, require_role
from app.models.onboarding_state import OnboardingState

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


_FLAGS = {
    1: "shop_info_done",
    2: "cashier_done",
    3: "items_done",
    4: "billing_seen",
}


def _serialize(state: OnboardingState) -> dict:
    return {
        "step": state.step,
        "shop_info_done": state.shop_info_done,
        "cashier_done": state.cashier_done,
        "items_done": state.items_done,
        "billing_seen": state.billing_seen,
        "completed_at": state.completed_at.isoformat() if state.completed_at else None,
    }


async def _load_or_create(session: AsyncSession, tenant_id: int) -> OnboardingState:
    """Backfill an onboarding_state row for legacy Stage 2 tenants that signed
    up before Phase 10 existed — they get a fresh wizard at step 1 the first
    time they hit this endpoint."""
    state = await session.get(OnboardingState, tenant_id)
    if state is None:
        state = OnboardingState(tenant_id=tenant_id, step=1)
        session.add(state)
        await session.flush()
    return state


@router.get("/status")
async def status(
    tenant_id: int = Depends(get_tenant),
    _owner: dict = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    state = await _load_or_create(session, tenant_id)
    await session.commit()
    return _serialize(state)


@router.post("/step/{n}")
async def mark_step(
    n: int,
    tenant_id: int = Depends(get_tenant),
    _owner: dict = Depends(require_role("owner")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if n not in _FLAGS:
        raise HTTPException(status_code=400, detail="step must be 1, 2, 3, or 4")

    state = await _load_or_create(session, tenant_id)
    setattr(state, _FLAGS[n], True)
    # Step counter only advances — never rolls back. Marking step 1 when
    # already at step 3 leaves the counter at 3.
    if state.step == n:
        state.step = n + 1
    if state.step >= 5 and state.completed_at is None:
        state.completed_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(state)
    return _serialize(state)

from fastapi import APIRouter

from app.services.forecast import compute_forecast

router = APIRouter(tags=["forecast"])


@router.get("/forecast")
async def get_forecast():
    return await compute_forecast()

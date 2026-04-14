from fastapi import APIRouter
from sqlalchemy import select

from app.database import SessionLocal
from app.models.menu_item import MenuItem
from app.schemas.menu import MenuItemResponse

router = APIRouter(tags=["menu"])


@router.get("/menu", response_model=list[MenuItemResponse])
async def list_menu():
    async with SessionLocal() as session:
        rows = await session.scalars(
            select(MenuItem).where(MenuItem.is_active.is_(True)).order_by(MenuItem.id)
        )
        return list(rows)

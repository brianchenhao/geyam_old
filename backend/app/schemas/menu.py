from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class MenuItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    label: str
    price: Decimal
    is_active: bool
    frame_count: int
    created_at: datetime

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TransactionItemIn(BaseModel):
    menu_item_id: int
    quantity: int = Field(default=1, ge=1)
    unit_price: float = Field(ge=0)
    confidence: float | None = None


class TransactionCreate(BaseModel):
    staff_id: int | None = None
    payment: str = "cash"
    items: list[TransactionItemIn] = Field(min_length=1)


class TransactionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    menu_item_id: int | None
    quantity: int
    unit_price: float
    confidence: float | None


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    staff_id: int | None
    total: float
    payment: str
    created_at: datetime
    items: list[TransactionItemOut]


class TransactionCreated(BaseModel):
    id: int
    total: float
    created_at: datetime


class TopItem(BaseModel):
    menu_item_id: int
    name: str
    quantity: int
    revenue: float


class SalesSummary(BaseModel):
    total_revenue: float
    total_transactions: int
    top_selling_items: list[TopItem]

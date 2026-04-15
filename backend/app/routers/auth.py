import bcrypt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.database import SessionLocal
from app.models.user import User

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user_id: int
    username: str
    role: str


@router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest):
    async with SessionLocal() as session:
        user = await session.scalar(
            select(User).where(User.username == payload.username)
        )
    if user is None or not bcrypt.checkpw(
        payload.password.encode("utf-8"), user.password.encode("utf-8")
    ):
        raise HTTPException(401, "invalid credentials")
    return LoginResponse(user_id=user.id, username=user.username, role=user.role)

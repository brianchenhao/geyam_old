from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.llm_service import ask_llm

router = APIRouter(tags=["ask"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1)


@router.post("/ask")
async def ask(payload: AskRequest):
    result = await ask_llm(payload.question)
    if "error" in result:
        return result
    return {"question": payload.question, **result}

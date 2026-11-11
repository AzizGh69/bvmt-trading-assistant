"""The assistant chat."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..assistant import answer
from ..config import get_settings
from ..db import get_db
from ..models import User
from ..security import optional_user
from .market import market_or_503

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatIn(BaseModel):
    messages: list[Message] = Field(min_length=1, max_length=20)


@router.get("/status")
def status() -> dict:
    settings = get_settings()
    return {"configured": settings.llm_configured, "model": settings.llm_model if settings.llm_configured else None}


@router.post("/chat")
def chat(body: ChatIn, user: User | None = Depends(optional_user), db: Session = Depends(get_db)) -> dict:
    """Answer from the knowledge base, the user's paper portfolio and the stocks the question names."""
    messages = [m.model_dump() for m in body.messages]
    if messages[-1]["role"] != "user":
        messages.append({"role": "user", "content": "Continue."})
    return answer(db, market_or_503(), messages, user)

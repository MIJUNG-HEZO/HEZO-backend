from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: str
    user_message: str
    domain: str = ""
    template_id: str = ""


class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    turn_status: str  # "answer_accepted" | "answer_rejected" | "ready_for_contract_compile"
    next_stage: str   # "proactive_questioning" | "contract_compile" | "retry_answer"
    slot_filled: dict = {}
    missing_slots: list[str] = []
    mock: bool = False

from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    session_id: str
    user_message: str
    answered_slot: str = ""    # 직전 에이전트가 질문한 슬롯 키
    domain: str = ""
    domain_label: str = ""
    category: str = "landing"
    template_id: str = ""


class ChatResponse(BaseModel):
    session_id: str
    assistant_message: str
    turn_status: str   # "answer_accepted" | "answer_rejected" | "ready_for_contract_compile"
    next_stage: str    # "proactive_questioning" | "contract_compile" | "retry_answer"
    slot_filled: dict = {}
    missing_slots: list[str] = []
    current_slot: str = ""  # 다음 질문의 슬롯 키 (프론트에서 다음 턴 answered_slot으로 사용)
    mock: bool = False

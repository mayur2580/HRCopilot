from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas.chat import ChatRequest, ChatResponse, SessionResponse
from backend.app.services.hr_runtime import SessionManager, get_session_payload, process_user_message

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    result = process_user_message(request.session_id, request.message)
    return ChatResponse(**result)


@router.post("/{session_id}/confirm", response_model=ChatResponse)
def confirm_email(session_id: str) -> ChatResponse:
    session = SessionManager.get_or_create(session_id)
    if not session.get("pending_email_draft"):
        raise HTTPException(status_code=400, detail="No pending email draft found for this session.")

    result = process_user_message(session_id, "yes")
    return ChatResponse(**result)


@router.post("/{session_id}/cancel", response_model=ChatResponse)
def cancel_email(session_id: str) -> ChatResponse:
    session = SessionManager.get_or_create(session_id)
    if not session.get("pending_email_draft"):
        raise HTTPException(status_code=400, detail="No pending email draft found for this session.")

    result = process_user_message(session_id, "no")
    return ChatResponse(**result)


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(session_id: str) -> SessionResponse:
    return SessionResponse(**get_session_payload(session_id))


@router.delete("/{session_id}")
def reset_session(session_id: str) -> dict[str, str]:
    SessionManager.reset(session_id)
    return {"message": f"Session '{session_id}' was reset."}
from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from backend.app.core.config import settings
from backend.app.services.session_store import session_store
from agent.orchestrator import graph

try:
    from main import ensure_index
except Exception:  # pragma: no cover
    ensure_index = None


_INITIALIZED = False


def bootstrap_runtime() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return

    if settings.auto_ensure_index and ensure_index is not None:
        ensure_index()

    _INITIALIZED = True


class SessionManager:
    @staticmethod
    def _empty_session() -> dict[str, Any]:
        return {
            "messages": [],
            "last_agent": "",
            "needs_input": False,
            "route": None,
            "pending_email_draft": None,
            "cancelled_email_draft": None,
            "last_eval": None,
            "db_ground_truth": None,
            "eval_feedback": None,
            "retry_count": 0,
            "retry_agent": None,
            "orchestrator_feedback": None,
            "orchestrator_retry_count": 0,
        }

    @staticmethod
    def get_or_create(session_id: str) -> dict[str, Any]:
        session = session_store.get(session_id)
        if session is None:
            session = SessionManager._empty_session()
            session_store.set(session_id, session)
        return session

    @staticmethod
    def reset(session_id: str) -> None:
        session_store.set(session_id, SessionManager._empty_session())


def _serialize_messages(messages: list[BaseMessage]) -> list[dict[str, str]]:
    serialized: list[dict[str, str]] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            serialized.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            serialized.append({"role": "assistant", "content": msg.content})
    return serialized


def _latest_ai_message(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return msg.content
    return ""


def _build_graph_input(session: dict[str, Any], new_message: str) -> dict[str, Any]:
    updated_messages = list(session["messages"]) + [HumanMessage(content=new_message)]
    return {
        "messages": updated_messages,
        "last_agent": "",
        "needs_input": False,
        "route": None,
        "pending_email_draft": session.get("pending_email_draft"),
        "cancelled_email_draft": session.get("cancelled_email_draft"),
        "last_eval": None,
        "db_ground_truth": None,
        "eval_feedback": None,
        "retry_count": 0,
        "retry_agent": None,
        "orchestrator_feedback": None,
        "orchestrator_retry_count": 0,
    }


def process_user_message(session_id: str, message: str) -> dict[str, Any]:
    bootstrap_runtime()
    session = SessionManager.get_or_create(session_id)
    initial_state = _build_graph_input(session, message)

    # ── LangSmith Thread config ──────────────────────────────────────────
    # session_id is already a stable, per-conversation identifier from the
    # frontend. Passing it as `session_id` in metadata tells LangSmith to
    # group every trace from this conversation under one Thread.
    langsmith_config = {
        "run_name": "hr-assistant",
        "tags":     ["hr-assistant"],
        "metadata": {
            "session_id": session_id,   # ← groups traces into a Thread
        },
    }
    # ────────────────────────────────────────────────────────────────────

    final_state: dict[str, Any] = {}
    for chunk in graph.stream(initial_state, config=langsmith_config, stream_mode="updates"):
        for _, node_output in chunk.items():
            if isinstance(node_output, dict):
                final_state = {**final_state, **node_output}

    if not final_state:
        final_state = initial_state

    new_session = {
        **session,
        "messages": final_state.get("messages", initial_state["messages"]),
        "pending_email_draft": final_state.get("pending_email_draft"),
        "cancelled_email_draft": final_state.get("cancelled_email_draft"),
        "last_eval": final_state.get("last_eval"),
        "last_agent": final_state.get("last_agent", ""),
    }
    session_store.set(session_id, new_session)

    return {
        "session_id": session_id,
        "reply": _latest_ai_message(new_session["messages"]),
        "last_agent": final_state.get("last_agent"),
        "route": final_state.get("route"),
        "requires_confirmation": bool(new_session.get("pending_email_draft")),
        "pending_email_draft": new_session.get("pending_email_draft"),
        "last_eval": new_session.get("last_eval"),
        "messages": _serialize_messages(new_session["messages"]),
    }


def get_session_payload(session_id: str) -> dict[str, Any]:
    session = SessionManager.get_or_create(session_id)
    return {
        "session_id": session_id,
        "has_pending_email_draft": bool(session.get("pending_email_draft")),
        "cancelled_email_draft": session.get("cancelled_email_draft"),
        "last_agent": session.get("last_agent"),
        "messages": _serialize_messages(session.get("messages", [])),
        "last_eval": session.get("last_eval"),
    }
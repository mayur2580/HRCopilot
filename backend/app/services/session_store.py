from __future__ import annotations

from threading import Lock
from typing import Any


class InMemorySessionStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            session = self._data.get(session_id)
            return None if session is None else dict(session)

    def set(self, session_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._data[session_id] = dict(payload)

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._data.pop(session_id, None)


session_store = InMemorySessionStore()
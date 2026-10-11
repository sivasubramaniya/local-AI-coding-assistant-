"""Connection state shown in the sidebar model card."""

from __future__ import annotations

from enum import Enum


class ConnectionState(Enum):
    CHECKING = "Checking…"
    CONNECTED = "Connected"
    DISCONNECTED = "Disconnected"
    MODEL_MISSING = "Model missing"

    @property
    def is_ok(self) -> bool:
        return self is ConnectionState.CONNECTED


def stub_connection_state() -> ConnectionState:
    """Phase 3 stub: Ollama is never contacted, so report Disconnected.

    Phase 4 replaces this with a real health check in a worker thread.
    """
    return ConnectionState.DISCONNECTED

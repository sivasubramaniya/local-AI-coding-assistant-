"""Connection state shown in the sidebar model card."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConnectionState(Enum):
    CHECKING = "Checking…"
    CONNECTED = "Connected"
    DISCONNECTED = "Disconnected"
    MODEL_MISSING = "Model missing"

    @property
    def is_ok(self) -> bool:
        return self is ConnectionState.CONNECTED


@dataclass(frozen=True)
class HealthResult:
    state: ConnectionState
    message: str
    version: str | None = None


def stub_connection_state() -> ConnectionState:
    """Used when health checks are switched off (demo screenshots, some tests)."""
    return ConnectionState.DISCONNECTED

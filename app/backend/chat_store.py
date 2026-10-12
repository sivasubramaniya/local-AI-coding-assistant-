"""The ChatStore protocol and the records it works with.

Both ``InMemoryChatStore`` (demo, screenshots, some tests) and
``SqliteChatRepository`` (real history) implement ``ChatStore``, so
``ChatService`` and the UI never depend on a specific backend.

Message rules shared by every store:
- ``role`` is "user" or "assistant". The system prompt is never stored.
- ``status`` is "complete", "stopped" (partial text kept) or "error"
  (the user-friendly error text only, never a stack trace).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from app.errors import StorageError

DEFAULT_TITLE = "New chat"
AUTO_TITLE_MAX = 40
TITLE_MAX = 80
ROLES = ("user", "assistant")
STATUSES = ("complete", "stopped", "error")
FEEDBACK_BAD = "bad"
FEEDBACK_VALUES = (None, FEEDBACK_BAD)
LAST_CHAT_SETTING = "last_chat_id"
PROJECT_STATUSES = ("planned", "generating", "complete", "partial", "failed", "cancelled")


@dataclass
class ChatMessage:
    role: str  # "user" or "assistant"
    content: str
    files: list[str] = field(default_factory=list)  # project-relative paths shown as file cards
    status: str = "complete"
    eval_count: int | None = None
    tokens_per_sec: float | None = None
    feedback: str | None = None
    id: int | None = None
    seq: int | None = None
    created_at: str | None = None
    project_id: str | None = None  # the project the file cards belong to


@dataclass
class Conversation:
    id: str
    title: str
    model_name: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class ProjectRecord:
    id: str
    conversation_id: str | None
    name: str
    path: str
    status: str
    created_at: str
    updated_at: str


def utc_now() -> str:
    """UTC timestamp as an ISO-8601 string with microseconds."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def title_from_prompt(prompt: str, limit: int = AUTO_TITLE_MAX) -> str:
    """Chat title from the first non-empty line of the first user message."""
    first_line = next((line for line in prompt.splitlines() if line.strip()), "")
    words = " ".join(first_line.split())
    if not words:
        return DEFAULT_TITLE
    title = words[0].upper() + words[1:]
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


def clean_title(title: str) -> str:
    """Trim and collapse whitespace; 1–80 characters, else StorageError."""
    cleaned = " ".join(str(title).split())
    if not cleaned:
        raise StorageError("A chat title cannot be empty.")
    if len(cleaned) > TITLE_MAX:
        raise StorageError(f"A chat title can have at most {TITLE_MAX} characters.")
    return cleaned


def check_message(message: ChatMessage) -> None:
    if message.role not in ROLES:
        raise StorageError("Could not save the message.", detail=f"invalid role {message.role!r}")
    if message.status not in STATUSES:
        raise StorageError("Could not save the message.", detail=f"invalid status {message.status!r}")
    if not isinstance(message.content, str):
        raise StorageError("Could not save the message.", detail="content must be text")


def check_project_status(status: str) -> None:
    if status not in PROJECT_STATUSES:
        raise StorageError("Could not save the project.", detail=f"invalid status {status!r}")


def check_feedback(value: str | None) -> None:
    if value not in FEEDBACK_VALUES:
        raise StorageError("Could not save the feedback.", detail=f"invalid feedback {value!r}")


class ChatStore(Protocol):
    """Chat history storage. Every method raises StorageError on failure."""

    def create_chat(self, title: str = DEFAULT_TITLE, model_name: str | None = None) -> Conversation: ...

    def list_chats(self) -> list[Conversation]:
        """Most recently updated first."""
        ...

    def get_chat(self, chat_id: str) -> Conversation: ...

    def chat_exists(self, chat_id: str) -> bool: ...

    def get_messages(self, chat_id: str) -> list[ChatMessage]:
        """Messages in send order (seq ascending)."""
        ...

    def add_message(self, chat_id: str, message: ChatMessage) -> ChatMessage:
        """Append a message. The first user message of a 'New chat' also sets the title."""
        ...

    def replace_reply(self, chat_id: str, message: ChatMessage) -> ChatMessage:
        """Atomically drop assistant messages after the last user message, then append ``message``."""
        ...

    def rename_chat(self, chat_id: str, title: str) -> Conversation: ...

    def delete_chat(self, chat_id: str) -> None:
        """Delete the chat and its messages. Linked projects keep existing, unlinked."""
        ...

    def set_feedback(self, message_id: int, value: str | None) -> None: ...

    def list_projects(self) -> list[ProjectRecord]:
        """Most recently updated first."""
        ...

    def create_project(self, name: str, path: str, conversation_id: str | None,
                       status: str = "planned") -> ProjectRecord: ...

    def update_project_status(self, project_id: str, status: str) -> None: ...

    def get_project(self, project_id: str) -> ProjectRecord: ...

    def latest_project_for_chat(self, chat_id: str) -> ProjectRecord | None: ...

    def get_setting(self, key: str, default: str | None = None) -> str | None: ...

    def set_setting(self, key: str, value: str | None) -> None: ...

    def close(self) -> None: ...

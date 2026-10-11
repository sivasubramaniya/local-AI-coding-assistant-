"""In-memory chat store used until SQLite storage arrives in Phase 5.

The public methods mirror what the SQLite store will offer, so the UI does not
change when the storage backend is swapped.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field

from app.errors import StorageError

DEFAULT_TITLE = "New chat"


@dataclass
class ChatMessage:
    role: str  # "user" or "assistant"
    content: str
    files: list[str] = field(default_factory=list)
    status: str | None = None


@dataclass
class Conversation:
    id: str
    title: str
    messages: list[ChatMessage] = field(default_factory=list)
    updated: int = 0


def title_from_prompt(prompt: str, limit: int = 40) -> str:
    """A short chat title from the first user message."""
    words = " ".join(prompt.split())
    if not words:
        return DEFAULT_TITLE
    title = words[0].upper() + words[1:]
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


class InMemoryChatStore:
    def __init__(self) -> None:
        self._chats: dict[str, Conversation] = {}
        self._clock = itertools.count(1)

    def create(self, title: str = DEFAULT_TITLE) -> Conversation:
        chat = Conversation(id=uuid.uuid4().hex[:12], title=title, updated=next(self._clock))
        self._chats[chat.id] = chat
        return chat

    def list(self) -> list[Conversation]:
        """Most recently updated first."""
        return sorted(self._chats.values(), key=lambda c: c.updated, reverse=True)

    def get(self, chat_id: str) -> Conversation:
        try:
            return self._chats[chat_id]
        except KeyError:
            raise StorageError("That chat no longer exists.", detail=f"chat id {chat_id!r}") from None

    def exists(self, chat_id: str) -> bool:
        return chat_id in self._chats

    def rename(self, chat_id: str, title: str) -> Conversation:
        title = " ".join(title.split())
        if not title:
            raise StorageError("A chat title cannot be empty.")
        chat = self.get(chat_id)
        chat.title = title
        return chat

    def delete(self, chat_id: str) -> None:
        self.get(chat_id)
        del self._chats[chat_id]

    def add_message(self, chat_id: str, message: ChatMessage) -> ChatMessage:
        chat = self.get(chat_id)
        chat.messages.append(message)
        chat.updated = next(self._clock)
        return message

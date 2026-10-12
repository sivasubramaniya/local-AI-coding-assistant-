"""In-memory ChatStore: used by --demo, screenshot mode and tests. Nothing is saved to disk."""

from __future__ import annotations

import itertools
import uuid
from dataclasses import replace

from app.backend.chat_store import (
    DEFAULT_TITLE,
    ChatMessage,
    Conversation,
    ProjectRecord,
    check_feedback,
    check_message,
    clean_title,
    title_from_prompt,
    utc_now,
)
from app.errors import StorageError

__all__ = ["DEFAULT_TITLE", "ChatMessage", "Conversation", "InMemoryChatStore", "title_from_prompt"]


class InMemoryChatStore:
    def __init__(self) -> None:
        self._chats: dict[str, Conversation] = {}
        self._messages: dict[str, list[ChatMessage]] = {}
        self._order: dict[str, int] = {}
        self._settings: dict[str, str] = {}
        self._clock = itertools.count(1)
        self._ids = itertools.count(1)

    def _touch(self, chat: Conversation) -> None:
        chat.updated_at = utc_now()
        self._order[chat.id] = next(self._clock)

    def create_chat(self, title: str = DEFAULT_TITLE, model_name: str | None = None) -> Conversation:
        now = utc_now()
        chat = Conversation(uuid.uuid4().hex, clean_title(title), model_name, now, now)
        self._chats[chat.id] = chat
        self._messages[chat.id] = []
        self._order[chat.id] = next(self._clock)
        return replace(chat)

    def list_chats(self) -> list[Conversation]:
        ordered = sorted(self._chats.values(), key=lambda c: self._order[c.id], reverse=True)
        return [replace(c) for c in ordered]

    def _chat(self, chat_id: str) -> Conversation:
        try:
            return self._chats[chat_id]
        except KeyError:
            raise StorageError("That chat no longer exists.", detail=f"chat id {chat_id!r}") from None

    def get_chat(self, chat_id: str) -> Conversation:
        return replace(self._chat(chat_id))

    def chat_exists(self, chat_id: str) -> bool:
        return chat_id in self._chats

    def get_messages(self, chat_id: str) -> list[ChatMessage]:
        self._chat(chat_id)
        return [replace(m, files=list(m.files)) for m in self._messages[chat_id]]

    def _append(self, chat: Conversation, message: ChatMessage) -> ChatMessage:
        check_message(message)
        messages = self._messages[chat.id]
        stored = replace(message, files=list(message.files), id=next(self._ids),
                         seq=(messages[-1].seq + 1) if messages else 1, created_at=utc_now())
        messages.append(stored)
        self._touch(chat)
        return replace(stored, files=list(stored.files))

    def add_message(self, chat_id: str, message: ChatMessage) -> ChatMessage:
        chat = self._chat(chat_id)
        check_message(message)
        is_first_user = message.role == "user" and not any(m.role == "user" for m in self._messages[chat_id])
        if is_first_user and chat.title == DEFAULT_TITLE:
            chat.title = title_from_prompt(message.content)
        return self._append(chat, message)

    def replace_reply(self, chat_id: str, message: ChatMessage) -> ChatMessage:
        chat = self._chat(chat_id)
        check_message(message)
        messages = self._messages[chat_id]
        while messages and messages[-1].role == "assistant":
            messages.pop()
        return self._append(chat, message)

    def rename_chat(self, chat_id: str, title: str) -> Conversation:
        chat = self._chat(chat_id)
        chat.title = clean_title(title)
        return replace(chat)

    def delete_chat(self, chat_id: str) -> None:
        self._chat(chat_id)
        del self._chats[chat_id], self._messages[chat_id], self._order[chat_id]

    def set_feedback(self, message_id: int, value: str | None) -> None:
        check_feedback(value)
        for messages in self._messages.values():
            for message in messages:
                if message.id == message_id:
                    message.feedback = value
                    return
        raise StorageError("That message no longer exists.", detail=f"message id {message_id}")

    def list_projects(self) -> list[ProjectRecord]:
        return []

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        return self._settings.get(key, default)

    def set_setting(self, key: str, value: str | None) -> None:
        if value is None:
            self._settings.pop(key, None)
        else:
            self._settings[key] = str(value)

    def close(self) -> None:
        pass

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
    check_project_status,
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
        self._projects: dict[str, ProjectRecord] = {}
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
        for pid, project in list(self._projects.items()):
            if project.conversation_id == chat_id:
                self._projects[pid] = replace(project, conversation_id=None)

    def set_feedback(self, message_id: int, value: str | None) -> None:
        check_feedback(value)
        for messages in self._messages.values():
            for message in messages:
                if message.id == message_id:
                    message.feedback = value
                    return
        raise StorageError("That message no longer exists.", detail=f"message id {message_id}")

    def list_projects(self) -> list[ProjectRecord]:
        return sorted(self._projects.values(), key=lambda p: p.updated_at, reverse=True)

    def create_project(self, name: str, path: str, conversation_id: str | None,
                       status: str = "planned") -> ProjectRecord:
        check_project_status(status)
        if conversation_id is not None:
            self._chat(conversation_id)
        now = utc_now()
        record = ProjectRecord(uuid.uuid4().hex, conversation_id, name, path, status, now, now)
        self._projects[record.id] = record
        return record

    def update_project_status(self, project_id: str, status: str) -> None:
        check_project_status(status)
        record = self.get_project(project_id)
        self._projects[project_id] = replace(record, status=status, updated_at=utc_now())

    def get_project(self, project_id: str) -> ProjectRecord:
        try:
            return self._projects[project_id]
        except KeyError:
            raise StorageError("That project no longer exists.", detail=f"project id {project_id!r}") from None

    def latest_project_for_chat(self, chat_id: str) -> ProjectRecord | None:
        linked = [p for p in self._projects.values() if p.conversation_id == chat_id]
        return max(linked, key=lambda p: p.created_at) if linked else None

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        return self._settings.get(key, default)

    def set_setting(self, key: str, value: str | None) -> None:
        if value is None:
            self._settings.pop(key, None)
        else:
            self._settings[key] = str(value)

    def close(self) -> None:
        pass

"""Chat orchestration: message lists for the model, context trimming, history updates.

The system prompt is always the first message of every request (send, regenerate,
retry) and is never stored. Works with any ChatStore (in-memory or SQLite).
"""

from __future__ import annotations

import logging
import math

from app.backend.chat_store import ChatMessage, ChatStore
from app.config import AppConfig
from app.errors import StorageError
from app.prompts import load_system_prompt

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4
MESSAGE_OVERHEAD_TOKENS = 4
MIN_REPLY_RESERVE = 1024


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def message_tokens(message: dict) -> int:
    return estimate_tokens(message["content"]) + MESSAGE_OVERHEAD_TOKENS


def reply_reserve(num_ctx: int) -> int:
    """Tokens kept free for the answer: a quarter of the context, at least 1024, at most half."""
    return min(max(MIN_REPLY_RESERVE, num_ctx // 4), num_ctx // 2)


def _in_context(message: ChatMessage) -> bool:
    """Error notices are app messages, not model output: they never go back to the model."""
    return message.role in ("user", "assistant") and bool(message.content) and message.status != "error"


def build_messages(
    history: list[ChatMessage],
    user_text: str,
    system_prompt: str,
    num_ctx: int,
) -> list[dict]:
    """[system, ...trimmed history..., latest user]. Oldest turns are dropped first."""
    earlier = [{"role": m.role, "content": m.content} for m in history if _in_context(m)]
    system = {"role": "system", "content": system_prompt}
    latest = {"role": "user", "content": user_text}

    budget = num_ctx - reply_reserve(num_ctx) - message_tokens(system) - message_tokens(latest)
    kept: list[dict] = []
    used = 0
    for message in reversed(earlier):
        cost = message_tokens(message)
        if used + cost > budget:
            break
        kept.append(message)
        used += cost
    kept.reverse()
    # do not start the history with an assistant reply whose question was dropped
    while kept and kept[0]["role"] == "assistant" and len(kept) < len(earlier):
        kept.pop(0)

    dropped = len(earlier) - len(kept)
    if dropped:
        logger.info(
            "Context trimmed: dropped %d of %d earlier messages to fit num_ctx=%d", dropped, len(earlier), num_ctx
        )
    return [system, *kept, latest]


class ChatService:
    def __init__(self, store: ChatStore, config: AppConfig, system_prompt: str | None = None) -> None:
        self.store = store
        self.config = config
        self.system_prompt = system_prompt if system_prompt is not None else load_system_prompt()

    def _build(self, history: list[ChatMessage], user_text: str, context: str | None = None) -> list[dict]:
        latest = f"{user_text}\n\n{context}" if context else user_text
        return build_messages(history, latest, self.system_prompt, self.config.num_ctx)

    def context_budget_chars(self) -> int:
        """Characters available for project files/attachments in one request (about half the prompt room)."""
        prompt_room = self.config.num_ctx - reply_reserve(self.config.num_ctx) - estimate_tokens(self.system_prompt)
        return max(2000, prompt_room * CHARS_PER_TOKEN // 2)

    def add_user_message(self, chat_id: str, text: str) -> ChatMessage:
        """Store a user message without building a request (project generation flow)."""
        return self.store.add_message(chat_id, ChatMessage("user", text))

    def send(self, chat_id: str, text: str, context: str | None = None) -> list[dict]:
        """Store the user message (the store sets the auto-title) and return the request messages.

        ``context`` (project files, attachments) is added to the request only; the stored
        message is exactly what the user typed.
        """
        history = self.store.get_messages(chat_id)
        self.store.add_message(chat_id, ChatMessage("user", text))
        return self._build(history, text, context)

    def last_user_text(self, chat_id: str) -> str | None:
        messages = [m for m in self.store.get_messages(chat_id) if m.role == "user"]
        return messages[-1].content if messages else None

    def regenerate(self, chat_id: str, context: str | None = None) -> list[dict]:
        """Rebuild the request for the last user message, ignoring any reply after it.

        Also used for Retry after an error. The old reply stays stored until the new
        one is recorded (record_reply replaces it in one transaction).
        """
        messages = self.store.get_messages(chat_id)
        while messages and messages[-1].role == "assistant":
            messages.pop()
        if not messages:
            raise StorageError("There is no message to answer again.")
        return self._build(messages[:-1], messages[-1].content, context)

    def record_reply(
        self,
        chat_id: str,
        text: str,
        status: str = "complete",
        files: list[str] | None = None,
        eval_count: int | None = None,
        tokens_per_sec: float | None = None,
        project_id: str | None = None,
    ) -> ChatMessage | None:
        """Save the assistant reply, replacing any earlier reply to the same user message."""
        if not text or not self.store.chat_exists(chat_id):
            return None
        message = ChatMessage("assistant", text, files=list(files or []), status=status,
                              eval_count=eval_count, tokens_per_sec=tokens_per_sec, project_id=project_id)
        return self.store.replace_reply(chat_id, message)

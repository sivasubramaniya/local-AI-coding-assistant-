"""Chat orchestration: message lists for the model, context trimming, history updates.

The system prompt is always the first message of every request (send, regenerate,
retry). The store is the in-memory one until Phase 5 swaps in SQLite.
"""

from __future__ import annotations

import logging
import math

from app.backend.memory_store import DEFAULT_TITLE, ChatMessage, InMemoryChatStore, title_from_prompt
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


def build_messages(
    history: list[ChatMessage],
    user_text: str,
    system_prompt: str,
    num_ctx: int,
) -> list[dict]:
    """[system, ...trimmed history..., latest user]. Oldest turns are dropped first."""
    earlier = [{"role": m.role, "content": m.content} for m in history if m.role in ("user", "assistant") and m.content]
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
    def __init__(self, store: InMemoryChatStore, config: AppConfig, system_prompt: str | None = None) -> None:
        self.store = store
        self.config = config
        self.system_prompt = system_prompt if system_prompt is not None else load_system_prompt()

    def _build(self, history: list[ChatMessage], user_text: str) -> list[dict]:
        return build_messages(history, user_text, self.system_prompt, self.config.num_ctx)

    def send(self, chat_id: str, text: str) -> list[dict]:
        """Store the user message and return the request messages for it."""
        chat = self.store.get(chat_id)
        history = list(chat.messages)
        if not chat.messages and chat.title == DEFAULT_TITLE:
            self.store.rename(chat_id, title_from_prompt(text))
        self.store.add_message(chat_id, ChatMessage("user", text))
        return self._build(history, text)

    def regenerate(self, chat_id: str) -> list[dict]:
        """Drop the last reply (if any) and rebuild the request for the last user message.

        Also used for Retry after an error, where there is no reply to drop.
        """
        self.store.remove_trailing_assistant(chat_id)
        chat = self.store.get(chat_id)
        if not chat.messages or chat.messages[-1].role != "user":
            raise StorageError("There is no message to answer again.")
        return self._build(chat.messages[:-1], chat.messages[-1].content)

    def record_reply(self, chat_id: str, text: str, status: str | None = None,
                     files: list[str] | None = None) -> None:
        if not self.store.exists(chat_id) or not text:
            return
        self.store.add_message(chat_id, ChatMessage("assistant", text, files=list(files or []), status=status))

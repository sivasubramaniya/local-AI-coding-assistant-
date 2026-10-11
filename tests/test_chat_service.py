import logging

import pytest

from app.backend.chat_service import ChatService, build_messages, estimate_tokens, reply_reserve
from app.backend.memory_store import ChatMessage, InMemoryChatStore
from app.errors import StorageError
from app.prompts import load_system_prompt

SYSTEM = "You are a coding assistant."


def _turns(n: int, size: int) -> list[ChatMessage]:
    out = []
    for i in range(n):
        out.append(ChatMessage("user", f"q{i} " + "x" * size))
        out.append(ChatMessage("assistant", f"a{i} " + "y" * size))
    return out


def test_system_prompt_first_and_latest_last():
    messages = build_messages(_turns(2, 10), "latest?", SYSTEM, 8192)
    assert messages[0] == {"role": "system", "content": SYSTEM}
    assert messages[-1] == {"role": "user", "content": "latest?"}
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user", "assistant", "user"]


def test_no_trimming_when_it_fits(caplog):
    with caplog.at_level(logging.INFO, logger="app.backend.chat_service"):
        messages = build_messages(_turns(3, 50), "q", SYSTEM, 8192)
    assert len(messages) == 1 + 6 + 1
    assert not caplog.records


def test_trimming_drops_oldest_first_and_logs(caplog):
    history = _turns(10, 2000)  # ~500 tokens per message, far more than fits in 4096
    with caplog.at_level(logging.INFO, logger="app.backend.chat_service"):
        messages = build_messages(history, "newest question", SYSTEM, 4096)
    assert messages[0]["role"] == "system" and messages[0]["content"] == SYSTEM
    assert messages[-1]["content"] == "newest question"
    kept = messages[1:-1]
    assert 0 < len(kept) < len(history)
    # the kept turns are the most recent ones, in order
    assert kept[-1]["content"].startswith("a9")
    assert kept[0]["role"] == "user"
    assert "q0 " not in "".join(m["content"] for m in kept)
    assert any("Context trimmed" in r.getMessage() for r in caplog.records)
    assert "x" * 50 not in "".join(r.getMessage() for r in caplog.records)  # no content logged


def test_huge_latest_message_still_kept():
    messages = build_messages(_turns(2, 10), "z" * 100_000, SYSTEM, 2048)
    assert messages == [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "z" * 100_000}]


def test_estimates():
    assert estimate_tokens("abcd" * 10) == 10
    assert reply_reserve(8192) == 2048
    assert reply_reserve(2048) == 1024


@pytest.fixture
def service(tmp_config):
    return ChatService(InMemoryChatStore(), tmp_config)


def test_service_uses_real_system_prompt_on_send(service):
    chat = service.store.create()
    messages = service.send(chat.id, "write a function")
    assert messages[0] == {"role": "system", "content": load_system_prompt()}
    assert messages[-1] == {"role": "user", "content": "write a function"}
    assert service.store.get(chat.id).title == "Write a function"


def test_regenerate_replaces_reply_and_keeps_system_first(service):
    chat = service.store.create()
    service.send(chat.id, "first")
    service.record_reply(chat.id, "answer one", status="done")
    service.send(chat.id, "second")
    service.record_reply(chat.id, "answer two")
    messages = service.regenerate(chat.id)
    assert messages[0]["role"] == "system"
    assert [m["content"] for m in messages[1:]] == ["first", "answer one", "second"]
    assert [m.role for m in service.store.get(chat.id).messages] == ["user", "assistant", "user"]


def test_retry_without_reply(service):
    chat = service.store.create()
    service.send(chat.id, "question")
    messages = service.regenerate(chat.id)  # used for Retry after an error
    assert messages[0]["role"] == "system" and messages[-1]["content"] == "question"


def test_regenerate_without_user_message_fails(service):
    chat = service.store.create()
    with pytest.raises(StorageError):
        service.regenerate(chat.id)


def test_record_reply_ignores_empty_text(service):
    chat = service.store.create()
    service.send(chat.id, "q")
    service.record_reply(chat.id, "")
    assert len(service.store.get(chat.id).messages) == 1

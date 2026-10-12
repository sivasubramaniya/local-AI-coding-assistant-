import logging

import pytest

from app.backend.chat_service import ChatService, build_messages, estimate_tokens, reply_reserve
from app.backend.memory_store import ChatMessage, InMemoryChatStore
from app.storage.chat_repository import SqliteChatRepository
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


@pytest.fixture(params=["memory", "sqlite"])
def service(request, tmp_config, tmp_path):
    """ChatService must behave identically on both stores."""
    if request.param == "memory":
        store = InMemoryChatStore()
    else:
        store = SqliteChatRepository.open(tmp_path / "chat.db")
    yield ChatService(store, tmp_config)
    store.close()


def test_service_uses_real_system_prompt_on_send(service):
    chat = service.store.create_chat()
    messages = service.send(chat.id, "write a function")
    assert messages[0] == {"role": "system", "content": load_system_prompt()}
    assert messages[-1] == {"role": "user", "content": "write a function"}
    assert service.store.get_chat(chat.id).title == "Write a function"


def test_system_prompt_is_never_stored(service):
    chat = service.store.create_chat()
    service.send(chat.id, "q")
    service.record_reply(chat.id, "a")
    stored = service.store.get_messages(chat.id)
    assert [m.role for m in stored] == ["user", "assistant"]
    assert all(load_system_prompt() not in m.content for m in stored)


def test_history_is_rebuilt_from_the_store(service):
    chat = service.store.create_chat()
    service.send(chat.id, "first")
    service.record_reply(chat.id, "answer one", eval_count=5, tokens_per_sec=2.5)
    messages = service.send(chat.id, "second")
    assert [(m["role"], m["content"]) for m in messages] == [
        ("system", load_system_prompt()), ("user", "first"), ("assistant", "answer one"), ("user", "second"),
    ]
    reply = service.store.get_messages(chat.id)[1]
    assert (reply.eval_count, reply.tokens_per_sec, reply.status) == (5, 2.5, "complete")


def test_regenerate_replaces_reply_and_keeps_system_first(service):
    chat = service.store.create_chat()
    service.send(chat.id, "first")
    service.record_reply(chat.id, "answer one")
    service.send(chat.id, "second")
    service.record_reply(chat.id, "answer two")
    messages = service.regenerate(chat.id)
    assert messages[0]["role"] == "system"
    assert [m["content"] for m in messages[1:]] == ["first", "answer one", "second"]
    # the old reply stays until the new one is recorded, which replaces it
    assert len(service.store.get_messages(chat.id)) == 4
    service.record_reply(chat.id, "answer two, again", replace=True)
    stored = service.store.get_messages(chat.id)
    assert [(m.role, m.content) for m in stored] == [
        ("user", "first"), ("assistant", "answer one"), ("user", "second"), ("assistant", "answer two, again"),
    ]
    assert [m.seq for m in stored] == [1, 2, 3, 4]


def test_retry_without_reply(service):
    chat = service.store.create_chat()
    service.send(chat.id, "question")
    messages = service.regenerate(chat.id)  # used for Retry after an error
    assert messages[0]["role"] == "system" and messages[-1]["content"] == "question"


def test_error_replies_are_stored_but_never_sent_to_the_model(service):
    chat = service.store.create_chat()
    service.send(chat.id, "q1")
    service.record_reply(chat.id, "Ollama is not running.", status="error")
    stopped_chat = service.store.create_chat()
    service.send(stopped_chat.id, "x")
    service.record_reply(stopped_chat.id, "partial", status="stopped")
    assert service.store.get_messages(chat.id)[-1].status == "error"
    messages = service.send(chat.id, "q2")
    assert [m["content"] for m in messages[1:]] == ["q1", "q2"]
    assert service.store.get_messages(stopped_chat.id)[-1].status == "stopped"


def test_regenerate_without_user_message_fails(service):
    chat = service.store.create_chat()
    with pytest.raises(StorageError):
        service.regenerate(chat.id)


def test_record_reply_ignores_empty_text(service):
    chat = service.store.create_chat()
    service.send(chat.id, "q")
    assert service.record_reply(chat.id, "") is None
    assert len(service.store.get_messages(chat.id)) == 1


def test_record_reply_for_deleted_chat_is_ignored(service):
    chat = service.store.create_chat()
    service.send(chat.id, "q")
    service.store.delete_chat(chat.id)
    assert service.record_reply(chat.id, "late answer") is None


def test_invalid_status_is_rejected(service):
    chat = service.store.create_chat()
    service.send(chat.id, "q")
    with pytest.raises(StorageError):
        service.record_reply(chat.id, "a", status="done")



def test_replies_append_by_default_so_nothing_is_lost(service):
    """Regression (REAL app test, Phase 12): plan, summary and test results all follow one request."""
    chat = service.store.create_chat()
    service.send(chat.id, "make a todo app")
    service.record_reply(chat.id, "plan")
    service.record_reply(chat.id, "summary", files=["todo.py"], project_id=None)
    service.record_reply(chat.id, "Exit code 0")
    assert [m.content for m in service.store.get_messages(chat.id)] == [
        "make a todo app", "plan", "summary", "Exit code 0"]
    assert service.store.get_messages(chat.id)[2].files == ["todo.py"]

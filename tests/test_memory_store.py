import pytest

from app.backend.memory_store import ChatMessage, InMemoryChatStore, title_from_prompt
from app.errors import StorageError


def test_create_and_list_most_recent_first():
    store = InMemoryChatStore()
    a = store.create("A")
    b = store.create("B")
    assert [c.id for c in store.list()] == [b.id, a.id]
    store.add_message(a.id, ChatMessage("user", "hi"))
    assert store.list()[0].id == a.id


def test_rename_and_delete():
    store = InMemoryChatStore()
    chat = store.create()
    store.rename(chat.id, "  My   chat ")
    assert store.get(chat.id).title == "My chat"
    store.delete(chat.id)
    assert not store.exists(chat.id)


def test_errors():
    store = InMemoryChatStore()
    with pytest.raises(StorageError):
        store.get("missing")
    chat = store.create()
    with pytest.raises(StorageError):
        store.rename(chat.id, "   ")


def test_title_from_prompt():
    assert title_from_prompt("create a welcome html file") == "Create a welcome html file"
    assert title_from_prompt("") == "New chat"
    assert len(title_from_prompt("x" * 100)) == 40

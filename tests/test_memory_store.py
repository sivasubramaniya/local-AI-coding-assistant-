import pytest

from app.backend.memory_store import ChatMessage, InMemoryChatStore, title_from_prompt
from app.errors import StorageError


def test_create_and_list_most_recent_first():
    store = InMemoryChatStore()
    a = store.create_chat("A")
    b = store.create_chat("B")
    assert [c.id for c in store.list_chats()] == [b.id, a.id]
    store.add_message(a.id, ChatMessage("user", "hi"))
    assert store.list_chats()[0].id == a.id


def test_rename_and_delete():
    store = InMemoryChatStore()
    chat = store.create_chat()
    store.rename_chat(chat.id, "  My   chat ")
    assert store.get_chat(chat.id).title == "My chat"
    store.delete_chat(chat.id)
    assert not store.chat_exists(chat.id)


def test_errors():
    store = InMemoryChatStore()
    with pytest.raises(StorageError):
        store.get_chat("missing")
    chat = store.create_chat()
    with pytest.raises(StorageError):
        store.rename_chat(chat.id, "   ")


def test_returned_objects_are_copies():
    store = InMemoryChatStore()
    chat = store.create_chat()
    store.add_message(chat.id, ChatMessage("user", "hi"))
    store.get_messages(chat.id)[0].content = "changed"
    store.get_chat(chat.id).title = "changed"
    assert store.get_messages(chat.id)[0].content == "hi"
    assert store.get_chat(chat.id).title == "Hi"


def test_title_from_prompt():
    assert title_from_prompt("create a welcome html file") == "Create a welcome html file"
    assert title_from_prompt("") == "New chat"
    assert len(title_from_prompt("x" * 100)) == 40

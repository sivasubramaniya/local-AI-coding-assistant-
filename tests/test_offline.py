"""Offline verification (automated part): everything works with non-loopback networking blocked.

Chat, generation, storage and export run here through real loopback sockets with every
other destination blocked. The model is MOCK (a fake Ollama on 127.0.0.1). The full suite
can also run this way: python -m pytest --offline-guard
"""

import json
import socket

import pytest

from app.agent.project_generator import ProjectGenerator, ProjectWriter
from app.backend.chat_store import ChatMessage
from app.backend.ollama_client import OllamaClient
from app.config import load_config
from app.errors import ConfigError, ModelNotFoundError, OllamaUnavailableError
from app.export.project_exporter import export_zip
from app.storage.chat_repository import SqliteChatRepository
from app.ui.offline_web import is_allowed_url
from tests.fake_ollama import FakeOllama, LoopbackOllama
from tests.offline_guard import OfflineViolation, block_network

PLAN = json.dumps({"project_name": "offline-demo", "description": "d", "language": "Python",
                   "files": [{"path": "app.py", "purpose": "main"}, {"path": "README.md", "purpose": "docs"}],
                   "run_instructions": "python app.py", "test_command": ""})


def _config(tmp_path, url):
    return load_config({"LAA_DATA_DIR": str(tmp_path / "data"), "LAA_EXPORT_DIR": str(tmp_path / "export"),
                        "LAA_OLLAMA_URL": url})


def test_guard_blocks_internet_and_allows_loopback():
    with block_network() as attempts:
        with pytest.raises(OfflineViolation):
            socket.create_connection(("8.8.8.8", 53), timeout=1)
        with pytest.raises(OfflineViolation):
            socket.getaddrinfo("example.com", 443)
        with pytest.raises(OfflineViolation):
            socket.socket().connect(("1.1.1.1", 80))
        socket.getaddrinfo("localhost", 80)  # allowed
    assert attempts == ["8.8.8.8", "example.com", "1.1.1.1"]


def test_chat_generation_storage_and_export_offline(tmp_path):
    fake = FakeOllama()
    with LoopbackOllama(fake) as server, block_network() as attempts:
        config = _config(tmp_path, server.url)
        with OllamaClient(config) as client:
            assert client.ensure_ready() == "0.40.2"
            assert "".join(client.stream_chat([{"role": "user", "content": "hi"}])) == "Hello from the model."

            fake.replies = [PLAN, "```python\nprint('offline')\n```", "````markdown\n# Offline demo\n````"]
            generator = ProjectGenerator(lambda m: "".join(client.stream_chat(m)), "system")
            plan = generator.make_plan("tiny app")
            writer = ProjectWriter(config.projects_dir, plan.project_name)
            result = generator.generate(plan, writer)
        assert result.written == ["app.py", "README.md"]

        repo = SqliteChatRepository.open(config.db_path)
        chat = repo.create_chat()
        repo.add_message(chat.id, ChatMessage("user", "make it"))
        repo.create_project(plan.project_name, str(writer.root), chat.id, result.status)
        repo.close()
        reopened = SqliteChatRepository.open(config.db_path)
        assert reopened.list_projects()[0].status == "complete"
        reopened.close()

        exported = export_zip(writer.root, config.export_dir, plan.project_name)
        assert exported.verified
    assert attempts == []  # nothing tried to leave the machine


def test_ollama_stopped_and_model_missing_give_clear_errors_offline(tmp_path):
    with block_network() as attempts:
        stopped = OllamaClient(_config(tmp_path, "http://127.0.0.1:9"))
        with pytest.raises(OllamaUnavailableError) as info:
            stopped.ensure_ready()
        assert "Ollama is not running" in info.value.message
        stopped.close()
        with LoopbackOllama(FakeOllama(models=["qwen2.5-coder:14b"])) as server:
            with OllamaClient(_config(tmp_path, server.url)) as client:
                with pytest.raises(ModelNotFoundError) as missing:
                    client.ensure_ready()
        assert "qwen2.5-coder-14b:latest is not installed" in missing.value.message
        assert "ollama create qwen2.5-coder-14b -f .\\ollama\\Modelfile" in missing.value.message
    assert attempts == []


def test_remote_ollama_urls_are_refused_before_any_request(tmp_path):
    with block_network() as attempts:
        for url in ("https://api.example.com", "http://192.168.1.10:11434", "http://ollama.internal:11434"):
            with pytest.raises(ConfigError):
                _config(tmp_path, url)
    assert attempts == []


@pytest.mark.parametrize("scheme, host, allowed", [
    ("https", "cdn.jsdelivr.net", False), ("http", "fonts.googleapis.com", False), ("wss", "example.com", False),
    ("ftp", "example.com", False), ("http", "localhost", True), ("http", "127.0.0.1", True),
    ("data", "", True), ("about", "", True), ("file", "", True), ("blob", "", True), ("mailto", "", False),
])
def test_html_preview_blocks_remote_requests(scheme, host, allowed):
    assert is_allowed_url(scheme, host) is allowed


@pytest.mark.gui
def test_window_chat_over_real_loopback_socket_offline(qtbot, themed_app, tmp_path):
    from app.backend.status import ConnectionState
    from app.ui.main_window import MainWindow

    fake = FakeOllama()
    with LoopbackOllama(fake) as server, block_network() as attempts:
        config = _config(tmp_path, server.url)
        repo = SqliteChatRepository.open(config.db_path)
        win = MainWindow(config, store=repo, use_webengine=False)  # the real client factory
        qtbot.addWidget(win)
        win.show()
        qtbot.waitUntil(lambda: win.health().state is ConnectionState.CONNECTED, timeout=10000)
        with qtbot.waitSignal(win.streamFinished, timeout=15000):
            win.submit_prompt("hello offline")
        assert repo.get_messages(win.current_chat_id())[-1].content == "Hello from the model."
        win.close()
        repo.close()
    assert attempts == []


@pytest.mark.gui
def test_webengine_preview_uses_offline_profile(qtbot, themed_app):
    from app.ui.preview_panel import HtmlPreview, webengine_available

    if not webengine_available():
        pytest.skip("QtWebEngine not installed")
    preview = HtmlPreview(use_webengine=True)
    qtbot.addWidget(preview)
    assert preview.page.profile().isOffTheRecord()
    assert preview.page.offline_interceptor is not None

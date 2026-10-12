import threading
import time

import pytest

from app.backend.ollama_client import (
    NdjsonDecoder,
    OllamaClient,
    StreamStats,
    close_matches,
    create_command,
)
from app.config import load_config
from app.errors import ModelNotFoundError, OllamaUnavailableError
from tests.fake_ollama import MODEL, FakeOllama, StallingServer, content_line, done_line

MESSAGES = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
CREATE_CMD = r"ollama create qwen2.5-coder-14b -f .\ollama\Modelfile"


@pytest.fixture
def config(tmp_path):
    return load_config({"LAA_DATA_DIR": str(tmp_path), "LAA_EXPORT_DIR": str(tmp_path)})


@pytest.fixture
def fake():
    return FakeOllama()


@pytest.fixture
def client(config, fake):
    with OllamaClient(config, transport=fake.transport()) as c:
        yield c


# --- health -----------------------------------------------------------------
def test_version_and_tags(client):
    assert client.get_version() == "0.40.2"
    assert client.list_models() == [MODEL]
    assert client.has_model() is True
    assert client.ensure_ready() == "0.40.2"


def test_exact_match_only_no_fallback(config, fake):
    fake.models = ["qwen2.5-coder:14b", "llama3:8b"]
    with OllamaClient(config, transport=fake.transport()) as client:
        assert client.has_model() is False
        with pytest.raises(ModelNotFoundError) as info:
            client.ensure_ready()
    message = info.value.message
    assert "qwen2.5-coder-14b:latest is not installed" in message
    assert "qwen2.5-coder:14b" in message  # listed as a close match ...
    assert "not used automatically" in message  # ... but never used
    assert "from the project folder" in message and CREATE_CMD in message
    assert "/api/chat" not in fake.paths()


def test_create_command_built_from_config(tmp_path):
    cfg = load_config({"LAA_DATA_DIR": str(tmp_path), "LAA_EXPORT_DIR": str(tmp_path),
                       "LAA_MODEL_NAME": "my-coder:latest"})
    assert create_command(cfg) == r"ollama create my-coder -f .\ollama\Modelfile"


def test_ensure_ready_only_calls_version_and_tags(client, fake):
    client.ensure_ready()
    client.has_model()
    fake.models = []
    with pytest.raises(ModelNotFoundError):
        client.ensure_ready()
    assert set(fake.paths()) <= {"/api/version", "/api/tags"}
    assert "/api/chat" not in fake.paths() and "/api/generate" not in fake.paths()


def test_close_matches():
    found = close_matches(MODEL, ["qwen2.5-coder:14b", "llama3:8b", "qwen2.5-coder:7b"])
    assert found[0] == "qwen2.5-coder:14b"
    assert "llama3:8b" not in found


# --- error mapping -------------------------------------------------------------
def test_connect_error_maps_to_unavailable(client, fake):
    fake.down = True
    with pytest.raises(OllamaUnavailableError) as info:
        client.get_version()
    assert "Ollama is not running" in info.value.message


def test_timeout_maps_to_too_slow(client, fake):
    fake.timeout = True
    with pytest.raises(OllamaUnavailableError) as info:
        client.chat(MESSAGES)
    assert "took too long" in info.value.message


def test_404_maps_to_model_not_found(config, fake):
    fake.chat_status = 404
    fake.chat_error = 'model "qwen2.5-coder-14b:latest" not found, try pulling it first'
    with OllamaClient(config, transport=fake.transport()) as client:
        with pytest.raises(ModelNotFoundError) as info:
            list(client.stream_chat(MESSAGES))
    assert CREATE_CMD in info.value.message


def test_server_error_is_reported(client, fake):
    fake.chat_status = 500
    fake.chat_error = "CUDA out of memory"
    with pytest.raises(OllamaUnavailableError) as info:
        client.chat(MESSAGES)
    assert info.value.message == "Ollama reported an error: CUDA out of memory"


# --- chat / options --------------------------------------------------------------
def test_chat_non_streaming(client, fake):
    assert client.chat(MESSAGES) == "Hello from the model."
    body = fake.chat_bodies()[-1]
    assert body["stream"] is False


def test_options_sent_on_every_request(client, fake, config):
    client.chat(MESSAGES)
    list(client.stream_chat(MESSAGES))
    bodies = fake.chat_bodies()
    assert [b["stream"] for b in bodies] == [False, True]
    for body in bodies:
        assert body["model"] == config.model_name
        assert body["keep_alive"] == "10m"
        assert body["options"] == {"temperature": 0.2, "top_p": 0.8, "num_ctx": 8192}
        assert body["messages"] == MESSAGES


# --- streaming ---------------------------------------------------------------------
def test_stream_multi_chunk_and_stats(client):
    pieces = list(client.stream_chat(MESSAGES))
    assert "".join(pieces) == "Hello from the model."
    assert client.last_stats == StreamStats(42, 2_000_000_000, 2_500_000_000, 120, 300_000_000)
    assert client.last_stats.tokens_per_second == pytest.approx(21.0)


def test_stream_lines_split_across_chunks(client, fake):
    data = content_line("ab") + content_line("cd") + done_line()
    # cut in awkward places, including inside a JSON object and inside a multi-byte char
    data = data.replace(b'"cd"', '"cé"'.encode())
    fake.raw_chunks = [data[:7], data[7:40], data[40:41], data[41:90], data[90:]]
    assert "".join(client.stream_chat(MESSAGES)) == "ab" + "cé"
    assert client.last_stats is not None


def test_error_chunk_inside_stream(client, fake):
    fake.raw_chunks = [content_line("partial"), b'{"error":"model runner has unexpectedly stopped"}\n']
    received = []
    with pytest.raises(OllamaUnavailableError) as info:
        for piece in client.stream_chat(MESSAGES):
            received.append(piece)
    assert received == ["partial"]
    assert "unexpectedly stopped" in info.value.message


def test_stream_without_done_is_an_error(client, fake):
    fake.raw_chunks = [content_line("x")]
    with pytest.raises(OllamaUnavailableError) as info:
        list(client.stream_chat(MESSAGES))
    assert "ended unexpectedly" in info.value.message


def test_cancel_mid_stream_stops_iteration(client, fake):
    fake.tokens = [f"t{i} " for i in range(200)]
    fake.chunk_delay_s = 0.002
    cancel = threading.Event()
    received = []
    for piece in client.stream_chat(MESSAGES, cancel):
        received.append(piece)
        if len(received) == 5:
            cancel.set()
    assert len(received) == 5
    assert client.last_stats is None


def test_ndjson_decoder_flush():
    decoder = NdjsonDecoder()
    assert decoder.feed(b'{"a": 1}\n{"b"') == [{"a": 1}]
    assert decoder.feed(b": 2}") == []
    assert decoder.flush() == [{"b": 2}]
    with pytest.raises(OllamaUnavailableError):
        NdjsonDecoder().feed(b"not json\n")


# --- abort over a real socket ---------------------------------------------------
def test_abort_unblocks_a_stalled_stream_and_keeps_client_usable(tmp_path):
    with StallingServer() as server:
        cfg = load_config({"LAA_DATA_DIR": str(tmp_path), "LAA_EXPORT_DIR": str(tmp_path),
                           "LAA_OLLAMA_URL": server.url})
        client = OllamaClient(cfg)
        received: list[str] = []
        errors: list[Exception] = []
        ended = threading.Event()

        def consume():
            try:
                for piece in client.stream_chat(MESSAGES):
                    received.append(piece)
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(exc)
            finally:
                ended.set()

        thread = threading.Thread(target=consume, daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while not received and time.monotonic() < deadline:
            time.sleep(0.01)
        assert received == ["first"]  # now the server stalls

        started = time.monotonic()
        client.abort()
        assert ended.wait(2.0), "stream did not stop after abort()"
        assert time.monotonic() - started < 1.0
        assert errors == []
        # abort closed only the stream response: other requests still work on this client
        assert client.ensure_ready() == "0.40.2"
        client.close()


def test_packaged_build_points_at_bundled_modelfile(tmp_path, monkeypatch):
    import sys

    from app.backend.ollama_client import create_hint

    cfg = load_config({"LAA_DATA_DIR": str(tmp_path), "LAA_EXPORT_DIR": str(tmp_path)})
    assert create_hint(cfg) == f"Run this from the project folder: {CREATE_CMD}"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", r"C:\Apps\LocalAIAssistant\_internal", raising=False)
    assert create_hint(cfg) == ('Run this in PowerShell: ollama create qwen2.5-coder-14b -f '
                                '"C:\Apps\LocalAIAssistant\_internal\docs\Modelfile"')

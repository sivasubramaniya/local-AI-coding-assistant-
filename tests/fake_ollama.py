"""Test doubles for the Ollama API: a scripted MockTransport and a tiny real-socket server."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

MODEL = "qwen2.5-coder-14b:latest"
DONE_STATS = {
    "eval_count": 42,
    "eval_duration": 2_000_000_000,  # 2 s -> 21.0 tok/s
    "total_duration": 2_500_000_000,
    "prompt_eval_count": 120,
    "load_duration": 300_000_000,
}


def content_line(text: str) -> bytes:
    return json.dumps({"model": MODEL, "message": {"role": "assistant", "content": text}, "done": False}).encode() + b"\n"


def done_line(stats: dict | None = None) -> bytes:
    payload = {"model": MODEL, "message": {"role": "assistant", "content": ""}, "done": True,
               "done_reason": "stop", **(stats or DONE_STATS)}
    return json.dumps(payload).encode() + b"\n"


def stream_bytes(tokens: list[str], stats: dict | None = None) -> list[bytes]:
    return [content_line(t) for t in tokens] + [done_line(stats)]


class FakeOllama:
    """Scripted Ollama. Change attributes between calls to simulate recovery or failures."""

    def __init__(self, models: list[str] | None = None, tokens: list[str] | None = None) -> None:
        self.models = list(models) if models is not None else [MODEL]
        self.version = "0.40.2"
        self.tokens = tokens if tokens is not None else ["Hello", " from", " the", " model."]
        self.raw_chunks: list[bytes] | None = None  # overrides tokens when set
        self.chunk_delay_s = 0.0
        self.down = False
        self.timeout = False
        self.chat_status: int | None = None
        self.chat_error: str | None = None
        self.requests: list[tuple[str, str, dict | None]] = []
        self._lock = threading.Lock()

    # --- inspection ------------------------------------------------------------
    def paths(self) -> list[str]:
        with self._lock:
            return [path for _method, path, _body in self.requests]

    def chat_bodies(self) -> list[dict]:
        with self._lock:
            return [body for _m, path, body in self.requests if path == "/api/chat" and body]

    # --- transport ---------------------------------------------------------------
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def _chunks(self):
        chunks = self.raw_chunks if self.raw_chunks is not None else stream_bytes(self.tokens)
        for chunk in chunks:
            if self.chunk_delay_s:
                time.sleep(self.chunk_delay_s)
            yield chunk

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        with self._lock:
            self.requests.append((request.method, path, body))
        if self.down:
            raise httpx.ConnectError("[WinError 10061] connection refused", request=request)
        if self.timeout:
            raise httpx.ReadTimeout("timed out", request=request)
        if path == "/api/version":
            return httpx.Response(200, json={"version": self.version})
        if path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m, "model": m} for m in self.models]})
        if path == "/api/chat":
            if self.chat_status:
                return httpx.Response(self.chat_status, json={"error": self.chat_error or "failure"})
            if body["model"] not in self.models:
                return httpx.Response(404, json={"error": f'model "{body["model"]}" not found, try pulling it first'})
            if body.get("stream"):
                return httpx.Response(200, content=self._chunks(),
                                      headers={"content-type": "application/x-ndjson"})
            return httpx.Response(200, json={"model": body["model"], "done": True,
                                             "message": {"role": "assistant", "content": "".join(self.tokens)},
                                             **DONE_STATS})
        return httpx.Response(404, json={"error": "not found"})


class StallingServer:
    """Real HTTP server on 127.0.0.1 whose /api/chat sends one chunk, then stalls.

    Used to prove that abort() unblocks a read that is waiting for the next chunk.
    """

    def __init__(self, stall_s: float = 30.0) -> None:
        stall = stall_s
        release = threading.Event()
        self.release = release

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *args):  # keep test output quiet
                pass

            def _json(self, payload: dict) -> None:
                data = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802
                if self.path == "/api/version":
                    self._json({"version": "0.40.2"})
                elif self.path == "/api/tags":
                    self._json({"models": [{"name": MODEL}]})
                else:
                    self.send_error(404)

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                self.rfile.read(length)
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                try:
                    self.wfile.write(content_line("first"))
                    self.wfile.flush()
                    release.wait(stall)  # simulate a model that stops sending
                except OSError:
                    pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> StallingServer:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.release.set()
        self._server.shutdown()
        self._server.server_close()

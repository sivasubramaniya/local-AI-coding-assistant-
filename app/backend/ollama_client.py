"""Synchronous client for the local Ollama HTTP API (call it from worker threads).

Safety rules enforced here:
- Only the client's ``model`` is ever sent: ``config.model_name`` (default) or, when the user
  selected Fast mode for the chat, ``config.fast_model_name``. There is no fallback model.
- The base URL comes from config, which only allows loopback hosts.
- Proxy environment variables are ignored (``trust_env=False``).
- Prompt and code content is never logged; DEBUG logs carry sizes and counts only.
"""

from __future__ import annotations

import difflib
import json
import logging
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass

import httpx

from app.config import AppConfig, model_options
from app.errors import AppError, ModelNotFoundError, OllamaUnavailableError

logger = logging.getLogger(__name__)

MODELFILE_PATH = r".\ollama\Modelfile"
FAST_MODELFILE_PATH = r".\ollama\Modelfile.fast"


def modelfile_path(fast: bool = False) -> str:
    """The Modelfile to use: the bundled copy in a packaged build, else the project's ollama folder."""
    name = "Modelfile.fast" if fast else "Modelfile"
    bundle_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and bundle_root:
        return f'"{bundle_root}\\docs\\{name}"'
    return FAST_MODELFILE_PATH if fast else MODELFILE_PATH


def create_command(config: AppConfig, model: str | None = None) -> str:
    """The command that creates ``model`` (default: the main model) from its Modelfile."""
    model = model or config.model_name
    fast = model == config.fast_model_name
    return f"ollama create {model.removesuffix(':latest')} -f {modelfile_path(fast)}"


def create_hint(config: AppConfig, model: str | None = None) -> str:
    where = "in PowerShell" if getattr(sys, "frozen", False) else "from the project folder"
    return f"Run this {where}: {create_command(config, model)}"


@dataclass(frozen=True)
class StreamStats:
    eval_count: int = 0
    eval_duration_ns: int = 0
    total_duration_ns: int = 0
    prompt_eval_count: int = 0
    load_duration_ns: int = 0

    @classmethod
    def from_chunk(cls, chunk: dict) -> StreamStats:
        return cls(
            eval_count=int(chunk.get("eval_count") or 0),
            eval_duration_ns=int(chunk.get("eval_duration") or 0),
            total_duration_ns=int(chunk.get("total_duration") or 0),
            prompt_eval_count=int(chunk.get("prompt_eval_count") or 0),
            load_duration_ns=int(chunk.get("load_duration") or 0),
        )

    @property
    def tokens_per_second(self) -> float:
        if self.eval_duration_ns <= 0:
            return 0.0
        return self.eval_count / (self.eval_duration_ns / 1e9)


class NdjsonDecoder:
    """Incremental newline-delimited JSON decoder; tolerates lines split across chunks."""

    def __init__(self) -> None:
        self._buffer = b""

    def feed(self, chunk: bytes) -> list[dict]:
        self._buffer += chunk
        *lines, self._buffer = self._buffer.split(b"\n")
        return [self._parse(line) for line in lines if line.strip()]

    def flush(self) -> list[dict]:
        rest, self._buffer = self._buffer, b""
        return [self._parse(rest)] if rest.strip() else []

    @staticmethod
    def _parse(line: bytes) -> dict:
        try:
            value = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise OllamaUnavailableError(
                "Ollama sent a response that could not be read.", detail=f"bad NDJSON line: {exc}"
            ) from None
        if not isinstance(value, dict):
            raise OllamaUnavailableError("Ollama sent an unexpected response.", detail=f"type {type(value).__name__}")
        return value


def _normalize(name: str) -> str:
    return name.lower().removesuffix(":latest").replace(":", "").replace("-", "").replace("_", "")


def close_matches(name: str, available: list[str]) -> list[str]:
    """Installed models whose names look like ``name`` (for the error message only)."""
    target = _normalize(name)
    family = target.split("coder")[0] if "coder" in target else target[:6]
    found = [m for m in available if _normalize(m) == target or (family and _normalize(m).startswith(family))]
    for match in difflib.get_close_matches(name, available, n=3, cutoff=0.5):
        if match not in found:
            found.append(match)
    return found[:5]


def _error_text(response: httpx.Response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict) and data.get("error"):
            return str(data["error"])
    except ValueError:
        pass
    return response.text[:300] or f"HTTP {response.status_code}"


def _is_model_missing(message: str) -> bool:
    text = message.lower()
    return "not found" in text and "model" in text


class OllamaClient:
    """One client per worker. ``abort()`` closes only the active stream response."""

    def __init__(self, config: AppConfig, transport: httpx.BaseTransport | None = None,
                 model: str | None = None) -> None:
        self.config = config
        # The one model this client sends. Chosen by the caller (the chat's selection); never changed here.
        self.model = model or config.model_name
        self.last_stats: StreamStats | None = None
        self._lock = threading.Lock()
        self._active: httpx.Response | None = None
        self._abort_requested = threading.Event()
        timeout = httpx.Timeout(
            connect=config.connect_timeout_s,
            read=config.request_timeout_s,
            write=30.0,
            pool=config.connect_timeout_s,
        )
        self._http = httpx.Client(base_url=config.ollama_url, timeout=timeout, transport=transport, trust_env=False)

    # --- helpers -------------------------------------------------------------
    def _unavailable(self, exc: Exception) -> OllamaUnavailableError:
        return OllamaUnavailableError(
            f"Ollama is not running at {self.config.ollama_url}. Start Ollama and try again.",
            detail=f"{type(exc).__name__}: {exc}",
        )

    def _too_slow(self, seconds: float, exc: Exception) -> OllamaUnavailableError:
        return OllamaUnavailableError(
            f"The model took too long to respond (no output for {seconds:.0f} s). "
            "It may still be loading, or the computer is busy. Try again.",
            detail=f"{type(exc).__name__}: {exc}",
        )

    def model_missing_error(self, available: list[str] | None = None, model: str | None = None) -> ModelNotFoundError:
        name = model or self.model
        if available is None:
            try:
                available = self.list_models()
            except AppError:
                available = []
        matches = close_matches(name, available)
        parts = [f"Model {name} is not installed in Ollama."]
        if matches:
            parts.append(f"Similar installed models: {', '.join(matches)} (not used automatically).")
        parts.append(create_hint(self.config, name))
        return ModelNotFoundError(" ".join(parts), detail=f"installed: {', '.join(available) or 'none'}")

    def _check_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        message = _error_text(response)
        if response.status_code == 404 or _is_model_missing(message):
            raise self.model_missing_error()
        raise OllamaUnavailableError(f"Ollama reported an error: {message}", detail=f"HTTP {response.status_code}")

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.ConnectTimeout as exc:
            raise self._unavailable(exc) from None
        except httpx.TimeoutException as exc:
            raise self._too_slow(self.config.request_timeout_s, exc) from None
        except httpx.HTTPError as exc:
            raise self._unavailable(exc) from None
        self._check_status(response)
        return response

    def _payload(self, messages: list[dict], stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "keep_alive": self.config.keep_alive,
            "options": model_options(self.config),
        }

    # --- health (only /api/version and /api/tags) ------------------------------
    def _health_timeout(self) -> httpx.Timeout:
        seconds = max(5.0, self.config.connect_timeout_s)
        return httpx.Timeout(seconds, connect=self.config.connect_timeout_s)

    def get_version(self) -> str:
        response = self._request("GET", "/api/version", timeout=self._health_timeout())
        return str(response.json().get("version", "unknown"))

    def list_models(self) -> list[str]:
        data = self._request("GET", "/api/tags", timeout=self._health_timeout()).json()
        return [m.get("name") or m.get("model") for m in data.get("models", []) if m.get("name") or m.get("model")]

    def has_model(self, name: str | None = None) -> bool:
        """Exact match, tag included. 'qwen2.5-coder:14b' does not count as 'qwen2.5-coder-14b:latest'."""
        return (name or self.model) in self.list_models()

    def ensure_ready(self) -> str:
        """Check Ollama and this client's exact model without loading it. Returns the Ollama version."""
        version = self.get_version()
        models = self.list_models()
        if self.model not in models:
            raise self.model_missing_error(models)
        return version

    def check_models(self) -> tuple[str, dict[str, bool]]:
        """Version plus presence of BOTH configured models (only /api/version and /api/tags)."""
        version = self.get_version()
        installed = set(self.list_models())
        names = (self.config.model_name, self.config.fast_model_name)
        return version, {name: name in installed for name in names}

    # --- chat ------------------------------------------------------------------
    def chat(self, messages: list[dict]) -> str:
        logger.debug("chat request: %d messages", len(messages))
        response = self._request("POST", "/api/chat", json=self._payload(messages, stream=False))
        data = response.json()
        if data.get("error"):
            self._raise_stream_error(str(data["error"]))
        self.last_stats = StreamStats.from_chunk(data)
        return str(data.get("message", {}).get("content", ""))

    def _raise_stream_error(self, message: str) -> None:
        if _is_model_missing(message):
            raise self.model_missing_error()
        raise OllamaUnavailableError(f"Ollama reported an error: {message}")

    def stream_chat(self, messages: list[dict], cancel_event: threading.Event | None = None) -> Iterator[str]:
        """Yield content pieces as they arrive. Stops quietly when cancelled or aborted."""
        cancel_event = cancel_event or threading.Event()
        self.last_stats = None
        self._abort_requested.clear()
        stream_timeout = httpx.Timeout(
            connect=self.config.connect_timeout_s,
            read=self.config.stream_read_timeout_s,
            write=30.0,
            pool=self.config.connect_timeout_s,
        )
        request = self._http.build_request(
            "POST", "/api/chat", json=self._payload(messages, stream=True), timeout=stream_timeout
        )
        logger.debug("stream request: %d messages", len(messages))

        def cancelled() -> bool:
            return cancel_event.is_set() or self._abort_requested.is_set()

        try:
            response = self._http.send(request, stream=True)
        except httpx.ConnectTimeout as exc:
            raise self._unavailable(exc) from None
        except httpx.TimeoutException as exc:
            raise self._too_slow(self.config.stream_read_timeout_s, exc) from None
        except httpx.HTTPError as exc:
            raise self._unavailable(exc) from None

        with self._lock:
            self._active = response
        try:
            if response.status_code >= 400:
                response.read()
                self._check_status(response)
            decoder = NdjsonDecoder()
            pieces = 0
            for chunk in response.iter_raw():
                if cancelled():
                    logger.debug("stream cancelled after %d pieces", pieces)
                    return
                for item in decoder.feed(chunk):
                    if item.get("error"):
                        self._raise_stream_error(str(item["error"]))
                    content = (item.get("message") or {}).get("content") or ""
                    if content:
                        pieces += 1
                        yield content
                        if cancelled():
                            return
                    if item.get("done"):
                        self.last_stats = StreamStats.from_chunk(item)
                        logger.debug("stream done: %d pieces, eval_count=%d", pieces, self.last_stats.eval_count)
                        return
            for item in decoder.flush():
                if item.get("error"):
                    self._raise_stream_error(str(item["error"]))
                if item.get("done"):
                    self.last_stats = StreamStats.from_chunk(item)
                    return
            if cancelled():
                return
            raise OllamaUnavailableError("The response from Ollama ended unexpectedly. Try again.")
        except httpx.TimeoutException as exc:
            if cancelled():
                return
            raise self._too_slow(self.config.stream_read_timeout_s, exc) from None
        except (httpx.HTTPError, OSError) as exc:
            if cancelled():
                return
            raise OllamaUnavailableError(
                "The connection to Ollama was lost while the answer was streaming.",
                detail=f"{type(exc).__name__}: {exc}",
            ) from None
        finally:
            with self._lock:
                self._active = None
            response.close()

    def abort(self) -> None:
        """Close the active stream response (thread-safe). Other requests are not affected."""
        with self._lock:
            response = self._active
        if response is not None:
            self._abort_requested.set()
            try:
                response.close()
            except Exception:  # closing from another thread may race with the reader; that's fine
                logger.debug("abort: close raised", exc_info=True)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

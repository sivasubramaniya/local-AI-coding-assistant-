"""Background worker pattern: a QObject moved to a QThread, talking through signals.

Rules:
- Workers never touch widgets. They only emit signals.
- Connect worker signals to bound methods of QObjects that live in the UI thread
  (not to lambdas), so Qt queues the calls onto the UI thread.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot

from app.backend.ollama_client import OllamaClient
from app.backend.status import ConnectionState, HealthResult
from app.errors import AppError, ModelNotFoundError, OllamaUnavailableError

logger = logging.getLogger(__name__)


class StreamWorker(QObject):
    """Base class. Subclasses implement ``work()`` and emit ``token`` as they go."""

    token = Signal(str)
    finished = Signal(object)
    error = Signal(object)  # always an AppError
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def work(self) -> object:  # pragma: no cover - abstract
        raise NotImplementedError

    @Slot()
    def run(self) -> None:
        try:
            result = self.work()
        except AppError as exc:
            logger.warning("Worker %s: %s", type(self).__name__, exc.full_text())
            self.error.emit(exc)
            return
        except Exception as exc:  # report every failure to the UI instead of dying silently
            logger.exception("Worker %s failed", type(self).__name__)
            self.error.emit(AppError(f"Something went wrong: {exc or type(exc).__name__}", detail=repr(exc)))
            return
        if self.is_cancelled():
            self.cancelled.emit()
        else:
            self.finished.emit(result)


@dataclass(eq=False)
class WorkerHandle:
    thread: QThread
    worker: StreamWorker

    def cancel(self) -> None:
        self.worker.cancel()

    def wait(self, timeout_ms: int = 5000) -> bool:
        return self.thread.wait(timeout_ms)

    def is_running(self) -> bool:
        return self.thread.isRunning()


class _Reaper(QObject):
    """Lives in the UI thread and keeps every worker/thread alive until its thread has ended.

    Python owns the worker objects. Dropping the last reference while the thread is still
    running (or also calling deleteLater) frees the C++ object twice or too early and crashes
    the process. The reaper releases a handle only after its thread has fully finished.
    """

    def __init__(self) -> None:
        super().__init__()
        self.live: set[WorkerHandle] = set()

    def add(self, handle: WorkerHandle) -> None:
        self.live.add(handle)

    @Slot()
    def collect(self) -> None:
        for handle in list(self.live):
            try:
                done = handle.thread.isFinished()
                if done:
                    handle.thread.wait(100)
            except RuntimeError:  # the C++ thread was already deleted with its parent
                done = True
            if done:
                self.live.discard(handle)


_reaper: _Reaper | None = None


def _get_reaper() -> _Reaper:
    global _reaper
    if _reaper is None:
        _reaper = _Reaper()
    return _reaper


def live_worker_count() -> int:
    return len(_get_reaper().live)


def start_worker(worker: StreamWorker, parent: QObject | None = None) -> WorkerHandle:
    """Move ``worker`` to a new QThread and start it. Call from the UI thread."""
    reaper = _get_reaper()
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    # Direct connection: quit() runs in the worker thread right away (QThread.quit is
    # thread-safe). A queued quit would wait for the UI thread, so a UI-side wait() would hang.
    direct = Qt.ConnectionType.DirectConnection
    worker.finished.connect(thread.quit, direct)
    worker.error.connect(thread.quit, direct)
    worker.cancelled.connect(thread.quit, direct)
    thread.finished.connect(reaper.collect)  # queued to the UI thread
    handle = WorkerHandle(thread, worker)
    reaper.add(handle)
    thread.start()
    return handle


_TOKEN_RE = re.compile(r"\s*\S+|\s+")


def split_tokens(text: str) -> list[str]:
    """Split text into word-sized pieces that join back to the original text."""
    return _TOKEN_RE.findall(text)


class FakeStreamWorker(StreamWorker):
    """DEMO ONLY. Streams canned text at about 25 tokens per second.

    Used only with ``python main.py --demo`` and in screenshot mode. It never contacts a model.
    """

    def __init__(self, text: str, files: list[str] | None = None, delay_s: float = 0.04) -> None:
        super().__init__()
        self._text = text
        self._files = list(files or [])
        self._delay_s = delay_s

    def work(self) -> object:
        streamed: list[str] = []
        for piece in split_tokens(self._text):
            if self.is_cancelled():
                return None
            self.token.emit(piece)
            streamed.append(piece)
            if self._delay_s:
                time.sleep(self._delay_s)
        return {"text": "".join(streamed), "files": self._files}


class OllamaStreamWorker(StreamWorker):
    """Streams one chat answer from the local model. Owns its OllamaClient."""

    def __init__(self, client: OllamaClient, messages: list[dict]) -> None:
        super().__init__()
        self._client = client
        self._messages = messages
        self._partial: list[str] = []

    def partial_text(self) -> str:
        return "".join(self._partial)

    def cancel(self) -> None:
        super().cancel()
        self._client.abort()  # unblocks a read that is waiting for the next chunk

    def work(self) -> object:
        try:
            for piece in self._client.stream_chat(self._messages, self._cancel_event):
                if self.is_cancelled():
                    break
                self._partial.append(piece)
                self.token.emit(piece)
            if self.is_cancelled():
                return None
            return {"text": self.partial_text(), "stats": self._client.last_stats}
        finally:
            self._client.close()


class HealthCheckWorker(StreamWorker):
    """Runs ensure_ready() (only /api/version and /api/tags) and reports a HealthResult."""

    def __init__(self, client: OllamaClient) -> None:
        super().__init__()
        self._client = client

    def work(self) -> object:
        try:
            version = self._client.ensure_ready()
            name = self._client.config.model_name
            return HealthResult(ConnectionState.CONNECTED, f"Ollama {version} · {name} is ready", version)
        except ModelNotFoundError as exc:
            return HealthResult(ConnectionState.MODEL_MISSING, exc.message)
        except OllamaUnavailableError as exc:
            return HealthResult(ConnectionState.DISCONNECTED, exc.message)
        finally:
            self._client.close()

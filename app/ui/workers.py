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

logger = logging.getLogger(__name__)


class StreamWorker(QObject):
    """Base class. Subclasses implement ``work()`` and emit ``token`` as they go."""

    token = Signal(str)
    finished = Signal(object)
    error = Signal(str)
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
        except Exception as exc:  # report every failure to the UI instead of dying silently
            logger.exception("Worker %s failed", type(self).__name__)
            self.error.emit(str(exc) or type(exc).__name__)
            return
        if self.is_cancelled():
            self.cancelled.emit()
        else:
            self.finished.emit(result)


@dataclass
class WorkerHandle:
    thread: QThread
    worker: StreamWorker

    def cancel(self) -> None:
        self.worker.cancel()

    def wait(self, timeout_ms: int = 5000) -> bool:
        return self.thread.wait(timeout_ms)

    def is_running(self) -> bool:
        return self.thread.isRunning()


def start_worker(worker: StreamWorker, parent: QObject | None = None) -> WorkerHandle:
    """Move ``worker`` to a new QThread, start it, and clean both up when done."""
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    # Direct connection: quit() runs in the worker thread right away (QThread.quit is
    # thread-safe). A queued quit would wait for the UI thread, so a UI-side wait() would hang.
    direct = Qt.ConnectionType.DirectConnection
    worker.finished.connect(thread.quit, direct)
    worker.error.connect(thread.quit, direct)
    worker.cancelled.connect(thread.quit, direct)
    thread.finished.connect(worker.deleteLater)
    thread.start()
    return WorkerHandle(thread, worker)


_TOKEN_RE = re.compile(r"\s*\S+|\s+")


def split_tokens(text: str) -> list[str]:
    """Split text into word-sized pieces that join back to the original text."""
    return _TOKEN_RE.findall(text)


class FakeStreamWorker(StreamWorker):
    """DEMO ONLY. Streams canned text at about 25 tokens per second.

    Used in Phase 3 to prove the UI stays responsive. It never contacts a model.
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

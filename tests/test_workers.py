import pytest
from PySide6.QtCore import QObject, QTimer, Slot

from app.ui.workers import FakeStreamWorker, StreamWorker, split_tokens, start_worker

pytestmark = pytest.mark.gui


class Receiver(QObject):
    """Lives in the UI thread, so worker signals reach it queued, like real widgets."""

    def __init__(self, worker: StreamWorker):
        super().__init__()
        self.tokens: list[str] = []
        self.result = None
        self.errors: list[str] = []
        self.was_cancelled = False
        worker.token.connect(self.on_token)
        worker.finished.connect(self.on_finished)
        worker.error.connect(self.on_error)
        worker.cancelled.connect(self.on_cancelled)

    @property
    def done(self) -> bool:
        return self.result is not None or bool(self.errors) or self.was_cancelled

    @Slot(str)
    def on_token(self, token):
        self.tokens.append(token)

    @Slot(object)
    def on_finished(self, result):
        self.result = result

    @Slot(str)
    def on_error(self, message):
        self.errors.append(message)

    @Slot()
    def on_cancelled(self):
        self.was_cancelled = True


def test_split_tokens_round_trip():
    text = "Hello  world\n\n```py\nx = 1\n```\n"
    assert "".join(split_tokens(text)) == text


def test_fake_worker_streams_all_tokens(qtbot):
    text = "one two three four five"
    worker = FakeStreamWorker(text, ["a.html"], delay_s=0.0)
    receiver = Receiver(worker)
    handle = start_worker(worker)
    qtbot.waitUntil(lambda: receiver.done, timeout=5000)
    assert handle.wait(2000)
    assert receiver.result == {"text": text, "files": ["a.html"]}
    assert "".join(receiver.tokens) == text


def test_fake_worker_cancel(qtbot):
    worker = FakeStreamWorker("word " * 500, delay_s=0.01)
    receiver = Receiver(worker)
    handle = start_worker(worker)
    QTimer.singleShot(50, lambda: handle.cancel())  # runs in the UI thread
    qtbot.waitUntil(lambda: receiver.done, timeout=5000)
    assert receiver.was_cancelled and receiver.result is None
    assert handle.wait(2000)
    assert 0 < len(receiver.tokens) < 500


def test_wait_after_cancel_returns_quickly(qtbot):
    worker = FakeStreamWorker("word " * 500, delay_s=0.01)
    handle = start_worker(worker)
    qtbot.wait(30)
    handle.cancel()
    assert handle.wait(1000), "thread did not stop within 1 s of cancel()"


class _FailingWorker(StreamWorker):
    def work(self):
        raise RuntimeError("boom")


def test_worker_error_is_reported(qtbot):
    worker = _FailingWorker()
    receiver = Receiver(worker)
    handle = start_worker(worker)
    qtbot.waitUntil(lambda: receiver.done, timeout=5000)
    assert receiver.errors == ["boom"]
    assert handle.wait(2000)


def test_ui_thread_stays_responsive_while_streaming(qtbot):
    ticks = []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start()
    worker = FakeStreamWorker("token " * 40, delay_s=0.01)  # about 0.4 s of streaming
    receiver = Receiver(worker)
    handle = start_worker(worker)
    qtbot.waitUntil(lambda: receiver.done, timeout=5000)
    timer.stop()
    assert handle.wait(2000)
    assert len(ticks) >= 10, f"UI timer fired only {len(ticks)} times"

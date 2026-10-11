import pytest

from app.errors import (
    AppError,
    CommandRejectedError,
    ConfigError,
    ExportError,
    ModelNotFoundError,
    OllamaUnavailableError,
    PathValidationError,
    StorageError,
)

SUBCLASSES = [
    ConfigError,
    OllamaUnavailableError,
    ModelNotFoundError,
    StorageError,
    PathValidationError,
    CommandRejectedError,
    ExportError,
]


@pytest.mark.parametrize("cls", SUBCLASSES)
def test_subclasses_inherit_app_error(cls):
    assert issubclass(cls, AppError)
    assert issubclass(cls, Exception)


@pytest.mark.parametrize("cls", SUBCLASSES)
def test_default_message_is_friendly(cls):
    err = cls()
    assert str(err) == err.message
    assert err.message and err.message != AppError.default_message
    assert err.detail is None


def test_custom_message_and_detail():
    err = ModelNotFoundError("Model qwen2.5-coder-14b:latest not found.", detail="HTTP 404 from /api/show")
    assert str(err) == "Model qwen2.5-coder-14b:latest not found."
    assert err.detail == "HTTP 404 from /api/show"
    assert err.full_text() == "Model qwen2.5-coder-14b:latest not found. (HTTP 404 from /api/show)"


def test_full_text_without_detail():
    assert ExportError("Disk full.").full_text() == "Disk full."


def test_catchable_as_app_error():
    with pytest.raises(AppError):
        raise PathValidationError("Absolute paths are not allowed.")

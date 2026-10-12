"""Application exception hierarchy.

Every error carries a short user-facing ``message`` and an optional technical
``detail`` (for logs and an expandable "details" area in the UI).
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for all expected application errors."""

    default_message = "An unexpected application error occurred."

    def __init__(self, message: str | None = None, detail: str | None = None) -> None:
        self.message: str = message or self.default_message
        self.detail: str | None = detail
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message

    def full_text(self) -> str:
        """Message plus technical detail, for logs."""
        return f"{self.message} ({self.detail})" if self.detail else self.message


class ConfigError(AppError):
    default_message = "The application configuration is invalid."


class OllamaUnavailableError(AppError):
    default_message = "Ollama is not running. Start Ollama and try again."


class ModelNotFoundError(AppError):
    default_message = "The required model is not installed in Ollama."


class StorageError(AppError):
    default_message = "Could not read or write the local database."


class PathValidationError(AppError):
    default_message = "The file path is not allowed."


class CommandRejectedError(AppError):
    default_message = "The command is not on the approved list and was not run."


class ExportError(AppError):
    default_message = "The project could not be exported."


class GenerationError(AppError):
    default_message = "The project could not be generated."


class ResponseFormatError(GenerationError):
    """The model's answer did not follow the required format."""

    default_message = "The model's answer was not in the expected format."


class PatchError(AppError):
    default_message = "The suggested change could not be applied."

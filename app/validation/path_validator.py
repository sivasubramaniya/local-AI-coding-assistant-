"""Path validation for every file the app writes.

All writes of generated or edited files go through ``PathValidator``. A relative path
from the model (or the user) is accepted only if it stays inside the approved root:

- no absolute paths, drive letters (``C:``), UNC paths (``\\\\server``) or rooted paths
- no ``..`` segments, empty segments or ``.`` segments
- no reserved Windows device names (CON, NUL, COM1, LPT1, ...), also with extensions
- no characters Windows forbids (``<>:"|?*``), control characters or NUL bytes
- no segment ending in a space or dot, no overly long segments or paths
- the resolved path must stay under the resolved root, and no existing component
  between the root and the target may be a symlink or junction
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path, PurePosixPath

from app.errors import PathValidationError

MAX_SEGMENT = 120
MAX_RELATIVE = 200
MAX_ABSOLUTE = 250  # stays below the classic Windows MAX_PATH of 260
MAX_NAME = 60

_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$",
             *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10)),
             "COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³"}
_ILLEGAL = set('<>:"|?*')
_DRIVE = re.compile(r"^[A-Za-z]:")
_SAFE_NAME = re.compile(r"[^a-z0-9._-]+")


def _reject(path: str, reason: str) -> PathValidationError:
    return PathValidationError(f"The path '{path}' is not allowed: {reason}.", detail=reason)


def validate_relative_path(raw: str) -> str:
    """Check a relative path and return it normalised with forward slashes."""
    if not isinstance(raw, str) or not raw.strip():
        raise _reject(str(raw), "it is empty")
    path = raw.strip()
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in path):
        raise _reject(path, "it contains control characters")
    if path.startswith(("\\\\", "//")):
        raise _reject(path, "network (UNC) paths are not allowed")
    if path.startswith(("/", "\\")):
        raise _reject(path, "absolute paths are not allowed")
    if _DRIVE.match(path):
        raise _reject(path, "drive letters are not allowed")
    if len(path) > MAX_RELATIVE:
        raise _reject(path, f"it is longer than {MAX_RELATIVE} characters")
    segments = re.split(r"[\\/]", path)
    for segment in segments:
        if segment == "":
            raise _reject(path, "it contains an empty folder name")
        if segment in (".", ".."):
            raise _reject(path, "'.' and '..' are not allowed")
        if set(segment) & _ILLEGAL:
            raise _reject(path, 'it contains a character Windows does not allow (<>:"|?*)')
        if segment[-1] in " .":
            raise _reject(path, "a name cannot end with a space or a dot")
        if len(segment) > MAX_SEGMENT:
            raise _reject(path, f"a name is longer than {MAX_SEGMENT} characters")
        stem = unicodedata.normalize("NFKC", segment).split(".")[0].rstrip(" ").upper()
        if stem in _RESERVED or segment.upper() in _RESERVED:
            raise _reject(path, f"'{segment}' is a reserved Windows device name")
    return "/".join(segments)


def safe_name(name: str, fallback: str = "project") -> str:
    """A folder-safe project name: lowercase letters, digits, '.', '_' and '-'."""
    slug = _SAFE_NAME.sub("-", unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-._")[:MAX_NAME].strip("-._")
    if not slug or slug.split(".")[0].upper() in _RESERVED:
        slug = fallback
    return slug


def _is_link(path: Path) -> bool:
    try:
        return path.is_symlink() or path.is_junction()
    except OSError:
        return True


class PathValidator:
    """Resolves relative paths inside one approved root folder."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def resolve(self, relative: str) -> Path:
        """Absolute path for ``relative`` inside the root, or PathValidationError."""
        clean = validate_relative_path(relative)
        target = self.root.joinpath(*PurePosixPath(clean).parts)
        if len(str(target)) > MAX_ABSOLUTE:
            raise _reject(clean, f"the full path would be longer than {MAX_ABSOLUTE} characters")
        current = self.root
        for part in PurePosixPath(clean).parts:
            current = current / part
            if _is_link(current):
                raise _reject(clean, "it goes through a symbolic link or junction")
        resolved = target.resolve()
        if not resolved.is_relative_to(self.root):
            raise _reject(clean, "it points outside the project folder")
        return resolved

    def relative(self, absolute: Path) -> str:
        """The forward-slash relative form of an absolute path inside the root."""
        resolved = Path(absolute).resolve()
        if not resolved.is_relative_to(self.root):
            raise _reject(str(absolute), "it is outside the project folder")
        return resolved.relative_to(self.root).as_posix()

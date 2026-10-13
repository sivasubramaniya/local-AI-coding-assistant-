"""Local references in generated web files: find them, report missing ones, add image placeholders.

- ``scan_references`` reads ``src=``/``href=`` attributes in HTML and ``url(...)`` in CSS.
  Remote (http/https, ``//host``), ``data:``, ``mailto:``, ``tel:``, ``javascript:`` and ``#anchor``
  references are ignored: the preview never fetches them anyway.
- Missing images get a neutral grey placeholder with the file name (listed as "placeholder").
- Missing CSS/JS/other files are only reported; no code is invented.
- Every resolved path goes through the path validator: a reference that would leave the project is
  reported as unsafe and never created.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

from app.errors import PathValidationError
from app.validation.path_validator import PathValidator

logger = logging.getLogger(__name__)

WEB_SUFFIXES = {".html", ".htm", ".css"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp"}
_ATTR = re.compile(r"""\b(?:src|href|poster)\s*=\s*(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL)
_SRCSET = re.compile(r"""\bsrcset\s*=\s*(["'])(.*?)\1""", re.IGNORECASE | re.DOTALL)
_CSS_URL = re.compile(r"""url\(\s*(["']?)([^"')]+)\1\s*\)""", re.IGNORECASE)
_CSS_IMPORT = re.compile(r"""@import\s+(["'])([^"']+)\1""", re.IGNORECASE)
_DRIVE_OR_ROOT = re.compile(r"^([A-Za-z]:|[/\\])")
_SKIP_SCHEMES = ("http:", "https:", "data:", "mailto:", "tel:", "javascript:", "about:", "blob:", "ftp:")


@dataclass(frozen=True)
class Reference:
    source: str  # the file that contains the reference (project-relative)
    target: str  # the referenced file (project-relative), or the raw value when unsafe
    raw: str


@dataclass
class ReferenceReport:
    missing_images: list[Reference] = field(default_factory=list)
    missing_other: list[Reference] = field(default_factory=list)  # css, js, html, fonts...
    unsafe: list[Reference] = field(default_factory=list)
    placeholders: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing_images or self.missing_other or self.unsafe)

    def problems(self) -> list[str]:
        out = [f"missing image: {r.target} (in {r.source})" for r in self.missing_images
               if r.target not in self.placeholders]
        out += [f"missing file: {r.target} (in {r.source})" for r in self.missing_other]
        out += [f"reference leaves the project: {r.raw} (in {r.source})" for r in self.unsafe]
        return out

    def summary_markdown(self) -> str:
        lines: list[str] = []
        if self.placeholders:
            lines.append("Placeholder images created for missing pictures (replace them with your own):")
            lines += [f"- `{p}` (placeholder)" for p in self.placeholders]
        if self.missing_other:
            lines.append("Files the pages reference but which were not generated (not invented):")
            lines += [f"- `{r.target}` (referenced in `{r.source}`)" for r in self.missing_other]
        if self.unsafe:
            lines.append("References that point outside the project were ignored:")
            lines += [f"- `{r.raw}` (in `{r.source}`)" for r in self.unsafe]
        return "\n".join(lines)


def _is_local(value: str) -> bool:
    value = value.strip()
    if not value or value.startswith(("#", "//", "{", "$")):
        return False
    return not value.lower().startswith(_SKIP_SCHEMES)


def _raw_references(text: str, suffix: str) -> list[str]:
    values: list[str] = []
    if suffix in (".html", ".htm"):
        values += [m.group(2) for m in _ATTR.finditer(text)]
        for m in _SRCSET.finditer(text):
            values += [part.strip().split()[0] for part in m.group(2).split(",") if part.strip()]
        for style in re.findall(r"<style[^>]*>(.*?)</style>", text, re.IGNORECASE | re.DOTALL):
            values += [m.group(2) for m in _CSS_URL.finditer(style)]
        for style_attr in re.finditer(r"""\bstyle\s*=\s*(["'])(.*?)\1""", text, re.IGNORECASE | re.DOTALL):
            values += [m.group(2) for m in _CSS_URL.finditer(style_attr.group(2))]
    else:
        values += [m.group(2) for m in _CSS_URL.finditer(text)]
        values += [m.group(2) for m in _CSS_IMPORT.finditer(text)]
    return [v.strip() for v in values if _is_local(v)]


def scan_references(root: Path, files: list[str] | None = None) -> list[tuple[Reference, bool]]:
    """(reference, is_safe) for every local reference in the project's HTML/CSS files."""
    root = Path(root)
    validator = PathValidator(root)
    if files is None:
        files = [p.relative_to(root).as_posix() for p in root.rglob("*")
                 if p.is_file() and p.suffix.lower() in WEB_SUFFIXES]
    found: list[tuple[Reference, bool]] = []
    for relative in files:
        suffix = PurePosixPath(relative).suffix.lower()
        if suffix not in WEB_SUFFIXES:
            continue
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        base = PurePosixPath(relative).parent
        for raw in _raw_references(text, suffix):
            target_part = unquote(re.split(r"[?#]", raw, maxsplit=1)[0]).strip()
            if not target_part:
                continue
            if _DRIVE_OR_ROOT.match(target_part):
                # C:/x, /x (the drive root in a file:// page) or \\server\x: outside the project
                found.append((Reference(relative, raw, raw), False))
                continue
            normalised = _normalise(str(PurePosixPath(base, target_part)))
            if normalised is None:
                found.append((Reference(relative, raw, raw), False))
                continue
            try:
                validator.resolve(normalised)
            except PathValidationError:
                found.append((Reference(relative, raw, raw), False))
                continue
            found.append((Reference(relative, normalised, raw), True))
    return found


def _normalise(path: str) -> str | None:
    """Collapse '.' and '..' inside the project; None if it would climb above the root."""
    parts: list[str] = []
    for part in path.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts) or None


def check_references(root: Path, files: list[str] | None = None) -> ReferenceReport:
    root = Path(root)
    report = ReferenceReport()
    seen: set[str] = set()
    for ref, safe in scan_references(root, files):
        if not safe:
            report.unsafe.append(ref)
            continue
        if ref.target in seen or (root / ref.target).exists():
            continue
        seen.add(ref.target)
        if PurePosixPath(ref.target).suffix.lower() in IMAGE_SUFFIXES:
            report.missing_images.append(ref)
        else:
            report.missing_other.append(ref)
    return report


def placeholder_svg(name: str, width: int = 320, height: int = 200) -> str:
    label = (name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))[:40]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#D9D9D9"/>'
            f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" fill="none" stroke="#9B9B9B"/>'
            f'<text x="50%" y="50%" font-family="Segoe UI, Arial, sans-serif" font-size="16" fill="#4A4A4A" '
            f'text-anchor="middle" dominant-baseline="middle">{label}</text></svg>')


def plain_png(width: int = 320, height: int = 200) -> bytes:
    """A grey box with a darker border as PNG bytes (pure Python, no Qt needed)."""
    import struct
    import zlib

    fill, edge = b"\xd9\xd9\xd9", b"\x9b\x9b\x9b"
    rows = []
    for y in range(height):
        if y in (0, height - 1):
            row = edge * width
        else:
            row = edge + fill * (width - 2) + edge
        rows.append(b"\x00" + row)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + chunk(b"IEND", b""))


def _write_raster_placeholder(path: Path, name: str) -> None:
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.instance() is None:  # drawing text needs a GUI application; write a plain box
        path.write_bytes(plain_png())
        return
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter

    image = QImage(320, 200, QImage.Format.Format_RGB32)
    image.fill(QColor(217, 217, 217))
    painter = QPainter(image)
    painter.setPen(QColor(155, 155, 155))
    painter.drawRect(0, 0, 319, 199)
    painter.setPen(QColor(74, 74, 74))
    font = QFont("Segoe UI")
    font.setPixelSize(16)
    painter.setFont(font)
    painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, name[:40])
    painter.end()
    if not image.save(str(path)):  # format from the extension (png/jpg/...); PNG bytes if unsupported
        image.save(str(path), "PNG")


def create_placeholders(root: Path, report: ReferenceReport) -> list[str]:
    """Create grey placeholder images for every missing image reference. Returns the created paths."""
    validator = PathValidator(Path(root))
    created: list[str] = []
    for ref in report.missing_images:
        try:
            target = validator.resolve(ref.target)
        except PathValidationError:
            continue
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        name = PurePosixPath(ref.target).name
        if target.suffix.lower() == ".svg":
            target.write_text(placeholder_svg(name), encoding="utf-8")
        else:
            _write_raster_placeholder(target, name)
        created.append(ref.target)
        logger.info("Created placeholder image %s", ref.target)
    report.placeholders.extend(created)
    return created

"""Structure checks for a generated project: expected files exist, none empty, README present."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from app.errors import PathValidationError
from app.validation.path_validator import PathValidator

README_NAMES = ("README.md", "README.txt", "README.rst", "README")


@dataclass
class ValidationReport:
    root: Path
    missing: list[str] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)
    unsafe: list[str] = field(default_factory=list)
    has_readme: bool = False

    @property
    def ok(self) -> bool:
        return not (self.missing or self.empty or self.unsafe) and self.has_readme

    def problems(self) -> list[str]:
        out = [f"missing: {p}" for p in self.missing]
        out += [f"empty: {p}" for p in self.empty]
        out += [f"unsafe path: {p}" for p in self.unsafe]
        if not self.has_readme:
            out.append("no README file")
        return out

    def summary(self) -> str:
        return "Project check passed." if self.ok else "Project check: " + "; ".join(self.problems()) + "."


def validate_project(root: Path, expected: Iterable[str] = ()) -> ValidationReport:
    root = Path(root)
    report = ValidationReport(root)
    if not root.is_dir():
        report.missing.append(".")
        return report
    validator = PathValidator(root)
    for relative in expected:
        try:
            target = validator.resolve(relative)
        except PathValidationError:
            report.unsafe.append(relative)
            continue
        if not target.is_file():
            report.missing.append(relative)
        elif not target.read_bytes().strip():
            report.empty.append(relative)
    report.has_readme = any((root / name).is_file() and (root / name).read_bytes().strip() for name in README_NAMES)
    return report

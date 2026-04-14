"""Core diagnostic types: level enum and finding dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DiagnosticLevel(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Diagnostic:
    """A single diagnostic finding."""

    level: DiagnosticLevel
    code: str
    message: str
    module_name: str
    file: str | None = None
    suggestion: str | None = None

    def __str__(self) -> str:
        prefix = {"error": "\u2717", "warning": "\u26a0", "info": "\u2139"}[self.level]
        parts = [f"{prefix} {self.code} [{self.level.upper()}] {self.module_name}: {self.message}"]
        if self.file:
            parts.append(f"  \u21b3 {self.file}")
        if self.suggestion:
            parts.append(f"  \u21b3 Suggestion: {self.suggestion}")
        return "\n".join(parts)

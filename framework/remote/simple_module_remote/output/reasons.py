"""A readable reason for an OS error, never a bare exception class name."""

from __future__ import annotations

__all__ = ["os_reason"]

_REASONS: dict[type[OSError], str] = {
    FileNotFoundError: "no such file or directory",
    IsADirectoryError: "it is a directory",
    NotADirectoryError: "a parent is not a directory",
    PermissionError: "permission denied",
}


def os_reason(exc: BaseException) -> str:
    """``no such file or directory`` and friends; the exception name for anything else."""
    return _REASONS.get(type(exc), type(exc).__name__)

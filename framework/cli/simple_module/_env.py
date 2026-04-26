"""Shared helpers for editing dotenv-style files at scaffold time."""

from __future__ import annotations

__all__ = ["set_env_key"]


def set_env_key(text: str, key: str, value: str) -> str:
    """Replace or append ``KEY=VALUE`` in an env-style file body."""
    lines = [ln for ln in text.splitlines() if not ln.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"

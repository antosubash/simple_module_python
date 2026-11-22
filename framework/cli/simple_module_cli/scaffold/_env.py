"""Shared helpers for editing dotenv-style files at scaffold time."""

from __future__ import annotations

__all__ = ["env_values", "set_env_key"]


def set_env_key(text: str, key: str, value: str) -> str:
    """Replace or append ``KEY=VALUE`` in an env-style file body."""
    lines = [ln for ln in text.splitlines() if not ln.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def env_values(text: str) -> dict[str, str]:
    """Parse the ``KEY=VALUE`` lines of an env-style file body (comments skipped)."""
    lines = text.splitlines()
    pairs = (ln.split("=", 1) for ln in lines if "=" in ln and not ln.lstrip().startswith("#"))
    return {key.strip(): value for key, value in pairs}

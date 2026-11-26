"""Hook for curated command providers (filled in by a later release)."""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["load_providers"]


def load_providers(names: Sequence[str]) -> list:
    """Providers for the named curated command sets; none exist yet."""
    return []

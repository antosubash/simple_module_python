"""Module-scoped state container, stored as ``app.state.api_tokens``."""

from __future__ import annotations

from dataclasses import dataclass

from api_tokens.settings import ApiTokensSettings


@dataclass
class ApiTokensServices:
    """api_tokens singletons. ``settings`` is swapped on a settings save."""

    settings: ApiTokensSettings

"""App-scoped OAuth factories, retained when settings are replaced."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from users.oauth.providers import OAuthProvider

type OAuthProviderFactory = Callable[[FastAPI], OAuthProvider | None]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Entry:
    factory: OAuthProviderFactory
    label_key: str | None = None
    icon: str | None = None


def _builtin(name: str, app: FastAPI) -> OAuthProvider | None:
    from users.oauth.builtins import build_builtin

    return build_builtin(name, app.state.users.settings)


def _registry(app: FastAPI) -> dict[str, _Entry]:
    registry = getattr(app.state, "_users_oauth_registry", None)
    if registry is None:
        from users.oauth.builtins import BUILTIN_FACTORIES

        registry = {name: _Entry(partial(_builtin, name)) for name in BUILTIN_FACTORIES}
        app.state._users_oauth_registry = registry
    return registry


def register_oauth_provider(
    app: FastAPI,
    name: str,
    factory: OAuthProviderFactory,
    *,
    label_key: str | None = None,
    icon: str | None = None,
) -> None:
    """Register during ``register_settings``, before startup builds clients.

    The synchronous factory reads current settings from ``app`` and returns
    ``None`` when disabled or incomplete. ``label_key`` translates the provider
    name inside the login button; ``icon`` names a shared UI ``NavIcon``.
    Duplicate names (including built-ins) are refused.
    """
    if re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name) is None:
        raise ValueError(f"Invalid OAuth provider name: {name!r}")
    registry = _registry(app)
    if name in registry:
        raise ValueError(f"OAuth provider {name!r} already registered")
    registry[name] = _Entry(factory, label_key, icon)


def build_registered_providers(
    app: FastAPI,
) -> tuple[dict[str, OAuthProvider], list[dict[str, str]]]:
    """Build clients and button metadata together from the same active entries."""
    clients: dict[str, OAuthProvider] = {}
    buttons: list[dict[str, str]] = []
    for name, entry in _registry(app).items():
        try:
            provider = entry.factory(app)
        except Exception as exc:
            # Never log the message or traceback: factory errors can quote credentials.
            logger.error(
                "OAuth factory for %s failed (%s); provider disabled", name, type(exc).__name__
            )
            continue
        if provider is None:
            continue
        if provider.name != name:
            # A mismatched name is a programming error, but one broken provider must
            # not keep the previous (possibly disabled) clients alive or block the rest.
            logger.error(
                "OAuth factory for %s returned provider name %r; provider disabled",
                name,
                provider.name,
            )
            continue
        clients[name] = provider
        button = {"name": name, "display_name": provider.display_name}
        if entry.label_key:
            button["label_key"] = entry.label_key
        if entry.icon:
            button["icon"] = entry.icon
        buttons.append(button)
    return clients, buttons

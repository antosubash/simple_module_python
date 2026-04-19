"""Helpers for building Inertia shared-props payloads."""

from __future__ import annotations

import logging

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import Scope

logger = logging.getLogger(__name__)

_I18N_SESSION_LOCALE_KEY = "__i18n_locale"
_INERTIA_HEADER = "x-inertia"
_INERTIA_HEADER_TRUE = "true"


def build_i18n_block(scope: Scope, request: Request) -> dict:
    """Assemble the ``i18n`` shared-props block for the current request.

    Rules:

    * No registry / no locale → serve an empty English block and log once.
    * Inertia XHR partials (``X-Inertia: true``) reuse the client-side
      cached messages; send ``messages: None`` unless the locale differs
      from what was last served on this session.
    * Full page loads and locale transitions ship the complete dict.
    """
    # Test fixtures sometimes build a bare FastAPI with a partial app.state.sm
    # stub (e.g. permissions-only, no i18n); guard both lookups to keep them usable.
    sm = getattr(request.app.state, "sm", None)
    registry = getattr(sm, "i18n_registry", None) if sm is not None else None
    locale = getattr(request.state, "locale", None)
    if registry is None or locale is None:
        logger.warning(
            "InertiaLayoutDataMiddleware: i18n not fully wired "
            "(registry_present=%s, locale_present=%s); serving empty messages",
            registry is not None,
            locale is not None,
        )
        return {"locale": "en", "supportedLocales": ["en"], "messages": {}}

    is_inertia = Headers(scope=scope).get(_INERTIA_HEADER) == _INERTIA_HEADER_TRUE
    session_dict = scope.get("session")
    # When the session is absent (pre-session-middleware routes, WebSocket
    # upgrades), treat locale as "unchanged" so Inertia XHR requests still
    # skip the messages payload. Non-Inertia requests will always ship them
    # regardless of the session state.
    if session_dict is not None:
        last_locale = session_dict.get(_I18N_SESSION_LOCALE_KEY)
        locale_changed = last_locale != locale
        if locale_changed:
            session_dict[_I18N_SESSION_LOCALE_KEY] = locale
    else:
        locale_changed = False
    send_messages = (not is_inertia) or locale_changed
    return {
        "locale": locale,
        "supportedLocales": registry.available_locales(),
        "messages": registry.messages_snapshot(locale) if send_messages else None,
    }

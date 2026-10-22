"""Helpers for building Inertia shared-props payloads."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import Any

from simple_module_core.i18n import Translator
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import Scope

from simple_module_hosting.csrf import get_csrf_token

logger = logging.getLogger(__name__)

_I18N_SESSION_LOCALE_KEY = "__i18n_locale"
_I18N_SESSION_AUDIENCE_KEY = "__i18n_audience"
_INERTIA_HEADER = "x-inertia"
_INERTIA_HEADER_TRUE = "true"
#: Shared-prop key the frontend API client reads its ``X-CSRF-Token`` from (#504).
CSRF_SHARED_PROP = "csrfToken"


def _accepts_html(scope: Scope) -> bool:
    return "text/html" in Headers(scope=scope).get("accept", "").lower()


def build_i18n_block(scope: Scope, request: Request, *, is_authenticated: bool = True) -> dict:
    """Assemble the ``i18n`` shared-props block for the current request.

    Rules:

    * No registry / no locale → serve an empty English block and log once.
    * Inertia XHR partials (``X-Inertia: true``) reuse the client-side
      cached messages; send ``messages: None`` unless the locale — or the
      audience, see below — differs from what was last served this session.
    * Full page loads and locale transitions ship the complete dict.
    * Anonymous visitors receive the public snapshot: catalogs of modules
      declaring ``i18n_audience="admin"`` are withheld (issue #248). A login
      or logout mid-session counts as a change so the freshly-authenticated
      client isn't left holding the anonymous catalog (or vice versa).
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
    audience = "full" if is_authenticated else "public"
    session_dict = scope.get("session")
    # When the session is absent (pre-session-middleware routes, WebSocket
    # upgrades), treat locale as "unchanged" so Inertia XHR requests still
    # skip the messages payload. Non-Inertia requests will always ship them
    # regardless of the session state.
    if session_dict is not None:
        # Remembering the locale only pays off for a client that will come back
        # with an Inertia XHR (to skip re-sending the catalog). A bare API or
        # health-check call from a cookie-less client will not, and writing
        # here would make Starlette's SessionMiddleware emit a two-week
        # Set-Cookie on every anonymous response, which keeps shared caches
        # from storing it (GH #349). So persist only when a session already
        # exists (it has data) or the caller is page-shaped.
        persist = bool(session_dict) or is_inertia or _accepts_html(scope)
        last_locale = session_dict.get(_I18N_SESSION_LOCALE_KEY)
        locale_changed = last_locale != locale
        if locale_changed and persist:
            session_dict[_I18N_SESSION_LOCALE_KEY] = locale
        last_audience = session_dict.get(_I18N_SESSION_AUDIENCE_KEY)
        audience_changed = last_audience != audience
        if audience_changed and persist:
            session_dict[_I18N_SESSION_AUDIENCE_KEY] = audience
    else:
        locale_changed = False
        audience_changed = False
    send_messages = (not is_inertia) or locale_changed or audience_changed
    return {
        "locale": locale,
        "supportedLocales": registry.available_locales(),
        "messages": (
            registry.messages_snapshot(locale, include_admin=is_authenticated)
            if send_messages
            else None
        ),
    }


def csrf_shared_prop(request: Request, *, is_authenticated: bool) -> dict[str, str]:
    """``{"csrfToken": ...}`` for a signed-in session, ``{}`` for anyone else (#504).

    Anonymous pages never carry it: minting would write the session and set a
    cookie on every public response (GH #349), and a page a module marks
    cacheable is, by construction, an anonymous one — a token in it would be
    served to the next visitor. API-token principals reach here as anonymous.
    """
    if not is_authenticated:
        return {}
    token = get_csrf_token(request)
    return {CSRF_SHARED_PROP: token} if token else {}


def lazy_csrf_shared_prop(
    request: Request, *, is_authenticated: bool
) -> dict[str, Callable[[], str]]:
    """Like :func:`csrf_shared_prop`, but the token is resolved at render time.

    The shared props are built for every request; a JSON call or a download
    never renders a page, so minting eagerly would write the session (a
    ``Set-Cookie``) on responses that have no use for the token. Inertia calls
    the callable only when it serialises props.
    """
    if not is_authenticated or request.scope.get("session") is None:
        return {}
    return {CSRF_SHARED_PROP: lambda: get_csrf_token(request)}


def build_menu_translator(request: Request) -> Callable[[str], str] | None:
    """Return a locale-bound translator for menu labels, or None if unavailable.

    Menu labels are translated on the server rather than in the client: the
    payload then carries finished text, so the sidebar, topbar and command
    palette all keep rendering ``item.label`` unchanged. It also sidesteps the
    catalog audience split — an admin-audience module's labels never have to be
    present in the anonymous snapshot to be readable.

    Mirrors ``build_i18n_block``'s defensive lookups: test fixtures build apps
    with a partial ``app.state.sm``, and a missing registry must degrade to the
    literal labels rather than raise on every request.
    """
    sm = getattr(request.app.state, "sm", None)
    registry = getattr(sm, "i18n_registry", None) if sm is not None else None
    locale = getattr(request.state, "locale", None)
    if registry is None or locale is None:
        return None
    settings = getattr(sm, "settings", None)
    default_locale = getattr(settings, "i18n_default_locale", "en") if settings else "en"
    translator = Translator(registry, locale=locale, default_locale=default_locale)
    return translator.t


async def merge_shared_prop_providers(app: Any, request: Request, shared: dict) -> None:
    """Merge module-registered Inertia shared-prop providers into ``shared`` in place.

    Providers are read off ``app.state.inertia_shared_providers`` (never importing
    the plugin — preserves SM009). A provider that raises is skipped and logged; a
    provider may not clobber a framework-owned key (auth/menus/i18n) or an earlier
    provider's key. A provider may be ``async`` (its result is awaited) — a
    per-tenant lookup cannot be answered from a process-wide object.
    """
    providers = getattr(app.state, "inertia_shared_providers", None) or ()
    for provider in providers:
        name = getattr(provider, "__name__", provider)
        try:
            extra = provider(request)
            if inspect.isawaitable(extra):
                extra = await extra
        except Exception:  # a bad provider must not break the page render
            logger.warning("shared-prop provider %r raised; skipping", name, exc_info=True)
            continue
        for key, value in (extra or {}).items():
            if key in shared:
                logger.warning(
                    "provider %r tried to overwrite reserved shared-prop %r; ignoring",
                    name,
                    key,
                )
                continue
            shared[key] = value


def default_home_url(app: Any) -> str:
    """Where the layouts' "home" links point when no module publishes ``homeUrl``.

    The users module publishes its configured landing URL and wins; this covers
    installs without it (Keycloak). Dashboard is the conventional landing page,
    named by string from ``sm.view_prefixes`` so nothing is imported (SM009);
    ``/`` is a host route in every app, so the link can never 404.
    """
    sm = getattr(app.state, "sm", None)
    prefix = getattr(sm, "view_prefixes", {}).get("Dashboard")
    return f"{prefix}/" if prefix else "/"

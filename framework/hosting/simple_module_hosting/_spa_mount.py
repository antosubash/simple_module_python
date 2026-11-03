"""Serve legacy client-routed SPAs under a URL prefix (GH #541).

The mount is a ``StaticFiles`` subclass with one addition: a request for a path
that is not a file and *looks like a page* (no extension, client accepts HTML)
is answered with the SPA's ``index.html`` so its router can take over. A missing
asset (``/legacy/missing.js``) stays a 404 — answering it with HTML would make
the browser fail on a script it cannot parse and hide the real problem.

Nothing here builds a filesystem path from the request except through
``StaticFiles`` itself (which refuses traversal); the fallback serves the one
configured index name and never the requested path.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import anyio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from simple_module_core.app_state import get_host_services, get_public_routes, get_spa_prefixes
from simple_module_core.diagnostics._spa_mount import check_spa_mount_overlaps
from simple_module_core.spa_mount import SPA_AUTH_PUBLIC, SpaMount
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, Response
from starlette.types import Scope

from simple_module_hosting._route_paths import app_route_paths
from simple_module_hosting.static_files import IMMUTABLE_CACHE_CONTROL

logger = logging.getLogger(__name__)

_NOT_FOUND = 404
_OK = 200
_SAFE_METHODS = ("GET", "HEAD")
_NO_CACHE = "no-cache"
_CACHE_CONTROL = "Cache-Control"
# Set by SecurityHeadersMiddleware for every HTTP request.
_NONCE_STATE_KEY = "csp_nonce"
_SCRIPT_WITHOUT_NONCE = re.compile(r"<script\b(?![^>]*\snonce\s*=)", re.IGNORECASE)
# Vite shells preload their chunks; a script preload without the nonce is refused.
_SCRIPT_PRELOAD_WITHOUT_NONCE = re.compile(
    r"<link\b(?=[^>]*\s(?:rel\s*=\s*[\"']?modulepreload|as\s*=\s*[\"']?script))"
    r"(?![^>]*\snonce\s*=)",
    re.IGNORECASE,
)
_CONDITIONAL_HEADERS = (b"if-none-match", b"if-modified-since", b"if-match", b"if-unmodified-since")
# Vite/webpack content-hashed file: `index-3f9a8c21.js`, `chunk.AbC123xy.css`.
_HASHED_FILE = re.compile(r"[-.]([A-Za-z0-9_-]{8,})\.[A-Za-z0-9]+$")
_PRIVATE_IMMUTABLE = "private, max-age=31536000, immutable"
_PRIVATE_NO_CACHE = "private, no-cache"
_LOOKS_LIKE_FILE = re.compile(r"\.[A-Za-z0-9]+$")


class SpaMountError(RuntimeError):
    """A SPA mount cannot be served; raised at boot so it never half-works."""


def looks_hashed(filename: str) -> bool:
    """Whether *filename* carries a bundler content hash (8+ chars, a digit or mixed case)."""
    found = _HASHED_FILE.search(filename)
    if not found:
        return False
    token = found.group(1)
    mixed = token != token.lower() and token != token.upper()
    return any(c.isdigit() for c in token) or mixed


class SpaStaticFiles(StaticFiles):
    """``StaticFiles`` plus the ``index.html`` deep-link fallback.

    ``public`` decides shared-cache exposure: only a public mount's responses
    may be stored by shared caches; a login-gated mount's are ``private``.
    """

    def __init__(self, *, directory, index: str, public: bool = False) -> None:
        super().__init__(directory=directory)
        self._index = index
        self._public = public

    async def get_response(self, path: str, scope: Scope) -> Response:
        if scope["method"] not in _SAFE_METHODS:
            raise HTTPException(status_code=405)
        segments = path.replace("\\", "/").split("/")
        if ".." in segments or "\x00" in path:
            raise HTTPException(status_code=_NOT_FOUND)
        if path in ("", ".", self._index):
            return await self._index_response(scope)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != _NOT_FOUND or not _is_page_request(path, scope):
                raise
            return await self._index_response(scope)
        if response.status_code == _OK and looks_hashed(segments[-1]):
            response.headers[_CACHE_CONTROL] = (
                IMMUTABLE_CACHE_CONTROL if self._public else _PRIVATE_IMMUTABLE
            )
        return response

    async def _index_response(self, scope: Scope) -> Response:
        nonce = (scope.get("state") or {}).get(_NONCE_STATE_KEY)
        if nonce:
            # A 304 would revive a cached shell carrying an older nonce (or none).
            scope = {
                **scope,
                "headers": [(k, v) for k, v in scope["headers"] if k not in _CONDITIONAL_HEADERS],
            }
        response = await super().get_response(self._index, scope)
        if nonce and isinstance(response, FileResponse) and response.status_code == _OK:
            response = await anyio.to_thread.run_sync(_with_script_nonce, response, nonce)
        # The shell references hashed bundles, so it must revalidate on each visit.
        response.headers[_CACHE_CONTROL] = _NO_CACHE if self._public else _PRIVATE_NO_CACHE
        return response


def _with_script_nonce(response: FileResponse, nonce: str) -> Response:
    """The shell with the request's CSP nonce on every ``<script>`` tag.

    The production script policy is ``'nonce-…' 'strict-dynamic'``, under which a
    CSP3 browser ignores ``'self'``: a static shell's own entry script would be
    blocked. The nonce differs per response, so the validators go too: a 304
    would revive a cached shell whose nonce no longer matches the header.
    """
    html = Path(response.path).read_text(encoding="utf-8")
    html = _SCRIPT_WITHOUT_NONCE.sub(f'<script nonce="{nonce}"', html)
    html = _SCRIPT_PRELOAD_WITHOUT_NONCE.sub(f'<link nonce="{nonce}"', html)
    headers = {
        k: v
        for k, v in response.headers.items()
        if k.lower() not in ("content-length", "etag", "last-modified", "accept-ranges")
    }
    return Response(html, status_code=_OK, headers=headers, media_type="text/html")


def _is_page_request(path: str, scope: Scope) -> bool:
    if _LOOKS_LIKE_FILE.search(path.rsplit("/", 1)[-1]):
        return False
    return "text/html" in Headers(scope=scope).get("accept", "").lower()


def mount_spa_mounts(app: FastAPI, modules: list) -> None:
    """Mount every module's SPAs, exempt the public ones from auth, publish prefixes."""
    problems = check_spa_mount_overlaps(modules, app_route_paths(app))
    if problems:
        raise SpaMountError("\n".join(str(p) for p in problems))

    prefixes: list[str] = []
    registry = get_public_routes(app)
    for mod in modules:
        for mount in mod.spa_mounts():
            if _mount(app, mod.meta.name, mount, registry):
                prefixes.append(mount.prefix)
    app.state.spa_prefixes = tuple(prefixes)


def _mount(app: FastAPI, module_name: str, mount: SpaMount, registry) -> bool:
    if not (mount.dist_dir / mount.index).is_file():
        logger.warning(
            "Module '%s' declared SPA mount %s but %s/%s does not exist (not built?)",
            module_name,
            mount.prefix,
            mount.dist_dir,
            mount.index,
        )
        return False
    app.mount(
        mount.prefix,
        SpaStaticFiles(
            directory=mount.dist_dir, index=mount.index, public=mount.auth == SPA_AUTH_PUBLIC
        ),
        name=f"spa:{module_name}:{mount.prefix}",
    )
    if mount.auth == SPA_AUTH_PUBLIC and registry is not None:
        # Anchored to this mount's own paths. No other route can share the
        # prefix: mount_spa_mounts refused the boot if one was registered.
        registry.add_regex(f"{re.escape(mount.prefix)}(/.*)?$", methods=_SAFE_METHODS)
    return True


def native_prefixes(app: FastAPI) -> list[str]:
    """Prefixes the client must not intercept: mounted SPAs + the host setting."""
    host = get_host_services(app)
    configured = getattr(getattr(host, "settings", None), "native_link_prefixes", None) or []
    spa = [f"{prefix}/" for prefix in get_spa_prefixes(app)]
    return sorted({*spa, *configured})

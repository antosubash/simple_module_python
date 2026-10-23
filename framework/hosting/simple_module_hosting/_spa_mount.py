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

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from simple_module_core.app_state import get_host_services, get_public_routes, get_spa_prefixes
from simple_module_core.diagnostics._spa_mount import check_spa_mount_overlaps
from simple_module_core.spa_mount import SPA_AUTH_PUBLIC, SpaMount
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

from simple_module_hosting._route_paths import app_route_paths
from simple_module_hosting.static_files import IMMUTABLE_CACHE_CONTROL

logger = logging.getLogger(__name__)

_NOT_FOUND = 404
_OK = 200
_SAFE_METHODS = ("GET", "HEAD")
_NO_CACHE = "no-cache"
_CACHE_CONTROL = "Cache-Control"
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
        response = await super().get_response(self._index, scope)
        # The shell references hashed bundles, so it must revalidate on each visit.
        response.headers[_CACHE_CONTROL] = _NO_CACHE if self._public else _PRIVATE_NO_CACHE
        return response


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

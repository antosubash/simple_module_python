"""Static-file serving: immutable caching and pre-compressed variants.

Split out of ``_phase_helpers`` — static delivery is its own responsibility,
and that module was near the repo's 300-line cap.

Two optimizations live here, both aimed at cold page load:

* **Immutable caching.** Vite emits content-hashed filenames, so the bytes for
  a given URL never change and the browser can skip even the revalidation
  round-trip.
* **Pre-compressed variants.** ``GZipMiddleware`` would otherwise re-compress
  the same immutable bundle on every request, using a fast (and therefore
  worse) compression level. Files compressed once at build time can afford the
  maximum level, and brotli is ~14% smaller than gzip on this bundle.
"""

from __future__ import annotations

from mimetypes import guess_type

from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

__all__ = ["IMMUTABLE_CACHE_CONTROL", "PrecompressedStaticFiles"]

IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"

_HASHED_ASSET_PREFIX = "dist/assets/"
_ACCEPT_ENCODING = "accept-encoding"
_CONTENT_ENCODING = "Content-Encoding"
_CONTENT_TYPE = "content-type"
_VARY = "Vary"
_ACCEPT_ENCODING_HEADER = "Accept-Encoding"
_OK = 200

# (encoding token, filename suffix), best first. Brotli wins where offered:
# measured 248.5 KB vs 287.6 KB gzip-9 across this bundle.
_VARIANTS: tuple[tuple[str, str], ...] = (("br", ".br"), ("gzip", ".gz"))


def _accepted_encodings(scope: Scope) -> set[str]:
    """Encoding tokens the client advertises.

    Deliberately ignores q-values. Any client sending ``br;q=0`` to actively
    refuse brotli is vanishingly rare, and getting it wrong only costs a few
    KB — whereas parsing it wrong could serve a body the client cannot read.
    Tokens are matched exactly, so a ``q=0`` entry still reads as "accepted";
    that is the conservative direction only because every real client that
    lists an encoding can decode it.
    """
    raw = Headers(scope=scope).get(_ACCEPT_ENCODING, "")
    return {part.split(";")[0].strip().lower() for part in raw.split(",") if part.strip()}


class PrecompressedStaticFiles(StaticFiles):
    """Serve ``.br``/``.gz`` siblings when present, and mark hashed assets immutable.

    A request for ``app.js`` is answered with ``app.js.br`` when the client
    accepts brotli and that file exists, falling back to ``.gz`` and then to the
    original. The response keeps the *original* file's Content-Type — serving
    ``app.js.br`` directly would have Starlette type it from the ``.br``
    extension, and a browser will refuse to execute a script typed as
    ``application/octet-stream``.

    ``Vary: Accept-Encoding`` is always set on a negotiated response so shared
    caches cannot hand a compressed body to a client that never asked for one.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await self._get_negotiated_response(path, scope)
        # StaticFiles hands us an OS-separator path (backslashes on Windows), so
        # normalize before matching the forward-slash asset prefix.
        if response.status_code == _OK and path.replace("\\", "/").startswith(_HASHED_ASSET_PREFIX):
            response.headers["Cache-Control"] = IMMUTABLE_CACHE_CONTROL
        return response

    async def _get_negotiated_response(self, path: str, scope: Scope) -> Response:
        accepted = _accepted_encodings(scope)
        for encoding, suffix in _VARIANTS:
            if encoding not in accepted:
                continue
            # StaticFiles signals "no such file" by *raising* HTTPException(404),
            # not by returning a 404 response — so a missing variant has to be
            # caught here, not detected from a status code.
            try:
                variant = await super().get_response(path + suffix, scope)
            except HTTPException:
                continue
            if variant.status_code != _OK:
                continue
            # Type by the original filename, not the variant's extension: a
            # browser refuses to execute a script typed application/octet-stream.
            content_type = guess_type(path)[0]
            if content_type:
                variant.headers[_CONTENT_TYPE] = content_type
            variant.headers[_CONTENT_ENCODING] = encoding
            variant.headers[_VARY] = _ACCEPT_ENCODING_HEADER
            return variant
        return await super().get_response(path, scope)

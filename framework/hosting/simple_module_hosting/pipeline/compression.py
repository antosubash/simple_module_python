"""Host response compression with range and media-type exclusions."""

import re
from http import HTTPStatus
from inspect import signature
from typing import TypedDict

from starlette.datastructures import Headers
from starlette.middleware.gzip import GZipMiddleware, GZipResponder, IdentityResponder
from starlette.types import ASGIApp, Message, Receive, Scope, Send

DEFAULT_EXCLUDED_CONTENT_TYPES = (
    "application/grpc",
    "application/gzip",
    "application/vnd.pmtiles",
    "application/x-gzip",
    "application/zip",
    "audio/*",
    "font/woff",
    "font/woff2",
    "image/*",
    "text/event-stream",
    "video/*",
)


class _ResponderOptions(TypedDict, total=False):
    exclude_content_types: tuple[str, ...]


# Older supported Starlette releases have a built-in SSE exclusion and no
# constructor option. Where available, let the host list control selection.
_RESPONDER_OPTIONS: _ResponderOptions = (
    {"exclude_content_types": ()}
    if "exclude_content_types" in signature(IdentityResponder).parameters
    else {}
)


def _media_type(value: str) -> str:
    return value.partition(";")[0].strip().lower()


_QUALITY = re.compile(r"q[ \t]*=[ \t]*(0(?:\.[0-9]{0,3})?|1(?:\.0{0,3})?)", re.IGNORECASE)


def _accepts_gzip(value: str) -> bool:
    """Apply explicit coding preferences before the RFC 9110 wildcard fallback."""
    accepted: dict[str, bool] = {}
    for entry in value.split(","):
        coding, separator, parameter = entry.partition(";")
        coding = coding.strip().lower()
        if coding == "x-gzip":
            coding = "gzip"
        if coding not in {"gzip", "*"}:
            continue
        quality = 1.0
        if separator:
            match = _QUALITY.fullmatch(parameter.strip())
            quality = float(match[1]) if match else 0.0
        accepted[coding] = quality > 0
    return accepted.get("gzip", accepted.get("*", False))


class HostGZipMiddleware(GZipMiddleware):
    """Leave partial responses and excluded media types untouched."""

    def __init__(
        self,
        app: ASGIApp,
        minimum_size: int = 500,
        compresslevel: int = 9,
        *,
        exclude_content_types: tuple[str, ...] = DEFAULT_EXCLUDED_CONTENT_TYPES,
    ) -> None:
        super().__init__(app, minimum_size=minimum_size, compresslevel=compresslevel)
        self._excluded_types = frozenset(map(_media_type, exclude_content_types))
        # SVG is textual: the default image wildcard leaves it compressible, but
        # a caller's own image/* exclusion means every image type.
        self._svg_compressible = exclude_content_types is DEFAULT_EXCLUDED_CONTENT_TYPES

    def _skip_compression(self, message: Message) -> bool:
        if message["status"] == HTTPStatus.PARTIAL_CONTENT:
            return True
        headers = Headers(raw=message.get("headers", []))
        if "content-range" in headers:
            return True
        media_type = _media_type(headers.get("content-type", ""))
        if media_type in self._excluded_types:
            return True
        if (
            media_type.startswith("application/grpc+")
            and "application/grpc" in self._excluded_types
        ):
            return True
        if media_type == "image/svg+xml" and self._svg_compressible:
            return False
        return f"{media_type.partition('/')[0]}/*" in self._excluded_types

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def select_response(scope: Scope, receive: Receive, send_compressed: Send) -> None:
            send_response = send_compressed

            async def send_with_exclusions(message: Message) -> None:
                nonlocal send_response
                if message["type"] == "http.response.start" and self._skip_compression(message):
                    send_response = send
                await send_response(message)

            await self.app(scope, receive, send_with_exclusions)

        responder: IdentityResponder
        if _accepts_gzip(",".join(Headers(scope=scope).getlist("accept-encoding"))):
            responder = GZipResponder(
                select_response, self.minimum_size, self.compresslevel, **_RESPONDER_OPTIONS
            )
        else:
            responder = IdentityResponder(select_response, self.minimum_size, **_RESPONDER_OPTIONS)
        await responder(scope, receive, send)

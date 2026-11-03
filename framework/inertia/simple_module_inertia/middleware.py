"""Pure ASGI response normalization for Inertia visits."""

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from simple_module_inertia.response import back_url

# Redirect headers that describe a body the 409 no longer has.
_BODY_HEADERS = (
    "content-type",
    "content-encoding",
    "content-disposition",
    "etag",
    "transfer-encoding",
)


def _declares_empty_body(headers: MutableHeaders) -> bool:
    """An explicit ``Content-Length: 0``. A streaming response declares none,
    so it is never held back waiting for a first chunk."""
    value = headers.get("content-length", "").strip()
    return value.isdigit() and int(value) == 0


def add_vary(headers: MutableHeaders) -> None:
    """Add ``X-Inertia`` to ``Vary``, keeping whatever is already listed."""
    existing = headers.get("vary")
    if not existing:
        headers["vary"] = "X-Inertia"
    elif not any(part.strip().lower() == "x-inertia" for part in existing.split(",")):
        headers["vary"] = f"{existing}, X-Inertia"


class InertiaMiddleware:
    """Normalize redirects and empty responses without buffering body streams."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_headers = Headers(scope=scope)
        inertia = "x-inertia" in request_headers
        pending: Message | None = None
        discard_body = False
        empty_sent = False

        async def send_response(message: Message) -> None:
            nonlocal pending, discard_body, empty_sent
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                headers = MutableHeaders(scope=message)
                html = headers.get("content-type", "").split(";", 1)[0].strip() == "text/html"
                if inertia or "x-inertia" in headers or html:
                    add_vary(headers)
                if inertia:
                    code = message["status"]
                    target = headers.get("location", "")
                    if (
                        300 <= code < 400
                        and "#" in target
                        and request_headers.get("purpose") != "prefetch"
                    ):
                        message["status"] = 409
                        headers["x-inertia-redirect"] = target
                        del headers["location"]
                        for name in _BODY_HEADERS:
                            del headers[name]
                        headers["content-length"] = "0"
                        discard_body = True
                    elif code in (302, 307) and scope["method"] in (
                        "PUT",
                        "PATCH",
                        "DELETE",
                        "QUERY",
                    ):
                        message["status"] = 303
                    elif code == 200 and _declares_empty_body(headers):
                        # Hold only the start; the first chunk decides whether this is empty.
                        pending = message
                        return
            elif message["type"] == "http.response.body":
                if pending is not None:
                    if not message.get("body") and not message.get("more_body", False):
                        pending["status"] = 303
                        headers = MutableHeaders(scope=pending)
                        headers["location"] = back_url(Request(scope))
                        headers["content-length"] = "0"
                    await send(pending)
                    pending = None
                if discard_body:
                    if not empty_sent:
                        await send({"type": "http.response.body", "body": b""})
                        empty_sent = True
                    return
            await send(message)

        await self.app(scope, receive, send_response)

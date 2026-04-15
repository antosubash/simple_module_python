"""LocaleMiddleware — resolve active locale from cookie / Accept-Language / default."""

from __future__ import annotations

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


class LocaleMiddleware:
    """Set ``request.state.locale`` based on cookie, Accept-Language, and default.

    Resolution order:

    1. Cookie named ``cookie_name``, validated against ``supported_locales``.
    2. ``Accept-Language`` header, negotiated against supported_locales via
       longest-prefix match (``es-MX`` matches supported ``es``).
    3. ``default_locale``.

    Runs as a pure ASGI middleware (no BaseHTTPMiddleware) to match the rest
    of the framework's middleware stack.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        supported_locales: list[str],
        default_locale: str,
        cookie_name: str = "locale",
    ) -> None:
        self.app = app
        self.supported = list(supported_locales)
        self.default_locale = default_locale
        self.cookie_name = cookie_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        locale = self._resolve(request)
        request.state.locale = locale
        await self.app(scope, receive, send)

    def _resolve(self, request: Request) -> str:
        # 1. Cookie.
        cookie = request.cookies.get(self.cookie_name)
        if cookie and cookie in self.supported:
            return cookie

        # 2. Accept-Language.
        accept = Headers(scope=request.scope).get("accept-language")
        if accept:
            matched = self._negotiate(accept)
            if matched:
                return matched

        # 3. Default.
        return self.default_locale

    def _negotiate(self, accept_language: str) -> str | None:
        """Parse Accept-Language and return the highest-q supported locale.

        Matches either exact tag or primary prefix (``es-MX`` -> ``es``).
        """
        # Hard cap to blunt adversarial Accept-Language: a,a,a,... spam.
        # Real browsers send <10 tags; 20 is comfortably above that.
        parts = accept_language.split(",", 20)
        candidates: list[tuple[float, str]] = []
        for part in parts[:20]:
            part = part.strip()
            if not part:
                continue
            tag, _, q_part = part.partition(";")
            tag = tag.strip().lower()
            q_part = q_part.strip().lower()
            try:
                q = float(q_part.split("=", 1)[1]) if q_part.startswith("q=") else 1.0
            except ValueError:
                q = 1.0
            candidates.append((q, tag))

        # Sort by q descending, stable.
        candidates.sort(key=lambda pair: -pair[0])

        supported_lower = {loc.lower(): loc for loc in self.supported}
        for _, tag in candidates:
            if tag in supported_lower:
                return supported_lower[tag]
            primary = tag.split("-", 1)[0]
            if primary in supported_lower:
                return supported_lower[primary]
        return None

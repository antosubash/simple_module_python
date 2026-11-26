"""The guarded HTTP client: every CLI request goes through ApiClient."""

import time
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from simple_module_remote.config.environments import Environment
from simple_module_remote.http.errors import ApiError, UnsafePathError
from simple_module_remote.http.safety import (
    validate_api_path,
    validate_base_url,
    validate_request_url,
)

REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
MAX_HOPS = 5
MAX_RETRIES = 3
MAX_WAIT_SECONDS = 30.0
DEFAULT_RETRY_AFTER = 1.0
TOO_MANY_REQUESTS = 429
TIMEOUT_SECONDS = 30.0
REDIRECTED_EXTENSION = "smr_redirected"
_STRIPPED_HEADERS = frozenset({"authorization", "cookie", "host", "user-agent"})


def _retry_delay(value: str | None, now: datetime | None = None) -> float:
    if value is None:
        return DEFAULT_RETRY_AFTER
    text = value.strip()
    if text.isascii() and text.isdigit():
        return min(float(text), MAX_WAIT_SECONDS)
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return DEFAULT_RETRY_AFTER
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return min(max(0.0, (when - (now or datetime.now(UTC))).total_seconds()), MAX_WAIT_SECONDS)


class ApiClient:
    def __init__(
        self,
        env: Environment,
        token: str | None,
        *,
        user_agent: str,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._base = validate_base_url(env.url).rstrip("/")
        self._sleep = sleep
        self._token = token
        headers = {"User-Agent": user_agent}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            headers=headers,
            follow_redirects=False,
            transport=transport,
            timeout=TIMEOUT_SECONDS,
        )
        # No token, no cookie carry-over: used only to follow redirects.
        self._follower = httpx.Client(
            headers={"User-Agent": user_agent},
            follow_redirects=False,
            transport=transport,
            timeout=TIMEOUT_SECONDS,
        )

    def redact(self, text: str) -> str:
        """``text`` with this client's token replaced, for anything shown to the user."""
        return text.replace(self._token, "[redacted]") if self._token else text

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()
        self._follower.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        files: Any = None,
        data: Any = None,
        content: Any = None,
        headers: Mapping[str, str] | None = None,
        follow: bool = True,
    ) -> httpx.Response:
        return self._execute(
            method, path, params, json, files, data, content, headers,
            stream=False, follow=follow,
        )  # fmt: skip

    @contextmanager
    def stream(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Generator[httpx.Response]:
        """Like ``request`` but the body is not read; iterate it, then the response closes."""
        response = self._execute(method, path, params, None, None, None, None, headers, stream=True)
        try:
            yield response
        finally:
            response.close()

    def _execute(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None,
        json: Any,
        files: Any,
        data: Any,
        content: Any,
        headers: Mapping[str, str] | None,
        *,
        stream: bool,
        follow: bool = True,
    ) -> httpx.Response:
        url = validate_request_url(self._base, self._base + validate_api_path(path))
        extra = {k: v for k, v in (headers or {}).items() if k.lower() not in _STRIPPED_HEADERS}
        verb = method.upper()
        attempts = 0
        while True:
            try:
                request = self._client.build_request(
                    verb, url, params=params, json=json, files=files, data=data,
                    content=content, headers=extra,
                )  # fmt: skip
            except httpx.InvalidURL:
                raise UnsafePathError("the request URL is not valid") from None
            validate_request_url(self._base, str(request.url), allow_query=True)
            response = self._send(self._client, request, stream)
            if response.status_code != TOO_MANY_REQUESTS or attempts >= MAX_RETRIES:
                break
            attempts += 1
            self._sleep(_retry_delay(response.headers.get("Retry-After")))
            response.close()
        if follow and verb == "GET" and response.status_code in REDIRECT_STATUSES:
            return self._follow(response, stream)
        return response

    @staticmethod
    def was_redirected(response: httpx.Response) -> bool:
        """True when ``response`` came from a redirect hop (sent without the token)."""
        return bool(response.extensions.get(REDIRECTED_EXTENSION))

    @staticmethod
    def _send(client: httpx.Client, request: httpx.Request, stream: bool) -> httpx.Response:
        try:
            return client.send(request, stream=stream)
        except httpx.HTTPError as exc:
            raise ApiError(0, message=f"request failed: {type(exc).__name__}") from None

    def _follow(self, response: httpx.Response, stream: bool) -> httpx.Response:
        current = response
        for _ in range(MAX_HOPS):
            location = current.headers.get("Location")
            if current.status_code not in REDIRECT_STATUSES or not location:
                return current
            target = urljoin(str(current.url), location)
            if not target.lower().startswith(("http://", "https://")):
                current.close()
                raise ApiError(0, message="redirect to an unsupported URL scheme")
            try:
                has_userinfo = "@" in urlsplit(target).netloc
            except ValueError:
                has_userinfo = True
            if self._token and any(
                self._token in text for text in (target, unquote(target), unquote(unquote(target)))
            ):
                has_userinfo = True
            if has_userinfo:
                current.close()
                raise ApiError(0, message="redirect to a URL carrying credentials or invalid")
            current.close()
            self._follower.cookies.clear()
            current = self._send(
                self._follower, self._follower.build_request("GET", target), stream
            )
            current.extensions[REDIRECTED_EXTENSION] = True
        if current.status_code in REDIRECT_STATUSES:
            current.close()
            raise ApiError(0, message=f"too many redirects (more than {MAX_HOPS})")
        return current

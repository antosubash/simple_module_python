"""The guarded HTTP client: every CLI request goes through ApiClient."""

import ipaddress
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
    LOOPBACK_HOSTS,
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
METADATA_HOSTS = frozenset({"metadata.google.internal", "metadata"})
REDIRECTED_EXTENSION = "smr_redirected"
INVALID_REDIRECT = "the server sent an invalid redirect URL"
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
        on_wait: Callable[[float], None] | None = None,
    ) -> None:
        self._on_wait = on_wait
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
            delay = _retry_delay(response.headers.get("Retry-After"))
            if self._on_wait is not None:
                self._on_wait(delay)
            self._sleep(delay)
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
        except httpx.InvalidURL:
            # httpx parses a redirect's Location while sending, even with redirects off.
            raise ApiError(0, message=INVALID_REDIRECT) from None

    def _unsafe_redirect(self, target: str) -> bool:
        """True for a target with userinfo (or unparsable) or one that carries the token."""
        try:
            if "@" in urlsplit(target).netloc:
                return True
        except ValueError:
            return True
        decoded = (target, unquote(target), unquote(unquote(target)))
        return bool(self._token) and any(self._token in text for text in decoded)

    def _is_local(self, host: str) -> bool:
        """Whether the environment itself is on loopback or a private address."""
        if host in LOOPBACK_HOSTS:
            return True
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        return ip.is_private or ip.is_loopback

    def _blocked_hop(self, target: str) -> str | None:
        """Why the tokenless follower must not fetch ``target``, or ``None`` when it may."""
        parts = urlsplit(target)
        host = (parts.hostname or "").lower()
        if parts.scheme == "http" and host not in LOOPBACK_HOSTS:
            return "plain http to a non-loopback host"
        if host in METADATA_HOSTS:
            return "a metadata service address"
        env_local = self._is_local((urlsplit(self._base).hostname or "").lower())
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return None if host not in LOOPBACK_HOSTS or env_local else "a loopback address"
        if ip.is_link_local:
            return "a link-local address"
        if (ip.is_private or ip.is_loopback or ip.is_unspecified or ip.is_reserved) and (
            not env_local
        ):
            return "a private or loopback address"
        return None

    def _stays_in_api(self, target: str) -> bool:
        """True for a redirect target on the environment's origin under its /api/ prefix."""
        try:
            validate_request_url(self._base, target, allow_query=True)
        except UnsafePathError:
            return False
        return True

    def _follow(self, response: httpx.Response, stream: bool) -> httpx.Response:
        current = response
        for _ in range(MAX_HOPS):
            location = current.headers.get("Location")
            if current.status_code not in REDIRECT_STATUSES or not location:
                return current
            try:
                target = urljoin(str(current.url), location)
            except ValueError:
                current.close()
                raise ApiError(0, message=INVALID_REDIRECT) from None
            if not target.lower().startswith(("http://", "https://")):
                current.close()
                raise ApiError(0, message="redirect to an unsupported URL scheme")
            if self._unsafe_redirect(target):
                current.close()
                raise ApiError(0, message="redirect to a URL carrying credentials or invalid")
            current.close()
            # Same origin and still under the env's /api/: the token travels with it.
            # Anything else goes out bare, through the client that holds no credentials.
            keep_token = self._stays_in_api(target)
            if not keep_token and (why := self._blocked_hop(target)):
                raise ApiError(0, message=f"redirect refused: it points at {why}")
            client = self._client if keep_token else self._follower
            client.cookies.clear()
            try:
                hop = client.build_request("GET", target)
            except httpx.InvalidURL:
                raise ApiError(0, message=INVALID_REDIRECT) from None
            current = self._send(client, hop, stream)
            if not keep_token:
                current.extensions[REDIRECTED_EXTENSION] = True
        if current.status_code in REDIRECT_STATUSES:
            current.close()
            raise ApiError(0, message=f"too many redirects (more than {MAX_HOPS})")
        return current

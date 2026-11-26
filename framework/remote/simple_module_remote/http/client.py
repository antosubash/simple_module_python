"""The guarded HTTP client: every CLI request goes through ApiClient."""

import time
from collections.abc import Callable, Mapping
from types import TracebackType
from typing import Any
from urllib.parse import urljoin

import httpx

from simple_module_remote.config.environments import Environment
from simple_module_remote.http.errors import ApiError
from simple_module_remote.http.safety import validate_api_path, validate_base_url

REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
MAX_HOPS = 5
MAX_WAIT_SECONDS = 30.0
DEFAULT_RETRY_AFTER = 1.0
TOO_MANY_REQUESTS = 429
TIMEOUT_SECONDS = 30.0
_STRIPPED_HEADERS = frozenset({"authorization", "cookie", "host", "user-agent"})


def _retry_delay(value: str | None) -> float:
    if value is None:
        return DEFAULT_RETRY_AFTER
    text = value.strip()
    if text.isascii() and text.isdigit():
        return min(float(text), MAX_WAIT_SECONDS)
    # An HTTP date or anything unparsable: wait the default.
    return DEFAULT_RETRY_AFTER


class ApiClient:
    def __init__(
        self,
        env: Environment,
        token: str | None,
        *,
        user_agent: str,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
    ) -> None:
        self._base = validate_base_url(env.url).rstrip("/")
        self._sleep = sleep
        self._max_retries = max_retries
        self._user_agent = user_agent
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
    ) -> httpx.Response:
        url = self._base + validate_api_path(path)
        extra = {k: v for k, v in (headers or {}).items() if k.lower() not in _STRIPPED_HEADERS}
        verb = method.upper()
        attempts = 0
        while True:
            response = self._send(verb, url, params, json, files, data, content, extra)
            if response.status_code != TOO_MANY_REQUESTS or attempts >= self._max_retries:
                break
            attempts += 1
            self._sleep(_retry_delay(response.headers.get("Retry-After")))
            response.close()
        if verb == "GET" and response.status_code in REDIRECT_STATUSES:
            return self._follow(response)
        return response

    def _send(
        self,
        verb: str,
        url: str,
        params: Mapping[str, Any] | None,
        json: Any,
        files: Any,
        data: Any,
        content: Any,
        headers: Mapping[str, str],
    ) -> httpx.Response:
        try:
            return self._client.request(
                verb,
                url,
                params=params,
                json=json,
                files=files,
                data=data,
                content=content,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise ApiError(0, message=f"request failed: {type(exc).__name__}") from None

    def _follow(self, response: httpx.Response) -> httpx.Response:
        current = response
        for _ in range(MAX_HOPS):
            location = current.headers.get("Location")
            if current.status_code not in REDIRECT_STATUSES or not location:
                return current
            target = urljoin(str(current.url), location)
            if not target.lower().startswith(("http://", "https://")):
                raise ApiError(0, message="redirect to an unsupported URL scheme")
            self._follower.cookies.clear()
            try:
                current = self._follower.get(target)
            except httpx.HTTPError as exc:
                raise ApiError(0, message=f"redirect failed: {type(exc).__name__}") from None
        if current.status_code in REDIRECT_STATUSES:
            raise ApiError(0, message=f"too many redirects (more than {MAX_HOPS})")
        return current

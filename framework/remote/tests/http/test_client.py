import httpx
import pytest
from simple_module_remote.config.environments import Environment
from simple_module_remote.http.client import ApiClient
from simple_module_remote.http.errors import ApiError, UnsafePathError, exit_code_for

UA = "smdev/1 simple_module_remote/0"
TOKEN = "s3cret-token"


def _client(handler, url="https://app.example", sleeps=None, **kw) -> ApiClient:
    return ApiClient(
        Environment("e", url),
        TOKEN,
        user_agent=UA,
        transport=httpx.MockTransport(handler),
        sleep=(sleeps if sleeps is not None else []).append,
        **kw,
    )


def test_auth_and_user_agent_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={})

    with _client(handler, "https://app.example/app/") as c:
        c.request("GET", "/api/x", params={"a": "1"}, headers={"Authorization": "evil"})
    assert str(seen[0].url) == "https://app.example/app/api/x?a=1"
    assert seen[0].headers["authorization"] == f"Bearer {TOKEN}"
    assert seen[0].headers["user-agent"] == UA


def test_rejects_unsafe_path_sends_nothing() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("must not send")

    with _client(handler) as c, pytest.raises(UnsafePathError):
        c.request("GET", "/api/../x")


def test_http_url_refused_non_loopback() -> None:
    with pytest.raises(UnsafePathError):
        _client(lambda r: httpx.Response(200), "http://app.example")


def test_http_loopback_allowed() -> None:
    with _client(lambda r: httpx.Response(200), "http://localhost:8000") as c:
        assert c.request("GET", "/api/x").status_code == 200


def test_redirect_drops_auth() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.host == "app.example":
            return httpx.Response(
                302, headers={"Location": "https://storage.example/obj"}, content=b""
            )
        return httpx.Response(200, content=b"data")

    with _client(handler) as c:
        resp = c.request("GET", "/api/file")
    assert resp.content == b"data"
    assert "authorization" not in seen[1].headers
    assert "cookie" not in seen[1].headers


def test_relative_redirect_resolved_and_no_auth() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.path == "/api/a":
            return httpx.Response(307, headers={"Location": "/dl/b"})
        return httpx.Response(200)

    with _client(handler) as c:
        c.request("GET", "/api/a")
    assert str(seen[1].url) == "https://app.example/dl/b"
    assert "authorization" not in seen[1].headers


def test_redirect_loop_gives_up() -> None:
    n = {"c": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        n["c"] += 1
        return httpx.Response(302, headers={"Location": "https://o.example/x"})

    with _client(handler) as c, pytest.raises(ApiError) as ei:
        c.request("GET", "/api/a")
    assert TOKEN not in str(ei.value) + repr(ei.value)
    assert n["c"] == 6


def test_non_get_redirect_returned_as_is() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://o.example/x"})

    with _client(handler) as c:
        assert c.request("POST", "/api/a", json={}).status_code == 302


def test_429_retries_with_retry_after() -> None:
    codes = iter([429, 200])
    sleeps: list[float] = []

    def handler(req: httpx.Request) -> httpx.Response:
        code = next(codes)
        return httpx.Response(code, headers={"Retry-After": "2"} if code == 429 else {})

    with _client(handler, sleeps=sleeps) as c:
        assert c.request("GET", "/api/x").status_code == 200
    assert sleeps == [2.0]


@pytest.mark.parametrize(
    ("header", "expected"),
    [("Wed, 21 Oct 2099 07:28:00 GMT", 1.0), ("junk", 1.0), ("999", 30.0)],
)
def test_retry_after_forms(header: str, expected: float) -> None:
    codes = iter([429, 200])
    sleeps: list[float] = []

    def handler(req: httpx.Request) -> httpx.Response:
        code = next(codes)
        return httpx.Response(code, headers={"Retry-After": header} if code == 429 else {})

    with _client(handler, sleeps=sleeps) as c:
        c.request("GET", "/api/x")
    assert sleeps == [expected]


def test_429_gives_up_after_3() -> None:
    sleeps: list[float] = []
    with _client(lambda r: httpx.Response(429), sleeps=sleeps) as c:
        assert c.request("GET", "/api/x").status_code == 429
    assert sleeps == [1.0, 1.0, 1.0]


def test_network_error_is_api_error_without_token() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=req)

    with _client(handler) as c, pytest.raises(ApiError) as ei:
        c.request("GET", "/api/x")
    assert exit_code_for(ei.value.status) == 3
    assert TOKEN not in str(ei.value) + repr(ei.value)


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, 4), (403, 4), (404, 5), (409, 6), (412, 6), (422, 2), (500, 3)],
)
def test_exit_code_mapping(status: int, code: int) -> None:
    assert exit_code_for(status) == code


def test_stream_follows_redirect_without_auth_and_flags_it() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.url.host == "app.example":
            return httpx.Response(302, headers={"Location": "https://cdn.example/f"})
        return httpx.Response(200, content=b"abc", headers={"Content-Type": "image/png"})

    with _client(handler) as c, c.stream("GET", "/api/f") as r:
        assert b"".join(r.iter_bytes()) == b"abc"
        assert c.was_redirected(r)
    assert "authorization" not in seen[1].headers
    assert seen[0].headers["authorization"] == f"Bearer {TOKEN}"


def test_direct_response_not_marked_redirected() -> None:
    with _client(lambda r: httpx.Response(200)) as c:
        assert not c.was_redirected(c.request("GET", "/api/x"))

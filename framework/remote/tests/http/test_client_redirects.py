import httpx
import pytest
from simple_module_remote.config.environments import Environment
from simple_module_remote.http.client import ApiClient
from simple_module_remote.http.errors import ApiError, exit_code_for

UA = "smdev/1 simple_module_remote/0"
TOKEN = "s3cret-token"


def _client(handler, url="https://app.example") -> ApiClient:
    return ApiClient(
        Environment("e", url),
        TOKEN,
        user_agent=UA,
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )


@pytest.mark.parametrize(
    "location", ["javascript:alert(1)", "http:\\\\evil\\x", "http://[::1", "//[::1"]
)
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_invalid_redirect_location_is_a_clean_api_error(method, location) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": location})

    with _client(handler) as c, pytest.raises(ApiError) as info:
        c.request(method, "/api/x")
    assert exit_code_for(info.value.status) == 3
    assert info.value.message and TOKEN not in info.value.message


def _redirecting(location: str, seen: list[httpx.Request]):
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if len(seen) == 1:
            return httpx.Response(307, headers={"Location": location})
        return httpx.Response(200, json={})

    return handler


@pytest.mark.parametrize(
    "location",
    ["/api/users/", "https://app.example/api/users/?a=1", "https://app.example:443/api/x"],
)
def test_same_origin_redirect_under_api_keeps_the_token(location: str) -> None:
    seen: list[httpx.Request] = []
    with _client(_redirecting(location, seen)) as c:
        response = c.request("GET", "/api/users")
    assert seen[1].headers["authorization"] == f"Bearer {TOKEN}"
    assert not c.was_redirected(response)


@pytest.mark.parametrize(
    "location",
    [
        "https://other.example/api/users/",  # another host
        "https://app.example:8443/api/users/",  # another port
        "http://app.example/api/users/",  # another scheme
        "/dl/users",  # same origin, outside /api/
        "/api/../dl/users",  # dot segments escape the prefix
    ],
)
def test_other_redirect_targets_drop_the_token(location: str) -> None:
    seen: list[httpx.Request] = []
    with _client(_redirecting(location, seen)) as c:
        response = c.request("GET", "/api/users")
    assert "authorization" not in seen[1].headers
    assert c.was_redirected(response)


def test_same_origin_redirect_under_a_base_path_must_stay_under_it() -> None:
    seen: list[httpx.Request] = []
    with _client(_redirecting("/other/api/x", seen), "https://app.example/app/") as c:
        c.request("GET", "/api/x")
    assert "authorization" not in seen[1].headers

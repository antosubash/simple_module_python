import httpx
import pytest
from simple_module_remote.http.errors import UnsafePathError
from simple_module_remote.http.safety import (
    validate_api_path,
    validate_base_url,
    validate_request_url,
)


@pytest.mark.parametrize(
    "path",
    [
        "http://x/api/a",
        "/api//evil",
        "/api/a@b",
        "/other",
        "/api/a\\b",
        "/api/a\nb",
        "/api/../admin",
        "/api/%2e%2e/admin",
        "/api/a?x=1",
        "/api/a#f",
    ],
)
def test_rejects_paths(path: str) -> None:
    with pytest.raises(UnsafePathError):
        validate_api_path(path)


def test_accepts_api_path() -> None:
    assert validate_api_path("/api/users/1") == "/api/users/1"


@pytest.mark.parametrize("url", ["https://h.example", "http://localhost:8000", "http://[::1]:1"])
def test_base_url_ok(url: str) -> None:
    assert validate_base_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://h.example",
        "ftp://h",
        "https://u:p@h",
        "https://h?x=1",
        "https://host/outside#",
        "https://host/x?",
        "https://host:abc",
        "https://host:99999",
        "https://host:0",
    ],
)
def test_base_url_refused(url: str) -> None:
    with pytest.raises(UnsafePathError):
        validate_base_url(url)


@pytest.mark.parametrize(
    "url", ["ftp://user:hunter2@h.example", "//user:hunter2@h", "user:hunter2@h"]
)
def test_base_url_error_never_echoes_userinfo(url: str) -> None:
    with pytest.raises(UnsafePathError) as err:
        validate_base_url(url)
    assert "hunter2" not in str(err.value)


def test_request_url_must_stay_under_base_api() -> None:
    base = "https://h.example/app"
    assert (
        validate_request_url(base, "https://h.example/app/api/x") == "https://h.example/app/api/x"
    )
    for bad in (
        "https://h.example/api/x",
        "https://h.example/app/api/x?y=1",
        "https://h.example/app/api/x#f",
        "https://other.example/app/api/x",
        "https://h.example/app/other",
    ):
        with pytest.raises(UnsafePathError):
            validate_request_url(base, bad)


@pytest.mark.parametrize("url", ["https://h/a/../b", "https://h/a/%2e%2e/b", "https://h/./x"])
def test_base_url_with_dot_segments_refused(url: str) -> None:
    with pytest.raises(UnsafePathError):
        validate_base_url(url)


def test_built_url_check_allows_query_and_default_port() -> None:
    ok = validate_request_url("https://h:443/app", "https://h/app/api/x?a=1", allow_query=True)
    assert ok.endswith("?a=1")
    with pytest.raises(UnsafePathError):
        validate_request_url(
            "https://h/app", str(httpx.URL("https://h/app/api/../x")), allow_query=True
        )

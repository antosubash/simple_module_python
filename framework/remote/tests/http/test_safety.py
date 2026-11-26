import pytest
from simple_module_remote.http.errors import UnsafePathError
from simple_module_remote.http.safety import validate_api_path, validate_base_url


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


@pytest.mark.parametrize("url", ["http://h.example", "ftp://h", "https://u:p@h", "https://h?x=1"])
def test_base_url_refused(url: str) -> None:
    with pytest.raises(UnsafePathError):
        validate_base_url(url)

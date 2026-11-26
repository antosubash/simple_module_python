"""Guards that keep requests inside the environment's own /api/ surface."""

from urllib.parse import unquote, urlsplit

from simple_module_remote.http.errors import UnsafePathError

API_PREFIX = "/api/"
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_FORBIDDEN_SUBSTRINGS = ("://", "@", "//", "\\", "?", "#")
_DOT_SEGMENTS = frozenset({"..", "."})


def validate_api_path(path: str) -> str:
    if not path.startswith(API_PREFIX):
        raise UnsafePathError(f"path must start with {API_PREFIX}: {path!r}")
    if any(token in path for token in _FORBIDDEN_SUBSTRINGS):
        raise UnsafePathError(f"unsafe characters in path: {path!r}")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in path):
        raise UnsafePathError("control characters in path")
    for segment in path.split("/"):
        decoded = unquote(segment)
        if decoded in _DOT_SEGMENTS or "/" in decoded or "\\" in decoded:
            raise UnsafePathError(f"unsafe path segment in {path!r}")
    return path


def validate_base_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname
    if not host or parts.scheme not in ("http", "https"):
        raise UnsafePathError(f"environment url must be http(s) with a host: {url!r}")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise UnsafePathError("environment url must not carry credentials, query or fragment")
    if parts.scheme == "http" and host not in LOOPBACK_HOSTS:
        raise UnsafePathError(f"refusing plain http to non-loopback host {host!r}: use https")
    return url

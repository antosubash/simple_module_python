"""Guards that keep requests inside the environment's own /api/ surface."""

from urllib.parse import SplitResult, unquote, urlsplit, urlunsplit

import httpx

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


def _redacted(parts: SplitResult) -> str:
    """The URL without userinfo, query or fragment, safe to show in an error."""
    return urlunsplit(parts._replace(netloc=parts.netloc.rpartition("@")[2], query="", fragment=""))


def validate_base_url(url: str) -> str:
    if not url.isprintable() or any(ch.isspace() for ch in url) or "\\" in url:
        raise UnsafePathError(
            "environment url must not contain whitespace, control characters or backslashes"
        )
    try:
        parts = urlsplit(url)
    except ValueError:
        raise UnsafePathError("environment url is not a valid URL") from None
    if (
        "@" in parts.netloc
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or "?" in url
        or "#" in url
    ):
        raise UnsafePathError("environment url must not carry credentials, query or fragment")
    if any(unquote(seg) in _DOT_SEGMENTS for seg in parts.path.split("/")):
        raise UnsafePathError("environment url path must not contain dot segments")
    try:
        port = parts.port  # raises ValueError for a malformed or out-of-range port
    except ValueError:
        port = 0
    if port == 0:
        raise UnsafePathError("environment url has an invalid port")
    host = parts.hostname
    if not host or parts.scheme not in ("http", "https"):
        shown = "" if "@" in url else f": {_redacted(parts)!r}"
        raise UnsafePathError(f"environment url must be http(s) with a host{shown}")
    if parts.scheme == "http" and host not in LOOPBACK_HOSTS:
        raise UnsafePathError(f"refusing plain http to non-loopback host {host!r}: use https")
    return url


_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_origin(url: str) -> str:
    """``scheme://host[:port]`` with a lowercase scheme and host and no default port.

    A string that does not parse comes back unchanged (validation reports it elsewhere).
    """
    try:
        parts = urlsplit(url)
        host, number = parts.hostname, parts.port
    except ValueError:
        return url
    if not host or not parts.scheme:
        return url
    shown = f"[{host}]" if ":" in host else host
    port = f":{number}" if number and number != _DEFAULT_PORTS.get(parts.scheme.lower()) else ""
    return f"{parts.scheme.lower()}://{shown}{port}"


def normalize_url(url: str) -> str:
    """The canonical form stored for an environment: normalised origin, path without ``/``."""
    try:
        path = urlsplit(url).path.rstrip("/")
    except ValueError:
        return url
    origin = normalize_origin(url)
    return url if origin == url else origin + path


def _origin(parts: SplitResult) -> tuple[str, str | None, int | None]:
    return (parts.scheme, parts.hostname, parts.port or _DEFAULT_PORTS.get(parts.scheme))


def validate_request_url(base: str, url: str, *, allow_query: bool = False) -> str:
    """Refuse a request URL that is not under ``base`` + ``/api/`` on the same origin.

    Run it on the composed string and again on the URL httpx built, which has had its
    dot segments resolved (``allow_query`` then admits the encoded query parameters).
    """
    try:
        # The same parser as the client, so IDNA hosts compare in their ASCII form.
        wanted, got = urlsplit(str(httpx.URL(base))), urlsplit(str(httpx.URL(url)))
        same_origin = _origin(got) == _origin(wanted)
    except (ValueError, httpx.InvalidURL):
        raise UnsafePathError("request URL is not valid") from None
    prefix = wanted.path.rstrip("/") + API_PREFIX
    if (
        not same_origin
        or (got.query and not allow_query)
        or got.fragment
        or not got.path.startswith(prefix)
    ):
        raise UnsafePathError("request URL would leave the environment's /api/ surface")
    return url

"""Validation shared by settings used as public link bases."""

from urllib.parse import urlsplit

from pydantic import HttpUrl


def validate_http_base_url(value: str, field_name: str) -> str:
    """Trim a blank or credential-free HTTP(S) URL, preserving path prefixes."""
    value = value.strip()
    if not value:
        return value
    message = (
        f"{field_name} must be an absolute http(s) URL without credentials "
        "of at most 2083 characters (e.g. https://example.com), or blank"
    )
    try:
        parts = urlsplit(value)
        if (
            not parts.netloc
            or parts.username is not None
            # URL parsers can silently repair controls and backslashes.
            or any(c.isspace() or c == "\\" or ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ValueError(message)
        HttpUrl(value)
    except ValueError as exc:
        raise ValueError(message) from exc
    return value

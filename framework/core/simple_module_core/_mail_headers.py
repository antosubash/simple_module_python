"""Validation shared by mail messages and transports."""

import re

_HEADER_NAME = re.compile(r"[!-9;-~]+")
_RESERVED_HEADERS = frozenset(
    {"from", "to", "cc", "bcc", "subject", "reply-to", "date", "message-id", "mime-version"}
)


def validate_mail_headers(headers: dict[str, str]) -> dict[str, str]:
    """Copy safe custom headers; reject sender-owned names and injection."""
    for name, value in headers.items():
        if not isinstance(name, str) or not _HEADER_NAME.fullmatch(name):
            raise ValueError("mail header names must be printable ASCII without spaces or colons")
        if name.lower() in _RESERVED_HEADERS or name.lower().startswith("content-"):
            raise ValueError(f"mail header {name!r} is owned by the sender")
        if not isinstance(value, str) or "\r" in value or "\n" in value:
            raise ValueError("mail header values must be strings without CR or LF")
    return dict(headers)

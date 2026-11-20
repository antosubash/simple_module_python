"""Validation shared by mail messages and transports."""

import re

_HEADER_NAME = re.compile(r"[!-9;-~]{1,997}")
_UNSAFE_VALUE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f-\x9f\u2028\u2029]")
_RESERVED_HEADERS = frozenset(
    {
        "from",
        "to",
        "cc",
        "bcc",
        "subject",
        "reply-to",
        "date",
        "message-id",
        "mime-version",
        "sender",
        "return-path",
        "received",
        "received-spf",
        "dkim-signature",
        "authentication-results",
        "delivered-to",
        "envelope-to",
        "envelope-from",
    }
)

# Routing, authentication and delivery trace fields belong to the transport/MTA.
_RESERVED_PREFIXES = ("content-", "resent-", "arc-", "x-original-", "x-delivered-", "x-envelope-")


def validate_mail_headers(headers: dict[str, str]) -> dict[str, str]:
    """Copy custom headers, excluding transport/MTA fields and control characters."""
    for name, value in headers.items():
        if not isinstance(name, str) or not _HEADER_NAME.fullmatch(name):
            raise ValueError(
                "mail header names must be 1-997 ASCII characters without spaces or colons"
            )
        if name.lower() in _RESERVED_HEADERS or name.lower().startswith(_RESERVED_PREFIXES):
            raise ValueError(f"mail header {name!r} is owned by the sender")
        if not isinstance(value, str) or _UNSAFE_VALUE.search(value):
            raise ValueError(
                "mail header values must be strings without controls other than horizontal tab"
            )
    return dict(headers)

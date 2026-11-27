"""Keep error payloads renderable as UTF-8 without dropping their fields."""

import re
from typing import Any

_SURROGATES = re.compile(r"[\ud800-\udfff]")


def sanitize_error_payload(value: Any) -> Any:
    """Replace surrogate code points in JSON-shaped error data with U+FFFD."""
    if isinstance(value, str):
        return _SURROGATES.sub("\ufffd", value)
    if isinstance(value, dict):
        return {
            sanitize_error_payload(key): sanitize_error_payload(child)
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_error_payload(child) for child in value]
    return value

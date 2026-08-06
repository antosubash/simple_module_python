"""Configurable footer — limits, link validation and settings (de)serialisation.

Ported from IIASA.GeoWiki's ``FooterAppService``. The footer is stored as two
JSON blobs in the shared settings store (there is no branding table), so this
module owns turning them into structures and back.

``validate_href`` is the security-relevant part: these URLs are authored by an
admin and rendered into an anchor on *every* page, including guest ones. Only
http(s) and single-leading-slash app paths are allowed, which is what keeps a
``javascript:`` URL out of the document.
"""

from __future__ import annotations

import json
from typing import Any, Final
from urllib.parse import urlparse

MAX_COLUMNS: Final = 6
MAX_LINKS_PER_COLUMN: Final = 8
MAX_SOCIAL_LINKS: Final = 8
MAX_LABEL_LEN: Final = 40
MAX_HREF_LEN: Final = 500
MAX_TEXT_LEN: Final = 200
#: Ceiling on either serialised blob, so one setting row can't grow unbounded.
MAX_SERIALISED_LEN: Final = 8_000

_ALLOWED_SCHEMES: Final = frozenset({"http", "https"})

HREF_ERROR: Final = "is not a valid link. Use a relative path (/page/...) or an http(s) URL."


def validate_href(href: str) -> str:
    """Return a trimmed, safe href or raise ``ValueError``.

    Rejects every scheme but http(s) — notably ``javascript:``, which would
    otherwise execute from a link an admin pasted. A single leading slash is an
    in-app path and allowed; ``//host`` is *not* a path but a protocol-relative
    absolute URL, so it falls through to the scheme check and is rejected.
    """
    cleaned = href.strip()
    if not cleaned:
        raise ValueError("A link URL is required.")
    if len(cleaned) > MAX_HREF_LEN:
        raise ValueError(f"A link URL must be at most {MAX_HREF_LEN} characters")

    if cleaned.startswith("/") and not cleaned.startswith("//"):
        return cleaned

    parsed = urlparse(cleaned)
    if parsed.scheme in _ALLOWED_SCHEMES and parsed.netloc:
        return cleaned

    raise ValueError(f"{cleaned!r} {HREF_ERROR}")


def clean_label(value: str, *, what: str = "label") -> str:
    """Trim + bound a user-visible label."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"A link {what} is required.")
    if len(cleaned) > MAX_LABEL_LEN:
        raise ValueError(f"A link {what} must be at most {MAX_LABEL_LEN} characters")
    return cleaned


def clean_text(value: str) -> str:
    """Trim + bound a free-text footer line (tagline, copyright, note)."""
    cleaned = value.strip()
    if len(cleaned) > MAX_TEXT_LEN:
        raise ValueError(f"Footer text must be at most {MAX_TEXT_LEN} characters")
    return cleaned


def dumps(items: list[dict[str, Any]]) -> str:
    """Serialise a footer structure for the settings store, bounded in size."""
    payload = json.dumps(items, separators=(",", ":"))
    if len(payload) > MAX_SERIALISED_LEN:
        raise ValueError("Footer configuration is too large. Please remove some links.")
    return payload


def loads(raw: str) -> list[dict[str, Any]]:
    """Parse a stored footer blob, tolerating anything unusable.

    Deliberately lenient: settings hydrate from the DB, where a hand-edited or
    truncated row must degrade to "no configured footer" rather than break
    every page render.
    """
    if not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]

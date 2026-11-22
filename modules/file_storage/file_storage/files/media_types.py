"""Which stored content types are safe to hand a browser inline (#545).

The stored type comes from the uploader (``allowed_content_types`` is ``None``
by default), so this decides from a strict allow-list rather than a list of
known-dangerous types: a deny-list missed ``application/rss+xml``,
``text/xsl`` and the rest of the scriptable XML family, and an exact-match
check let ``Text/HTML`` or ``text/html,`` through.

A malformed value is never "cleaned up" into a safe-looking one: browsers
disagree on how to read ``image/png,text/html`` (Fetch's MIME extraction takes
the *last* type), so anything that is not exactly one ``type/subtype`` token
pair is treated as active.
"""

from __future__ import annotations

import re

from file_storage.core import constants
from file_storage.files.thumbnails import base_type

# RFC 9110 ``token`` characters, on both sides of a single "/".
_MEDIA_TYPE = re.compile(r"[a-z0-9!#$%&'*+.^_`|~-]+/[a-z0-9!#$%&'*+.^_`|~-]+")
_TOKEN = r"[A-Za-z0-9!#$%&'*+.^_`|~-]+"
# RFC 9110 quoted-string / quoted-pair, with control chars excluded below.
_QUOTED = r'"(?:[\x20-\x21\x23-\x5b\x5d-\x7e\x80-\xff]|\\[\x20-\x7e\x80-\xff])*"'
_RESPONSE_PARAM = re.compile(rf"(?:; *)+({_TOKEN}=(?:{_TOKEN}|{_QUOTED})) *")


def normalise_media_type(content_type: str | None) -> str | None:
    """``type/subtype`` lower-cased with parameters dropped; ``None`` if malformed.

    ``Image/PNG; charset=x`` -> ``image/png``. ``text/html,``, a comma or quote
    anywhere (even in a parameter), an empty value, or anything with stray
    characters around the pair -> ``None``.
    """
    # A comma anywhere, parameters included, splits the header for a browser:
    # ``image/png;x=1,text/html`` is read as ``text/html`` while the part
    # before ";" looks safe. Quotes would let a parameter hide one, and
    # control chars must never reach response headers.
    if not content_type or any(ord(c) < 0x20 or ord(c) == 0x7F or c in ',"' for c in content_type):
        return None
    media = base_type(content_type)
    return media if _MEDIA_TYPE.fullmatch(media) else None


def safe_media_type(content_type: str | None) -> str:
    """Return a validated media type preserving safe MIME parameters, else fallback."""
    if not content_type or any(
        ord(c) < 0x20 or ord(c) == 0x7F or ord(c) > 0xFF for c in content_type
    ):
        return "application/octet-stream"
    head, sep, tail = content_type.partition(";")
    base = head.strip().lower()
    if not _MEDIA_TYPE.fullmatch(base):
        return "application/octet-stream"
    remaining = sep + tail
    params = []
    while remaining.strip("; "):
        match = _RESPONSE_PARAM.match(remaining)
        if match is None:
            # Never echo malformed quotes or a second header value.
            return "application/octet-stream" if any(c in remaining for c in ',"') else base
        params.append(match[1])
        remaining = remaining[match.end() :]
    return f"{base}; {'; '.join(params)}" if params else base


def is_active_content(content_type: str | None) -> bool:
    """Whether the type must be served as a sandboxed attachment, never inline.

    True for everything outside :data:`~file_storage.core.constants.INLINE_SAFE_CONTENT_TYPES`
    and the media families, for any XML subtype even inside those families,
    and for any value :func:`normalise_media_type` cannot read.
    """
    media = normalise_media_type(content_type)
    if media is None:
        return True
    if media in constants.INLINE_SAFE_CONTENT_TYPES:
        return False
    family, subtype = media.split("/", 1)
    if "xml" in subtype or "html" in subtype:
        return True
    return family not in constants.INLINE_SAFE_FAMILIES

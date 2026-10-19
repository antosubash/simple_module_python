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

from file_storage import constants

# RFC 9110 ``token`` characters, on both sides of a single "/".
_MEDIA_TYPE = re.compile(r"[a-z0-9!#$%&'*+.^_`|~-]+/[a-z0-9!#$%&'*+.^_`|~-]+")


def normalise_media_type(content_type: str | None) -> str | None:
    """``type/subtype`` lower-cased with parameters dropped; ``None`` if malformed.

    ``Image/PNG; charset=x`` -> ``image/png``. ``text/html,``, an empty value,
    or anything with stray characters around the pair -> ``None``.
    """
    if not content_type:
        return None
    media = content_type.split(";", 1)[0].strip().lower()
    return media if _MEDIA_TYPE.fullmatch(media) else None


def is_active_content(content_type: str | None) -> bool:
    """Whether the type must be served as a sandboxed attachment, never inline.

    True for everything outside :data:`~file_storage.constants.INLINE_SAFE_CONTENT_TYPES`
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

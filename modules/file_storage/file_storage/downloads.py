"""How a stored file leaves the app: result shapes and download headers.

``Content-Disposition`` (RFC 6266 / 5987) lives here so the service (presigned
redirects) and the serving helpers (streamed bodies) build it the same way
without importing each other.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    from file_storage.contracts.service import StorageBackend
    from file_storage.models import StoredFile


@dataclass
class StreamDownload:
    """Response shape for backends that proxy bytes through the app."""

    file: StoredFile
    body: AsyncIterator[bytes] | None  # None when the caller opted out via open_body=False


@dataclass
class RedirectDownload:
    """Response shape for backends that issue presigned URLs."""

    file: StoredFile
    url: str


Download = StreamDownload | RedirectDownload


def content_disposition(filename: str, *, attachment: bool) -> str:
    ascii_name = "".join(
        c for c in filename.encode("ascii", "ignore").decode() if c.isprintable() and c not in '"\\'
    )
    kind = "attachment" if attachment else "inline"
    return f"{kind}; filename=\"{ascii_name or 'file'}\"; filename*=UTF-8''{quote(filename)}"


async def presigned_download_url(
    backend: StorageBackend, row: StoredFile, ttl_seconds: int, *, attachment: bool
) -> str:
    """A presigned URL whose response carries ``row``'s own name and type.

    Without the overrides the backend answers with the object's stored
    metadata, and the browser saves the file under its opaque key (GH #489).
    """
    return await backend.presigned_get_url(
        row.key,
        ttl_seconds,
        content_disposition=content_disposition(row.filename, attachment=attachment),
        content_type=row.content_type,
    )

"""Branding module constants."""

from __future__ import annotations

from typing import Final

PACKAGE: Final = "branding"

PERM_VIEW: Final = "branding.view"
PERM_MANAGE: Final = "branding.manage"

# Image upload guard-rails (enforced before handing the file to file_storage).
MAX_IMAGE_BYTES: Final = 2 * 1024 * 1024  # 2 MB
ALLOWED_IMAGE_TYPES: Final = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/svg+xml",
        "image/webp",
        "image/gif",
        "image/x-icon",
        "image/vnd.microsoft.icon",
    }
)

# Mirrors the file_storage download route (``/api/file-storage`` +
# ``/files/{id}/download``). Branding depends on FileStorage, so this stable
# public URL is safe to derive without a runtime lookup.
FILE_DOWNLOAD_URL: Final = "/api/file-storage/files/{}/download"

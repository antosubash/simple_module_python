"""Branding module constants."""

from __future__ import annotations

from typing import Final

PACKAGE: Final = "branding"

# Modules this one depends on (kept as constants so the depends_on list doesn't
# carry bare string literals — see scripts/check_hardcoded_strings.py).
_MODULE_SETTINGS: Final = "Settings"
_MODULE_FILE_STORAGE: Final = "FileStorage"

# Inertia page identifier. The view endpoint renders this as a literal (so the
# SM003/SM004 static-AST diagnostics can pair it with pages/Manage.tsx); a test
# asserts the literal matches this constant.
_PAGE_MANAGE: Final = "Branding/Manage"

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

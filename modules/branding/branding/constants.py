"""Branding module constants."""

from __future__ import annotations

import re
from typing import Final

from file_storage.constants import PATH_FILE_DOWNLOAD, ROUTE_PREFIX_API

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

# A #rrggbb hex colour (single source of truth for both the settings and the
# update-DTO validators).
HEX_COLOR_RE: Final = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_APP_NAME_LEN: Final = 60

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

# file_storage download URL, derived from file_storage's own route constants
# (branding depends on FileStorage) so it tracks any route change. The
# ``{file_id}`` placeholder is filled per stored-file id.
FILE_DOWNLOAD_URL: Final = ROUTE_PREFIX_API + PATH_FILE_DOWNLOAD

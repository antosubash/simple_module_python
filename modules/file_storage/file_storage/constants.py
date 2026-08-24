"""Single source of truth for every literal in the file_storage module.

Permissions, event topics, route prefixes, env-var prefix, page names, table
names, error codes, default config values — all live here. Other files in the
module import from this one rather than embedding string literals, so renames
stay localised and `rg` can prove there are no magic strings outside of this
file.
"""

from __future__ import annotations

from typing import Final

# ── Module identity ──────────────────────────────────────────────────
# ``MODULE_NAME`` is the snake_case package name; ``MODULE_PASCAL`` matches the
# Inertia page-prefix convention (PascalCase of the module dir). ``meta.name``
# uses ``MODULE_PASCAL`` so the diagnostic code SM003 lines up against
# ``FileStorage/Browse.tsx``. ``MODULE_DISPLAY_NAME`` is the user-visible label
# (menu, permission group) — keep it free-form.
MODULE_NAME: Final = "file_storage"
MODULE_PASCAL: Final = "FileStorage"
MODULE_DISPLAY_NAME: Final = "Files"
_MODULE_SETTINGS: Final = "Settings"

# ── Configuration ────────────────────────────────────────────────────
ENV_PREFIX: Final = "SM_FILE_STORAGE_"

# ── Routing ──────────────────────────────────────────────────────────
ROUTE_PREFIX_API: Final = "/api/file-storage"
ROUTE_PREFIX_VIEW: Final = "/file-storage"

# REST sub-paths (joined to ROUTE_PREFIX_API by the router)
PATH_UPLOAD: Final = "/upload"
PATH_FILES: Final = "/files"
PATH_FILE_BY_ID: Final = "/files/{file_id}"
PATH_FILE_DOWNLOAD: Final = "/files/{file_id}/download"

# ── Inertia page names ───────────────────────────────────────────────
PAGE_BROWSE: Final = "FileStorage/Browse"

# ── Database ─────────────────────────────────────────────────────────
SCHEMA_NAME: Final = "file_storage"
TABLE_STORED_FILE: Final = "file_storage_stored_file"

# ── i18n ─────────────────────────────────────────────────────────────
LOCALE_NAMESPACE: Final = MODULE_NAME


class BackendId:
    """Stable identifiers for built-in storage providers.

    Third-party providers register themselves under any string id, but the
    built-ins are referenced from settings, the model, and tests, so they
    deserve named constants.
    """

    FILESYSTEM: Final = "filesystem"
    S3: Final = "s3"


class AddressingStyle:
    """S3 URL addressing modes, mapped straight onto botocore's values.

    ``VIRTUAL`` puts the bucket in the hostname (``bucket.s3.amazonaws.com``);
    ``PATH`` keeps it in the path (``host/bucket/key``). Providers reached by
    IP or ``localhost`` — MinIO, Ceph — can only do path-style, since a bucket
    hostname would not resolve. ``AUTO`` defers to botocore's own heuristic.
    """

    AUTO: Final = "auto"
    PATH: Final = "path"
    VIRTUAL: Final = "virtual"


class Permission:
    UPLOAD: Final = "file_storage.upload"
    DOWNLOAD: Final = "file_storage.download"
    DELETE: Final = "file_storage.delete"
    MANAGE: Final = "file_storage.manage"


class Event:
    FILE_UPLOADED: Final = "file_storage.file.uploaded"
    FILE_DELETED: Final = "file_storage.file.deleted"


class FeatureFlag:
    PUBLIC_UPLOADS: Final = "file_storage.public_uploads"


class ErrorCode:
    """Machine-readable codes returned in 4xx response bodies."""

    TOO_LARGE: Final = "file_storage.too_large"
    BAD_TYPE: Final = "file_storage.bad_type"
    NOT_FOUND: Final = "file_storage.not_found"
    BACKEND_ERROR: Final = "file_storage.backend_error"


class I18nKey:
    """Translator keys (full dotted paths). Mirror locales/en.json shape."""

    ERR_NOT_FOUND: Final = "file_storage.errors.not_found"
    ERR_TOO_LARGE: Final = "file_storage.errors.too_large"
    ERR_BAD_TYPE: Final = "file_storage.errors.bad_type"
    ERR_BACKEND: Final = "file_storage.errors.backend_error"


# ── Defaults ─────────────────────────────────────────────────────────
DEFAULT_BACKEND: Final = BackendId.FILESYSTEM
DEFAULT_FS_ROOT: Final = "./uploads"
DEFAULT_KEY_PREFIX: Final = ""  # blank = bucket root, preserving legacy layout
# Providers that ignore regions (R2, most MinIO deployments) still need *some*
# region string for SigV4 to compute a signature, so we default rather than
# require. ``us-east-1`` is the conventional filler.
DEFAULT_S3_REGION: Final = "us-east-1"
DEFAULT_ADDRESSING_STYLE: Final = AddressingStyle.AUTO
DEFAULT_MAX_FILE_SIZE_BYTES: Final = 100 * 1024 * 1024  # 100 MB
DEFAULT_PRESIGN_TTL_SECONDS: Final = 300  # 5 minutes
DEFAULT_CHUNK_SIZE: Final = 64 * 1024  # 64 KB
SPOOL_MAX_SIZE_BYTES: Final = 10 * 1024 * 1024  # 10 MB before disk-spill

# ── Menu ─────────────────────────────────────────────────────────────
MENU_ICON: Final = "files"
MENU_ORDER: Final = 40
MENU_ROLES: Final = ("admin",)
ADMIN_ROLE: Final = "admin"
USER_ROLE: Final = "user"

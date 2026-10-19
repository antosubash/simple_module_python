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
PATH_FILE_THUMBNAIL: Final = "/files/{file_id}/thumbnail"
# Anonymous serving of ``public`` files (#353). The thumbnail route is declared
# before the named one, so a file literally called "thumbnail" is reachable
# only through the id-only form.
PUBLIC_SEGMENT: Final = "/public"
PATH_PUBLIC: Final = "/public/{file_id}"
PATH_PUBLIC_THUMBNAIL: Final = "/public/{file_id}/thumbnail"
PATH_PUBLIC_NAMED: Final = "/public/{file_id}/{filename}"
# POST, not DELETE: a selection is a body, and DELETE with a body is refused
# or silently stripped by enough proxies that it cannot be relied on.
PATH_FILES_BULK_DELETE: Final = "/files/bulk-delete"

# Resumable / direct uploads (#454). ``PATH_UPLOAD`` is the one-shot multipart
# form; these are the session flow for files too big for it.
PATH_UPLOAD_SESSIONS: Final = "/uploads"
PATH_UPLOAD_SESSION: Final = "/uploads/{upload_id}"
PATH_UPLOAD_PART_URLS: Final = "/uploads/{upload_id}/part-urls"
PATH_UPLOAD_PART: Final = "/uploads/{upload_id}/parts/{part_no}"
PATH_UPLOAD_COMPLETE: Final = "/uploads/{upload_id}/complete"

# ── Inertia page names ───────────────────────────────────────────────
PAGE_BROWSE: Final = "FileStorage/Browse"

# ── Database ─────────────────────────────────────────────────────────
SCHEMA_NAME: Final = "file_storage"
TABLE_STORED_FILE: Final = "file_storage_stored_file"
TABLE_UPLOAD_SESSION: Final = "file_storage_upload_session"

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
    BAD_IMAGE: Final = "file_storage.bad_image"
    QUOTA_EXCEEDED: Final = "file_storage.quota_exceeded"
    DIRECT_UNSUPPORTED: Final = "file_storage.direct_upload_unsupported"
    BAD_PART: Final = "file_storage.bad_part"
    PARTS_MISMATCH: Final = "file_storage.parts_mismatch"
    SIZE_MISMATCH: Final = "file_storage.size_mismatch"
    SESSION_CLOSED: Final = "file_storage.upload_session_closed"


class UploadStatus:
    """Lifecycle of an ``UploadSession`` row."""

    ACTIVE: Final = "active"
    COMPLETED: Final = "completed"
    ABORTED: Final = "aborted"


class Task:
    """Celery task names (``tasks.py``; only loaded when background_tasks is installed)."""

    REAP_STALE_UPLOADS: Final = "file_storage.reap_stale_uploads"
    COMPUTE_CHECKSUM: Final = "file_storage.compute_checksum"


class I18nKey:
    """Translator keys (full dotted paths). Mirror locales/en.json shape."""

    ERR_NOT_FOUND: Final = "file_storage.errors.not_found"
    ERR_TOO_LARGE: Final = "file_storage.errors.too_large"
    ERR_BAD_TYPE: Final = "file_storage.errors.bad_type"
    ERR_BACKEND: Final = "file_storage.errors.backend_error"
    ERR_BAD_IMAGE: Final = "file_storage.errors.bad_image"
    ERR_QUOTA: Final = "file_storage.errors.quota_exceeded"
    ERR_DIRECT_UNSUPPORTED: Final = "file_storage.errors.direct_upload_unsupported"
    ERR_BAD_PART: Final = "file_storage.errors.bad_part"
    ERR_PARTS_MISMATCH: Final = "file_storage.errors.parts_mismatch"
    ERR_SIZE_MISMATCH: Final = "file_storage.errors.size_mismatch"
    ERR_SESSION_CLOSED: Final = "file_storage.errors.upload_session_closed"


# ── Defaults ─────────────────────────────────────────────────────────
DEFAULT_BACKEND: Final = BackendId.FILESYSTEM
DEFAULT_FS_ROOT: Final = "./uploads"
DEFAULT_MAX_FILE_SIZE_BYTES: Final = 100 * 1024 * 1024  # 100 MB
# Multipart boundaries and part headers on top of the file bytes, for the
# host request-body guard.
MULTIPART_OVERHEAD_BYTES: Final = 1024 * 1024
DEFAULT_PRESIGN_TTL_SECONDS: Final = 300  # 5 minutes
DEFAULT_CHUNK_SIZE: Final = 64 * 1024  # 64 KB
SPOOL_MAX_SIZE_BYTES: Final = 10 * 1024 * 1024  # 10 MB before disk-spill

# ── Resumable uploads (#454) ─────────────────────────────────────────
MIB: Final = 1024 * 1024
DEFAULT_DIRECT_UPLOAD_THRESHOLD_BYTES: Final = 64 * MIB
DEFAULT_MAX_DIRECT_UPLOAD_BYTES: Final = 10 * 1024 * MIB  # 10 GiB
DEFAULT_PART_SIZE_BYTES: Final = 16 * MIB
# S3's hard ceiling; ``part_size`` is grown until the upload fits under it.
MAX_UPLOAD_PARTS: Final = 10_000
# S3 rejects non-final parts below 5 MiB.
MIN_PART_SIZE_BYTES: Final = 5 * MIB
DEFAULT_UPLOAD_SESSION_TTL_SECONDS: Final = 24 * 3600
DEFAULT_UPLOAD_SESSION_RETENTION_DAYS: Final = 7
# Headroom over ``part_size`` for the filesystem part PUT's body-limit rule.
PART_BODY_SLACK_BYTES: Final = 64 * 1024
# The directory under the filesystem root that holds in-flight parts.
FS_MULTIPART_DIR: Final = ".multipart"

# Shown where a file has no uploader at all — rows predating authenticated
# uploads. The label is resolved server-side, so this is the only copy.
UNKNOWN_UPLOADER: Final = "—"

# ── Public serving & thumbnails ──────────────────────────────────────
PUBLIC_MAX_AGE_SECONDS: Final = 3600
# Per-IP budget for anonymous public file GETs (its own bucket in the shared
# rate limiter, #347), wider than the default because one page embeds many.
PUBLIC_FILES_RATE: Final = "600/minute"
# The only types served ``inline`` (and, on S3, by redirect). Everything else —
# HTML, any XML (``*+xml``, ``text/xsl``, SVG), scripts, unknown or malformed
# values — is "active": forced to an attachment and streamed under the sandbox
# CSP, so a public upload cannot become stored XSS on the app's origin (#545).
# An allow-list, because the uploader controls the stored type and a deny-list
# has to anticipate every scriptable document format a browser will render.
INLINE_SAFE_CONTENT_TYPES: Final = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/avif",
        "image/apng",
        "image/bmp",
        "image/tiff",
        "image/x-icon",
        "image/vnd.microsoft.icon",
        "application/pdf",
        "application/json",
        "text/plain",
        "text/csv",
    }
)
# Whole families that render as media, never as a document — minus any XML
# subtype, which ``media_types.is_active_content`` refuses on its own.
INLINE_SAFE_FAMILIES: Final = frozenset({"audio", "video"})
PUBLIC_CSP: Final = "default-src 'none'; style-src 'unsafe-inline'; sandbox"

THUMBNAIL_WIDTHS: Final = (64, 128, 256, 512, 1024)
THUMBNAIL_DEFAULT_WIDTH: Final = 256
THUMBNAIL_MIN_WIDTH: Final = 32
THUMBNAIL_MAX_WIDTH: Final = 1024
THUMBNAIL_CONTENT_TYPE: Final = "image/webp"
# Decode budget: refuse an image whose pixel count would balloon memory
# (decompression bomb) before Pillow ever decodes it.
THUMBNAIL_MAX_PIXELS: Final = 25_000_000
THUMBNAIL_MAX_SOURCE_BYTES: Final = 20 * 1024 * 1024
THUMBNAIL_MAX_CONCURRENCY: Final = 2
THUMBNAIL_MAX_AGE_SECONDS: Final = 86400

# ── Listing ──────────────────────────────────────────────────────────
DEFAULT_SORT: Final = "-created_at"

# ── Menu ─────────────────────────────────────────────────────────────
MENU_ICON: Final = "files"
MENU_ORDER: Final = 40
ADMIN_ROLE: Final = "admin"
USER_ROLE: Final = "user"

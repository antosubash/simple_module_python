# file_storage

Pluggable file storage with two shipped backends — local filesystem and S3-compatible — plus a browse / upload / download admin UI. Backend selection is per-deployment (DB-backed setting), so you can switch from `filesystem` (dev / single-node) to `s3` (prod) without code changes.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `FileStorage` |
| `route_prefix` | `/api/file-storage` |
| `view_prefix` | `/file-storage` |
| `depends_on` | `["Settings"]` |

## Routes

### API

| Method + path | Body / response | Permission |
|---|---|---|
| `POST /api/file-storage/upload` | `multipart` (`file`, optional `public=true`) → `StoredFileOut` (201) | `file_storage.upload` |
| `GET /api/file-storage/files` | `?page=&per_page=&q=&content_type=&sort=` → `StoredFileListOut` | `file_storage.download` |
| `GET /api/file-storage/files/{file_id}` | → `StoredFileOut` | `file_storage.download` |
| `PATCH /api/file-storage/files/{file_id}` | `{"public": bool}` → `StoredFileOut` | `file_storage.upload` |
| `GET /api/file-storage/files/{file_id}/thumbnail` | `?w=` → `image/webp` | `file_storage.download` |
| `GET /api/file-storage/files/{file_id}/download` | → 302 (S3) or stream (filesystem) | `file_storage.download` |
| `DELETE /api/file-storage/files/{file_id}` | → 204 | `file_storage.delete` |
| `GET /api/file-storage/public/{file_id}[/{filename}]` | bytes (**anonymous**) | none, `public` files only |
| `GET /api/file-storage/public/{file_id}/thumbnail` | `?w=` → `image/webp` (**anonymous**) | none, `public` files only |

### Listing: search, filter, sort

`GET /files` takes `q` (case-insensitive substring of the original filename;
`%` and `_` match literally), `content_type` (an exact type, or a family
ending in `/` such as `image/`) and `sort` — one of `created_at`, `-created_at`
(default), `name`, `-name`, `size`, `-size` (anything else is a `422`). `name`
sorts case-insensitively; ties break on `id` so pages never overlap. `total`
reflects the filters.

### Thumbnails

`GET /files/{id}/thumbnail?w=` returns a Pillow-resized WebP, aspect ratio
preserved, never enlarged. `w` is clamped to 32–1024 and **snapped up** to one
of `64, 128, 256, 512, 1024` (default 256), so a file has at most five
variants. Only `image/jpeg`, `png`, `webp` and `gif` (first frame) have
thumbnails; everything else, including SVG, is `404`. An undecodable image is
`422 file_storage.bad_image`, and an image over 25 megapixels, or a source over 20 MB, is refused before any
decode (decompression-bomb guard; `DecompressionBombWarning` is an error). Only
JPEG/PNG/WebP/GIF are ever opened (Pillow `formats=` allowlist), the sniffed
format must match the declared type, animated images yield their first frame,
metadata is not carried into the output, and at most two decodes run at once.

Variants are cached **in the storage backend** next to the original, under
`{key}.w{width}.webp`: they survive restarts, are shared by all workers, are
bounded by the width whitelist, inherit the tenant key prefix, and are deleted
with the file. A cache hit never re-reads the original. A concurrent first
request may render twice; both write identical bytes.

### Public files

`StoredFile.public` (default `false`) opts a file into anonymous serving.
Set it with `public=true` on upload or `PATCH /files/{id}`; both need
`file_storage.upload`, so anyone who may add files may publish them. `StoredFileOut` carries
`public` and, while public, `public_url` (`/api/file-storage/public/{id}/{filename}`),
so consumers never build the URL themselves — an `<img src>` on a public page
can use it, or `.../public/{id}/thumbnail?w=256`.

The public routes are exempt from `AuthMiddleware` through
`register_public_routes` (GET only; uploads, PATCH and deletes stay gated).
Serving rules:

- Only `public=True`, non-deleted rows resolve; unknown, private and deleted
  ids are the same `404`, so existence is not leaked.
- Tenancy: an anonymous request binds no tenant, so the single lookup by
  (unguessable) id runs under `all_tenants()` and requires `public=True`.
  Making a file public is the owner's explicit choice to publish it
  cross-tenant; nothing else is reachable this way.
- `Cache-Control: public, max-age=3600`, a checksum `ETag` (`304` on
  `If-None-Match`) and `X-Content-Type-Options: nosniff`.
- Every public response carries `Content-Security-Policy: default-src 'none';
  style-src 'unsafe-inline'; sandbox` (the security-headers middleware now
  keeps a CSP the response already set). Active content — HTML, XHTML, SVG,
  XML, JavaScript — is forced to `Content-Disposition: attachment` and is
  always streamed, so stored XSS on the app origin is not possible. Other
  types are `inline`.
- Presigning backends (S3) answer with a `302` to the presigned URL, cached
  for at most half the signature's TTL; filesystem backends stream.

### View

| Method + path | Inertia component | Permission |
|---|---|---|
| `GET /file-storage/` | `FileStorage/Browse` | `file_storage.download` |

## Public contracts

```python
from file_storage.contracts import (
    StoredFileOut,
    StoredFileListOut,
    FileUploaded,
    FileDeleted,
    StorageBackend,
    StorageError,
    StorageNotFoundError,
    StorageBackendError,
    NotSupportedError,
    ConfigurationError,
)
```

| Class | Purpose |
|---|---|
| `StoredFileOut` | File metadata: `id`, `key`, `filename`, `content_type`, `size_bytes`, `backend`, `checksum_sha256`, `uploaded_by`, `created_at`, `public`, `public_url`. |
| `StoredFileListOut` | `items`, `total`, `page`, `per_page`. |
| `FileUploaded` (event) | `file_id`, `key`, `backend`, `size_bytes`, `uploaded_by`. Topic: `file_storage.file.uploaded`. |
| `FileDeleted` (event) | `file_id`, `key`. Topic: `file_storage.file.deleted`. |
| `StorageBackend` (Protocol) | The backend interface (see [Writing your own backend](#writing-your-own-backend)). |
| `StorageError` + subclasses | Raise these from a backend; the API maps them to 404 / 415 / 500. |

## Models

`StoredFile` (table `file_storage_stored_file`)

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` | PK |
| `tenant_id` | `str(50)` | owning tenant, from `MultiTenantMixin` |
| `key` | `str(512)` | backend-relative path; **unique per tenant** |
| `filename` | `str(255)` | original upload filename |
| `content_type` | `str(128)` | sniffed / declared MIME type |
| `size_bytes` | `int` | |
| `backend` | `str(32)` | `"filesystem"` or `"s3"` — recorded at upload time |
| `checksum_sha256` | `str(64)` | computed during stream-upload |
| `public` | `bool` | default `false`; opt-in anonymous serving |
| `extra_metadata` | `dict` | per-backend extras |
| audit + soft-delete | from `AuditMixin` + `SoftDeleteMixin` | |

Indexes on `(tenant_id, key)` (unique), `tenant_id`, `created_by`, `is_deleted`.

## Multi-tenancy

`StoredFile` is [`MultiTenantMixin`](/framework/multi-tenancy) (#383). Every
route acts for the request's active tenant: another tenant's file id answers
`404` exactly like an unknown one, listings and the browse screen's totals and
facets count only the tenant's rows, and bulk delete skips ids it cannot see.
The aggregate cache is keyed per tenant, and a write drops only the slots of
the tenants it wrote (plus the unscoped slot).

New storage keys are `{tenant_id}/YYYY/MM/DD/<uuid><ext>`, so each tenant's
objects live under their own backend prefix. Rows written before the adoption
migration keep their un-prefixed key (the column stores the full path) and were
back-filled into `DEFAULT_TENANT_ID` (branding's system images into the
platform owner, below). A single-tenant install (`multi_tenant`
off) stamps uploads with `DEFAULT_TENANT_ID` and reads every row; with
`multi_tenant` on and no tenant bound, an upload fails closed *before* any
bytes reach the backend.

**Platform files.** Files that belong to the install rather than to a tenant —
branding's *system* logo and favicon — are written and read with `platform=True` on
`FileStorageService.upload` / `get` / `download` / `delete`. They are owned by
`PLATFORM_TENANT_ID` (`"platform"`, exported by `simple_module_db`) and looked
up under `all_tenants()` **restricted to that owner**, so they resolve from
anonymous requests while no tenant's file can be reached that way. The id is
reserved — `is_valid_tenant_id` refuses it, so no request, header, claim, task
message, `default_tenant` setting or `tenants` organisation can ever be bound
to it — and it is distinct from `DEFAULT_TENANT_ID`, the owner of a
single-tenant install's ordinary rows. The adoption migration made only the
files the system branding settings referenced platform files; every other
existing row went to `DEFAULT_TENANT_ID`. **Never re-stamp platform rows**: a
script adopting `default_tenant` must update `WHERE tenant_id = 'default'`,
never every row.

The bypass covers only the platform row. `platform_scope` flushes the
session's other pending writes *before* lifting isolation — so they are
stamped with, and checked against, the bound tenant as usual — and turns
autoflush off inside, so a platform read cannot carry them through unguarded.

Platform files are not listed on any tenant's Files screen. A tenant's own
branding images are ordinary tenant files (no `platform=True`), uploaded and
served in that tenant's scope.

The audit-log label resolver names files across tenants on purpose: the audit
log is a platform screen over every tenant's entries, each of which already
records the filename.

The module has no background jobs, sweeps or CLI commands. Anything added
later that touches `StoredFile` outside a request must run under
`tenant_context(row.tenant_id)` for per-tenant work, or `all_tenants()` for a
deliberate platform-wide sweep.

## Settings

DB-backed via `register_module_settings`; pydantic defaults seed at boot. Live edits under Files at `/admin/settings/`.

| Field | Default | Purpose |
|---|---|---|
| `backend` | `"filesystem"` | active backend id (`filesystem` \| `s3`) |
| `fs_root_path` | `"./uploads"` | root dir for the filesystem backend (resolved against repo root) |
| `s3_bucket` | `""` | required when `backend="s3"` |
| `s3_region` | `""` | required when `backend="s3"` |
| `s3_access_key_id` | `""` | optional — falls back to env / IAM if empty |
| `s3_secret_access_key` | `""` | optional |
| `s3_endpoint_url` | `""` | optional — set for MinIO / Cloudflare R2 |
| `s3_presign_ttl_seconds` | `300` | TTL for presigned `GET` URLs |
| `max_file_size_bytes` | `100 * 1024 * 1024` | upload limit (100 MB) |
| `allowed_content_types` | `None` | optional MIME-type whitelist; `None` ⇒ any |

## Backends

### Filesystem (default)

Stores files on local disk under `fs_root_path`, sharded by the first two characters of the storage key (`<root>/ab/abcd1234...`) so a single directory doesn't blow up `readdir`. Path traversal is blocked. `presigned_get_url()` is unsupported — downloads stream through the API process.

### S3

Async client built on `aioboto3`. `aioboto3` is an **optional** dependency — install with `uv add --optional s3 aioboto3` (or include it in your deployment's lockfile). Works against AWS S3 and any S3-compatible provider (MinIO, Cloudflare R2, …) by setting `s3_endpoint_url`. `presigned_get_url()` returns a time-limited URL so downloads don't have to round-trip through the API.

### Writing your own backend

Implement the `StorageBackend` protocol:

```python
from file_storage.contracts import StorageBackend, StoredFile


class GcsBackend(StorageBackend):
    backend_id = "gcs"
    supports_presigned_url = True

    async def put(self, key, stream, content_type, size): ...
    async def get(self, key): ...
    async def delete(self, key): ...
    async def exists(self, key) -> bool: ...
    async def presigned_get_url(self, key, ttl_seconds: int) -> str: ...
```

Register it in your module's `register_settings` so the file_storage service can pick it up. (The shipped two backends are wired into a private `BACKEND_REGISTRY`; see `backends/__init__.py` for the pattern.)

## Permissions

| Code | Granted to | Purpose |
|---|---|---|
| `file_storage.upload` | `user`, `admin`, `tenant:member`/`admin`/`owner` | upload files |
| `file_storage.download` | `user`, `admin`, `tenant:member`/`admin`/`owner` | list / get / download |
| `file_storage.delete` | `admin`, `tenant:admin`, `tenant:owner`; also `user` when `multi_tenant` is off | delete |
| `file_storage.manage` | `admin` | reserved for future admin operations |

With `multi_tenant` on, delete is an organisation-admin act: the platform
`user` role, which every account holds, does not carry it (it would hand it to
every tenant member). With `multi_tenant` off the install is the only tenant,
so `on_startup` maps `file_storage.delete` onto `user` and ordinary users keep
deleting their files.

## Menu

| Label | URL | Icon | Section | Group | Order | Roles |
|---|---|---|---|---|---|---|
| `Files` | `/file-storage` | `files` | `SIDEBAR` | `Content` | `40` | `["admin", "tenant:owner", "tenant:admin", "tenant:member"]` |

## Events

The module **publishes**:

- `FileUploaded(file_id, key, backend, size_bytes, uploaded_by)` — after the row is committed.
- `FileDeleted(file_id, key)` — after delete (soft or hard) commits.

Subscribe from any other module's `register_event_handlers`:

```python
from file_storage.contracts import FileUploaded


class MyModule(ModuleBase):
    def register_event_handlers(self, bus):
        bus.subscribe(FileUploaded, self._on_uploaded)

    async def _on_uploaded(self, event: FileUploaded) -> None: ...
```

## Inertia pages

- `FileStorage/Browse.tsx` — file list + upload dropzone; handles the upload progress + delete confirmation flow. Each row shows a "Public" badge and a make public / make private action.
- `FileStorage/components/UploadDropzone.tsx` — drag-drop upload child component.

## Locales

Top-level keys in `file_storage/locales/en.json`: `browse`, `table`, `actions`, `delete_dialog`, `toasts`, `errors`. The `errors` namespace is keyed by error *code* (`not_found`, `too_large`, `bad_type`, `backend_error`, `bad_image`) so the UI can render a deterministic message per `StorageError` subclass.

# file_storage

Pluggable file storage with two shipped backends — local filesystem and S3-compatible — plus a browse / upload / download admin UI. Backend selection is per-deployment (DB-backed setting), so you can switch from `filesystem` (dev / single-node) to `s3` (prod) without code changes.

Install `simple_module_file_storage[tasks]` to include the matching
`simple_module_background_tasks` package, then enable `background_tasks` and run
its worker for asynchronous multipart-upload checksums. Run its beat scheduler
as well for upload cleanup jobs.
The extras combine as `simple_module_file_storage[s3,tasks]`. Without
`background_tasks`, uploads still work; completed multipart uploads keep
`checksum_sha256` null. Streamed uploads compute their checksum inline.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `FileStorage` |
| `route_prefix` | `/api/file-storage` |
| `view_prefix` | `/file-storage` |
| `depends_on` | `[]` (optional: `["Settings"]`) |

## Routes

### API

| Method + path | Body / response | Permission |
|---|---|---|
| `POST /api/file-storage/upload` | `multipart` (`file`, optional `public=true`) → `StoredFileOut` (201) | `file_storage.upload` |
| `GET /api/file-storage/files` | `?page=&per_page=&q=&content_type=&sort=` → `StoredFileListOut` | `file_storage.download` |
| `GET /api/file-storage/files/{file_id}` | → `StoredFileOut` | `file_storage.download` |
| `PATCH /api/file-storage/files/{file_id}` | `{"public": bool}` → `StoredFileOut` | `file_storage.upload` |
| `GET /api/file-storage/files/{file_id}/thumbnail` | `?w=` → `image/webp` | `file_storage.download` |
| `GET /api/file-storage/files/{file_id}/download` | → 302 (S3) or stream (filesystem); honours `Range` (see [Range requests](#range-requests)) | `file_storage.download` |
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

Public file reads are readable cross-origin: any origin, no credentials, `GET`/`HEAD`/`OPTIONS`,
`Range`, `If-Range` and `If-None-Match` allowed, and `Content-Range`, `Accept-Ranges`, `ETag` and
`Content-Length` exposed, so a page on another site can seek in a video or PDF. The DB-backed
setting `public_files_cors` (default on) turns this off without a restart. With the S3 backend a
read can redirect to a presigned bucket URL; the browser then applies the bucket's own CORS
configuration, which you must set on the bucket.

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
  keeps a CSP the response already set). Only an allow-list of types is
  served `inline` (and redirected on S3): common raster images, PDF, JSON,
  GeoJSON, plain text, CSV, opaque binaries (`application/octet-stream`, zip,
  gzip, protobuf / vector tiles) and `audio/*` / `video/*` / `font/*` minus
  any XML or HTML subtype
  (`INLINE_SAFE_CONTENT_TYPES` / `INLINE_SAFE_FAMILIES`). Everything else —
  HTML, SVG, any XML, scripts, unknown types, and malformed values such as
  `text/html,` — is forced to `Content-Disposition: attachment` and always
  streamed, so stored XSS on the app origin is not possible. The stored type
  is lower-cased and stripped of parameters before the check
  (`media_types.is_active_content`).
- Presigning backends (S3) answer with a `302` to the presigned URL, cached
  for at most half the signature's TTL; filesystem backends stream.

### Range requests

Whenever bytes stream through the app (the download endpoint on a
non-presigning backend, and the public route for filesystem backends or active
content), a single `Range` is honoured so COG / PMTiles readers can fetch
just the tiles they need:

- `bytes=a-b`, `bytes=a-` and the suffix form `bytes=-n` answer `206 Partial
  Content` with `Content-Range: bytes a-b/size` and the slice's
  `Content-Length`. An end past the object is clamped to `size - 1`.
- A range starting at or past the end (or `bytes=-0`) is `416` with
  `Content-Range: bytes */size`.
- Multiple ranges, another unit, or a malformed header are ignored and the
  whole file is sent with `200` (RFC 9110 allows this). So is a request whose
  `If-Range` does not match the current `ETag`.
- Streamed responses advertise `Accept-Ranges: bytes`. Auth, `ETag`,
  `Content-Disposition`, `Cache-Control` and CSP headers are the same as for
  the full response.

Redirected (presigned) downloads are served by the object store, which handles
`Range` itself. Always redirecting large downloads to a presigned URL, as an
opt-in setting, is not implemented.

### Direct, resumable uploads

Files above `direct_upload_threshold_bytes` (default 64 MiB) upload in parts through a *session*, so a dropped connection or a reload loses at most one part. The Files page does this automatically; API clients drive it themselves. All routes need `file_storage.upload` and act only on the caller's own sessions (anyone else's id is a 404).

| Route | Purpose |
|---|---|
| `POST /api/file-storage/uploads` `{filename, content_type, total_size, public}` | Open a session. Checks the content-type allow-list, `max_direct_upload_bytes` (default 10 GiB) and the quota (stored bytes plus the declared size of every still-open session). Returns `part_size` (16 MiB, grown so the file needs at most 10,000 parts) and `total_parts`. |
| `GET /uploads/{id}` | The session plus the parts the backend holds — the source of truth for resuming. |
| `POST /uploads/{id}/part-urls` `{parts: [n]}` | Where to PUT each part: presigned S3 URLs (`direct: true`, bound to the part's length) or the app's own part route. Only part numbers `1..total_parts`. |
| `PUT /uploads/{id}/parts/{n}` | Filesystem backend only: the part body, relayed through the app (capped at that part's exact size). |
| `POST /uploads/{id}/complete` `{parts: [{n, etag}]}` | Assemble, verify, create the `StoredFile`, publish `FileUploaded`. The assembled size must equal `total_size`; the maximum and the quota are re-checked against the stored object, and a violation deletes it. Retrying a completed session returns the same file. |
| `DELETE /uploads/{id}` | Abort and discard the parts. |

Sessions expire after `upload_session_ttl_seconds` (24 h). With `background_tasks` installed, the hourly beat task `file_storage.reap_stale_uploads` aborts expired sessions and, on S3, orphaned multipart uploads older than twice the TTL that have this module's key shape and no active session (a bucket shared with other applications is left alone); without it, `POST /uploads` aborts the caller's own expired sessions. Completed and aborted session rows are deleted `upload_session_retention_days` (default 7) after their expiry, by the same task or, without `background_tasks`, by the caller's next `POST /uploads` (own rows only). `file_storage.compute_checksum` fills `checksum_sha256` after completion when `background_tasks` is installed.

In the browser, parts go four at a time with per-part retry and backoff. The session id is kept in `localStorage` keyed by file name, size and last-modified time; after a reload, select the same file again and the page offers **Resume upload** or **Start over**. (Browsers cannot keep a file handle across a reload, so the file must be picked again.)

Known limitations:

- Two simultaneous `PUT`s of the same part on the filesystem backend can leave the part's data and ETag from different writers; `complete` then reports a mismatch and the client re-sends the part.
- The resume key is file name, size and last-modified time, so two tabs uploading an identical file share one session.
- A part shorter than expected is stored and refused with 400; it stays until the client re-sends the part (the resend overwrites it), and `complete` flags it as mismatched.

#### S3 setup

Parts are PUT by the browser straight to the bucket, so:

- **CORS** on the bucket must allow `PUT` from the app's origin and expose `ETag`:
  ```json
  [{"AllowedOrigins": ["https://app.example.com"], "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["*"], "ExposeHeaders": ["ETag"], "MaxAgeSeconds": 3000}]
  ```
- `s3_public_endpoint_url` is the endpoint browsers reach, when it differs from the one the server uses (`s3_endpoint_url`, e.g. an in-cluster MinIO hostname). Presigned URLs are signed for it, and the redirect for presigned downloads uses it too. Blank falls back to `s3_endpoint_url`.
- The endpoint's origin is added to the CSP `connect-src` automatically (for AWS defaults, the bucket's `*.s3.<region>.amazonaws.com` hosts).

New settings: `direct_upload_threshold_bytes`, `max_direct_upload_bytes`, `multipart_part_size_bytes`, `upload_session_ttl_seconds`, `upload_session_retention_days`, `s3_public_endpoint_url`. A backend opts in with `supports_direct_upload = True` and the `DirectUploadBackend` methods in `file_storage.contracts.service`; without it, `POST /uploads` answers 501 and the page never uses sessions.

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
| `checksum_sha256` | `str(64) \| null` | computed during stream-upload; **null** for a direct (multipart) upload until `file_storage.compute_checksum` runs (never, without `background_tasks`) |
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

The optional checksum task and upload reaper use the background-tasks worker.
Any task that touches `StoredFile` outside a request must run under
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
| `s3_signature_version` | `"s3v4"` | presign signature version; pinned so custom endpoints get SigV4 |
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
    async def get(self, key): ...  # awaited; returns an AsyncIterator[bytes]
    async def get_range(self, key, start, end): ...  # end inclusive
    async def delete(self, key): ...
    async def exists(self, key) -> bool: ...
    async def presigned_get_url(self, key, ttl_seconds: int) -> str: ...
```

`get` and `get_range` must stream in bounded chunks (never buffer the whole
object) and raise `StorageNotFoundError` from the awaited call, before the
first byte. `get_range(key, start, end)` uses HTTP semantics — `end` is
inclusive — and receives an already-validated `0 <= start <= end < size`. A
backend without `get_range` still works: the endpoints then ignore `Range`.

Register it in your module's `register_settings` so the file_storage service can pick it up. (The shipped two backends are wired into a private `BACKEND_REGISTRY`; see `backends/__init__.py` for the pattern.)

## Permissions

| Code | Granted to | Purpose |
|---|---|---|
| `file_storage.upload` | `user`, `admin`, `tenant:member`/`admin`/`owner` | upload files |
| `file_storage.download` | `user`, `admin`, `tenant:member`/`admin`/`owner` | list / get / download |
| `file_storage.delete` | `admin`, `tenant:admin`, `tenant:owner`; also `user` when `multi_tenant` is off | delete |
| `file_storage.manage` | `admin`, `tenant:admin`, `tenant:owner` | act on every file in the active tenant, not only one's own |

With `multi_tenant` on, delete is an organisation-admin act: the platform
`user` role, which every account holds, does not carry it (it would hand it to
every tenant member). With `multi_tenant` off the install is the only tenant,
so `on_startup` maps `file_storage.delete` onto `user` and ordinary users keep
deleting their files.

**Ownership.** Every authenticated route — list, get, download, thumbnail,
publish/unpublish, delete, bulk delete and the browse screen — acts only on the
files the caller uploaded (`created_by` is their user id), unless they hold
`file_storage.manage`. Someone else's file answers `404`, exactly like an
unknown id, and the browse screen's type and uploader filters list only the
caller's own rows (the usage figure stays bucket-wide, as the quota is). The
scope is passed explicitly by the endpoints (`deps.get_owner_scope`) to the
service's `owner=` argument; internal callers such as branding and reapers
pass none and stay unscoped, and anonymous `public` serving is unaffected.

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

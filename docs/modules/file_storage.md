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
| `POST /api/file-storage/upload` | `multipart` → `StoredFileOut` (201) | `file_storage.upload` |
| `GET /api/file-storage/files` | `?page=&per_page=` → `StoredFileListOut` | `file_storage.download` |
| `GET /api/file-storage/files/{file_id}` | → `StoredFileOut` | `file_storage.download` |
| `GET /api/file-storage/files/{file_id}/download` | → 302 (S3) or stream (filesystem) | `file_storage.download` |
| `DELETE /api/file-storage/files/{file_id}` | → 204 | `file_storage.delete` |

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
| `StoredFileOut` | File metadata: `id`, `key`, `filename`, `content_type`, `size_bytes`, `backend`, `checksum_sha256`, `uploaded_by`, `created_at`. |
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
back-filled into `DEFAULT_TENANT_ID`. A single-tenant install (`multi_tenant`
off) stamps uploads with `DEFAULT_TENANT_ID` and reads every row; with
`multi_tenant` on and no tenant bound, an upload fails closed *before* any
bytes reach the backend.

**Platform files.** Files that belong to the install rather than to a tenant —
branding's *system* logo and favicon — are written and read with `platform=True` on
`FileStorageService.upload` / `get` / `download` / `delete`. They are owned by
`file_storage.scope.PLATFORM_TENANT_ID` (`DEFAULT_TENANT_ID`, which tenant ids
never collide with) and looked up under `all_tenants()` **restricted to that
owner**, so they resolve from anonymous requests while no tenant's file can be
reached that way. Platform files are not listed on any tenant's Files screen. A tenant's own
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
| `file_storage.delete` | `admin`, `tenant:admin`, `tenant:owner` | delete |

Delete is an organisation-admin act: the platform `user` role, which every
account holds, no longer carries it (it would hand it back to every tenant
member).
| `file_storage.manage` | `admin` | reserved for future admin operations |

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

- `FileStorage/Browse.tsx` — file list + upload dropzone; handles the upload progress + delete confirmation flow.
- `FileStorage/components/UploadDropzone.tsx` — drag-drop upload child component.

## Locales

Top-level keys in `file_storage/locales/en.json`: `browse`, `table`, `actions`, `delete_dialog`, `toasts`, `errors`. The `errors` namespace is keyed by error *code* (`not_found`, `too_large`, `bad_type`, `backend_error`) so the UI can render a deterministic message per `StorageError` subclass.

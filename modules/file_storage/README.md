# simple_module_file_storage

Pluggable file-upload + storage module for [simple_module](https://github.com/antosubash/simple_module_python) apps. Defaults to local-disk storage for development; install the `[s3]` extra to switch to any S3-compatible backend via `aioboto3`.

## Install

```bash
# local-disk storage (dev default)
pip install simple_module_file_storage

# S3-compatible storage (production)
pip install "simple_module_file_storage[s3]"
```

Install `simple_module_file_storage[tasks]` to include the matching
`simple_module_background_tasks` package, then enable `background_tasks` and run
its worker for asynchronous multipart-upload checksums. Run its beat scheduler
as well for upload cleanup jobs.
The extras combine as `simple_module_file_storage[s3,tasks]`. Without
`background_tasks`, uploads still work; completed multipart uploads keep
`checksum_sha256` null. Streamed uploads compute their checksum inline.

## What it provides

- `POST /api/file-storage/upload` multipart upload endpoint.
- `GET /api/file-storage/files` (paged list), `GET /api/file-storage/files/{file_id}` (metadata), `GET /api/file-storage/files/{file_id}/download` (signed-URL redirect or stream), `DELETE /api/file-storage/files/{file_id}`.
- Pluggable backend selected by the `backend` setting (`filesystem` default | `s3`); third-party backends can register under any id.
- Settings (`backend`, `s3_bucket`, `s3_region`, `s3_endpoint_url` for R2/MinIO/etc., `s3_access_key_id`, `s3_secret_access_key`, `s3_presign_ttl_seconds`) are configured from the DB settings store via the admin UI — they are not read from `SM_FILE_STORAGE_*` environment variables at runtime.

## Sync workers

With the `[tasks]` extra installed, synchronous task bodies can import
`store_path`, `open_local`, and `presigned_url` from `file_storage.contracts`.
Run calls inside `simple_module_db.tenant_context(tenant_id)`. `store_path`
accepts a path or binary stream and returns committed `StoredFileOut` metadata;
`open_local(file_id)` yields a temporary local path and always cleans it up.
`presigned_url(file_id)` requires a backend with signing support.

Uploads retain the existing MIME, quota, size and hashing rules. S3 writes above
`direct_upload_threshold_bytes` use bounded multipart, including unknown-size
streams. Raise the DB's `max_file_size_bytes` for large worker outputs and set an
S3 lifecycle rule to abort incomplete server uploads left by terminated jobs.
See `docs/modules/file_storage.md` in the repository for transaction and cleanup
semantics.

## Usage

From another module, inject the service via its dependency:

```python
from fastapi import Depends, File, UploadFile

from file_storage.deps import get_file_storage_service
from file_storage.service import FileStorageService


async def attach_receipt(
    upload: UploadFile = File(...),
    svc: FileStorageService = Depends(get_file_storage_service),
):
    record = await svc.upload(upload)
    return {"file_id": record.id}
```

Backend and S3 credentials are configured from the admin UI at **/settings/modules → FileStorage** (DB-backed settings); switch `backend` to `s3` and fill in `s3_bucket`, `s3_region`, `s3_endpoint_url` (for MinIO/R2), `s3_access_key_id`, and `s3_secret_access_key`.

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`, `simple_module_settings`
- `aiofiles`
- Optional: `aioboto3` (install the `[s3]` extra)
- Optional: `simple_module_background_tasks` (install the `[tasks]` extra)

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).

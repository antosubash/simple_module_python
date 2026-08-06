# simple_module_file_storage

Pluggable file-upload + storage module for [simple_module](https://github.com/antosubash/simple_module_python) apps. Defaults to local-disk storage for development; install the `[s3]` extra to switch to any S3-compatible backend via `aioboto3`.

## Install

```bash
# local-disk storage (dev default)
pip install simple_module_file_storage

# S3-compatible storage (production)
pip install "simple_module_file_storage[s3]"
```

## What it provides

- `POST /api/file-storage/upload` multipart upload endpoint.
- `GET /api/file-storage/files` (paged list), `GET /api/file-storage/files/{file_id}` (metadata), `GET /api/file-storage/files/{file_id}/download` (signed-URL redirect or stream), `DELETE /api/file-storage/files/{file_id}`.
- Pluggable backend selected by the `backend` setting (`filesystem` default | `s3`); third-party backends can register under any id.
- Works with any S3-compatible provider — AWS, MinIO, Cloudflare R2, Wasabi, Backblaze B2, DigitalOcean Spaces, self-hosted gateways.
- All settings are configured from the DB settings store via the admin UI — they are **not** read from `SM_FILE_STORAGE_*` environment variables at runtime. Changing them rebuilds the backend in place; no restart needed.

### Settings

| Setting | Group | Notes |
|---|---|---|
| `backend` | General | `filesystem` (default) or `s3` |
| `key_prefix` | General | Folder every object is stored under, e.g. `media/`. Blank = bucket root. Applies to all backends. |
| `fs_root_path` | Filesystem | Local storage root |
| `s3_bucket` | S3 | Required when `backend=s3` |
| `s3_region` | S3 | Defaults to `us-east-1`; region-less providers (R2) accept `auto` |
| `s3_access_key_id` / `s3_secret_access_key` | S3 | Blank falls back to the ambient AWS credential chain |
| `s3_endpoint_url` | S3 | Custom endpoint for MinIO / R2. Blank uses the AWS default |
| `s3_public_endpoint_url` | S3 | Host used to *sign* download URLs when it differs from the endpoint the app connects to |
| `s3_addressing_style` | S3 | `auto` / `path` / `virtual`. Use `path` for MinIO, Ceph, and IP/localhost endpoints |
| `s3_signature_version` | S3 | e.g. `s3v4`. Blank uses the default |
| `s3_verify_ssl` | S3 | Set false only for internal gateways with self-signed certificates |
| `s3_presign_ttl_seconds` | S3 | Lifetime of download redirect URLs |
| `max_file_size_bytes` / `allowed_content_types` | Limits | Upload validation |

**Folder prefix.** `key_prefix` is baked into each object's key at upload time and stored on the row, so changing it later affects only new uploads — every existing file keeps resolving. `media` and `/media/` both normalise to `media/`; `..` segments are rejected.

**Presigning across a network boundary.** If the app reaches storage privately (`http://minio:9000`) but browsers need a public host, set `s3_public_endpoint_url` to `https://files.example.com`. Download URLs are signed for that host, since an S3 signature is bound to the host in the URL.

## Usage

From another module, inject the service via its dependency:

```python
from fastapi import Depends, File, UploadFile

from file_storage.deps import get_file_storage_service  # type: ignore[import-not-found]
from file_storage.service import FileStorageService  # type: ignore[import-not-found]


async def attach_receipt(
    upload: UploadFile = File(...),
    svc: FileStorageService = Depends(get_file_storage_service),
):
    record = await svc.upload(upload)
    return {"file_id": record.id}
```

Backend and S3 credentials are configured from the admin UI at **/settings/modules → FileStorage** (DB-backed settings); switch `backend` to `s3` and fill in `s3_bucket`, `s3_access_key_id`, and `s3_secret_access_key`. Set `key_prefix` to keep every object inside one folder.

Provider examples:

| Provider | `s3_endpoint_url` | `s3_region` | `s3_addressing_style` |
|---|---|---|---|
| AWS S3 | *(blank)* | your region | `auto` |
| MinIO | `http://minio:9000` | `us-east-1` | `path` |
| Cloudflare R2 | `https://<account>.r2.cloudflarestorage.com` | `auto` | `auto` |
| DigitalOcean Spaces | `https://<region>.digitaloceanspaces.com` | your region | `auto` |
| Backblaze B2 | `https://s3.<region>.backblazeb2.com` | your region | `auto` |

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`, `simple_module_settings`
- `aiofiles`
- Optional: `aioboto3` (install the `[s3]` extra)

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).

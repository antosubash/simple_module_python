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

- `POST /api/files` upload endpoint with multipart + metadata.
- `GET /api/files/{id}` signed-URL or stream download.
- Pluggable backend via `SM_FILE_STORAGE_BACKEND` (`local` | `s3`).
- S3 config via `SM_FILE_STORAGE_S3_BUCKET`, `SM_FILE_STORAGE_S3_ENDPOINT` (for R2/MinIO/etc.), `SM_FILE_STORAGE_S3_REGION`.

## Usage

From another module:

```python
from file_storage.service import FileStorageService   # type: ignore[import-not-found]

async def attach_receipt(
    svc: FileStorageService = Depends(FileStorageService),
    upload: UploadFile = File(...),
):
    record = await svc.save(upload, folder="receipts/")
    return {"file_id": record.id, "url": record.url}
```

Env config (example, S3):

```
SM_FILE_STORAGE_BACKEND=s3
SM_FILE_STORAGE_S3_BUCKET=my-app-uploads
SM_FILE_STORAGE_S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

## Depends on

- `simple_module_core`, `simple_module_db`, `simple_module_hosting`
- `aiofiles`
- Optional: `aioboto3` (install the `[s3]` extra)

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).

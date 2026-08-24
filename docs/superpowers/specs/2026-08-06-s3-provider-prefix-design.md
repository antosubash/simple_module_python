# Configurable S3 provider + bucket folder prefix

**Date:** 2026-08-06
**Module:** `modules/file_storage`

## Problem

Two gaps in the `file_storage` module:

1. **Provider portability.** The S3 backend exposes `s3_endpoint_url`, so
   MinIO/R2 partly work, but it never constructs a `botocore.config.Config`.
   That makes path-style addressing unreachable, which is the single most
   common breakage on MinIO, Ceph, and any endpoint that is an IP or
   `localhost`. `s3_region` is also required by the settings validator, so
   region-less providers (R2 wants `auto`) fail to boot. Presigned URLs are
   minted against the internal endpoint, so a browser cannot open a download
   when the app reaches storage over a private network.

2. **No folder prefix.** `service._generate_key()` emits `YYYY/MM/DD/<uuid><ext>`
   at the bucket root. There is no way to confine objects to a folder, and no
   way for an operator to configure one.

## Requirements

- Any S3-compatible provider must be usable (AWS, MinIO, R2, Wasabi, B2,
  DigitalOcean Spaces, self-hosted gateways).
- All objects live under a configurable folder.
- The folder is configured **at runtime through the admin Settings UI**, not
  hardcoded and not env-only.

## Design

### Key prefix

New DB-backed setting in a **General** group, so it renders in the existing
per-module Settings UI and picks up hot reload via
`settings.reload.apply_changes_and_reload`:

```python
key_prefix: str = Field(default="", json_schema_extra={"group": "General"})
```

Normalized and validated by a `field_validator` on `FileStorageSettings`, so a
bad value fails at config time rather than at first upload:

| Input | Stored |
|---|---|
| `media` | `media/` |
| `/media/` | `media/` |
| `a//b` | `a/b/` |
| `` (blank) | `` (bucket root) |
| `../escape`, `a/../b`, `C:\x` | rejected with `ValueError` |

**Scope: generic, all backends.** One `key_prefix` applies to every backend
rather than an S3-only field. The filesystem backend nests it under
`fs_root_path` (`./uploads/media/2026/...`); S3 prepends it to the object key.

**Application point: baked into the stored key.** The prefix is applied once,
at upload, inside `_generate_key`:

```python
def _generate_key(filename: str, prefix: str = "") -> str:
    return f"{prefix}{datetime.now(UTC):%Y/%m/%d}/{uuid.uuid4().hex}{Path(filename).suffix}"
```

The full prefixed key is persisted in `StoredFile.key`. Backends receive
already-qualified keys and never prepend anything themselves.

Consequence, and the reason for this choice: editing the prefix later steers
only new uploads. Every previously stored file keeps resolving, because its row
still carries the key it was written under. The transparent-backend alternative
(store bare keys, prepend on every operation) would orphan every existing
object the moment an operator edits the prefix.

A blank default means existing installations observe no behavior change.

### S3 provider compatibility

New fields in the existing **S3** settings group, all optional and inert when
blank:

| Field | Purpose |
|---|---|
| `s3_addressing_style` | `auto` \| `path` \| `virtual`. Requires building a real `botocore.config.Config`, which `_build` does not do today. Unblocks MinIO/Ceph. |
| `s3_public_endpoint_url` | Presign against this host instead of the internal one, so browser download redirects work across a private network boundary. |
| `s3_signature_version` | Blank = botocore default. For gateways needing an explicit `s3v4`/`s3`. |
| `s3_verify_ssl` | Allow self-signed internal gateways. |

`s3_region` drops out of the hard validator and defaults to `us-east-1`, so R2
and region-less providers boot. `s3_bucket` remains required when the S3
backend is selected.

`S3Backend` holds a second set of client kwargs used *only* by
`presigned_get_url`, identical to the main set except for `endpoint_url`. When
no public endpoint is configured the two are the same object and behavior is
unchanged. Signing against the public host is correct precisely because that is
the host the browser will contact.

`botocore` is imported lazily alongside `aioboto3`, matching the existing
pattern, so the module still loads without the `[s3]` extra installed.

### Error handling

Unchanged in shape. Config errors surface as `ConfigurationError` at boot
(fail-fast on a misconfigured prod deploy); per-operation failures stay
`StorageBackendError` / `StorageNotFoundError`. Prefix validation raises
`ValueError` from the pydantic validator, which the settings UI surfaces as a
field error.

### Testing

- Prefix normalization table, including every rejection case.
- Prefixed round-trip (put → get → delete) through both backends.
- `Config` carries path-style addressing when configured.
- Presign uses the public endpoint when set, the internal one when not.
- S3 backend builds with no region configured.
- Regression that guards the core guarantee: a pre-existing prefix-free key
  still downloads after a prefix is configured.

## Out of scope

- **Filesystem shard repair.** `FilesystemBackend._resolve` shards on `key[:2]`,
  which is `20` for every date-based key ever written, so all objects already
  land in one directory. A prefix makes it `me` rather than `20` — equally
  degenerate, not worse. Fixing it properly would relocate existing files on
  disk. This spec corrects the misleading docstring and leaves behavior alone.
- Provider presets and a "test connection" button in the settings UI.
- Multipart upload for very large files (already deferred to v2).

## Docs

`modules/file_storage/README.md` is stale: it documents `SM_FILE_STORAGE_*` env
vars as the configuration path (settings are DB-backed now) and calls the
filesystem backend `local` rather than `filesystem`. Corrected alongside the
new fields.

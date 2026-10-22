# /api endpoints without a response type (#504)

Operations whose JSON success response has no schema, so `openapi-typescript`
types the body as `unknown`. Found with `simple_module_cli.openapi_types.untyped_operations`
over the full host schema on 2026-10-22 (15 operations). `smpy openapi gen-types`
prints the same list per module it generates.

Most of them do not return JSON at all (files, images, CSV, redirects); FastAPI
still advertises an empty `application/json` schema because the route sets no
`response_class`. Those want `response_class=` (or `responses=`) so the schema
says what they send; the auth ones want a `response_model`.

## Binary or redirect responses (fix: declare `response_class`)

### AuditLog
- `GET /api/audit_log/export.csv`

### Branding
- `GET /api/branding/logo`
- `GET /api/branding/logo-dark`
- `GET /api/branding/favicon`

### FileStorage
- `GET /api/file-storage/files/{file_id}/thumbnail`
- `GET /api/file-storage/files/{file_id}/download`
- `GET /api/file-storage/public/{file_id}/thumbnail`
- `GET /api/file-storage/public/{file_id}/{filename}`
- `GET /api/file-storage/public/{file_id}`

### Users (OAuth redirects)
- `GET /api/users/auth/{provider}/login`
- `GET /api/users/auth/{provider}/callback`

## JSON responses without a model (fix: `response_model`)

### Users
- `DELETE /api/users/auth/token`
- `POST /api/users/auth/forgot-password`
- `POST /api/users/auth/reset-password`
- `POST /api/users/auth/request-verify-token`

None of these are called by the tenants or api_tokens pages migrated in this
batch; the users ones matter for batch 4b.

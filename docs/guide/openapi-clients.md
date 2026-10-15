# OpenAPI and generated clients

Every module's JSON API (`/api/**`) is described by one OpenAPI document. View
routes (Inertia pages) are not part of it.

## Where the schema lives

| Environment | `/api/openapi.json` |
|---|---|
| development | always served, no login |
| anything else | served only when `openapi_public` is on (`SM_OPENAPI_PUBLIC=true`) |

The schema lists every endpoint, so production keeps it off unless you opt in.
When it is served it is anonymous, like `/health`.

`info.title`, `info.version` and `info.description` come from the host settings
`api_title` (default `SimpleModule`), `api_version` (default: the host
package's version) and `api_description`. They are read at boot, so a change
needs a restart.

Operation ids are `<module>_<function>` (`users_list_users`), which gives
generated clients readable method names. A clash gets the method and path
appended and logs a warning.

::: warning Breaking change
The bare `/openapi.json` is gone. It used to be served in production too; use
`/api/openapi.json`.
:::

## Exporting without a server

```bash
uv run smpy openapi export --out openapi.json          # or: make openapi
uv run smpy openapi export --module users --module audit_log
```

The command builds the app in process and does not start a server or need
Redis. It reads host settings from the database when it is reachable;
otherwise it warns and uses the environment and defaults.

## TypeScript client (hey-api)

```yaml
# .github/workflows/client.yml (excerpt)
- run: uv sync --all-packages
- run: uv run smpy openapi export --out openapi.json
- run: npx @hey-api/openapi-ts -i openapi.json -o src/client -c @hey-api/client-fetch
```

## Dart client (openapi-generator `dart-dio`)

```yaml
- run: uv sync --all-packages
- run: uv run smpy openapi export --out openapi.json
- run: >
    npx @openapitools/openapi-generator-cli generate
    -i openapi.json -g dart-dio -o packages/api_client
    --additional-properties=pubName=api_client
- run: cd packages/api_client && dart pub get && dart run build_runner build
```

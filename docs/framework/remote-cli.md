# Remote CLI engine

`simple_module_remote` (`framework/remote/`) is a client-only package that turns
an app's OpenAPI document into a command line. It talks to a running app over
HTTP and never imports the server stack
(`framework/remote/tests/config/test_import_isolation.py`). A project wraps it:

```python
from simple_module_remote import build_cli

cli = build_cli("smdev", schema_path, defaults_path, version="1.0")
```

`build_cli` returns a `click.Group` with the built-ins `env`, `login`, `logout`,
`whoami`, `doctor`, `schema`, `api` and `raw`, plus one group per OpenAPI tag.
`transport=` and `keyring_backend=` let tests inject an ASGI bridge and an
in-memory keyring. `schema_path` is the bundled schema; before parsing each
invocation the root group peeks at `--env`/`--schema` and, when the selected
environment has a usable live cache (`schema sync`), rebuilds the generated groups
from it instead (`commands/schema_source.py`). The environment resolved there is
reused for the request, and a wrapper's `default_map` for `env`/`schema_source` is
honoured. Live operations take `x-cli-safe` only from the bundled schema, matched by
method and template with placeholder names erased (`generate/trust.py`); `schema
sync` refuses documents whose body and parameter shapes commands could not use
(`generate/validate.py`). The dev host's wrapper is `host_cli/smdev_cli/`; usage is in
[Project CLI](/guide/project-cli).

## A CLI for your own app

1. Export the schema: `smpy openapi export --out your_cli/openapi.json` (re-run it
   after API changes; the dev host's `make cli-schema` wraps it and CI checks it).
2. Optionally ship a defaults file (`[env.<name>] url = ...`, `protected = true`).
3. Write `main()` around `build_cli(name, schema_path, defaults_path, version=...)`
   (`host_cli/smdev_cli/__init__.py` is a complete example; `version` also feeds
   the User-Agent and `--version`).
4. Declare `[project.scripts]`, depend on `simple-module-remote`, and install with
   `uv tool install ./your_cli`.

CI without a config file: set `<CLI>_ENV`, `<CLI>_URL` and `<CLI>_TOKEN`.

## Architecture

| Area | Role |
|---|---|
| `schema/` | Load and `$ref`-resolve an OpenAPI file; the live schema cache (`cache.py`: `<cache>/<cli>/<env>/{openapi,meta}.json`, bound to origin and SHA-256) |
| `generate/` | Operations, naming, parameters, bodies, execution, confirmation, pagination, and the command tree (`tree.py`) |
| `config/` | Environments, origin-bound credentials, XDG config and cache paths, descriptor-based owner-only directories (`_private_dir.py`) |
| `http/` | Guarded `httpx` client: `/api/` only, no credentials in URLs, auth only on same-origin redirects under `/api/` |
| `output/` | Table/JSON/YAML/`id` rendering with terminal-escape sanitising |
| `commands/` | Built-in commands and the operation-to-click adapter |

## `x-sm-token`

The hosting package stamps every published operation with `x-sm-token`: `true`
when the route admits a personal access token (declared by its guards), `false`
for session-only routes. The engine builds commands only for `true` operations,
so a command that could never succeed with a token does not exist.
`GET /api/_meta/whoami` is the token-capable identity route that `login`,
`whoami` and `doctor` use.

## Form actions and `api_equivalent`

Page routes refuse tokens, so the CLI can only do what the API can. Every
non-GET view route therefore declares the `/api` operation that does the same
(`api_equivalent("PUT", "/api/…")`) or why no token may (`api_exempt(reason)`:
logout, sign-in, the signed-in account itself, token management, setup, locale).
`host/tests/test_view_api_equivalents.py` checks each target exists and admits
tokens; see `docs/module-authoring.md` § Form actions name their API equivalent.

The API twin normally asks for the same permissions as the page. One deliberate
exception: `POST /api/dashboard/doctor/rerun` accepts the delegable
`dashboard.doctor` permission, while the `/admin/doctor` page needs the `admin`
role, so an operator can grant a CI token the re-run without making it an admin.

## Operation hints

| Extension | Effect |
|---|---|
| `x-cli-name` | Override the generated command name |
| `x-cli-safe` | A non-GET operation that does not mutate: skips protected-environment confirmation |
| `x-cli-confirm` | Always require confirmation on a protected environment |

Command names come from the `operationId` with the tag prefix removed;
`find_collisions` reports duplicates and names that clash with built-ins.

## Testing a wrapper

`host/tests/remote_cli/conftest.py` shows the pattern: run the CLI in a worker
thread (`asyncio.to_thread`) and bridge each request to the test's event loop
with `LoopBridgeTransport`, so the in-process app keeps the loop that owns its
database engine.

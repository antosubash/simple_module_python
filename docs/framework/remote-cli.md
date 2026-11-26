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
in-memory keyring. The dev host's wrapper is `host_cli/smdev_cli/`; usage is in
[Project CLI](/guide/project-cli).

## Architecture

| Area | Role |
|---|---|
| `schema/` | Load and `$ref`-resolve the bundled OpenAPI file |
| `generate/` | Operations, naming, parameters, bodies, execution, confirmation, pagination, and the command tree (`tree.py`) |
| `config/` | Environments, origin-bound credentials, XDG paths |
| `http/` | Guarded `httpx` client: `/api/` only, no credentials in URLs, no cross-origin redirects with auth |
| `output/` | Table/JSON/YAML/`id` rendering with terminal-escape sanitising |
| `commands/` | Built-in commands and the operation-to-click adapter |

## `x-sm-token`

The hosting package stamps every published operation with `x-sm-token`: `true`
when the route admits a personal access token (declared by its guards), `false`
for session-only routes. The engine builds commands only for `true` operations,
so a command that could never succeed with a token does not exist.
`GET /api/_meta/whoami` is the token-capable identity route that `login`,
`whoami` and `doctor` use.

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

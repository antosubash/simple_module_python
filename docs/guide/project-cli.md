# Project CLI (`smdev`)

Every simple_module app can ship its own command line over its REST API. The
dev host in this repository ships `smdev`, generated from the host's bundled
OpenAPI schema by the `simple_module_remote` engine
(see [Remote CLI engine](/framework/remote-cli)).

## Install

`smdev` is a workspace package (`host_cli/`), installed by `make install`:

```bash
uv run smdev --help
```

## Environments

An environment is a named base URL. `local` (`http://localhost:8000`) ships as a
default; add your own:

```bash
uv run smdev env add staging --url https://staging.example.com
uv run smdev env add prod --url https://app.example.com --protected
uv run smdev env use staging
uv run smdev env list
```

Plain `http://` is accepted only for loopback hosts. The environment is chosen by
`--env`, then `SMDEV_ENV`, then the saved current environment. The config lives
in `~/.config/smdev/` (or `$XDG_CONFIG_HOME/smdev/`).

## Sign in with a personal access token

Create a token in the app (`/api-tokens/`), then store it:

```bash
printf '%s\n' "$PAT" | uv run smdev --env local login --token-stdin
uv run smdev --env local login --token      # hidden prompt
uv run smdev whoami
```

The token is verified against `GET /api/_meta/whoami` before anything is stored.
It goes to the OS keyring, or to a `0600` file when none exists, and is bound to
the environment's origin: if you later edit the environment URL, the stored
token is refused and nothing is sent until you log in again. A token never
travels in a URL, never follows a redirect to another origin, and is never
printed. A token pinned to a tenant works for that tenant; use
`--tenant <id>` with a separate `login` for another one.

## Generated commands

Each operation that a token may call (`x-sm-token`) becomes
`smdev <group> <command>`, also reachable as `smdev raw <group> <command>`.
Session-only routes do not appear.

```bash
uv run smdev users admin-list-users -o json
uv run smdev users admin-update-user <id> --set email=a@example.com --set full_name=Ada
uv run smdev users admin-update-user <id> --json '{"email": "a@example.com"}' --dry-run
uv run smdev tenants list-members --all
```

Useful flags on every generated command: `--json`, `--file` (body, `-` for
stdin), `--set key=value`, `--set-json key=<json>`, `--dry-run` (print the
request, send nothing), `-o`/`--output`, `--columns`, `-q`, `--out FILE`, `--yes`.
`smdev api METHOD /api/...` calls any path directly. `smdev schema status`
shows where the command schema comes from, and `smdev doctor` checks
connectivity, credentials and schema.

Exit codes: `0` success, `1` usage or local error, `2` other 4xx, `3` 5xx or
network failure, `4` HTTP 401/403, `5` HTTP 404, `6` HTTP 409/412.

## Protected environments

`--protected` makes a mutating call (or an operation marked `x-cli-confirm`)
ask you to type the environment name first. Runs without a terminal on both
stdin and stderr must pass `--yes`. Operations marked `x-cli-safe` (read-only
despite using POST) skip the prompt. `api METHOD PATH` takes the safe/confirm
marks of the schema operation whose path template matches; an unmatched
mutation is always confirmed. Re-running `env add` for an existing environment
changes only the flags you pass (`--protected`/`--no-protected`, `--tenant`).

## CI

```yaml
- run: uv run smdev users admin-list-users -o json
  env:
    SMDEV_ENV: staging
    SMDEV_TOKEN: ${{ secrets.SMDEV_TOKEN }}
```

`SMDEV_TOKEN` is honoured only when the environment is chosen explicitly
(`--env` or `SMDEV_ENV`), so a stray variable can never be sent to the default
environment.

## Refreshing the bundled schema

After an API change run `make cli-schema` and commit
`host_cli/smdev_cli/openapi.json`. CI (`make ci-cli-schema-fresh`) fails when it
is stale, and `host/tests/remote_cli/test_schema_coverage.py` checks it against
the live app.

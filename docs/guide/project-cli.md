# Project CLI (`smdev`)

Every simple_module app can ship its own command line over its REST API. The
dev host in this repository ships `smdev`, generated from the host's bundled
OpenAPI schema by the `simple_module_remote` engine
(see [Remote CLI engine](/framework/remote-cli)).

## Install

`smdev` is a workspace package (`host_cli/`), installed by `make install`:

```bash
uv run smdev --help
uv run smdev --version
```

To use it outside a checkout, install the package as a tool; the bundled schema
ships inside the wheel. `uv tool install` puts `smdev` in `~/.local/bin`: add that
directory to `PATH` (uv warns when it is missing).

```bash
uv tool install ./host_cli
```

A downstream app gets its own CLI the same way: a small package with
`[project.scripts]`, an `openapi.json` exported by `smpy openapi export --out ...`
(re-export after API changes), an optional defaults file, and a `main()` calling
`build_cli`. See [Remote CLI engine](/framework/remote-cli).

## Environments

An environment is a named base URL. `local` (`http://localhost:8000`) ships as a
default; add your own:

```bash
uv run smdev env add staging --url https://staging.example.com
uv run smdev env add prod --url https://app.example.com --protected
uv run smdev env use staging
uv run smdev env list
```

Environment URLs, including those in config files, are validated as written and then
stored canonical: lowercase scheme and host, no default
port (`:443`, `:80`), no trailing slash, and no userinfo (not even an empty
`user@`). Logins stored before this normalisation still match: the credential's
origin is normalised when compared. Plain `http://` is accepted only for loopback hosts. URLs may not contain
whitespace, control characters or backslashes; environment names are 1-40
lowercase letters, digits or `-`, starting with a letter or digit. `local` exists
before you add anything: `smdev env use local` is all a dev checkout needs. The environment is chosen by
`--env`, then `SMDEV_ENV`, then the saved current environment. The config lives
in `~/.config/smdev/` (or `$XDG_CONFIG_HOME/smdev/`).

## Sign in with a personal access token

Sign in to the app in a browser, open `<environment url>/api-tokens/` and create
a personal access token. Tick the permissions the commands you will run need: a
token holds at most the scopes you give it, and a command the token cannot use
answers 403 (the hint names the missing permission). Tokens cannot manage tokens
(`smdev api --session-only` lists every route a token cannot call), and a token
cannot act on your own account where the app forbids it. Then store it:

```bash
printf '%s\n' "$PAT" | uv run smdev --env local login --token-stdin
uv run smdev --env local login --token      # hidden prompt
uv run smdev whoami
```

The token is verified against `GET /api/_meta/whoami` before anything is stored.
It goes to the OS keyring (guarded by a `keyring.lock` lock file with no secrets in
the config directory, so concurrent logins do not lose entries), or to a `0600`
file when none exists, and is bound to
the environment's origin: if you later edit the environment URL, the stored
token is refused and nothing is sent until you log in again. A token never
travels in a URL, never follows a redirect to another origin, and is never
printed. A token must be printable ASCII with no spaces or control characters, at most
4096 characters. `login --token` needs a terminal; pipe to `--token-stdin` otherwise.

The one exception to "no redirects with the token" is a redirect to the same
origin that stays under the environment's `/api/` prefix (FastAPI's trailing
slash redirects): it is followed with the token, but only when the URL that will
be sent is a plain path (no backslash, no encoded dot, slash, backslash or
percent); anything ambiguous is followed without it. A redirect anywhere else (another
host, port or scheme, or a path outside `/api/`) is followed without it, and a
401 from there is reported as "followed a redirect".

A token pinned to a tenant works for that tenant. `--tenant` takes the tenant's
slug or its id (`whoami` shows both as `slug (id)`); use a separate `login` per
tenant. The stored login remembers the tenant its token is pinned to and is
refused for any other, banners read `[env/tenant]`, and `login`/`logout` name
the environment and tenant they acted on. Tenant ids and slugs the server reports
must be short printable words without spaces or the token, or the identity is
rejected. `env remove <name>` also deletes every
stored login of that environment.

## Generated commands

Each operation that a token may call (`x-sm-token`) becomes
`smdev <group> <command>`, also reachable as `smdev raw <group> <command>`.
Session-only routes do not appear.

```bash
uv run smdev users admin-list-users -o json
uv run smdev users admin-update-user <id> --set email=a@example.com --set full_name=Ada
uv run smdev users admin-update-user <id> --json '{"email": "a@example.com"}' --dry-run
uv run smdev feature-flags list-flags -o id
```

Commands on tenant-scoped routes (for example `tenants list-members`) need a
tenant: log in with a token pinned to one, or pass `--tenant`. On a stock
single-tenant install the server answers `403 tenant_required`, and the CLI
says "the server needs a tenant" instead of suggesting a new login.

Flags: `--dry-run`, `-o`/`--output`, `--columns`, `-q`, `--out FILE` and `--yes` on
every command (`--yes` only matters on a protected environment); body flags exist
only on commands with a body: `--json`, `--file` (body, `-` for
stdin), `--set key=value`, `--set-json key=<json>` (NaN, Infinity and numbers that overflow, like `1e999`, are
refused); `--dry-run` prints the request and sends nothing. A body that is required but has only
optional fields is sent as `{}` when no body flag is given, and a required raw body
needs `--body-file`. `-o id` and `-q`
print `id`, else `name`, `key`, `slug` or `email`, and fail with a hint to use
`-o json` when a row has none (or the value holds control characters). Path
arguments may not be empty. A non-JSON response (a download) is streamed to a
pipe; JSON responses larger than 64 MiB are refused with a hint to use `--out`.
`smdev api METHOD /api/...` calls any path directly. `smdev schema status`
shows where the command schema comes from, and `smdev doctor` checks
connectivity, credentials and schema.

Output: a table when stdout is a terminal and the result is a list, otherwise
JSON (so piping gives JSON). `-o table|json|yaml|id` overrides it. `--columns`
picks table columns (an unknown name is an error; json and yaml are not
filtered). Empty lists print `no results` as a table. `-o`, `-q` and `--columns`
do not apply to a non-JSON response such as the audit CSV export, and `-o id`/`-q`
refuse a body they cannot turn into identifiers (binary, invalid JSON, empty). A mutating call
prints a bracketed banner on stderr: `[env]`, or `[env/tenant]` with a tenant; a
204 answer prints `done` on stderr. A closed pipe (`| head`) ends quietly.

`--set` coerces by the body schema (numbers, booleans); an array field takes one
element per `--set` (repeat it to add more, each coerced by the items schema, or
use `--set-json field=[...]`); `--set k=null`
sends `null`; `--set k=@file` or `@-` reads the value from a file or stdin (one
trailing newline stripped; a UTF-8 BOM is ignored); a value that must start with
a literal `@` or be the text `null` needs `--set-json`. Order: `--json`, `--file`,
`--set-json`, `--set`. `--all` starts at page 1 (do not combine with `--page`).
`smdev api METHOD /api/path [--query k=v ...]` calls any path;
`smdev raw <group> <command>` is the same command tree as the top-level groups (kept for scripts
that must not collide with future built-ins). `--schema bundled` is the only
schema source today, and `smdev schema status` shows it.

Exit codes: `0` success, `1` usage or local error, `2` other 4xx (also a leftover
3xx), `3` 5xx or
network failure, `4` HTTP 401/403, `5` HTTP 404, `6` HTTP 409/412.

## Protected environments

`--protected` makes a mutating call (or an operation marked `x-cli-confirm`)
ask you to type the environment name first. Unless both stdin and
stderr are terminals, pass `--yes`. Operations marked `x-cli-safe` (read-only
despite using POST) skip the prompt. `api METHOD PATH` takes the safe/confirm
marks of the schema operation whose path template matches; an unmatched
mutation is always confirmed. Re-running `env add` for an existing environment
changes only the flags you pass (`--protected`/`--no-protected`, `--tenant`);
`--url` is required only for a new environment. `env remove` of a name that a
project default also defines resets it to the default. It deletes the
environment's stored logins first and lists the keys it removed; if the keyring
refuses one, the environment is kept and the command fails so you can retry. On a
keyring (which cannot be listed) logins for tenants the CLI never recorded may remain
and the command says so;
`logout` with `--tenant` removes one. Changing the URL or tenant warns that the
stored login may no longer apply.

## CI

A runner has no config file, so name the environment and give its URL:

```yaml
- run: uv run smdev users admin-list-users -o json
  env:
    SMDEV_ENV: staging
    SMDEV_URL: https://staging.example.com
    SMDEV_TOKEN: ${{ secrets.SMDEV_TOKEN }}
```

`SMDEV_URL` defines the environment named by `--env`/`SMDEV_ENV` only when no
environment of that name is configured, and follows the same rules as `env add`
(https, or http on loopback). `SMDEV_TOKEN` is honoured only when the
environment is chosen explicitly (`--env` or `SMDEV_ENV`), so a stray variable
can never be sent to the default environment. An environment made this way is
not protected.

## Refreshing the bundled schema

After an API change run `make cli-schema` and commit
`host_cli/smdev_cli/openapi.json`. CI (`make ci-cli-schema-fresh`) fails when it
is stale, and `host/tests/remote_cli/test_schema_coverage.py` checks it against
the live app.

## Safety notes

The config file (`config.toml`) holds no secrets and follows the umask; the
credentials file is `0600` in a `0700` directory. Redirects the server sends are
followed without the token unless they stay on the environment's origin under
`/api/`; the tokenless follower refuses plain `http://` to non-loopback hosts,
link-local and metadata addresses, and private or loopback addresses unless the
environment itself is on one. Error text is sanitised for terminals (escape
sequences, bidi overrides) before the token is redacted from it, and long error
bodies are cut at 500 characters. A 429 answer is retried up to three times and
the wait is announced on stderr. On a protected environment the typed name must
match exactly. `--tenant` is ignored (with a note at login) on a single-tenant
server, whose login is kept in the plain environment slot, and `logout` with no stored token exits 1.

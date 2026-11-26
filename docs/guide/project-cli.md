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
before you add anything: `smdev env use local` is all a dev checkout needs, and a `login` to a configured environment while none is current makes it the
current one (a one-off `SMDEV_URL` environment is not saved). The environment is chosen by
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
`smdev api METHOD /api/...` calls any path directly. A generated command's
`--help` lists up to 40 top-level JSON body fields with their types (`*` marks the
required ones; quoted names cannot be set with `--set`). `smdev schema status`
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
that must not collide with future built-ins). Which schema builds the commands
is described in [Live schema](#live-schema).

Exit codes: `0` success, `1` usage or local error, `2` other 4xx (also a leftover
3xx), `3` 5xx or
network failure, `4` HTTP 401/403, `5` HTTP 404, `6` HTTP 409/412.

## Protected environments

`--protected` makes a mutating call (or an operation marked `x-cli-confirm`)
ask you to type the environment name first. Unless both stdin and
stderr are terminals, pass `--yes`. Operations marked `x-cli-safe` (read-only
despite using POST) skip the prompt. `api METHOD PATH` takes the safe/confirm
marks of the schema operation whose path template matches; an unmatched
mutation, or a path that matches more than one template, is always confirmed. Re-running `env add` for an existing environment
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

## Credential matrix

What a credential may do depends on the route, not on the CLI: each cell is the
server's answer, and a refusal is HTTP 403 (exit code 4). The matrix below is
pinned by `host/tests/remote_cli/test_credential_matrix.py`.

| Credential | Host-level (users admin, system settings, tenant create) | Tenant-level in its tenant (members, invitations) | Tenant-level in another tenant |
|---|---|---|---|
| Platform-admin PAT pinned to tenant T | Yes, capped by the scopes it was minted with (a missing scope is 403) | Yes, within its scopes | Refused |
| Tenant-admin PAT of T | 403: the user does not hold platform permissions | Yes | Refused |
| Service key of T | Per its roles and scopes (content and settings work); never `admin` | 403: a service key is not a member, so no tenant resolves for the tenants module | Refused |

A PAT sends no CSRF token: `RequiresCsrf` routes skip the check for tokens,
while cookie sessions stay protected.

Routes that take a tenant id and need platform permissions (for example
`tenants list-tenants` or `create-tenant`) are host-level: they work with
`tenants.platform.*` whichever tenant the token is pinned to. "Another tenant"
only concerns tenant-level routes, which act on the token's active tenant and
never on a tenant named in the URL. The CLI sends no tenant id to the server:
`--tenant` only selects which stored login to use, and a login pinned to
another tenant is refused before any request (exit code 1, "no stored
credentials"). Use a separate `login` for each tenant.

Platform routes that take a tenant id (suspending a tenant, editing another
tenant's settings, tenant feature-flag overrides) are host-level too: a
platform-admin token holding the platform permissions can use them on any
tenant. This is deliberate. One guard applies: a token cannot suspend its own
tenant (409 `cannot_suspend_own_tenant`), because that would lock it out.

## Live schema

The commands come from the schema bundled with the CLI unless you sync the
environment's own:

```bash
smdev --env staging schema sync      # or: smdev schema sync --env staging
smdev --env staging schema status    # source, info.version, fingerprint, age
```

The fingerprint `schema status` and `schema sync` print is a hash of the document's
content (keys sorted, whitespace dropped), so the bundled file from
`smpy openapi export` and the same schema served live show the same value.

`schema sync` calls `GET /api/_meta/openapi` with your token (it needs the
`host.openapi.read` permission: admins have it, and a scoped token for CI can be
given it) and caches the answer in `~/.cache/smdev/<env>/` (`$XDG_CACHE_HOME`
when set): `openapi.json` plus `meta.json` with the environment's base URL (path
included), the SHA-256 fingerprint, the ETag and the fetch time. Both files are
`0600` in `0700` directories owned by you, opened without following symlinks, and
never hold the token. Concurrent syncs of one environment are serialised. A second
sync sends `If-None-Match`; a `304` keeps the cached schema and only updates the
fetch time. The schema is fetched uncompressed (`Accept-Encoding: identity`; a
compressed answer is refused), redirects are not followed and the body is capped
at 32 MiB. A body that is not an OpenAPI object, contains the token anywhere (keys
or values, also once control characters are removed), has an `x-cli-name` outside
lowercase letters, digits and `-`, has operation names that collide, or has
unusable shapes in its bodies or parameters (a non-object `properties`, a non-list
`required` or `enum`, a non-object parameter schema) is refused and nothing is
written. A cached schema with such shapes falls back to the bundled one. A root
`--env` and a `schema sync --env` that name different environments are refused. On a platform without descriptor-relative file calls
(Windows) the cache is unavailable and the bundled schema is used.

Each run picks the source before parsing its arguments: the live cache of the
selected environment when it exists, was fetched from the environment's current
URL and is intact; otherwise the bundled schema (`schema status` says why under
`live:`; a cache that cannot be turned into commands also prints a one-line note on
stderr). The environment chosen here is the one the request then uses. Pointing
the environment at another URL therefore drops its cache until the next sync. `--schema live` insists on the cache and fails with exit code 1
and a `schema sync` hint when it cannot be used (built-ins such as
`schema sync` still run); `--schema bundled` ignores the cache. When a generated
command gets an answer that suggests the schema is out of date (a 404 with no detail
or the router's exact `Not Found`, a 405, or a 422 for a missing or unknown field), the
error ends with a hint to run `schema sync`; a domain 404 (`member_not_found`, `Not
found`) or a value the server could not parse does not. A 403 suggests logging in again
only when it is about the credential (no detail, or a whole message such as `Not
authenticated` or `Token expired`), not when the server explains why it refuses the
action.

A live schema can only make the CLI more careful. Its `x-cli-confirm` adds a
confirmation on a protected environment, but its `x-cli-safe` is ignored: only the
bundled schema's `x-cli-safe` for the same method and path template waives the
confirmation of a mutation, for generated commands and `api METHOD PATH` alike.
Placeholder names do not matter when marks are matched (`/a/{x}` is `/a/{id}`), and
an `api` path that matches more than one template is always confirmed.
Server text shown in help, errors, `schema status` and `api --session-only` is
stripped of terminal control sequences, and enum values containing them are not
offered as choices.

## Refreshing the bundled schema

After an API change run `make cli-schema` and commit
`host_cli/smdev_cli/openapi.json`. CI (`make ci-cli-schema-fresh`) fails when it
is stale, and `host/tests/remote_cli/test_schema_coverage.py` checks it against
the live app.

## Safety notes

The config file (`config.toml`) holds no secrets and follows the umask; the
credentials file and the live schema cache are `0600` in `0700` directories,
read without following symlinks and refused when another user can read them. Redirects the server sends are
followed without the token unless they stay on the environment's origin under
`/api/`; the tokenless follower refuses plain `http://` to non-loopback hosts,
link-local and metadata addresses, and private or loopback addresses unless the
environment itself is on one. Error text is sanitised for terminals (escape
sequences, bidi overrides) before the token is redacted from it, and long error
bodies are cut at 500 characters. A 429 answer is retried up to three times and
the wait is announced on stderr. On a protected environment the typed name must
match exactly. `--tenant` is ignored (with a note at login) on a single-tenant
server, whose login is kept in the plain environment slot, and `logout` with no stored token exits 1.

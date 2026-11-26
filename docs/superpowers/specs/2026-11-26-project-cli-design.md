# Project CLI: a per-project command line over the REST API

Status: approved 2026-11-26, after a four-reviewer council (security, operator UX,
architecture, feasibility). Browser login is in v1.

## Intent

Every app built on this framework is deployed for a different project, and each
project runs several environments (dev, staging, prod). Today the only way to
manage a deployment (users, settings, tenants) or edit its content (module
records, pagebuilder pages) is the web UI. The two existing admin commands
(`users create-admin`, `settings import-from-env`) open the database directly,
so they only work on the server.

The goal: **everything an operator can do in the UI can be done from a CLI, through
the API**, against any environment of any project, from a laptop or CI.

- Each project has **its own CLI** with its own name (for example `plotwiki`), not
  `smpy`. `smpy` stays the developer tool (scaffold, gen, migrations).
- A project CLI knows several **environments** and switches between them.
- It goes through the same API, auth, permission checks, tenancy and audit log
  as the UI. It never opens the database.

## Goals

1. A framework package that turns a project's OpenAPI schema into a full
   command tree: one command per token-capable API operation, grouped by module.
2. Hand-written ("curated") commands layered on top for the jobs people do
   most, contributed per module through one provider interface.
3. Named environments with credentials bound to the server they were issued for,
   a current environment, and a guard on protected environments (prod).
4. `smpy new` scaffolds the project CLI and `smpy add cli` adds it to an existing
   app. One command refreshes its bundled schema.
5. Make every UI action reachable with an API token: close the API gaps, fix the
   routes that refuse tokens today, and add a guard so new gaps fail CI.

## Non-goals

- Replacing or extending `smpy` with operator commands.
- Direct database commands. `users create-admin` stays the bootstrap path for a
  deployment with no admin yet.
- A TUI or interactive wizard.
- Token management from the CLI (list/revoke stay in the UI; the CLI obtains its
  own token only through browser approval, see § 4).
- Self-account flows (own profile, own sessions, logout, accepting an invitation,
  switching the browser's active tenant). They are about a browser session.

## Anti-goals (a failure even if it works)

- The CLI imports server code (FastAPI app, SQLModel models, module packages)
  or needs `SM_DATABASE_URL`. It must install as a small client.
- A hand-maintained list of commands that drifts behind the API.
- A second permission model, or a CLI path that widens what a token may do.
- Tokens stored in the repo, the project config file, shell history or logs.
- A token sent to any host other than the one it was stored for.

## Constraints from the codebase

- **Tokens are opt-in per route.** `simple_module_hosting.auth.token_guard`
  refuses a token principal unless the route's dependency tree admits it
  (`route_admits_tokens`): `RequiresPermission` and `TokenAllowed` admit,
  `Authenticated()` alone does **not**, page routes never do. So today tenant
  list/create and users `/me` refuse tokens.
- **`RequiresCsrf` rejects token requests.** It skips the check only when no
  session is mounted (`auth/csrf.py:110`); `SessionMiddleware` is always
  mounted, so a bearer request without a CSRF token gets 403. The users,
  tenants and settings APIs don't use it; pagebuilder's save/publish/upload do.
- **Every token is pinned to the tenant it was issued in**
  (`modules/tenants/tenants/resolution/token_tenant.py`); a PAT also needs its
  owner to stay an active member. Token management routes require a browser
  session on purpose (`api_tokens/web/deps.py`).
- operationIds are `<module>_<function>` with clash dedupe that leaves the first
  one unsuffixed (`boot/_openapi.py`). Host routers can add untagged ops. The
  security block advertises bearer on every non-public op, even ones that refuse
  tokens, so it cannot drive the generator.
- `smpy openapi export` builds the app with `create_app` and lenient settings,
  without the host's own routers or `customize`. Importing `host.main` instead
  builds the real app but reads stored settings and is strict outside development.
- `/api/openapi.json` is public only when `openapi_public` is on (off by
  default in production).
- List endpoints don't share a pagination shape: `Page`, users admin
  (`page`/`per_page`, bare array), file_storage's envelope.
- Audit rows carry `user_id` and `correlation_id` only; a PAT action looks like a
  UI action by its owner.
- 300-line cap, ty, Ruff, no magic strings, framework area layout, lockstep releases.

## Approaches considered

1. **Hand-written commands only.** Best ergonomics, but every endpoint needs a
   command, so it lags the UI and "everything" never holds.
2. **Generated only.** Full automatic coverage; raw ergonomics.
3. **Hybrid (chosen).** Generated commands as the base for complete coverage,
   curated commands for daily jobs, each project's CLI a thin package on the
   framework engine. The only option where "everything the UI does" stays true
   as modules are added, while the common jobs still get good commands.

## Design

### 1. Engine package: `simple_module_remote`

New framework package `framework/remote/` (PyPI `simple_module_remote`), area
layout, lockstep. Dependencies: `typer`, `httpx`, `keyring`, `tomli-w`, `pyyaml`.
No dependency on any other `simple_module_*` package (import-isolation test).

Public entry: `build_cli(name: str, schema_path: Path, defaults_path: Path | None) -> typer.Typer`.
Areas (my call on names): `config/`, `http/`, `schema/`, `generate/`, `output/`,
`curated/` (provider loading + first-party providers), `commands/` (built-ins).

### 2. Generated commands

**Which operations.** Hosting adds an `x-sm-token: true|false` extension to every
operation when it builds the schema, computed with `route_admits_tokens`. The
generator builds commands only for `true`; the rest are listed by
`<cli> api --session-only` so it is clear why they are absent. Coverage test:
every token-capable operation in the dev host schema maps to exactly one command.

**Names.**
- Group = first tag, kebab-cased (`FeatureFlags` → `feature-flags`); untagged → `host`.
- Command = operationId minus `<module>_`, kebab-cased
  (`tenants_change_role` → `tenants change-role`).
- A route can pin its CLI name with `openapi_extra={"x-cli-name": "…"}`;
  overrides are keyed by operation, not by deduped id.
- Built-in names (`env`, `login`, `logout`, `whoami`, `doctor`, `schema`, `api`,
  `raw`) are reserved. Collisions after normalisation fail the coverage test, so
  they are fixed with `x-cli-name` at the source, never by route order.
- The full generated tree is also always reachable under `<cli> raw <group> <cmd>`,
  so scripts have a stable entry point even where a curated command takes the name.

**Input.**
- Path params → positional args; query params → typed options (enum choices,
  defaults, repeated for arrays) with help from the schema.
- JSON body: `--json '<obj>'`, `--file body.json`, `--file -`; plus
  `--set a.b=1` (dotted paths, coerced by the resolved schema incl. `$ref`),
  `--set-json k='[...]'`, `--set k=@file`, and `--set k=null`. Merged in that
  order; missing required fields reported before sending. Open-dict payloads
  (pagebuilder Puck data) are sent as given; the server validates.
- Multipart: `--upload field=path` + `--set`. Raw-body uploads (file_storage
  stream endpoints): `--body-file path [--content-type]`.
- `--dry-run` on every mutating command prints method, URL and body, sends nothing.

**Output.** `-o table|json|yaml|id` (default table on a TTY for lists, json
otherwise); `--columns`; `-q` prints ids only. JSON output is the server
response unchanged, so it is stable as the API is. `--out <path>` for binary
bodies (refused on a TTY without it). `--all` follows the known shapes (`Page`,
`page/per_page` arrays, file_storage envelope), shows progress, takes `--limit`.

**Exit codes.** 0 ok · 1 usage · 2 other 4xx · 3 5xx/network · 4 401/403 (with a
`login` hint) · 5 404 · 6 409/412. 429 is retried up to 3 times honouring `Retry-After`.

**HTTP safety.** Requests go only to `env.url` + a path that is relative, starts
with `/api/`, and has no scheme, `@` or `//`. OpenAPI `servers` is ignored. The
`api METHOD /api/path` escape hatch follows the same rule. Redirects (presigned
downloads) are followed by a separate client with no `Authorization` header.
An `http://` URL is refused unless the host is loopback. Every request sends
`User-Agent: <cli>/<ver> simple_module_remote/<ver>`.

**Startup.** No command-tree cache in v1; measure `<cli> --help` on the dev host
schema and add a JSON (never pickle) cache only if it exceeds 300 ms.

### 3. Curated commands

**Provider interface.** A provider is a `module:attr` factory returning a
descriptor: target tag, the operationIds it needs, and a function that registers
Typer commands given a context (HTTP client, output formatter, environment).
It is mounted only when its tag exists and **all** its required operations are
present and token-capable in the active schema; otherwise it is hidden and
`doctor` says why (this handles servers older or newer than the CLI). A curated
command with a generated command's name replaces it in the group (the generated
one stays under `raw`). `--help` shows each curated command's provider.

- First-party providers (users, settings, tenants) live in `simple_module_remote`
  under `curated/`, so the project CLI installs no server packages; lockstep
  releases plus required-operation gating cover version skew.
- Third-party providers register entry point `simple_module_remote.commands`
  and are loaded **only if listed** in the project's `defaults.toml`
  (`[curated] providers = [...]`). Duplicate providers for one name are an error.
- Providers import only `simple_module_remote` and the stdlib (tested in-repo).

| Group | Commands |
|---|---|
| `users` | `list` (search, role), `show <email\|id>`, `invite <email> [--role]`, `invite-bulk <csv>`, `disable`/`enable`/`unlock`, `set-roles <user> <role…>`, `reset-link`, `sign-ins <user>`, `unlink-sign-in` |
| `settings` | `list [module]`, `get <module.key>`, `set <module.key> <value>`, `unset`, `export [module]`, `import <file> [--dry-run]`, `diff --from <env> --to <env> [module]` |
| `tenants` | `list`, `show`, `create`, `members`, `invite <email> [--role]` (existing invitation flow), `remove-member`, `set-role`, `suspend`/`reactivate` |

Users can be named by email or id (resolved with a lookup).

**Settings export/import** moves non-secret overrides between environments; it
is not a backup. Secret fields are found by the server's `is_secret` flag (never
by matching the mask) and left out; import refuses any value equal to the
mask; the export file is written 0600 and a warning is shown when exporting to a
TTY. Import goes one module at a time through the per-module API, skips
modules with their own settings page with a note, stops at the first failure
and reports what was applied, and ends with a "set manually" list (secrets,
skipped modules). `diff` compares two environments' exports.

**Pagebuilder** curated commands (`pages list`, `pages pull <slug>` to JSON,
`pages push <file>` with a block diff then save draft, `pages publish`,
`media upload`) ship from `smpy_modules` as a small provider distribution
(`smpy_pagebuilder_remote`), filed upstream. Generated `pagebuilder` commands
work once the server fixes in § 7 and the upstream gate fixes land.

### 4. Environments, credentials and login

- Config `~/.config/<cli>/config.toml` (`current`, `[env.<name>] url, tenant,
  protected`). The project package bakes default environments into
  `defaults.toml` (no secrets), merged under user config. Env names match
  `[a-z0-9-]+`.
- `env list|add|use|remove|show`; selection: `--env/-e`, `<CLI>_ENV`, `current`.
  `<CLI>` is the CLI name upper-cased with `-` → `_`.
- **Credentials are bound to an origin.** Each stored token records the URL
  origin it was issued for; if the env's URL no longer matches, the CLI refuses
  to send it and asks for a fresh `login`. Store: OS keyring (service `<cli>`,
  key `<env>` or `<env>/<tenant>`); fallback `credentials.toml` created with
  `O_EXCL` at 0600 in a 0700 dir, refused if group/world-readable.
  `<CLI>_TOKEN` (CI) is honoured only with an explicit `--env` or `<CLI>_ENV`.
  Tokens are never accepted as an argument, never echoed, never in `-v` output.
- **Login (browser, default).** `login [--env] [--tenant]` runs a device-style
  approval (§ 4a), stores the minted PAT, calls `whoami`, then runs `schema sync`.
- **Login (token).** `login --token` reads a token at a hidden prompt, or
  `--token-stdin` for CI and service keys; it calls `whoami` and checks the
  token's pinned tenant matches `--tenant` if given.
- **Tenants.** One credential per (environment, tenant): `--tenant acme` (or the
  env default) picks `<env>/acme`; missing → the CLI names the `login` command.
  `whoami` shows the pinned tenant. Ignored on a single-tenant app.
- `whoami`: user, auth kind, scopes, pinned tenant, env name and URL; a banner
  when the env is protected.
- `doctor`: env resolves, URL reachable over https, token valid and bound to
  this origin, tenant matches, schema source and age, curated providers hidden
  and why. The scaffolded README's first-run flow is `env use` → `login` →
  `whoami` → `doctor`.
- **Protected environments.** Any mutation (generated, curated or `api`), and any
  GET whose operation carries `x-cli-confirm: true` (bulk PII reads), asks you to
  type the env name; the prompt shows name and URL. `--yes` skips it and is
  required off a TTY; it is never read from an environment variable. Operations
  marked `x-cli-safe: true` (read-like POSTs such as test-connection) don't ask.
  Every mutation prints `[<env>]` to stderr.
- Shell completion via Typer, with dynamic completion of env names.

### 4a. Browser login (device approval)

Modelled on the OAuth device authorization grant (RFC 8628), served by
`api_tokens`:

1. `POST /api/api_tokens/device/start` (public, rate-limited per IP) with
   `client_name` (`<cli>`), `hostname` and optional `tenant` hint returns
   `device_code` (secret, high entropy), `user_code` (8 chars, `XXXX-XXXX`,
   unambiguous alphabet), `verification_uri`, `expires_in` (600 s), `interval` (5 s).
2. The CLI prints the user code and URL and opens
   `<verification_uri>?code=<user_code>` in the browser (`--no-browser` just prints).
3. The approval page (view route under `/api-tokens/device`, signed-in session,
   CSRF-protected POST) shows the user code to compare with the terminal, the
   client name and hostname, the server URL, a tenant picker limited to the user's
   active memberships (preselected from the hint), scopes (default: all the user
   may grant, editable) and expiry (default 90 days). Approve or deny.
4. On approve the server mints a PAT owned by the user, pinned to the chosen
   tenant, named `<cli> on <hostname>` so it is recognisable and revocable on the
   API tokens page. The device request records the token id.
5. The CLI polls `POST /api/api_tokens/device/token` with `device_code`:
   `authorization_pending`, `slow_down`, `access_denied`, `expired_token`, or the
   token **once**; the request is then consumed.

Rules: `device_code` and `user_code` stored hashed; single use; expired requests
purged; start and poll rate-limited; a user code that fails to match too often
locks that request; approval requires a session (a token can never approve, so
tokens still cannot mint tokens); audit entries for start, approve, deny and
issue. The device-request table lives on the `api_tokens` migration branch.
Service keys are still created in the UI and passed with `--token-stdin`.

### 5. Schema: bundled and live

- The project CLI ships `openapi.json`. `smpy openapi export --app <factory>`
  exports from the project's real app factory (host routers and `customize`
  included) **without a database**: the scaffolded host exposes a factory the
  exporter calls with lenient, offline settings (mechanism left to the builder;
  the requirement is no DB and identical routes to the deployed app).
- New `GET /api/_meta/openapi` in `simple_module_hosting`: requires permission
  `host.openapi.read` (admin by default, assignable to scoped tokens so CI can
  sync), admits tokens, never public whatever `openapi_public` says, excluded
  from the schema it serves, `Cache-Control: private`, weak ETag.
- `schema sync [--env]` caches it at `~/.cache/<cli>/<env>/openapi.json` with its
  origin and fingerprint; a URL change invalidates it. The engine uses the live
  cache for that env when present, else bundled. `--schema bundled|live` pins the
  source; `schema status` shows source, `info.version`, fingerprint and age. A
  404/422 adds a `schema sync` hint when the cache is missing or stale.

### 6. Credential matrix

PR 2 produces and tests a matrix of which credential can do what, documented in
the guide. Expected shape, to confirm against the code:

| Operation class | PAT (platform admin, pinned to tenant T) | PAT (tenant admin of T) | Service key (tenant T) |
|---|---|---|---|
| Host-level: users admin, system settings, tenant create/suspend | yes, capped by scopes and users safety rules (no granting `admin`) | no | per roles chosen at creation |
| Tenant-level in T: members, invitations, tenant settings, content | yes | yes | content and settings per roles; members/invitations no (needs a real membership) |
| Tenant-level in another tenant | no (needs a token issued there) | no | no |

### 7. Server changes: every UI action reachable with a token

**Token gates and CSRF.**
- `RequiresCsrf` skips the check when the principal was authenticated by a
  bearer token (`auth_kind` pat/service), decided by how the request
  authenticated, not by header presence. Cookie sessions are unchanged.
  Security review before merge; contract test: PAT + mutation → 2xx, cookie
  session without token → 403.
- Tenant list (memberships) and create get token-admitting gates; create's
  platform-permission check must run for tokens.
- New token-admitting identity endpoint for `whoami` (user, auth kind, scopes,
  pinned tenant), in `simple_module_hosting` so it works with any auth provider.

**API gaps** (verified by the council):

| Module | Missing for tokens |
|---|---|
| settings | test-connection (+ list of testable packages), rate-limited per user |
| users | user detail, role catalog (if not already token-capable), linked sign-ins list + unlink |
| dashboard | doctor results + rerun, under a new permission (the current guard excludes scoped principals) |
| sharing | admin share listing; revoke via API accepts `MANAGE` like the view does |

Each new endpoint calls the same service as its view route, with the same
permission, no `RequiresCsrf`, and has a token test.

**Audit attribution.** Add nullable `auth_kind` and `token_id` to `audit_entry`
(migration on the `audit_log` branch), filled from the principal.

**Guard.** Every non-GET view route declares either `api_equivalent=(METHOD,
"/api/…")` or an exemption with a reason (logout, self-account, token
management). A host test builds the app once and checks each declared target
exists **and** admits tokens. Prerequisite reads are covered by the curated
contract tests. The scaffold's view template gets the declaration in the same
PR; the rule goes in `docs/module-authoring.md` and the conventions skill, and
to `smpy_modules` as an upstream issue (with pagebuilder's reader gate marking).

### 8. The project CLI package (scaffold)

```text
cli/
├── pyproject.toml        # "<project>-cli", [project.scripts] <project> = "<project>_cli:main"
├── <project>_cli/
│   ├── __init__.py       # main = build_cli("<project>", schema, defaults)
│   ├── openapi.json      # bundled schema (committed)
│   └── defaults.toml     # default environments, allowed providers; no secrets
└── README.md             # install, first-run flow
```

- `smpy new` includes it by default (`--no-cli` to skip) and adds
  `simple_module_api_tokens` with its initial migration. `--cli-name` overrides
  the name (defaults to project slug).
- `smpy add cli` is idempotent and never overwrites edited files. If the app
  lacks `api_tokens`, it reports the dependency, enablement and the migration to
  generate as separate steps instead of guessing.
- `make cli-schema` runs the export; a scaffolded CI check fails when stale.
- Install: `uv tool install ./cli`; a release-workflow step builds the wheel.
- This repo's dev host gets `smdev` under `host/cli/`.

### 9. Testing

- Engine unit tests: schema → tree (names, collisions, reserved names, params,
  body merge, multipart, raw body, `x-sm-token` filtering), output, pagination,
  exit codes, config and credential precedence, origin binding, path safety,
  redirect without auth, protected-env confirmation.
- Contract tests against the in-process dev host app (httpx transport, real PAT
  and service key) through `CliRunner`: every curated command, CSRF on token
  mutations, a tenant-pinned token refused in another tenant, token-management
  routes refused, the credential matrix.
- Coverage test (every token-capable op → one command), import-isolation test,
  guard test.
- Manual run before each merge: dev host, PAT from the UI, `smdev login`, curated
  commands, recorded terminal session in the PR.

### 10. Docs and release

`docs/guide/project-cli.md` (install, first run, environments, tenants, credential
matrix, protected envs, CI), `docs/framework/remote-cli.md` (providers, `x-cli-*`
extensions, `api_equivalent`). Sidebar, `skills/simple-module-cli`,
`simple-module-conventions`, root `pyproject.toml` wiring, `publish-pypi`
matrix, `CHANGELOG.md`.

## Delivery order

1. **Engine + smdev**: `simple_module_remote` (generated commands, env,
   credentials, output, `api`, `doctor`), `x-sm-token` in hosting, the
   token-aware identity endpoint. Usable against the dev host.
2. **Server**: CSRF for tokens, tenant gates, API gaps, audit attribution,
   `/api/_meta/openapi` + `schema sync`, guard test, credential matrix.
3. **Browser login**: device approval in `api_tokens` and `login` in the engine.
4. **Curated**: users, settings, tenants.
5. **Scaffold + docs**: `smpy new`/`add cli`, `export --app`, freshness check.
6. **Upstream** (`smpy_modules`): pagebuilder reader gate and CSRF use, provider
   distribution, guard adoption. Issues filed.

## Left to the builder

- Internal module names in `simple_module_remote`, the descriptor's exact type.
- Table defaults per curated list command.
- The offline export mechanism (§ 5), within the stated requirement.

# Project CLI: a per-project command line over the REST API

Status: design, awaiting approval (2026-11-26).

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
   command tree: one command per API operation, grouped by module.
2. Hand-written ("curated") commands layered on top for the jobs people do
   most, contributed per module.
3. Named environments with per-environment credentials, a current environment,
   and a guard on protected environments (prod).
4. `smpy new` scaffolds the project CLI, and `smpy add cli` adds it to an existing app.
   One command refreshes its bundled schema.
5. Close the gaps where the UI can do something the API cannot, and add a guard
   so new gaps fail CI.

## Non-goals

- Replacing or extending `smpy` with operator commands.
- Direct database commands. The existing `users create-admin` stays as the
  bootstrap path for a deployment with no admin yet.
- A TUI or interactive wizard.
- Browser or device-code login in v1 (follow-up issue; v1 uses API tokens).
- Logout and other browser-session-only routes; they have no CLI meaning.

## Anti-goals (a failure even if it works)

- The CLI imports server code (FastAPI app, SQLModel models, module packages)
  or needs `SM_DATABASE_URL`. It must install as a small client.
- A hand-maintained list of commands that drifts behind the API.
- A second permission model. The CLI can do exactly what its token can do
  through the API, nothing more.
- Tokens stored in the repo, the project config file, or shell history.

## Constraints from the codebase

- operationIds are already `<module>_<endpoint function name>`, deduplicated on
  clash (`framework/hosting/simple_module_hosting/boot/_openapi.py`), and each
  API router is tagged with its module. That gives stable group and command names.
- `smpy openapi export` writes a project's schema without a server
  (`framework/cli/simple_module_cli/commands/openapi_cmd.py`). The schema covers
  exactly the modules that project installs, including project-specific ones.
- `/api/openapi.json` is public only when the `openapi_public` host setting is
  on (off by default in production), so the CLI cannot rely on fetching it.
- `smpy openapi export` builds the app with `create_app` directly, without the
  host's own routers or `customize` hook, and with the module set of the local
  config. It can miss host routes, and environments may differ in module set.
- Host routers can add untagged `/api` routes, whose operationId is the bare
  function name.
- `api_tokens` gives remote auth: `Authorization: Bearer smpat_…` (personal,
  acts as its owner capped by scopes) or `smsk_…` (service key). Not part of the
  `smpy new` scaffold today.
- **Every token is pinned to the tenant it was issued in**
  (`modules/tenants/tenants/resolution/token_tenant.py`); a PAT also needs its
  owner to stay an active member. A token can never act in another tenant.
- Token management routes (`/api/api_tokens/tokens`, admin tokens) require a
  browser-session principal on purpose: a leaked token cannot mint tokens.
- List endpoints do not share one pagination shape: some return `Page`, `users`
  admin list returns a bare array with offset/limit, `file_storage` has its own envelope.
- Inertia pages post to view routes (`SM018`). Most mutations also exist under
  `/api`; the audit below lists the ones that do not.
- 300-line file cap, ty, Ruff, no magic strings, area layout for framework
  packages (`docs/framework-layout.md`).

## Approaches considered

1. **Hand-written commands only.** Each module ships a command group; the
   project CLI bundles groups for its modules. Best ergonomics, but every
   endpoint needs a command, so it lags the UI and "everything" never holds.
2. **Generated only.** A generic engine plus the project's `openapi.json`
   produces one command per operation. Full, automatic coverage including
   project modules; ergonomics are raw (`--json` bodies, operation-derived names).
3. **Hybrid (chosen).** Generated commands as the base for complete coverage,
   curated commands per module for daily jobs, each project's CLI a thin package
   built on the framework engine. Chosen because it is the only option where
   "everything the UI does" stays true as modules are added, while still giving
   the common jobs good commands.

## Design

### 1. Engine package: `simple_module_remote`

New framework package `framework/remote/` (PyPI `simple_module_remote`), area
layout, published in lockstep. Dependencies: `typer`, `httpx`, `keyring`,
`tomli-w`, `pyyaml`, `rich` (via typer). No dependency on any other
`simple_module_*` package.

Public entry: `build_cli(name: str, schema_path: Path, defaults_path: Path | None) -> typer.Typer`.

Areas (my call on names): `config/` (environments, credentials), `http/`
(client, auth header, tenant header, errors, pagination), `schema/` (load,
cache, select live vs bundled), `generate/` (OpenAPI → Typer), `output/`
(table, json, yaml), `curated/` (entry-point loading and merge), `commands/`
(built-in `env`, `login`, `logout`, `whoami`, `schema`, `api`).

### 2. Generated commands

- **Group** = operation's first tag (the module), kebab-cased: `users`,
  `tenants`, `pagebuilder`. Untagged operations (host routers) go in a `host` group.
- **Command** = operationId with the `<module>_` prefix removed, kebab-cased:
  `users_update_user` → `users update-user`. Clashes after dedupe keep the
  deduped id.
- **Path params** → positional arguments in path order.
- **Query params** → `--option` with type, default, enum choices and help from
  the schema. Arrays repeat the option.
- **JSON body** →
  - `--json '<object>'`, `--file body.json`, or `--file -` (stdin);
  - `--set field=value` (repeatable) for top-level scalar fields, coerced by
    schema type, merged over `--json`/`--file`;
  - required fields missing after merge are reported before sending.
- **Multipart body** → `--upload field=path` for file parts, `--set` for the rest.
- **Responses** → `--output table|json|yaml` (`-o`). Default: `table` on a TTY
  for arrays and list envelopes, `json` otherwise. `--columns a,b` picks table columns.
- **Pagination**: `--all` follows pages for the shapes in use: the framework `Page`
  envelope, the `file_storage` envelope, and bare arrays with `offset`/`limit`
  (or `page`/`page_size`) query params, stopping on a short page. Operations
  matching none of these don't get `--all`.
- **Binary responses** (file downloads, exports): `--out <path>` writes the body;
  without it, a binary body is refused on a TTY and streamed to stdout otherwise.
  Redirect responses are followed for downloads.
- **Escape hatch**: `<cli> api METHOD /api/path [--json …]` sends any request
  with the environment's auth, for anything the generator cannot express.
- Help text comes from the operation summary/description and parameter
  descriptions, so docstrings on endpoints become CLI help.
- Exit codes: 0 ok; 1 usage error; 2 HTTP 4xx (body printed to stderr);
  3 HTTP 5xx or network error; 4 auth error (401/403, with a hint to run `login`).

### 3. Curated commands

- Entry-point group `simple_module_remote.commands`; each value resolves to a
  `typer.Typer` plus the tag it belongs to (declared as `tag:attr`, my call on
  the exact format). Mounted only when that tag exists in the active schema, so
  a project without `tenants` never shows tenant commands.
- A curated command with the same name as a generated one **replaces** it; the
  generated one stays reachable as `<cli> raw <group> <command>`.
- Curated commands receive a context object (configured HTTP client, output
  formatter, current environment). They call the API only.
- Curated command packages import only `simple_module_remote` and the stdlib.
  A test enforces this for the in-repo ones.

Shipped in this repo, inside `simple_module_remote` under `curated/` (they are
part of the engine distribution so the project CLI does not install server
packages):

| Group | Commands |
|---|---|
| `users` | `list` (search, role filter), `show <email\|id>`, `invite <email> [--role]`, `invite-bulk <csv>`, `disable`/`enable`/`unlock <user>`, `set-roles <user> <role…>`, `reset-link <user>` |
| `settings` | `list [module]`, `get <module.key>`, `set <module.key> <value>`, `unset <module.key>`, `export [module] > file`, `import file [--dry-run]` |

`settings export`/`import` moves **non-secret overrides** between environments
(staging → prod); it is not a backup. Masked/secret fields are left out of the
export. Import goes one module at a time through the existing per-module API,
`--dry-run` prints the client-side diff against the target, modules with their
own settings page are skipped with a note, and a failure stops at that module
and reports what was already applied (not atomic across modules).
| `tenants` | `list`, `show`, `create`, `members`, `invite <email> [--role]` (existing invitation flow; the person accepts it), `remove-member`, `set-role` |

There is **no `tokens` group**. Tokens are created and revoked in the UI only,
because token management stays session-only (a leaked token must not mint or
hide tokens). These routes go on the parity allowlist (§ 7) with that reason.

User arguments accept an email or id; the curated command resolves it with a
lookup call.

**Pagebuilder** lives in `smpy_modules`, so its curated commands
(`pages list`, `pages pull <slug> [--locale]` to a JSON file, `pages push <file>`
showing a block diff then saving a draft, `pages publish <slug>`, `media upload`)
ship there as a separate small distribution (`smpy_pagebuilder_remote`), filed as
an upstream issue. Until it lands, every pagebuilder operation is available
through the generated `pagebuilder` group.

### 4. Environments and credentials

- Config file: `~/.config/<cli>/config.toml`:

  ```toml
  current = "staging"

  [env.staging]
  url = "https://staging.example.org"
  tenant = "acme"          # optional default tenant
  protected = false

  [env.prod]
  url = "https://example.org"
  protected = true
  ```

- The project CLI package can bake in default environments (`defaults.toml`
  next to the bundled schema), merged under the user's config, so a new team
  member gets `dev/staging/prod` URLs without typing them. No secrets in it.
- Commands: `env list`, `env add <name> --url … [--protected]`,
  `env use <name>`, `env remove <name>`, `env show`.
- Selection order: `--env/-e`, `<CLI>_ENV`, `current`.
- Credentials: `login [--env]` prompts for a token with hidden input,
  verifies it with a whoami call, and stores it in the OS keyring under
  service `<cli>` and key `<env>`. If no keyring backend is available,
  it falls back to `~/.config/<cli>/credentials.toml` with mode 0600 and a warning.
  `<CLI>_TOKEN` overrides for CI. `logout` deletes the stored token.
- `whoami` prints the user, auth kind (pat/service), scopes, active tenant
  and environment.
- **Protected environments**: any non-GET request asks for confirmation that
  names the environment, unless `--yes` is passed. When not on a TTY, `--yes` is required.
- `--tenant <slug>` (or the environment default) selects **which stored token**
  to use (see § 6).

### 5. Schema: bundled and live

- The project CLI ships `openapi.json` produced by `smpy openapi export`.
- `smpy openapi export` gains `--app <module:attr>` to export from the host's real
  app object (`host.main:app` in a scaffolded app), so host routers and
  `customize` are included. The scaffolded `make cli-schema` uses it.
- New authenticated endpoint `GET /api/_meta/openapi` in `simple_module_hosting`
  returns the running app's schema. It is guarded by a new host permission
  (`host.openapi.read`, granted to admin by default) and served whatever
  `openapi_public` is set to. ETag supported. This is what lets the CLI match an
  environment whose module set or version differs from the bundled schema.
- `schema sync [--env]` downloads it into
  `~/.cache/<cli>/<env>/openapi.json`. When a cached live schema exists for the
  current environment, the engine uses it; otherwise it falls back to the bundled one.
  So one CLI binary works against environments on different versions.
- `schema status` shows which schema is in use, its version (the `info.version`
  of the app) and the age of the cache. A 404 or 422 from the API adds a hint
  to run `schema sync` when the cache is older than the bundled schema or missing.
- Startup cost: the parsed command tree is cached keyed on schema hash, so
  `<cli> --help` stays fast with large schemas (target < 300 ms).

### 6. Tenancy over the API

No server change. Tokens stay pinned to their issuing tenant; the CLI does not
widen that boundary. Instead the CLI keeps **one credential per (environment,
tenant)**:

- `login --env prod --tenant acme` stores the token under key `prod/acme`;
  `login --env prod` with no tenant stores the environment's default token
  (`prod`), used for host-level work (users, settings, `tenants create`).
- `--tenant acme` (or the environment's `tenant` default) picks `prod/acme`.
  If none is stored, the CLI says so and names the `login` command to run.
- `whoami` shows which tenant the active token is pinned to, so a mismatch is
  visible. On a single-tenant app, `--tenant` is ignored.
- Working in a tenant just created with `tenants create` needs a token issued in
  that tenant; the docs say so.

### 7. Closing API gaps

Scope of "everything": every UI **mutation** has a bearer-usable API operation,
and every **read the UI needs to drive a mutation** (for example the user's
linked sign-ins before unlinking one) has one too. Plain page reads already
backed by `/api` lists need nothing new.

The review checked the view-route mutations. Settings rows, both permission
edits, feature-flag toggle/clear and share revoke **already have** API
operations calling the same services. Remaining gaps to verify and close:

| Module | View route | Action |
|---|---|---|
| settings | `POST /test-connection/{package}` | test a module's connection settings |
| users | `DELETE /{user_id}/linked-sign-ins/{id}` (+ a read listing them) | unlink an OAuth sign-in |
| dashboard | `POST /rerun` (admin) | rerun dashboard checks |

Excluded on purpose: `logout` routes (keycloak, oidc, users) and token management
(§ 3).

For each, add an `/api` endpoint that calls the same service function as the
view route, with the same permission. The view route keeps working.
Each new endpoint gets a test.

**Guard**: a host test enumerates every non-GET view route in the built app.
Each one must either map to an API operation (declared with a small route
marker, `api_equivalent="<operationId>"`, my call on the mechanism) or appear in
an allowlist with a reason (logout, browser-only flows). A new UI-only mutation
then fails CI. The same rule is documented in `docs/module-authoring.md` and
the `simple-module-conventions` skill, and is offered to `smpy_modules` as an
upstream issue.

### 8. The project CLI package (scaffold)

`smpy new` gains the CLI by default (`--no-cli` to skip). `smpy add cli`
adds it to an existing app. Generated layout in the app repo:

```text
cli/
├── pyproject.toml        # name "<project>-cli", [project.scripts] <project> = "<project>_cli:main"
├── <project>_cli/
│   ├── __init__.py       # main = build_cli("<project>", schema, defaults)
│   ├── openapi.json      # bundled schema (committed)
│   └── defaults.toml     # default environments, no secrets
└── README.md             # install, login, env setup
```

- The CLI name defaults to the project slug; `--cli-name` overrides.
- Depends only on `simple_module_remote` (+ curated distributions for
  installed external modules that ship one, e.g. `smpy_pagebuilder_remote`).
- `make cli-schema` (scaffolded app Makefile) runs `smpy openapi export
  --app host.main:app --out cli/<project>_cli/openapi.json`. A scaffolded CI check fails
  when it is stale, mirroring `ci-api-types-fresh`.
- Install: `uv tool install ./cli` locally. A scaffolded release-workflow step
  builds the wheel as a CI artifact. Publishing to an index is left to each project.
- `smpy new` also adds `simple_module_api_tokens` to the scaffold when the CLI
  is enabled, since the CLI needs tokens (migration included in the scaffold's
  initial revisions).
- This repo's dev host gets its own CLI (`smdev`) under `host/cli/` so the
  engine is exercised end to end in CI.

### 9. Testing

- Engine unit tests: schema → command tree (names, params, body handling,
  multipart, enums), output formats, pagination, exit codes, config and
  credential precedence, protected-env confirmation.
- Contract tests against the real app: build the dev host app in-process
  (existing `app` fixture), mount an httpx transport into the engine, and drive
  generated and curated commands through `typer.testing.CliRunner` with a real
  PAT: list/create/update users, set a setting, create a tenant and invite a
  member, a tenant-pinned token cannot touch another tenant, a token cannot reach
  token-management routes.
- A schema-coverage test: every operation in the dev host schema produces
  exactly one reachable command.
- Import-isolation test: importing `simple_module_remote` and curated packages
  pulls in no `fastapi`, `sqlmodel` or `simple_module_*` server package.
- A guard test for UI-only mutations (§ 7).
- Manual end-to-end before merge: run the dev host, create a PAT in the UI,
  `smdev login`, run each curated command against it, and record a terminal session.

### 10. Docs and release

- `docs/guide/project-cli.md` (install, environments, login, generated vs
  curated, tenants, protected envs, CI usage with `<CLI>_TOKEN`), and
  `docs/framework/remote-cli.md` (writing curated commands, entry point,
  import rule). Sidebar entries.
- Update `skills/simple-module-cli` and `simple-module-conventions` (API-equivalent rule).
- Wire the new package: root `pyproject.toml` testpaths and ty extra-paths,
  the `publish-pypi` matrix, `CHANGELOG.md`.

## Delivery order

Separate PRs, in dependency order:

1. **Engine core**: `simple_module_remote` with generated commands, environments,
   credentials, output, `api` escape hatch, `smdev` for the dev host, tests.
2. **Server side**: `/api/_meta/openapi` plus `schema sync`; `smpy openapi export
   --app`; API-gap endpoints plus the guard test.
3. **Curated commands**: users, settings, tenants, tokens.
4. **Scaffold**: `smpy new` / `smpy add cli`, `make cli-schema`, freshness check, docs.
5. **Upstream** (`smpy_modules`): `smpy_pagebuilder_remote` curated commands and
   the API-equivalent guard; issues filed, not done in this repo.

## Left to the builder

- Exact internal module names inside `simple_module_remote`, the curated
  entry-point value format, and the route-marker mechanism for `api_equivalent`.
- Table rendering details and default columns per curated list command.
- Whether the command-tree cache is pickle or JSON.
- Which existing "me" endpoint backs `whoami`, or whether a small one is added.

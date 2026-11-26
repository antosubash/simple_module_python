# Project CLI — PR 1: engine + smdev Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `simple_module_remote`, a client-only engine that turns a project's OpenAPI schema into a CLI with environments and token credentials, plus `smdev`, the dev host's CLI, usable end to end against the dev host.

**Architecture:** Hosting marks every operation with `x-sm-token` and gains a token-capable `GET /api/_meta/whoami`. The engine (new framework package `framework/remote`) loads a bundled schema, generates a click command tree for token-capable operations, and sends requests through one guarded `httpx.Client`. Built-in commands (env, login, logout, whoami, doctor, schema status, api, raw) are Typer apps folded into the same click root.

**Tech Stack:** Python 3.12, click/Typer, httpx, keyring, tomli-w, PyYAML, rich (via typer); FastAPI on the server side.

**Spec:** `docs/superpowers/specs/2026-11-26-project-cli-design.md` (§§ 1, 2, 4 minus browser login, 5 bundled-only, 8 `smdev`, 9, 10). Later PRs (server gaps, browser login, curated, scaffold, upstream) get their own plans.

## Global Constraints

- Engine package `framework/remote/`, PyPI `simple_module_remote`, version equal to the other framework packages (lockstep; copy `framework/inertia/pyproject.toml` metadata shape).
- Engine dependencies only: `typer`, `httpx`, `keyring`, `tomli-w`, `pyyaml`. It must not import `fastapi`, `sqlmodel`, `sqlalchemy`, `starlette` or any `simple_module_*` package.
- Area layout: areas `config`, `http`, `schema`, `generate`, `output`, `curated`, `commands`; area `__init__.py` holds only a docstring; tests under `framework/remote/tests/<area>/`, no `__init__.py`, no flat `test_*.py`.
- 300-line cap per `.py` file, tests included. Ruff, ty clean. No `# type: ignore`.
- No fixed sleeps in tests: inject a sleeper callable.
- Env names match `^[a-z0-9-]+$`. `<CLI>` env-var prefix = CLI name upper-cased, `-` → `_`.
- Requests only to `env.url` + a path matching: starts with `/api/`, no `://`, no `@`, no `//`. `http://` refused unless host is `localhost`, `127.0.0.1` or `::1`.
- `User-Agent: <cli>/<cli_version> simple_module_remote/<engine_version>`.
- Exit codes: 0 ok · 1 usage · 2 other 4xx · 3 5xx/network · 4 401/403 · 5 404 · 6 409/412. 429 retried up to 3 times honouring `Retry-After` (seconds; default 1).
- Reserved top-level names: `env`, `login`, `logout`, `whoami`, `doctor`, `schema`, `api`, `raw`.
- Tokens never accepted as a CLI argument, never printed, never in exception text.
- Credential fallback file: `O_CREAT|O_EXCL`, mode 0600, dir 0700; refuse to read when `mode & 0o077`.
- `<CLI>_TOKEN` honoured only when `--env` or `<CLI>_ENV` is set explicitly.
- `--yes` is a flag only, never read from the environment.

## Review Focus

1. **A schema operation the generator can't express** (a `oneOf` body, a path param named like a reserved option, a query param named `json`): expect the command to still exist and accept `--json`, never a crash at startup. Test in Task 6 (`test_unexpressible_operation_still_builds`).
2. **A stored token whose env URL was edited afterwards** (`env add prod --url` to a new host): expect refusal with a `login` hint, no request sent. Test in Task 3 (`test_origin_mismatch_refuses`) and Task 9 (`test_edited_env_url_sends_nothing`).
3. **A response that is not JSON** (HTML error page from a proxy, empty 204, binary download): expect a clear message and correct exit code, no traceback. Test in Task 7 (`test_non_json_error_body`, `test_204_prints_nothing`).
4. **Redirect to another host on download**: expect the follow request to carry no `Authorization`. Test in Task 4 (`test_redirect_drops_auth`).
5. **Running with no config at all** (fresh machine, `smdev users list`): expect a message naming `smdev env use` / `smdev login`, exit 1. Test in Task 9 (`test_fresh_machine_hint`).

---

### Task 1: Hosting — `x-sm-token` on every operation and `GET /api/_meta/whoami`

**Files:**
- Modify: `framework/hosting/simple_module_hosting/auth/token_guard.py` (extract `gate_kinds_admit_tokens`)
- Modify: `framework/hosting/simple_module_hosting/pipeline/_route_access.py` (`ApiOperation.admits_tokens`)
- Modify: `framework/hosting/simple_module_hosting/boot/_openapi.py` (`add_security` writes the extension)
- Create: `framework/hosting/simple_module_hosting/auth/whoami.py`
- Modify: `framework/hosting/simple_module_hosting/boot/app_builder.py:256` (include the router next to `health_router`)
- Test: `framework/hosting/tests/boot/test_openapi_token_flag.py`, `framework/hosting/tests/auth/test_whoami.py`
- Modify: `CHANGELOG.md` (Unreleased: `x-sm-token`, `/api/_meta/whoami`)

**Interfaces:**
- Produces: `gate_kinds_admit_tokens(kinds: set[str]) -> bool` (page → False; allow → True; else permission present). `route_admits_tokens` uses it (behaviour unchanged).
- Produces: `ApiOperation.admits_tokens: bool` property.
- Produces: every schema operation has `"x-sm-token": true|false`.
- Produces: `GET /api/_meta/whoami`, tag `Meta`, operationId `meta_whoami`, dependencies `Authenticated()` + `TokenAllowed()`, response model `WhoAmI(SQLModel)`: `id: str, email: str, name: str, auth_kind: str, scopes: list[str] | None, tenant_id: str | None, roles: list[str]`.

- [ ] **Step 1: Write failing tests**

```python
# test_openapi_token_flag.py
async def test_operations_carry_token_flag(app):
    schema = app.openapi()
    flags = {op["operationId"]: op["x-sm-token"]
             for item in schema["paths"].values() for op in item.values() if isinstance(op, dict)}
    assert flags["meta_whoami"] is True
    assert flags["tenants_list_mine"] is False          # Authenticated() only, today
    assert flags["users_list_users"] is True            # RequiresPermission
    assert all(isinstance(v, bool) for v in flags.values())

# test_whoami.py
async def test_whoami_session(authenticated_client):
    body = (await authenticated_client.get("/api/_meta/whoami")).json()
    assert body["email"] == "admin@test" and body["auth_kind"] == "session" and body["scopes"] is None

async def test_whoami_anonymous_401(client):
    assert (await client.get("/api/_meta/whoami")).status_code == 401
```

Add a PAT case reusing `modules/api_tokens/tests/_api_tokens_support.py` patterns (`create_pat`), asserting `auth_kind == "pat"`, `scopes` is the list given, `tenant_id` set. Put it in `modules/api_tokens/tests/web/test_whoami_token.py` (the hosting tests can't import module helpers).

- [ ] **Step 2: Run, verify failure** — `uv run pytest framework/hosting/tests/boot/test_openapi_token_flag.py framework/hosting/tests/auth/test_whoami.py modules/api_tokens/tests/web/test_whoami_token.py -v` → FAIL (KeyError `x-sm-token`, 404).
- [ ] **Step 3: Implement.** In `add_security`, set `operation["x-sm-token"] = op.admits_tokens` in the same loop that sets `security`. The whoami handler reads `request.state.user`.
- [ ] **Step 4: Run, verify pass**, plus `uv run pytest framework/hosting/tests/auth/test_token_route_guard.py -q` (no regressions).
- [ ] **Step 5: Commit** `feat(hosting): mark token-capable operations and add /api/_meta/whoami`.

### Task 2: Engine package skeleton and environment config

**Files:**
- Create: `framework/remote/{pyproject.toml,README.md,LICENSE,NOTICE}`, `framework/remote/simple_module_remote/{__init__.py,py.typed}`, one docstring-only `__init__.py` per area.
- Create: `framework/remote/simple_module_remote/config/environments.py`, `config/paths.py`
- Modify: root `pyproject.toml` (`testpaths` add `framework/remote/tests`; ty `extra-paths` add `framework/remote`), `host/tests/test_framework_layout.py` (`FRAMEWORK_PACKAGES["remote"]`, `PACKAGE_ROOT_EXTRAS["remote"] = frozenset()`, `AREAS["remote"]`), `.github/workflows/release.yml` publish matrix (`simple_module_remote`), `scripts/bump_version.py` if it lists packages.
- Test: `framework/remote/tests/config/test_environments.py`

**Interfaces:**
- Produces (`config/paths.py`): `config_dir(cli: str) -> Path` (`$XDG_CONFIG_HOME/<cli>` else `~/.config/<cli>`), `cache_dir(cli: str) -> Path` (`$XDG_CACHE_HOME`…), `env_prefix(cli: str) -> str`.
- Produces (`config/environments.py`):
  - `@dataclass(frozen=True) class Environment: name: str; url: str; tenant: str | None = None; protected: bool = False` with `origin` property (`scheme://host[:port]`).
  - `@dataclass class Config: current: str | None; envs: dict[str, Environment]`.
  - `load_config(cli: str, defaults_path: Path | None) -> Config` — defaults merged under user file; user values win per key.
  - `save_config(cli: str, config: Config) -> None` — writes only user-owned envs and `current` (never copies defaults into the user file unless edited).
  - `select_env(config: Config, flag: str | None, environ: Mapping[str, str], cli: str) -> tuple[Environment, bool]` — returns env and `explicit` (True when from flag or `<CLI>_ENV`). Raises `ConfigError` with a hint when nothing resolves.
  - `validate_env_name(name: str) -> str`; `class ConfigError(Exception)`.

- [ ] **Step 1: Write failing tests** — `test_defaults_merge_user_wins`, `test_select_precedence_flag_env_current`, `test_select_explicit_flag`, `test_invalid_env_name_rejected` (`"Prod"`, `"../x"`), `test_no_env_hint_names_env_use`, `test_save_does_not_copy_defaults`, `test_env_prefix("my-app") == "MY_APP"`. Use `tmp_path` + `monkeypatch.setenv("XDG_CONFIG_HOME", ...)`.
- [ ] **Step 2: Run** `uv run pytest framework/remote/tests/config -v` → FAIL (import error).
- [ ] **Step 3: Implement** with `tomllib` read / `tomli_w` write. Config schema: `current = "<name>"`, `[env.<name>] url, tenant, protected`.
- [ ] **Step 4: Run** tests and `uv run pytest host/tests/test_framework_layout.py -q` → PASS. `uv sync --all-packages` then commit `uv.lock`.
- [ ] **Step 5: Commit** `feat(remote): add simple_module_remote package and environment config`.

### Task 3: Credentials bound to an origin

**Files:**
- Create: `framework/remote/simple_module_remote/config/credentials.py`, `config/_file_store.py`
- Test: `framework/remote/tests/config/test_credentials.py`

**Interfaces:**
- Consumes: `Environment`, `config_dir`, `env_prefix`.
- Produces:
  - `@dataclass(frozen=True) class StoredCredential: token: str; origin: str` (`__repr__` masks the token).
  - `credential_key(env: str, tenant: str | None) -> str` → `"prod"` / `"prod/acme"`.
  - `class CredentialStore: def __init__(self, cli: str, *, backend: KeyringBackend | None = None)`; `get(key) -> StoredCredential | None`, `put(key, cred) -> None`, `delete(key) -> bool`, `using_fallback: bool`. Backend = `keyring` when a usable backend exists (not `keyring.backends.fail.Keyring`), else the file store. Keyring value is JSON `{"token","origin"}`.
  - `resolve_token(store, env: Environment, tenant: str | None, environ, cli, explicit: bool) -> str` — order: `<CLI>_TOKEN` (only if `explicit`, else `CredentialError` explaining why), then stored key. Raises `CredentialError` with the exact `login` command when missing, or when `cred.origin != env.origin`.
  - `class CredentialError(Exception)`.

- [ ] **Step 1: Write failing tests** — `test_put_get_roundtrip_fallback`, `test_fallback_file_mode_0600_dir_0700`, `test_fallback_refuses_loose_permissions` (chmod 0644 → `CredentialError`), `test_origin_mismatch_refuses`, `test_env_token_requires_explicit_env`, `test_env_token_used_when_explicit`, `test_missing_names_login_command` (message contains `smdev login --env prod --tenant acme`), `test_repr_never_contains_token`. Inject a fake in-memory keyring backend for one keyring-path test.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** File store: `credentials.toml` written via `os.open(tmp, O_CREAT|O_EXCL|O_WRONLY, 0o600)` then `os.replace`; directory created with `mkdir(mode=0o700)`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(remote): origin-bound credential store`.

### Task 4: Guarded HTTP client

**Files:**
- Create: `framework/remote/simple_module_remote/http/client.py`, `http/errors.py`, `http/safety.py`
- Test: `framework/remote/tests/http/test_client.py`, `framework/remote/tests/http/test_safety.py`

**Interfaces:**
- Consumes: `Environment`.
- Produces:
  - `validate_api_path(path: str) -> str` (raises `UnsafePathError`); `validate_base_url(url: str) -> str` (https or loopback http).
  - `class ApiClient: def __init__(self, env: Environment, token: str | None, *, user_agent: str, transport: httpx.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep, max_retries: int = 3)`; `request(self, method: str, path: str, *, params=None, json=None, files=None, data=None, content=None, headers=None) -> httpx.Response`; context manager closes clients.
  - Redirects: main client `follow_redirects=False`; on 301/302/303/307/308 for GET, follow `Location` with a second client that has **no** `Authorization` (max 5 hops).
  - `exit_code_for(status: int) -> int` per Global Constraints; `class ApiError(Exception)` carrying `status`, `body_text`.

- [ ] **Step 1: Write failing tests** with `httpx.MockTransport`: `test_auth_and_user_agent_headers`, `test_rejects_paths` (parametrize: `"http://x/api/a"`, `"/api//evil"`, `"/api/a@b"`, `"/other"`), `test_http_url_refused_non_loopback`, `test_http_loopback_allowed`, `test_redirect_drops_auth` (302 to `https://storage.example/obj` → second request has no `authorization`), `test_429_retries_with_retry_after` (sleeper records `[2.0]`, then 200), `test_429_gives_up_after_3`, `test_exit_code_mapping` (parametrize 401→4, 403→4, 404→5, 409→6, 412→6, 422→2, 500→3).
- [ ] **Step 2: Run** `uv run pytest framework/remote/tests/http -v` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(remote): guarded HTTP client`.

### Task 5: Schema loading and operation model

**Files:**
- Create: `framework/remote/simple_module_remote/schema/loader.py`, `generate/operations.py`, `generate/naming.py`
- Test: `framework/remote/tests/schema/test_loader.py`, `framework/remote/tests/generate/test_operations.py`, `framework/remote/tests/generate/test_naming.py`
- Fixture: `framework/remote/tests/generate/fixtures/mini_openapi.json` (hand-written, ~12 ops covering: path+query params, enum, array query, JSON body with `$ref` and nested object, `oneOf` body, multipart, raw `application/octet-stream`, untagged op, `x-sm-token: false` op, `x-cli-name` override, a collision pair, `x-cli-safe`, `x-cli-confirm`)

**Interfaces:**
- Produces:
  - `load_schema(path: Path) -> dict`; `resolve_ref(schema: dict, node: dict) -> dict` (follows `$ref` chains, cycle-safe).
  - `group_name(tag: str | None) -> str` (`FeatureFlags` → `feature-flags`, `None` → `host`); `command_name(operation_id: str, tag: str | None, override: str | None) -> str` (strip `<snake(tag)>_` prefix, kebab-case; override wins); `RESERVED: frozenset[str]`.
  - `@dataclass(frozen=True) class Param: name: str; location: Literal["path","query"]; required: bool; schema: dict; description: str`.
  - `@dataclass(frozen=True) class Operation: operation_id: str; method: str; path: str; group: str; name: str; params: tuple[Param, ...]; body_kind: Literal["none","json","multipart","raw"]; body_schema: dict | None; summary: str; description: str; safe: bool; confirm: bool; token_capable: bool`.
  - `parse_operations(schema: dict) -> list[Operation]` (all ops); `cli_operations(ops) -> list[Operation]` (token-capable only).
  - `find_collisions(ops: list[Operation]) -> list[tuple[str, str, list[str]]]` — `(group, name, operation_ids)` for duplicates and for group names in `RESERVED`.

- [ ] **Step 1: Write failing tests** — naming table test (`("tenants_change_role","Tenants",None) → "change-role"`, `("users_list_users","Users",None) → "list-users"`, override → override), `test_untagged_goes_to_host`, `test_token_false_excluded_from_cli_operations`, `test_body_kinds_detected`, `test_ref_resolved`, `test_collision_reported`, `test_reserved_group_reported`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(remote): schema loader and operation model`.

### Task 6: Request building (params and bodies)

**Files:**
- Create: `framework/remote/simple_module_remote/generate/body.py`, `generate/params.py`
- Test: `framework/remote/tests/generate/test_body.py`, `framework/remote/tests/generate/test_params.py`

**Interfaces:**
- Consumes: `Operation`, `Param`, `resolve_ref`.
- Produces:
  - `click_params_for(op: Operation) -> list[click.Parameter]` — path params → `click.Argument` in path order; query params → `--kebab-name` options (enum → `click.Choice`, array → `multiple=True`, integer/number/boolean typed); body options per kind: json → `--json`, `--file`, `--set` (multiple), `--set-json` (multiple); multipart → `--upload` (multiple) + `--set`; raw → `--body-file`, `--content-type`. Always `--dry-run`, `-o/--output`, `--columns`, `-q`, `--out`, `--yes`; list-returning ops also `--all`, `--limit`. A param whose kebab name collides with these is exposed as `--param-<name>`.
  - `build_json_body(*, json_arg: str | None, file_arg: str | None, sets: Sequence[str], set_jsons: Sequence[str], body_schema: dict | None, root: dict, stdin: TextIO) -> dict | list | None` — merge order json → file → set-json → set; dotted paths create nested dicts; `@path` reads file; `null` literal → None; scalars coerced by the resolved property schema (`integer`, `number`, `boolean`, else string); unknown/`oneOf` schemas leave strings as given.
  - `missing_required(body: dict, body_schema: dict | None, root: dict) -> list[str]` (top-level only).
  - `class BodyError(Exception)`.

- [ ] **Step 1: Write failing tests** — `test_set_dotted_creates_nested`, `test_set_coerces_by_schema` (`is_active=false` → `False`, `max=3` → `3`), `test_set_null`, `test_set_at_file`, `test_merge_order`, `test_file_dash_reads_stdin`, `test_missing_required_reported`, `test_invalid_json_message` (BodyError names the flag), `test_param_name_collision_prefixed`, `test_unexpressible_operation_still_builds` (the `oneOf` op yields params including `--json` without raising).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(remote): parameter and body building`.

### Task 7: Output, pagination and operation execution

**Files:**
- Create: `framework/remote/simple_module_remote/output/render.py`, `http/pagination.py`, `generate/execute.py`, `commands/confirm.py`
- Test: `framework/remote/tests/output/test_render.py`, `framework/remote/tests/http/test_pagination.py`, `framework/remote/tests/generate/test_execute.py`

**Interfaces:**
- Consumes: `ApiClient`, `exit_code_for`, `Operation`, `build_json_body`, `Environment`.
- Produces:
  - `render(data: Any, *, fmt: Literal["table","json","yaml","id"] | None, columns: list[str] | None, quiet: bool, is_tty: bool, out: TextIO) -> None` — default table when `is_tty` and data is a list (or a dict with `items`), else json; `id`/`quiet` print one `id` per line.
  - `PaginationStyle = Literal["page_envelope","page_per_page","file_storage"]`; `pagination_style(op: Operation, response_schema: dict | None) -> PaginationStyle | None`; `iter_items(fetch: Callable[[dict], Any], style, params: dict, limit: int | None, on_progress: Callable[[int], None]) -> Iterator[Any]` — stops on a short or empty page.
  - `@dataclass class RunContext: env: Environment; client_factory: Callable[[], ApiClient]; is_tty: bool; stdout: TextIO; stderr: TextIO; stdin: TextIO; prompt: Callable[[str], str]`.
  - `confirm_protected(env: Environment, *, mutation: bool, op_confirm: bool, op_safe: bool, yes: bool, is_tty: bool, prompt) -> None` — when `env.protected` and (`mutation and not op_safe` or `op_confirm`): `--yes` passes; non-TTY without `--yes` raises `click.UsageError`; TTY prompt `Type "<name>" to run <METHOD> <path> on <name> (<url>):` must equal the env name. Mutations print `[<name>]` to stderr.
  - `run_operation(ctx: RunContext, op: Operation, values: dict[str, Any]) -> int` — builds request; `--dry-run` prints `METHOD URL` and the body as JSON to stdout, sends nothing, returns 0; binary response (`Content-Type` not JSON/text) without `--out` on a TTY → message, exit 1; with `--out` writes file; 204 prints nothing; non-JSON error body prints the first 500 chars to stderr; returns `exit_code_for`.

- [ ] **Step 1: Write failing tests** — render: `test_table_default_on_tty_for_lists`, `test_json_default_off_tty`, `test_id_format`, `test_yaml`. Pagination: one test per style, `test_limit_stops_early`, `test_short_page_stops`. Execute (MockTransport): `test_dry_run_sends_nothing`, `test_protected_non_tty_requires_yes`, `test_protected_prompt_must_match_name`, `test_safe_post_skips_confirm`, `test_confirm_flag_on_get`, `test_binary_refused_on_tty_without_out`, `test_out_writes_file`, `test_204_prints_nothing`, `test_non_json_error_body`, `test_mutation_prints_env_tag`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(remote): output, pagination and operation execution`.

### Task 8: Command tree and built-in commands

**Files:**
- Create: `framework/remote/simple_module_remote/generate/tree.py`, `commands/env_cmd.py`, `commands/auth_cmd.py` (login/logout/whoami), `commands/doctor_cmd.py`, `commands/schema_cmd.py`, `commands/api_cmd.py`, `commands/root.py`
- Create: `framework/remote/simple_module_remote/curated/registry.py` (empty provider hook for PR 4: `load_providers(names: Sequence[str]) -> list` returning `[]` when none listed)
- Export from `simple_module_remote/__init__.py`: `build_cli`, `__version__`
- Test: `framework/remote/tests/generate/test_tree.py`, `framework/remote/tests/commands/test_env_cmd.py`, `framework/remote/tests/commands/test_auth_cmd.py`, `framework/remote/tests/commands/test_api_cmd.py`, `framework/remote/tests/commands/test_doctor_cmd.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `build_cli(name: str, schema_path: Path, defaults_path: Path | None = None, *, version: str = "0", transport: httpx.BaseTransport | None = None) -> click.Group`. Root options: `--env/-e`, `--tenant`, `--schema bundled` (only `bundled` valid in PR 1; `live` arrives in PR 2). Generated groups mounted at top level and again under `raw`. `find_collisions` non-empty → raise at build time (the coverage test catches it in CI).
  - `env list|add <name> --url [--tenant] [--protected/--no-protected]|use|remove|show`.
  - `login [--token | --token-stdin]` — PR 1 supports token modes only; `--token` uses `click.prompt(hide_input=True)`; calls `GET /api/_meta/whoami` with the candidate token; if `--tenant` given, `whoami.tenant_id` must match the tenant's id or slug (compare both); stores `StoredCredential(token, env.origin)` under `credential_key`. Plain `login` with neither flag prints that browser login arrives with PR 3 and exits 1 (replaced in PR 3).
  - `logout`, `whoami` (prints user, auth kind, scopes, tenant, env name and URL; `PROTECTED` banner when protected).
  - `doctor` — checks, each printed `ok`/`FAIL` with a fix hint: env resolves; URL is https or loopback; server reachable (`GET /api/_meta/whoami` answers at all; a 401 still proves reachability — `/health` is outside `/api/` so the engine never calls it); credential present and origin-bound; whoami succeeds; tenant matches; schema source and `info.version`. Exit 1 if any FAIL.
  - `schema status` (source `bundled`, path, `info.version`, sha256 fingerprint first 12 chars).
  - `api METHOD PATH [--json|--file|--set …] [-o …] [--yes]` (same safety and confirmation), `api --session-only` lists `x-sm-token: false` operations as `METHOD path operationId`.
  - Typer apps for built-ins converted with `typer.main.get_command` and added to the click root.

- [ ] **Step 1: Write failing tests** (`click.testing.CliRunner`, mini schema fixture, `httpx.MockTransport`, `XDG_*` in `tmp_path`): `test_generated_groups_and_raw_mirror`, `test_session_only_ops_hidden_and_listed`, `test_build_fails_on_collision`, `test_env_add_use_list`, `test_login_token_stdin_stores_origin_bound`, `test_login_tenant_mismatch_refused`, `test_login_rejects_token_argument` (no `--token <value>` form exists: `--token` is a flag), `test_whoami_protected_banner`, `test_api_escape_hatch_rejects_unsafe_path`, `test_doctor_reports_failures`, `test_fresh_machine_hint`, `test_help_lists_groups`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `uv run pytest framework/remote/tests -q` → PASS.
- [ ] **Step 5: Measure startup.** `python -X importtime` not needed; time `CliRunner().invoke(cli, ["--help"])` against the real dev host schema from Task 9 in a throwaway script; record the number in the PR. If > 300 ms, file a follow-up issue for the JSON tree cache (do not build it here).
- [ ] **Step 6: Commit** `feat(remote): command tree and built-in commands`.

### Task 9: `smdev` for the dev host, contract tests and CI wiring

**Files:**
- Create: `host/cli/pyproject.toml` (name `smdev-cli`, `[project.scripts] smdev = "smdev_cli:main"`, depends on `simple_module_remote` workspace), `host/cli/smdev_cli/__init__.py` (`main = build_cli("smdev", <pkg>/openapi.json, <pkg>/defaults.toml, version=__version__)` invoked), `host/cli/smdev_cli/defaults.toml` (`[env.local] url = "http://localhost:8000"`), `host/cli/smdev_cli/openapi.json` (generated), `host/cli/README.md`
- Modify: root `pyproject.toml` workspace `members` add `"host/cli"`; `Makefile`: `cli-schema` target (`uv run smpy openapi export --out host/cli/smdev_cli/openapi.json`) and `ci-cli-schema-fresh` (regenerate then `git diff --exit-code host/cli/smdev_cli/openapi.json`), add it to `make lint` and to the `python-lint` job in `.github/workflows/pr.yml` (keep `make ci-check-ci-parity` green)
- Create: `host/tests/remote_cli/conftest.py`, `host/tests/remote_cli/test_smdev_contract.py`, `host/tests/remote_cli/test_schema_coverage.py`, `framework/remote/tests/config/test_import_isolation.py`
- Modify: `docs/guide/project-cli.md` (new: install, env, login with token, generated commands, protected envs, CI with `SMDEV_TOKEN` + `SMDEV_ENV`), `docs/framework/remote-cli.md` (new: engine architecture, `x-sm-token`, `x-cli-name`/`x-cli-safe`/`x-cli-confirm`), `docs/.vitepress/config.ts` sidebar, `skills/simple-module-cli/SKILL.md` (project CLI section), `CHANGELOG.md`, `framework/remote/README.md`

**Interfaces:**
- Consumes: `build_cli(..., transport=...)`; dev host `app` fixture; `create_pat` pattern from `modules/api_tokens/tests/_api_tokens_support.py`.
- Produces (test helper, `host/tests/remote_cli/conftest.py`): `LoopBridgeTransport(httpx.BaseTransport)` — wraps `httpx.ASGITransport(app=app)` and runs each request on the test's event loop via `asyncio.run_coroutine_threadsafe(...).result()`; tests call `await asyncio.to_thread(runner.invoke, cli, args)` so the app stays on the loop that owns its DB engine. Fixture `smdev(app, tmp_path, monkeypatch) -> Callable[..., Result]` that sets `XDG_*`, writes an env `local` with URL `http://localhost`, and returns an invoker.

- [ ] **Step 1: Write failing tests**
  - `test_schema_coverage.py::test_every_token_operation_has_one_command` — load `host/cli/smdev_cli/openapi.json`, `cli_operations`, assert `find_collisions == []` and each op reachable under `raw <group> <name>`.
  - `test_schema_coverage.py::test_bundled_schema_matches_app` — `app.openapi()` paths/operationIds equal the bundled file's (so staleness also fails locally).
  - `test_smdev_contract.py`: `test_login_token_stdin_then_whoami` (PAT with `users.view` scope), `test_generated_list_users_json`, `test_generated_update_user_set` (`--set is_active=false` then GET shows inactive), `test_dry_run_sends_nothing` (user unchanged), `test_session_only_route_absent`, `test_tenant_pinned_token_refused_elsewhere` (PAT pinned to tenant A, request with tenant B token key missing → CredentialError hint; and server-side: token for A cannot read B's members), `test_edited_env_url_sends_nothing` (change env URL after login → exit 1, no request reaches the app: assert via a counting wrapper on the transport).
  - `test_import_isolation.py::test_engine_imports_no_server_packages` — subprocess `python -I -c "import simple_module_remote, sys; bad=[m for m in sys.modules if m.split('.')[0] in {'fastapi','sqlmodel','sqlalchemy','starlette'} or (m.startswith('simple_module_') and not m.startswith('simple_module_remote'))]; print(bad); raise SystemExit(bool(bad))"`.
- [ ] **Step 2: Run** `uv run pytest host/tests/remote_cli framework/remote/tests/config/test_import_isolation.py -v` → FAIL.
- [ ] **Step 3: Implement** the package, `make cli-schema`, run it, commit the schema.
- [ ] **Step 4: Run** targeted tests → PASS; then `make gen`, `make lint`, and (once, at the end, after `~/.claude/bin/wait-for-headroom`) `PYTEST_WORKERS=8 make test-py`.
- [ ] **Step 5: Manual check** — after `wait-for-headroom`, start the stack per `.claude/skills/running-the-stack/SKILL.md` on spare ports, create a PAT in the UI, then `uv run smdev env add local --url http://localhost:<port>`, `smdev login --token`, `smdev whoami`, `smdev users list-users`, `smdev doctor`; save the terminal transcript for the PR; stop the stack.
- [ ] **Step 6: Commit** `feat(remote): smdev CLI for the dev host, contract tests and docs`.

---

## Self-review notes

- Spec coverage for PR 1: §1 (Task 2), §2 names/input/output/exit codes/safety (Tasks 4–8), `x-sm-token` (Task 1), §4 env/credentials/protected/doctor/whoami (Tasks 2, 3, 7, 8), §5 bundled schema + status (Task 8; `sync`/live in PR 2), §8 `smdev` (Task 9), §9 tests (each task + Task 9), §10 docs (Task 9). Deferred by design: CSRF/tenant gates/API gaps/audit/`_meta/openapi` (PR 2), browser login (PR 3), curated providers (PR 4; hook stub in Task 8), scaffold + `export --app` (PR 5), upstream (PR 6).
- Deviation from spec, minor: `build_cli` returns a `click.Group` (dynamic commands need click directly); Typer is still used for built-ins.

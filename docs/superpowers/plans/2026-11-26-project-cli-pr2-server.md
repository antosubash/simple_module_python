# Project CLI PR 2 (server side) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every UI action in the dev host is reachable with an API token, so the project CLI (`smdev`) can do what the UI does (#1178).

**Architecture:** Server changes in `simple_module_hosting` and the modules (CSRF for bearer principals, token gates, missing API routes, audit attribution, a permissioned live schema route), a view-route guard that keeps the UI and API in step, and live-schema support in `simple_module_remote`.

**Tech Stack:** FastAPI, SQLModel, Alembic, click (engine), pytest.

**Spec:** `docs/superpowers/specs/2026-11-26-project-cli-design.md` (§§ 5, 6, 7; approved). Issue #1178 and its QA comment are inputs.

## Global Constraints

- Tokens are opt-in per route through `token_guard` gate marks (`GATE_PERMISSION`, `GATE_ALLOW` via `TokenAllowed()`, `GATE_AUTHENTICATED`, `GATE_PAGE`, `GATE_SESSION`). Never weaken `gate_kinds_admit_tokens`.
- A token principal is one with `scopes is not None` (`token_guard.is_token_principal`); `auth_kind` is `pat` or `service` (`api_tokens/credentials/resolver.py`).
- Framework must not import modules (SM009). No magic strings (named constants / `PermissionCatalogue`). 300-line cap per file. ty clean. Area layout and `tests/<area>/` mirroring.
- Each new API endpoint calls the same service/helper as its view route, with the same permission, mutations keep `RequiresCsrf` (token principals skip it since Task 1), and has a token test (PAT with the scope → 2xx, without → 403).
- New migration on the `audit_log` branch: `down_revision = "819d8c5714a5"`, no branch label; update `host/tests/test_migration_graph.py` heads if it pins `819d8c5714a5`.
- After any route change: `make cli-schema` (refresh `host_cli/smdev_cli/openapi.json`) and `make gen-api-types` if a module with `pages/api.generated.ts` changed a response shape.
- Tests: targeted `uv run pytest <path>` while iterating; no full suite inside tasks.

## Rulings (made without asking; the spec is the authority)

- **Cross-tenant platform routes are host-level.** The QA comment saw a PAT pinned to A act on tenant B through routes that take a tenant id (`settings upsert-tenant-setting <B>`, `tenants suspend <B>`, feature-flag tenant overrides). Those routes require platform permissions, are what the platform admin UI uses, and so are the "host-level" row of the matrix, not "tenant-level in another tenant". Tokens keep them, capped by scopes. The "another tenant: no" row covers tenant-level routes acting on the *active* tenant (`/current/*`, content). The guide's matrix says this explicitly. Cost if wrong: a follow-up adding a platform-route opt-out for pinned tokens.
- **Tenant session routes stay session-only, explicitly.** `POST /{id}/switch`, `DELETE /current/membership`, `POST /invitations/accept` get `GATE_SESSION` (a token is pinned to one tenant; switching or accepting has no meaning for it). `GET /` (memberships) and `POST /` (create) get `TokenAllowed()`; create skips `switch_active` for token principals (no session write).
- **CSRF:** `RequiresCsrf` skips when `request.state`/scope principal is a token principal whose `auth_kind` is `pat` or `service`, read from the authenticated principal (`request.scope["user"]` / `request.state.user`, whatever `AuthMiddleware` sets), never from headers. A bearer header with no authenticated token principal still needs the CSRF token.
- **`token_id`:** the api_tokens resolver sets `token_id` on PAT and service principals; `UserContext` gains an optional `token_id: str | None = None`.
- **Audit context:** `simple_module_db` gains ContextVars `current_auth_kind` and `current_token_id` beside `current_user_id`; the auth middleware sets/resets them with it; snapshot records carry them into two nullable columns `auth_kind` (str, ≤16) and `token_id` (str, ≤64).
- **Dashboard doctor:** new `Permissions.DOCTOR = "dashboard.doctor"` mapped to the admin role; API routes use `RequiresPermission(DOCTOR)`; the view keeps `_require_admin`.
- **Sharing revoke by MANAGE:** new `POST /api/sharing/admin/shares/{share_id}/revoke` under `MANAGE` (mirrors the admin view); `DELETE /shares/{id}` keeps `SHARE`. Admin listing `GET /api/sharing/admin/shares` under `VIEW`.
- **Settings test-connection:** `GET /api/settings/modules/testable` (`VIEW`) and `POST /api/settings/modules/{package}/test-connection` (`EDIT`, `RateLimit("10/minute", key="user")`), both through one helper extracted from the view.
- **Users:** `GET /api/admin/users/roles`, `GET /api/admin/users/{user_id}`, `GET /api/admin/users/{user_id}/linked-sign-ins`, `DELETE /api/admin/users/{user_id}/linked-sign-ins/{link_id}`, all `MANAGE`, `/roles` declared before `/{user_id}`.
- **`/api/_meta/openapi`:** permission `host.openapi.read` registered by hosting itself (a small hosting permission catalogue registered before modules), mapped to the admin role; `TokenAllowed` is implied by `RequiresPermission`; excluded from the schema it serves; never in the public-route registry; `Cache-Control: private, no-cache`; weak ETag over the schema bytes; `If-None-Match` → 304.
- **Guard marker:** `api_equivalent(method, path)` and `api_exempt(reason)` in `simple_module_hosting.auth.api_equivalent`, each returning a no-op dependency carrying the declaration as an attribute; used as `dependencies=[Depends(api_equivalent("PUT", "/api/…"))]`. Exempt classes: logout, login/OAuth, self-account, token management, setup wizard, locale switch.

## Review Focus

1. A cookie session without `X-CSRF-Token` on a `RequiresCsrf` route must still get 403, including when it also sends an `Authorization: Bearer junk` header.
2. A PAT pinned to tenant A must get 403/404 on tenant-level (`/current/*`) routes when `--tenant B`/`X-Tenant` says B.
3. `/api/_meta/openapi` with `openapi_public=True` and no auth must still answer 401; a PAT without `host.openapi.read` must get 403.
4. Token-created tenant must not write a session cookie (`Set-Cookie` absent on the response).
5. The guard test must fail when a non-GET view route has no declaration, or when its declared target refuses tokens or does not exist.

---

### Task 1: CSRF for token principals + `token_id` on principals

**Files:** `framework/hosting/simple_module_hosting/auth/csrf.py`; `modules/api_tokens/api_tokens/credentials/resolver.py`; `UserContext` in `modules/auth/auth/contracts/` (optional `token_id`); tests under `framework/hosting/tests/auth/` and `modules/api_tokens/tests/credentials/`.

- [ ] Tests: PAT + `RequiresCsrf` mutation → 2xx; service key → 2xx; cookie session without token → 403; cookie session + junk bearer → 403; principal `token_id` equals the token row id for PAT and service.
- [ ] Implement the skip (read the authenticated principal, check `is_token_principal` and `auth_kind in {pat, service}`), set `token_id` in the resolver.
- [ ] Commit `feat(cli-token-reach): CSRF skip for token principals`.

### Task 2: Tenant gates

**Files:** `modules/tenants/tenants/web/endpoints/api.py`; tests in `modules/tenants/tests/web/`.

- [ ] Tests: PAT lists memberships (200, only its owner's); PAT with `tenants.platform.manage` creates a tenant (201, no `Set-Cookie`); PAT without it and self-service off → 403; switch/accept/leave with PAT → 403 `token_not_allowed`; session behaviour unchanged.
- [ ] Implement per Rulings. Commit.

### Task 3: Audit attribution

**Files:** `framework/db/simple_module_db/models/listeners.py` (ContextVars), `framework/db/simple_module_db/auditing/{audit,_bulk_audit_records}.py`, `modules/auth/auth/web/middleware.py` (set/reset), `modules/tenants/tenants/resolution/token_tenant.py` and `auth/_anonymous.py` (reset alongside `current_user_id`), `modules/audit_log/audit_log/{models.py,core/capture.py,entries/service.py}` and its read DTO/API, new migration `host/migrations/versions/<rev>_audit_entry_auth_kind_token_id.py`.

- [ ] Tests: a PAT mutation writes an audit row with `auth_kind="pat"` and `token_id=<id>`; a session mutation writes `auth_kind="session"` (or null if the session path has no kind — pick `session`), `token_id` null; bulk statements carry both; audit API returns both fields.
- [ ] Implement, write the migration (nullable columns, downgrade drops), run `uv run pytest host/tests/test_migration_graph.py`. Commit.

### Task 4: Settings test-connection API

**Files:** `modules/settings/settings/web/endpoints/module_api.py`, a helper beside `module_settings/props.py`, views.py uses the helper; tests in `modules/settings/tests/`.

- [ ] Tests: testable list via PAT (`settings.view`) matches the view prop; test-connection via PAT (`settings.edit`) returns the same payload as the view; 11th call in a minute → 429; unknown package → 404.
- [ ] Implement per Rulings. Commit.

### Task 5: Users API gaps

**Files:** `modules/users/users/admin/api.py` (split into a new file if it passes 300 lines), service reuse (`get_list_item`, `linked_sign_ins_for`, `unlink_sign_in`, `get_roles_cache`); tests in `modules/users/tests/admin/`.

- [ ] Tests: each route with a `users.manage` PAT → 2xx and shapes matching the view props; without scope → 403; unlink of another user's link → 404; unlink keeps the view's safety rules (e.g. last sign-in method) identical.
- [ ] Implement. Commit.

### Task 6: Dashboard doctor + sharing admin API

**Files:** `modules/dashboard/dashboard/{core/constants.py,module.py,web/endpoints/api.py}`; `modules/sharing/sharing/web/endpoints/` (new admin api file); tests.

- [ ] Tests: doctor results/rerun with a `dashboard.doctor` PAT → 200, without → 403, admin role maps the new permission; sharing admin listing (paginated, same presenter as the view) with `sharing.view` PAT; revoke with a `sharing.manage`-only PAT → 2xx.
- [ ] Implement. Commit.

### Task 7: `GET /api/_meta/openapi`

**Files:** `framework/hosting/simple_module_hosting/auth/` or `boot/` (new `meta_openapi.py`), hosting permission catalogue + registration in `boot/_registrations.py`, `boot/_openapi.py` exclusion; tests in `framework/hosting/tests/`.

- [ ] Tests: Review Focus 3; PAT with `host.openapi.read` → 200 JSON equal to `app.openapi()` minus this path; `Cache-Control` contains `private`; ETag weak; `If-None-Match` → 304; the route is absent from the served schema.
- [ ] Implement. Commit.

### Task 8: Engine live schema

**Files:** `framework/remote/simple_module_remote/config/paths.py` (`cache_dir(cli)`), `schema/` (new `cache.py`: read/write `<cache>/<env>/openapi.json` + `meta.json` with origin, fingerprint, fetched_at), `commands/root.py` (`--schema bundled|live`, default: live cache for the env when present and its origin matches, else bundled), `commands/schema_cmd.py` (`schema sync`, `schema status` shows source/version/fingerprint/age), 404/422 hint when cache missing/stale; `commands/doctor_cmd.py` source line; tests in `framework/remote/tests/`; docs `docs/guide/project-cli.md`, `docs/framework/remote-cli.md`.

- [ ] Tests: sync writes cache 0600 in a 0700 dir; origin change invalidates; `--schema live` without cache → usage error with a `schema sync` hint; tree built from the live cache includes a route absent from bundled; 304 keeps the cache; token never written to cache files.
- [ ] Implement. Regenerate the bundled schema (`make cli-schema`). Commit.

### Task 9: View-route guard

**Files:** new `framework/hosting/simple_module_hosting/auth/api_equivalent.py`; declarations on every non-GET view route in `modules/*` and `framework/hosting` (setup wizard, i18n); `host/tests/test_view_api_equivalents.py`; scaffold `framework/cli/simple_module_cli/templates/module/__PACKAGE__/web/endpoints/views.py.tpl` (+ any scaffold test); `docs/module-authoring.md`; `skills/simple-module-conventions/`.

- [ ] Test (host): builds the app once, walks routes outside `/api/` with a non-GET method, requires exactly one declaration, resolves each `api_equivalent` target against app routes (method + path template) and asserts `route_admits_tokens`; fails listing every offender. Plus unit tests of the markers.
- [ ] Declare every route. Where no API equivalent exists (e.g. invites bulk/resend, feature-flag toggle/clear, permissions role/user update), add the API route under the same permission and service, with a token test, in this task.
- [ ] Scaffold POSTs declare their API equivalents; scaffolded module still passes its tests. Commit.

### Task 10: Credential matrix, docs, changelog, upstream

**Files:** `host/tests/remote_cli/test_credential_matrix.py`; `docs/guide/project-cli.md` (matrix section), `docs/framework/remote-cli.md` (`api_equivalent`), `CHANGELOG.md` (Unreleased, cite #1178, the migration rev), `skills/simple-module-cli`.

- [ ] Matrix tests through the CLI runner/LoopBridgeTransport: platform-admin PAT (host-level ok, scope-capped), tenant-admin PAT (tenant-level in T ok, host-level 403), service key (content/settings per roles; members/invitations 403), tenant-level in another tenant 403 for all; PAT mutation on a `RequiresCsrf` route 2xx.
- [ ] Docs + changelog. File the upstream `smpy_modules` issue (pagebuilder reader gate, CSRF, guard adoption) if smpy_modules#478 does not already cover it; otherwise comment there.
- [ ] Commit.

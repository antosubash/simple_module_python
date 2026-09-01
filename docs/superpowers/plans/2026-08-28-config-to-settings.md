# Config-to-Settings + Setup Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce the operator-facing env surface to a Postgres URL, a Redis URL and an optional bootstrap admin, and give installs with no administrator a browser setup wizard that tests its own connections.

**Architecture:** A synchronous pre-app config read at the top of `create_app` merges DB-stored host overrides under env values before Phase 1, closing the gap that makes DB-backed host settings inert today. On that foundation, nine `BootstrapSettings` fields move to DB-backed, Redis collapses to one env var, the secret key becomes self-generating, and a new `SetupRegistry` gates the app behind a wizard until every required setup step reports complete.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, pydantic-settings, Alembic, Celery, Inertia.js + React 19, Tailwind 4.

**Spec:** `docs/superpowers/specs/2026-08-28-config-to-settings-design.md`

## Global Constraints

- **Precedence is always env → DB → default.** Env must keep winning. Inverting this silently changes behaviour for existing production deployments and nothing errors.
- **300-line cap** on every `.py`/`.ts`/`.tsx` file, enforced by `scripts/check_file_size.py`. Split by responsibility if approached.
- **SQLModel only** for models and DTOs. No Pydantic `BaseModel`, no SQLAlchemy `DeclarativeBase`.
- **SM009:** nothing under `framework/*` may statically import a plugin package name. Use `importlib` for runtime resolution, following `register_host_settings` in `_phase_helpers.py`.
- **Never fail the boot** on an unreachable or unmigrated database. The wizard is what repairs those states; failing the boot makes it unreachable.
- Test files need globally-unique basenames — no `__init__.py` in any `tests/` dir. Prefix module test files with the module name.
- Run `make lint` and `make test` before each commit.

---

### Task 1: Pre-app config read

Makes DB-stored host overrides visible to Phase 1 of `create_app`. Prerequisite for every later task; also fixes the standing bug where `i18n_*` and `multi_tenant` edits in the admin UI do nothing.

**Files:**
- Create: `framework/hosting/simple_module_hosting/_preapp_config.py`
- Modify: `framework/hosting/simple_module_hosting/app_builder.py` (top of `create_app`, ~line 105)
- Test: `framework/hosting/tests/test_preapp_config.py`

**Interfaces:**
- Produces: `load_host_overrides(database_url: str) -> dict[str, str]` returning `{field_name: raw_value}`, and `merge_host_settings(bootstrap: BootstrapSettings) -> Settings`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_returns_empty_when_table_missing(tmp_path):
    """An unmigrated DB must fall back to defaults, not raise."""
    url = f"sqlite+aiosqlite:///{tmp_path}/empty.db"
    assert load_host_overrides(url) == {}


async def test_returns_empty_when_db_unreachable():
    """A wrong host must not fail the boot — the wizard reports it instead."""
    url = "postgresql+asyncpg://nope:nope@127.0.0.1:1/nothing"
    assert load_host_overrides(url) == {}


async def test_reads_host_scoped_overrides(db_session, settings):
    await seed_setting(db_session, key="host.log_level", value="DEBUG")
    await seed_setting(db_session, key="users.smtp_host", value="mail.example.com")
    out = load_host_overrides(settings.database_url)
    assert out == {"log_level": "DEBUG"}  # 'users.' rows excluded


def test_env_beats_db_override(monkeypatch, seeded_db_url):
    monkeypatch.setenv("SM_LOG_LEVEL", "WARNING")
    merged = merge_host_settings(BootstrapSettings(_env_file=None))
    assert merged.log_level == "WARNING"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest framework/hosting/tests/test_preapp_config.py -v`
Expected: FAIL, `ImportError: cannot import name 'load_host_overrides'`

- [ ] **Step 3: Implement**

Read rows from `settings_setting` at SYSTEM scope with keys prefixed `host.`. Run in a dedicated thread with its own loop so it is safe whether or not a loop is already running:

```python
def load_host_overrides(database_url: str) -> dict[str, str]:
    """Read host settings overrides before the app exists.

    Returns {} on any failure — unreachable DB, missing table, empty table.
    All three are normal first-boot states that the setup wizard repairs, so
    none of them may fail the boot.
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(_read(database_url))).result()
```

`_read` opens an engine, selects `key, value` where `scope='system'` and `key LIKE 'host.%'`, strips the prefix, and skips nested keys (a remaining `.`). Wrap in `except Exception` — a missing table raises differently on SQLite vs Postgres and the recovery is identical either way. Log at DEBUG, not WARNING: this returning empty is the expected first-boot path, and a warning here would cry wolf on every fresh install.

- [ ] **Step 4: Wire into `create_app`**

Replace `settings = settings or Settings()` with a merge that applies DB overrides only to fields the env did not set. Detect env-set fields via `BootstrapSettings.model_fields_set` plus a check against `os.environ` for `SM_`-prefixed names.

- [ ] **Step 5: Run the full suite**

Run: `make test-py`
Expected: PASS, including existing `test_strict_discovery_wiring.py`

- [ ] **Step 6: Commit**

```bash
git add framework/hosting/simple_module_hosting/_preapp_config.py \
        framework/hosting/simple_module_hosting/app_builder.py \
        framework/hosting/tests/test_preapp_config.py
git commit -m "feat(hosting): read DB host overrides before create_app Phase 1"
```

---

### Task 2: Move nine fields to DB-backed

**Files:**
- Modify: `framework/hosting/simple_module_hosting/bootstrap_settings.py`, `host_settings.py`
- Test: `framework/hosting/tests/test_host_settings_fields.py`

**Interfaces:**
- Consumes: `merge_host_settings` from Task 1.
- Produces: `HostSettings` gains `trusted_proxy`, `log_level`, `log_format`, `auth_provider`, `auth_public_paths`, `db_pool_size`, `db_max_overflow`, `db_pool_pre_ping`, `db_pool_recycle`.

- [ ] **Step 1: Write the failing test**

```python
def test_pool_fields_marked_requires_restart():
    """The engine is built once at boot, so the UI must say so."""
    for name in ("db_pool_size", "db_max_overflow", "db_pool_pre_ping", "db_pool_recycle"):
        extra = HostSettings.model_fields[name].json_schema_extra
        assert extra["requires_restart"] is True


def test_trusted_proxy_still_normalizes_blank():
    assert HostSettings(trusted_proxy="  ").trusted_proxy is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest framework/hosting/tests/test_host_settings_fields.py -v`
Expected: FAIL, `KeyError: 'db_pool_size'`

- [ ] **Step 3: Move the fields**

Move each field and its validators from `BootstrapSettings` to `HostSettings`. Carry `_normalize_trusted_proxy` and `_normalize_auth_provider` across unchanged — the trusted-proxy one guards GH #223 and the auth-provider one keeps `make doctor` agreeing with the host about the active provider. Tag the four pool fields with `json_schema_extra={"requires_restart": True, "group": "Database"}`.

`database_url` and the `_absolutize_sqlite_url` logic stay in `BootstrapSettings` — they are what opens the DB.

- [ ] **Step 4: Run tests**

Run: `make test-py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(settings): move proxy, logging, auth and pool knobs to DB-backed"
```

---

### Task 3: `SM_REDIS_URL` consolidation

**Files:**
- Modify: `modules/background_tasks/background_tasks/settings.py`, `constants.py`
- Test: `modules/background_tasks/tests/test_bg_redis_url.py`

**Interfaces:**
- Produces: `SM_REDIS_URL` seeds both `broker_url` and `result_backend`.

- [ ] **Step 1: Write the failing tests**

```python
def test_redis_url_seeds_both(monkeypatch):
    monkeypatch.setenv("SM_REDIS_URL", "redis://cache:6379/2")
    s = BackgroundTasksSettings()
    assert s.broker_url == "redis://cache:6379/2"
    assert s.result_backend == "redis://cache:6379/2"


def test_legacy_broker_var_still_works(monkeypatch, caplog):
    """smpy_gis, smpy_saas, laco_wiki_python and nodes-k8s all set this."""
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "redis://old:6379/4")
    s = BackgroundTasksSettings()
    assert s.broker_url == "redis://old:6379/4"
    assert "SM_BG_TASKS_BROKER_URL is deprecated" in caplog.text


def test_legacy_var_beats_redis_url(monkeypatch):
    """A deployment that set both meant the specific one."""
    monkeypatch.setenv("SM_REDIS_URL", "redis://new:6379/0")
    monkeypatch.setenv("SM_BG_TASKS_BROKER_URL", "redis://old:6379/4")
    assert BackgroundTasksSettings().broker_url == "redis://old:6379/4"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest modules/background_tasks/tests/test_bg_redis_url.py -v`
Expected: FAIL on the first assertion of `test_redis_url_seeds_both`

- [ ] **Step 3: Implement**

Change both `default_factory` callables to check, in order: the legacy specific var, then `SM_REDIS_URL`, then the existing constant default. Emit `logger.warning` once per legacy var when it is the one that wins. Celery namespaces result keys as `celery-task-meta-*`, so sharing one Redis database between broker and backend is safe and is what upstream's quickstart does.

- [ ] **Step 4: Run tests**

Run: `uv run pytest modules/background_tasks/ -v`
Expected: PASS, including the existing `test_bg_settings_env.py`

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(background_tasks): single SM_REDIS_URL, legacy vars deprecated"
```

---

### Task 4: Optional self-generating secret key

**Files:**
- Modify: `framework/hosting/simple_module_hosting/bootstrap_settings.py`, `_preapp_config.py`
- Test: `framework/hosting/tests/test_secret_key_bootstrap.py`

**Interfaces:**
- Produces: `ensure_secret_key(database_url: str) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
def test_generates_and_persists_when_absent(fresh_db_url):
    first = ensure_secret_key(fresh_db_url)
    assert len(first) >= 40
    assert ensure_secret_key(fresh_db_url) == first  # stable across boots


def test_concurrent_boots_converge(fresh_db_url):
    """Two workers booting together must not mint different keys — that
    would invalidate each other's sessions intermittently."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = set(pool.map(lambda _: ensure_secret_key(fresh_db_url), range(8)))
    assert len(keys) == 1


def test_env_wins(monkeypatch, fresh_db_url):
    monkeypatch.setenv("SM_SECRET_KEY", "explicit")
    assert ensure_secret_key(fresh_db_url) == "explicit"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest framework/hosting/tests/test_secret_key_bootstrap.py -v`
Expected: FAIL, `ImportError`

- [ ] **Step 3: Implement**

`secrets.token_urlsafe(48)`, then `INSERT ... ON CONFLICT DO NOTHING` against `settings_setting` with key `host.secret_key`, then **re-read and return whatever actually landed**. Returning the locally generated value instead of the re-read is the bug this test exists to catch.

Keep the placeholder rejection in production, but only when a key is explicitly set to `change-me-in-production` — an absent key is now valid.

- [ ] **Step 4: Run tests**

Run: `make test-py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(hosting): generate and persist a secret key when unset"
```

---

### Task 5: Database and Redis health checks

Independently useful — they also feed `/health/ready`.

**Files:**
- Modify: `framework/hosting/simple_module_hosting/_phase_helpers.py`, `modules/background_tasks/background_tasks/module.py`
- Test: `framework/hosting/tests/test_db_health_check.py`, `modules/background_tasks/tests/test_bg_redis_health.py`

**Interfaces:**
- Consumes: `HealthRegistry.add(HealthCheck(name, check, probe=))` from `simple_module_core.health`.
- Produces: checks named `"database"` and `"redis"`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_database_check_healthy(app):
    result = await run_named_check(app, "database")
    assert result.status is HealthStatus.HEALTHY


async def test_database_check_reports_reason(broken_db_app):
    result = await run_named_check(broken_db_app, "database")
    assert result.status is HealthStatus.UNHEALTHY
    # The reason is the point: refused and auth-failed need different fixes.
    assert "connect" in (result.detail or "").lower()


async def test_redis_check_reports_refused(monkeypatch, app):
    monkeypatch.setenv("SM_REDIS_URL", "redis://127.0.0.1:1/0")
    result = await run_named_check(app, "redis")
    assert result.status is HealthStatus.UNHEALTHY
    assert result.detail
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest framework/hosting/tests/test_db_health_check.py -v`
Expected: FAIL, no check named "database"

- [ ] **Step 3: Implement**

Database check: `SELECT 1` plus migration revision status from the existing `check_migrations`. `probe=True` — it is a real readiness signal.

Redis check: broker `PING` plus result-backend reachability. `probe=True` for the same reason. Catch the connection exception and put `str(exc)` in `detail` — never swallow it to a bare "unhealthy", since the whole value of the wizard's connection step is telling refused apart from auth-failed.

- [ ] **Step 4: Run tests**

Run: `make test-py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(health): database and redis readiness checks"
```

---

### Task 6: SetupRegistry, hook, and middleware

**Files:**
- Create: `framework/core/simple_module_core/setup_steps.py`, `framework/hosting/simple_module_hosting/setup_gate.py`
- Modify: `framework/core/simple_module_core/module.py`, `framework/hosting/simple_module_hosting/_registrations.py`, `app_builder.py`, `modules/users/users/module.py`
- Test: `framework/hosting/tests/test_setup_gate.py`, `modules/users/tests/test_users_setup_step.py`

**Interfaces:**
- Produces: `SetupStep(id, title, description, is_complete)`, `SetupRegistry.add(step)`, `ModuleBase.register_setup_steps(registry)`, `SetupMiddleware`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_redirects_to_setup_when_no_admin(client_no_admin):
    resp = await client_no_admin.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/setup"


async def test_releases_once_admin_exists(authenticated_client):
    resp = await authenticated_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200


async def test_never_engages_under_keycloak(keycloak_app_client):
    """Keycloak installs have no local admin table. A hardcoded superuser
    count would lock them out of their own app permanently."""
    resp = await keycloak_app_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code != 302


async def test_static_and_health_stay_reachable(client_no_admin):
    for path in ("/health/ready", "/static/does-not-exist.css"):
        resp = await client_no_admin.get(path, follow_redirects=False)
        assert resp.status_code != 302
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest framework/hosting/tests/test_setup_gate.py -v`
Expected: FAIL, 200 instead of 302

- [ ] **Step 3: Implement the registry**

Mirror `PublicRouteRegistry` in structure and docstring style. `SetupStep.is_complete` is an async callable taking a session. Add the no-op `register_setup_steps` hook to `ModuleBase` alongside `register_public_routes`, and call it from `_registrations.py` in the same loop.

- [ ] **Step 4: Register the steps**

`users` registers *"an administrator exists"* — counting superusers. Host registers *"database migrated"*. Keycloak registers nothing, which is what makes the gate skip it.

- [ ] **Step 5: Implement the middleware**

Recompute completion per request rather than caching a one-way flag: an install that loses its admins is then recoverable through the browser instead of needing shell access. Exempt `/setup`, `/static`, `/health`. Install it inside `InertiaCache` so its redirect is not cached.

- [ ] **Step 6: Run tests**

Run: `make test-py`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git commit -am "feat(setup): SetupRegistry, register_setup_steps hook, and gate middleware"
```

---

### Task 7: Wizard pages

**Files:**
- Create: `host/client_app/pages/Setup/Connections.tsx`, `Migrations.tsx`, `Administrator.tsx`, `SiteBasics.tsx`, `host/routes_setup.py`
- Modify: `host/routes.py`
- Test: `framework/hosting/tests/test_setup_routes.py`, `tests/e2e/test_setup_wizard.py`

**Interfaces:**
- Consumes: health checks (Task 5), `SetupRegistry` (Task 6), `users.bootstrap.create_admin`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_setup_reachable_without_auth(client_no_admin):
    assert (await client_no_admin.get("/setup")).status_code == 200


async def test_create_admin_completes_setup(client_no_admin):
    resp = await client_no_admin.post(
        "/setup/administrator",
        json={
            "email": "admin@example.com",
            "password": "hunter2hunter2",
        },
    )
    assert resp.status_code == 200
    after = await client_no_admin.get("/dashboard", follow_redirects=False)
    assert after.status_code != 302


async def test_setup_closes_after_completion(authenticated_client):
    """Once an admin exists the wizard must stop answering — especially
    /setup/migrations, which can run Alembic."""
    assert (await authenticated_client.post("/setup/migrations")).status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest framework/hosting/tests/test_setup_routes.py -v`
Expected: FAIL, 404 on `/setup`

- [ ] **Step 3: Implement the routes**

Four steps, in order: Connections (live pass/fail via the Task 5 health checks, re-testable without a reload, showing the failure reason), Migrations (an "Apply migrations" button when `check_migrations` reports behind-head), Administrator (delegating to `users.bootstrap.create_admin`), Site basics (name, locale, auth provider → DB-backed host settings).

Every `/setup/*` route must 404 once setup is complete. This is what bounds the Alembic-over-HTTP exposure noted in the spec — verify with `test_setup_closes_after_completion`, not by inspection.

- [ ] **Step 4: Build the pages**

Follow existing host page structure. Reuse the `TestConnectionButton` result-rendering shape from `modules/settings/settings/pages/components/`. All user-visible strings go through `useT()` with keys in `host/locales/en.json`, or `make ci-check-untranslated` fails CI. Regenerate `keys.generated.ts` and keep every installed module's namespace in the diff.

- [ ] **Step 5: Run tests**

Run: `make test` then `make lint`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git commit -am "feat(setup): first-run wizard with connection testing"
```

---

### Task 8: Documentation

**Files:**
- Modify: `.env.example`, `CLAUDE.md`, `docs/framework-conventions.md`, `docs/module-authoring.md`

- [ ] **Step 1: Rewrite `.env.example`**

Reduce to the three variables an operator sets — `SM_DATABASE_URL`, `SM_REDIS_URL`, optional `SM_USERS_BOOTSTRAP_*` — plus a short note that everything else is configured in the app and that leaving the bootstrap unset opens the setup wizard.

- [ ] **Step 2: Update `CLAUDE.md`**

Correct the middleware pipeline line to include `SetupGate`. Document `register_setup_steps` in the lifecycle-hooks list. Note that host settings are now genuinely DB-backed — the existing text describing them is now wrong in the opposite direction.

- [ ] **Step 3: Document the hook**

Add `register_setup_steps` to `docs/module-authoring.md` with a worked example, matching how `register_public_routes` is documented.

- [ ] **Step 4: Verify and commit**

Run: `make doctor && make lint`
Expected: no new diagnostics

```bash
git commit -am "docs: env surface, setup wizard, register_setup_steps hook"
```

---

## Self-Review

**Spec coverage:** Pre-app read → Task 1. Nine fields → Task 2. Redis → Task 3. Secret key → Task 4. Health checks → Task 5. Gate → Task 6. Wizard incl. migrations step → Task 7. Docs → Task 8. All eight sequencing items covered.

**Deferred deliberately:** the spec's `test_setup_wizard.py` E2E is listed in Task 7 but is the most likely thing to slip, since it needs a live server. If it does, the unit-level `test_setup_routes.py` still gates the behaviour.

**Type consistency:** `load_host_overrides` / `merge_host_settings` (Task 1) are consumed by Task 2 and Task 4 under those exact names. `SetupStep` / `SetupRegistry.add` (Task 6) are consumed by Task 7 under those names. Health checks are named `"database"` and `"redis"` in both Task 5 and Task 7.

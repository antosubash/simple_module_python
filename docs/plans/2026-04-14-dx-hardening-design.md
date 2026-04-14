# DX Hardening — Design Document

**Goal:** Close the DX papercuts and pitfalls deferred from the 2026-04-14 framework review — behavior changes that need design decisions, not drive-by fixes.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy async, Starlette, UV workspace

**Input:** Review findings from `claude/review-framework-dx-FtWsy` that were consciously deferred (see the review summary at the end of that branch's commit log).

---

## Section 1: Scope

Nine items, grouped by theme. Each has a problem statement, the decision to make, and the chosen approach. The implementation plan in `2026-04-14-dx-hardening.md` maps each decision to a task.

| # | Theme | Item |
|---|---|---|
| 1 | Runtime safety | `get_db` commits on every successful request, including read-only GETs |
| 2 | Runtime safety | `discover_modules()` silently swallows entry-point load failures in production |
| 3 | Runtime safety | `ModuleBase.meta` is optional at runtime; only caught by dev diagnostics |
| 4 | Multi-tenancy | `TenantMiddleware` runs unconditionally, trusting `X-Tenant-ID` for every request |
| 5 | Routing | `DashboardModule.view_prefix=""` but menu points at `/dashboard` — broken on first boot |
| 6 | Docs | Middleware peer ordering is unspecified |
| 7 | Docs | Empty `README.md` |
| 8 | Nits | `_PROJECT_ROOT = parents[3]` is fragile; `all_module_bases` is an unbounded list; `print_diagnostics` writes to stdout; stray `modules/products/products/validation.ts` |

---

## Section 2: Runtime-safety items

### 2.1 `get_db` auto-commit on every request

**Problem.** `framework/db/simple_module_db/deps.py:26-42` yields a session and calls `await session.commit()` in the success path. Every successful HTTP request — including read-only `GET` endpoints — issues a SQL `COMMIT`. The waste is small per-request, but:

- It appears in `pg_stat_activity` / `pg_stat_statements` and muddies query profiling.
- Long-running read-only endpoints hold a write-capable transaction for their entire duration.
- It hides a genuine ergonomic question: who commits, the service layer or the dependency?

**Decision.** Keep the "auto-commit on success" contract — it is a widely-used pattern and changing it would ripple through every endpoint. But *skip the commit when the session has no pending work*.

**Approach.** Check `session.in_transaction()` and `session.dirty / session.new / session.deleted` before committing. A pure-read session will have an implicit begin but no dirty state — we `rollback()` (cheap, releases the transaction) instead of `commit()`. Writers still get the existing commit-on-success behaviour.

Pseudocode:

```python
async with factory() as session:
    try:
        yield session
        has_pending = bool(session.new or session.dirty or session.deleted)
        if has_pending:
            await session.commit()
        else:
            await session.rollback()
    except Exception:
        await session.rollback()
        raise
```

Rejected alternatives:
- *Split into `get_db_read` / `get_db_write`*: forces every endpoint to pick a side; API churn across every module; does not help when a "read" endpoint occasionally writes an audit log.
- *Leave as-is and document the behaviour*: does not address the profiling cost.

### 2.2 `discover_modules` swallowing load errors

**Problem.** `framework/core/simple_module_core/discovery.py:38-39` catches `Exception` on entry-point load failure and logs it. In dev this is helpful; in prod it can ship a partial app whose missing module silently breaks a feature.

**Decision.** Gate the swallow on `Settings.is_development`. Production must fail hard.

**Approach.** Since `discover_modules()` is called from `app_builder.create_app()` which already has `settings` in scope, thread a `strict: bool = False` kwarg through and set `strict=not settings.is_development` at the call site. The function re-raises the first load error with contextual framing when `strict=True`; unchanged behaviour otherwise.

`host/migrations/env.py` and `conftest.py` also call `discover_modules()` — both run in dev contexts, so the default `strict=False` is correct there.

### 2.3 Missing `meta` attribute at runtime

**Problem.** `ModuleBase.meta` is typed `ModuleMeta` but never enforced. `SM001` catches it at dev diagnostic time only. In prod, the first attribute access raises `AttributeError` during `app_builder` phase 4, producing a confusing stack trace.

**Decision.** Enforce structurally, in production too, with a clear error message.

**Approach.** Add `meta` to `discover_modules()`'s validation pass: after `instance = module_cls()`, check `isinstance(getattr(instance, "meta", None), ModuleMeta)`. If missing, raise `ModuleError(f"Module {module_cls.__qualname__} is missing 'meta = ModuleMeta(...)'")`. The error fires before the app is built, so the user sees it at boot, not during request handling.

Keep the existing `SM001` diagnostic — it still helps dev users catch the issue earlier (during diagnostics), but the production guard is the safety net.

---

## Section 3: Multi-tenancy

### 3.1 Unconditional `TenantMiddleware` + header-based tenant ID

**Problem.** `framework/hosting/simple_module_hosting/app_builder.py:225` installs `TenantMiddleware` always. Two concerns:

1. Single-tenant deployments pay for the middleware and, worse, any request can spoof `X-Tenant-ID` and change query semantics.
2. Even in multi-tenant mode, the header source is acceptable for authenticated internal clients but dangerous as the *primary* tenant source for untrusted callers.

**Decision.** Make tenancy opt-in via settings and scope header-based resolution to a settings-controlled allowlist. Production deployments must declare "I am multi-tenant" and which header (if any) is trusted.

**Approach.** Add to `Settings`:

```python
multi_tenant: bool = False
tenant_header: str = ""            # empty → header source disabled
```

In `app_builder`:

```python
if settings.multi_tenant:
    app.add_middleware(TenantMiddleware, header=settings.tenant_header or None)
```

Update `TenantMiddleware.__init__` to take an optional `header` kwarg; when `None`, resolve tenant only from `request.state.user.tenant_id`. The auth-token-claim path remains the primary, secure source.

Tests that need a header-based tenant fixture pass `multi_tenant=True, tenant_header="X-Tenant-ID"` in the test settings.

### 3.2 Document the security model

Add a short "Multi-tenancy" section to the `README` (covered under Section 4.2) that states:
- Header fallback is a dev/internal convenience.
- Production must authenticate users and carry `tenant_id` in the token.
- With `multi_tenant=False`, queries ignore tenancy entirely.

---

## Section 4: Routing & Docs

### 4.1 Dashboard routing

**Problem.** `modules/dashboard/dashboard/module.py:11-14` sets `view_prefix=""` so view routes mount at `/…`. The menu points at `/dashboard`. The only reason the app appears to work is that `Landing.tsx` / `Home.tsx` are mapped at both `/` and `/dashboard` (if at all).

**Decision.** Give the dashboard an honest `view_prefix="/dashboard"`. Host-level "landing at `/`" is a separate concern; it belongs to the host, not the module.

**Approach.**
1. `DashboardModule.meta.view_prefix = "/dashboard"`.
2. Move `pages/Landing.tsx` out of the dashboard module. The host already has a `host/client_app/pages/` directory (already scanned by `pages.ts`); move `Landing.tsx` there. Define the landing route on a small host-level router (a new `host/routes.py` module mounted from `main.py`, or inline in `create_app` — see task plan).
3. The dashboard keeps `Home.tsx` at `/dashboard`.

This also gives us a clean seam for future "unauthenticated landing" behaviour that should not live inside a plugin.

### 4.2 Middleware ordering & README

**Middleware ordering.** Add a section to `docs/superpowers/specs/` (or a new `docs/framework-conventions.md`) that documents:

- `add_middleware` is LIFO (last added runs first).
- The framework pipeline order: `CorrelationId → RequestLogging → SecurityHeaders → Session → <modules> → Tenant → InertiaLayoutData → app`.
- For two modules at the same dependency tier, *topological sort order determines registration order*, and "last added runs first" means the last module in sort order wraps its middleware *outermost*. Module authors who rely on relative ordering must express it via `ModuleMeta.depends_on`.

**README.** Write a one-page quickstart:
- Install (`uv sync --all-packages && npm install`).
- Env (`cp .env.example .env`).
- Run (`make dev`).
- Scaffold a module (`make new-module name=orders`).
- Test (`make test`), diagnostics (`make doctor`), migrations (`make migrate`).
- Link to `docs/plans/` for architecture, `docs/framework-conventions.md` for conventions.

---

## Section 5: Nits

### 5.1 `_PROJECT_ROOT = parents[3]`

`framework/hosting/simple_module_hosting/app_builder.py:52` computes the repo root by counting `..` four times. Fragile under `pip install` / wheel layout; works only because uv links the workspace packages in place.

**Approach.** Replace with an env-var override with a fallback: `os.environ.get("SM_PROJECT_ROOT", str(Path(__file__).resolve().parents[3]))`. `host/main.py` sets `SM_PROJECT_ROOT` to `Path(__file__).resolve().parent.parent` on import. This keeps the dev-loop working and makes the contract explicit.

### 5.2 `all_module_bases` is an unbounded list

`framework/db/simple_module_db/base.py:23` appends every `create_module_base(...)` result. In test suites that re-import modules (parametrised tests, plugin loaders), the list grows with duplicates. `_base_cache` protects against identity, but iteration over `all_module_bases` double-visits the same base.

**Approach.** Replace the list with a dict keyed by `cache_key`; expose `all_module_bases` as a list-valued view (`list(_bases_by_key.values())`) to preserve the public API.

### 5.3 `print_diagnostics` writes to stdout

`framework/core/simple_module_core/diagnostics.py:390-394` uses `print(...)` — docstring said "stderr". This matters when piping `make doctor` output, and when a CI runner classifies stdout vs stderr.

**Approach.** `print(..., file=sys.stderr)`.

### 5.4 Stray `modules/products/products/validation.ts`

A lone TypeScript file inside a Python package. Either it's leftover scaffolding or it's meant to be imported by pages. Investigate first, then either move it under `pages/` or delete it.

---

## Section 6: Out of scope

- Writing a full "module authoring" guide — that deserves its own plan.
- Redesigning `_check_settings_registration` beyond the exact-match fix already shipped.
- Rewriting permissions beyond the `DEFAULT_ROLE_PERMISSIONS` decoupling already shipped.
- Making `EventBus` persistent/transactional.

---

## Section 7: Acceptance

The plan is complete when:

- `make test` passes (currently 231 tests; new tests add for the behaviours above).
- `make lint` passes.
- `make doctor` still runs and still exits 0 on a clean tree.
- A fresh `make new-module name=widgets` → `make migrate` → `make dev` boots without warnings and shows the new module in the sidebar.
- A PostgreSQL deployment (`SM_DATABASE_URL=postgresql+asyncpg://…`) loads models with schema isolation and no code change.
- Setting `SM_MULTI_TENANT=false` removes the tenant middleware from the stack (assertable in a test).
- Missing `meta` raises a structured error at app boot, not during a request.

# Issue batch #413–#424 — design

**Date:** 2026-10-09 · **Status:** approved · **Branch:** `feat/issue-batch-413-424` · **One combined PR**

Twelve open issues filed on 2026-10-08, fixed together. #317 (re-verify the 28
hi-fi screens) is out: it needs the external design file, which neither the repo
nor this session can read.

## Scope

| # | Area | One-line fix |
|---|---|---|
| 413 | background_tasks | Admin page 500s on Postgres: four timestamp columns declared naive in the model |
| 414 | ui | Sign-in aside footer token below WCAG AA |
| 415 | i18n | Host override layer for module copy |
| 416 | auth | Only top-level navigations record the post-login target |
| 417 | db | Tenant filter turns an outer join into an inner join |
| 418 | hosting | Public tenancy API: mode, single-tenant id, `require_tenant`, complete `Vary` |
| 419 | hosting | gen-pages `@source` reaches subdirectories of wheel modules |
| 420 | ui | Brand foreground ink follows the brand colour; sidebar active row uses it |
| 421 | ui | `NativeSelect` gets a `wrapperClassName` |
| 422 | admin | `/admin/users/` title, `/admin/settings/` h1, admin errors inside the admin shell |
| 423 | hosting | `TenantMiddleware` merges every `Vary` line and never drops `*` |
| 424 | hosting | `tenant_source` is `None` whenever no tenant is bound |

Out of scope: #317; the optional route-walking test helper floated in #418; the
branding-settings alternative for #415.

## Design

### #413 — naive timestamps in `TaskExecution`

`queued_at`, `started_at`, `finished_at` and `heartbeat_at`
(`modules/background_tasks/background_tasks/models.py`) are bare
`datetime | None`, so SQLModel maps them to `timestamp without time zone`.
Every writer and comparer already uses aware UTC (`now_utc()`,
`datetime.now(UTC)`), and asyncpg refuses an aware parameter against a naive
column.

The schema side is already done: migration `e5f2a8c1d7b3_timestamps_timezone_aware`
retypes these four columns, and `users_refresh_token`'s, to `timestamptz` on
Postgres. Only the model is wrong. Fix: `Field(default=None, sa_type=DateTime(timezone=True))`
on the four fields. **No new migration.**

The same pass covers the model of every column that migration retyped
(`users_refresh_token.created_at/expires_at/revoked_at`), so model and schema
agree everywhere `alembic check` looks. The other bare-`datetime` fields the
audit turned up (`user_role.assigned_at`, `permissions`, `audit_log`) are
checked against their migrated column types. If a column is still naive in the
schema, it stays as it is: changing it needs a migration and has no reported bug
behind it.

### #414 — aside footer contrast

`--color-dark-text-subtle` goes from `oklch(0.45 0.01 250)` (2.7:1 on the aside)
to `oklch(0.62 0.01 250)`. That clears 4.5:1 and stays a shade lighter than
`--color-dark-text-muted` (0.6), so the two tokens remain distinct. The footer is
its only consumer.

### #415 — host override layer

A host ships `host/locales/overrides/<lang>.json`, keyed by full dotted path, for
example `{"users": {"login": {"aside_heading": "…"}}}` or the flat
`{"users.login.aside_heading": "…"}`. The overrides are applied after every module,
framework and host source.

- `I18nRegistry.add_overrides(dir)` applies them at the end of `load()`, before
  locale layering and snapshots, so the server-side `Translator`, menus and
  Inertia shared props all see them.
- **An override may only replace an existing key.** An unknown key is skipped
  with a warning and reported by `make doctor` as a new locale diagnostic. A
  typo can't silently invent a key, and `keys.generated.ts` doesn't churn.
- **Audience is preserved.** An override of a key that is only in the admin
  catalog stays admin-only. The public snapshot is updated only for keys it
  already holds, so the #248 split cannot leak.
- `build_i18n_registry` registers `host/locales/overrides` when it exists.
  Documented in the i18n docs next to the `host` namespace.

### #416 — post-login target

`AuthMiddleware` keeps redirecting every unauthenticated, non-public request
exactly as today. It writes `SESSION_NEXT_KEY`, and passes a `next` to the
provider, only for a top-level navigation:

1. If `Sec-Fetch-Dest` is present, the request must be `document`.
2. Else, if `Sec-Fetch-Mode` is present, it must be `navigate`.
3. Else, `Accept` must include `text/html`.
4. **And always** an Inertia visit (`X-Inertia: true`), so a session that
   expires mid-navigation still returns the user to the page they clicked.

A favicon, script, image or `fetch()` no longer overwrites the target. The
favicon half of the issue is already fixed on `main` (`branding_head()` falls
back to a data-URI icon). Only the scaffold template is re-checked.

### #417 — tenant filter and outer joins

A table referenced only inside a function (`func.count(Child.id)`) loses its ORM
annotation. `_plain_tables` then treats it as a Core table and puts
`child.tenant_id = :t` in `WHERE`, which defeats the outer join.

The obvious fix is to drop every outer-join target from the `WHERE` candidates,
and it is a tenant leak in one shape. When the target is a raw
`Model.__table__`, nothing puts its predicate in the `ON` clause:
`with_loader_criteria` only covers ORM entities. With the `WHERE` predicate gone,
another tenant's child rows would match the `ON` and inflate the count. So:

- For each outer-join entry in `stmt._setup_joins` whose **target is an ORM
  entity** (its loader criteria land in `ON`), exclude that entity's table from
  `_plain_tables`. Full outer joins are treated the same way.
- **A raw-table outer-join target keeps today's `WHERE` predicate.** That
  over-filters but is never a leak. Moving it into `ON` would need the statement's
  join rewritten, which is outside this fix.
- The soft-delete path (`_soft_delete_criteria`) uses the same helper and gets the
  same fix.

Tests, in `framework/db/tests/test_query_filters.py`, with a new
tenant-scoped parent/child pair:

- The issue's four shapes keep the unused parent with count 0.
- A second tenant's child rows never appear in any count. This is the leak guard.
- An inner join through `_setup_joins` still filters the child.
- A raw-table outer join stays filtered.
- The soft-delete variant.

This task goes to an `opus` implementer plus a separate security review.

### #418 — public tenancy API

New public module `simple_module_hosting.tenancy`. Modules import from it instead
of reading the middleware stack.

| API | Behaviour |
|---|---|
| `TenancyMode` | `StrEnum` `SINGLE` / `MULTI`, in `simple_module_core.tenancy` so core and modules can name it without importing hosting. |
| `tenancy_mode(app)` | Read from `app.state.sm.tenancy`, a new defaulted field on `Services` that the app builder sets where it decides on `TenantMiddleware`: `MULTI` iff `multi_tenant`. |
| `single_tenant_id(app)` | `app.state.sm.db.default_tenant_id`: the host's `default_tenant`, else `DEFAULT_TENANT_ID`. |
| `require_tenant(*, on_missing=403, detail="tenant_required")` | Async yield-dependency factory. `SINGLE` binds `single_tenant_id(app)`; `MULTI` takes `request.state.tenant_id`, or raises `on_missing`, which is a status code or a `Callable[[Request], Exception]` (a public surface passes its own 404). It enters `tenant_context(tenant)` for the rest of the request and yields the tenant id. Documented to be listed before `get_db`, and verified by a test that a write commits under the bound tenant. |
| `tenant_vary(request)` | The headers the resolved tenant depended on. `TenantMiddleware` now records `request.state.tenant_vary`. Meant for a route that builds its own cache headers before the middleware sees the response, e.g. a 304. |

`Vary` completeness, as chosen at the question batch:

- The tenants resolver adds `Cookie` when the source is `"session"`.
- The no-resolver `"claim"` path adds `Cookie` and `Authorization`, since the claim
  came from whichever credential authenticated the request.

Docs: the multi-tenancy guide gains a "For module authors" section with the four
calls and the dependency-order rule.

### #419 — `@source` for wheel-module subdirectories

uv writes `.venv/.gitignore` = `*`, and Tailwind's scanner honours ignore files
below an `@source` base, so only the base directory's own files are scanned.

`render_modules_css()` (`framework/hosting/simple_module_hosting/assets.py`) keeps
the base line for an out-of-repo module and adds one `@source "<dir>/**/*.{ts,tsx}"`
for every descendant directory that directly holds a `.ts`/`.tsx` file:

- skipping `__pycache__` and `node_modules`;
- de-duplicated and sorted, so the output is deterministic;
- tolerant of a directory that doesn't exist, as today.

In-repo modules still get no lines.

### #420 — brand foreground ink

`deriveBrandRamp` (`packages/ui/src/lib/color.ts`) also sets
`--primary-foreground` and `--sidebar-primary-foreground`. It picks by **WCAG
contrast ratio**, not a fixed lightness threshold: white if white reaches 4.5:1 on
the brand colour, otherwise a dark ink (`oklch(0.2 0.02 250)`); if neither
reaches 4.5:1, whichever is higher.

- That gives dark ink on `#62B8E2` and `#9AD3EF`, and white on `#2E6DB0` and
  `#16276E`, matching the issue's measurements.
- `BrandingHead` already applies and clears every key the ramp returns, so it
  needs no change.
- `sidebar-theme.ts` `activeClass` becomes `bg-primary text-primary-foreground`.
- `BrandingMark`'s gradient badge is checked for the same light-brand problem and
  fixed the same way if it has it.

### #421 — `NativeSelect` width

New `wrapperClassName` prop, merged with `cn()` onto
`[data-slot=native-select-wrapper]`. `className` keeps targeting the `<select>`,
so existing callers are unchanged. The JSDoc explains that width utilities belong
on `wrapperClassName`.

### #422 — admin titles, headings, errors

- **`/admin/users/` title:** `Users/Index.tsx` gets
  `<Head title={t(keys.users.index.title)} />`. A sweep of every page rendered in
  `AdminLayout` fixes any other missing `<Head>`, and a vitest guard fails if a
  future admin page omits one.
- **`/admin/settings/` h1:** `ModulesEdit.tsx` gets a translated `<h1>` that
  names the screen, visible and placed like the other admin pages' headings.
- **Admin errors in the admin shell:** `Error.tsx` gets a function layout. It
  wraps the page in `AdminLayout` when all of these hold:
  - the page URL is `/admin` or under `/admin/` (segment-aware, so `/administer`
    does not match);
  - the viewer is signed in;
  - the shared `adminSidebar` is non-empty.

  Anything else renders bare, as today. That covers anonymous 401s and 419s, a
  non-admin's 403, and a 500 raised before the shared props were built.
  `ErrorScreen` gets an `inline` variant without the full-viewport frame, so it
  sits inside the shell's content area. The server side is unchanged: one fix
  covers the 404 (`/admin/users/999999`) and the 422 (`/admin/apps/abc`).

### #423 / #424 — `TenantMiddleware` (`_tenant.py`)

**#424:**
```python
if isinstance(result, TenantResolution):
    return result if result.tenant_id is not None else TenantResolution(None, None, result.vary)
```

**#423:**
- `_vary_sender` reads every line with `headers.getlist("vary")`.
- If any token is `*`, the response is left exactly as it was.
- Otherwise it writes one merged line.
- `merge_vary` de-duplicates existing tokens case-insensitively, keeping the
  first spelling, so `merge_vary("Accept, accept", ("Host",)) == "Accept, Host"`.
  Its signature is unchanged; it is public.

These sit next to #418's `tenant_vary` change and are done in the same task, so
the shared file and test module are edited once.

## Decisions made (override any at approval)

1. **#413 has no new migration.** The DB columns are already `timestamptz`
   (`e5f2a8c1d7b3`), and the refresh-token model is aligned in the same pass.
2. **#414 sets the token to `oklch(0.62 …)`,** not 0.6, so it stays distinct
   from "muted".
3. **#415 overrides replace keys but never add them.** Unknown keys warn, and
   admin-only keys stay admin-only.
4. **#416 records `next` on Inertia visits too.** Otherwise a session expiring
   mid-navigation would lose the destination.
5. **#417 leaves raw-table outer-join targets filtered in `WHERE`.** That is
   safe over-filtering instead of a leak.
6. **#418 claim-sourced tenants vary on `Cookie, Authorization`,** and the
   optional route-walking test helper is not built.
7. **#418 puts `TenancyMode` in `simple_module_core`** and stores it on
   `Services`, rather than inferring it from `app.user_middleware`.
8. **#420 picks the ink by WCAG contrast,** not by the issue's 0.62 lightness
   threshold.
9. **#421 adds a new prop** instead of making the wrapper `w-full`, so existing
   layouts don't shift.
10. **#422 admin errors are wrapped client-side** with one function layout, not
    a second `AdminError` page. Anonymous and pre-shared-props errors stay bare.

## Testing

- **Python unit and integration**, per issue:
  - #413: column `timezone is True` for every retyped column, plus
    `success_count_since` against Postgres when `SM_TEST_DATABASE_URL` is set.
  - #415: registry overrides, audience preservation, unknown-key warning and
    diagnostic.
  - #416: header matrix (document, navigate, Accept, Inertia, image, fetch).
  - #417: the matrix above.
  - #418: mode and id for single, `default_tenant` and multi hosts; `require_tenant`
    403, custom 404 and write stamping; `Vary` for session and claim.
  - #419: nested-directory `@source` output.
  - #423 / #424: the issues' listed cases.
- **Vitest:**
  - `color.test.ts` brand inks;
  - `BrandingHead` sets and clears the foreground vars;
  - `native-select` wrapper class;
  - `Error` admin-layout gating;
  - admin-page `<Head>` guard;
  - `ModulesEdit` h1.
- **E2E:** `test_document_titles.py` gains `/admin/users/`, and
  `test_error_pages.py` gains an admin 404 rendered with the admin navigation.
- **Gates:** full `make lint`, the full Python suite, the Postgres users,
  tenants and background_tasks suites, and `make migrations-roundtrip-pg` for #413.
- **Browser QA (via `/ship`):**
  - sign-in and post-login landing;
  - a light brand colour on the admin buttons and sidebar;
  - `/admin/users/` title;
  - `/admin/settings/` h1;
  - an admin 404 and 422 inside the shell;
  - the background-tasks page on Postgres.

## Risks

- **#417** is the tenant isolation boundary. If the ORM-target test cannot
  separate the safe shape from the leaking one reliably, the fallback is the
  issue's option 2 restricted to entities in `all_mappers`, re-reviewed. If even
  that leaks, I stop and report back instead of shipping it.
- **#413:** if `alembic check` on Postgres reports drift after the model change
  (for example `e5f2a8c1d7b3` is Postgres-only and SQLite autogenerate differs),
  a no-op or SQLite-guarded revision may be needed. That is a small deviation,
  noted in the PR.
- **#422:** wrapping `Error` in `AdminLayout` depends on that layout tolerating
  partial shared props. If it can't, the gating gets stricter rather than the
  layout looser.
- **#418** adds public API surface that downstream modules will depend on, so the
  names above are the contract.

# Issue batch #426–#437 — design

**Date:** 2026-10-11 · **Status:** approved · **Branch:** `feat/issue-batch-426-437` · **One combined PR**

Twelve issues filed on 2026-10-11 from building Kuri on 0.0.35, fixed together.
#317 stays out (needs the external design deck).

## Scope

| # | Area | One-line fix |
|---|---|---|
| 426 | i18n | `ui` catalog ships inside `simple_module_hosting`, registered unconditionally |
| 427 | ui | Layout "home" links come from a `homeUrl` shared prop, not `/dashboard/` |
| 428 | ui | Default footer caption drops the framework's licence |
| 429 | scaffold | Template `app.tsx` calls `initTheme()` and wires the `title` callback |
| 430 | settings | Picker hides zero-field modules (unless they have `manage_url`) and opens on the first shown |
| 431 | scaffold | Generated module test uses `effective_route_paths` |
| 432 | file_storage | `s3_signature_version` setting, default `s3v4`, passed as botocore `Config` |
| 433 | settings | `import-from-env` reads `.env` under `os.environ` |
| 434 | core/hosting | CSP providers evaluated per response, so origins can follow DB settings |
| 435 | users/dashboard | "Module has views" comes from the routes actually mounted, so a root-mounted module counts |
| 436 | auth | `UserContext.permissions`, round-tripped through the session and merged by the resolver |
| 437 | users | Sign-in error gets `role="alert"` |

## Design

### #426 — ship the `ui` catalog

`_i18n_build.py` registers `ui` only when `<project_root>/packages/ui/locales`
exists, which is true only inside this monorepo. `hosting` already ships its own
catalog as package data (`simple_module_hosting/locales/`).

**Move** `packages/ui/locales/{en,es}.json` to
`framework/hosting/simple_module_hosting/ui_locales/` (a sibling directory; the
flat `locales/` is taken by the `hosting` namespace) and always register `ui`
from there. One source of truth, shipped in the wheel by the existing
`packages = ["simple_module_hosting"]`, no copy to keep in sync and no
force-include that breaks sdist builds. Apps that want different wording already
have the #415 host override layer. Update the three code comments that name the
old path (`Makefile`, `simple_module_core/__main__.py`, `diagnostics/_i18n.py`)
plus the i18n diagnostics if they scan that path, and the docs
(`framework-conventions.md`).

Rejected: copy + byte-identical sync test (two sources), hatch `force-include`
from `../../packages/ui/locales` (breaks building from the sdist).

### #427 — `homeUrl` shared prop

The users module already owns the landing URL (`login_redirect_url`, rewritten
at startup by `apply_login_redirect_fallback` when Dashboard is absent) and
already registers an Inertia shared-props provider. It adds
`homeUrl: <login_redirect_url>` there. `packages/ui` gets a `useHomeUrl()` hook
returning `props.homeUrl ?? '/'`, used by `AdminLayout`, `SidebarLayout` (logo)
and `PublicLayout`. `SharedProps` gains `homeUrl?: string`.

Fallback is `/`, not `/dashboard/`: `/` is a host route in every app, so the
link can never 404 when the users module is absent.

### #428 — no licence in the default footer

Default caption becomes `© {year} {appName}`. `BRAND_LICENSE` is removed (its
only consumers are `BrandingFooter` and `BrandingPreview`); a host wanting a
licence line sets `footer_text`. Tests that expect `MIT` are updated.

Rejected: a `license` branding setting — a free-text `footer_text` already covers it.

### #429 — scaffold `app.tsx`

The template gains what the in-repo `host/client_app/app.tsx` does for theme and
title: `title: (t) => formatTitle(t)`, `setTitleAppName(initialPage.props.branding?.appName)`
and `initTheme()` before the first render. `ErrorBoundary`/`OfflineBanner` parity
is out of scope. `test_cli_new_regressions.py` asserts the three calls.

### #430 — settings picker

Client-side in `ModulesEdit.tsx`: `visible = modules.filter(m => m.fields.length > 0 || m.manage_url)`;
search filters `visible`; initial selection is `visible[0]`. The JSON API is
unchanged. A module with no fields but a `manage_url` stays, because its card is
the way to its own settings page.

### #431 — scaffold module test

Template imports `effective_route_paths` from `simple_module_test` and asserts
on its result. `test_scaffolding_module.py` asserts the rendered test uses it.

### #432 — SigV4

`FileStorageSettings.s3_signature_version: str = "s3v4"` (group S3, admin-editable
like the other S3 fields). `_build` in `backends/s3.py` passes
`config=botocore.config.Config(signature_version=...)`, imported lazily because
botocore only exists with the `s3` extra. Test: presigned URL contains
`X-Amz-Algorithm=AWS4-HMAC-SHA256` with a custom endpoint.

### #433 — `.env` in `import-from-env`

`import_from_env_impl(app, store, environ=None)` reads from
`{**parse_dotenv(find_env_file()), **os.environ}` by default — the real
environment wins, as with pydantic-settings — using the framework's existing
`simple_module_core.dotenv` helpers (no new dependency). No mutation of
`os.environ`. When nothing was imported and a `.env` exists, the command prints a
hint naming the expected `SM_<MODULE>_<FIELD>` form. The `.env.example` colour
lines get a "quote values containing `#`" note.

### #434 — CSP sources that follow settings

`CspSourceRegistry.add_provider(fn)` where `fn(app) -> Iterable[tuple[str, str]]`
returns `(directive, source)` pairs, registered from the existing
`register_csp_sources` hook (no signature change). `SecurityHeadersMiddleware`
keeps the static policy string and, when providers exist, per response:

1. calls each provider (sync, must only read in-memory state such as
   `app.state.<pkg>.settings`); a provider that raises, or returns a pair that
   fails the same directive/source validation `add()` applies, is logged once
   and contributes nothing (fail closed — the static policy still applies);
2. looks the resulting `frozenset` of pairs up in a small dict cache of finished
   policy strings and builds it with `extend_policy` on a miss.

No version key or TTL is needed: the cache is keyed on the *value* providers
return, so a runtime settings edit (already hydrated per process by the settings
module and the `settings.values` invalidation channel) changes the key on the
next response. With no providers the middleware is byte-for-byte today's path.
Cache bounded (e.g. 32 entries, clear on overflow).

Rejected: recompute on `SettingsReloaded` + invalidation subscriptions (more
wiring, a missed event leaves a stale policy); passing `app` to the hook (still
runs before DB hydration, so it fixes nothing).

### #435 — root-mounted modules

`view_prefix=""` is both the default ("no views") and "mounted at `/`", so the
issue's `is not None` would match every API-only module. Instead
`wire_module_routes` records each module whose view router actually received
routes in `app.state.sm.view_prefixes: dict[str, str]` (module name → prefix,
discovery order). `apply_login_redirect_fallback` and `dashboard/stats.py` use
that map: the first non-users module in it wins, and `""` yields `/`. The admin
URL in stats stays as it is (an admin prefix is never empty).

Rejected: a `register_routes`-override check (an API-only module that overrides it
would be taken as root-mounted); `view_prefix: str | None` (breaking change for
every module).

### #436 — `UserContext.permissions`

`permissions: list[str] = field(default_factory=list)` appended after `tenant_id`
(positional order preserved), written by `to_session_dict` and read with
`payload.get("permissions") or []` so old cookies stay valid. Add
`has_permission(p)`. `resolve_principal_permissions` merges
`getattr(user, "permissions", None) or ()` after the role step, **dropping `*`**
— the same guarantee #398 gives grant sources, so a token or IdP claim can never
carry the wildcard. Duck-typed, so SM009 holds. `from_user` leaves it empty
(direct user grants keep coming from the permissions module's grant source).
Documented: these permissions are frozen in the session like `roles`; anything
revocable belongs in a grant source.

### #437 — announce the sign-in error

`role="alert"` on the `LoginForm` error paragraph, plus a vitest asserting
`getByRole('alert')` after a failed submit.

## Decisions made (override at approval)

1. #426 moves the catalog instead of copying it; `packages/ui/locales` is deleted.
2. #427 prop name `homeUrl`, owned by users, client fallback `/`.
3. #428 drops the licence entirely rather than adding a setting.
4. #432 is a setting (as the issue suggests), not a hard-coded value.
5. #434 is per-response providers with a value-keyed cache, not event-driven recompute.
6. #435 uses the mounted-routes map instead of a `ModuleMeta` change.
7. #436 filters `*` out of `UserContext.permissions`.
8. #429 adds theme + title only, not ErrorBoundary/OfflineBanner.

## Testing

- Python: `_i18n_build` registers `ui` with no `packages/ui` under the root;
  users shared props expose `homeUrl`; S3 presign is SigV4; `import_from_env_impl`
  reads a tmp `.env` and env wins over it; CSP provider adds/changes/fails closed
  and the static path is unchanged; root-mounted fake module wins the login
  fallback and gets `/` in dashboard stats while an API-only module does not;
  `UserContext` round-trip with and without `permissions`, resolver merges them
  and drops `*`; scaffold template content checks (#429, #431).
- JS: `useHomeUrl` in the three layouts, footer caption, settings picker
  hide/initial selection, LoginForm alert.
- QA in the browser: `/admin/users/` back link, footer caption, `/admin/settings/`
  picker, failed sign-in.

## Risks

- #426: the generated i18n keys/resources read the registry, so moving the
  catalog must keep `keys.generated.ts` identical — checked by regenerating.
- #434: the per-response provider call is on the hot path; providers must stay
  attribute reads. The no-provider path is unchanged, so only apps using it pay.
- #435: the test harness in `simple_module_test` also calls `wire_module_routes`,
  so `app.state.sm` must exist there too.

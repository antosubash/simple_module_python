# Batch 4: typed API client (#504) and typed page props (#505)

Approved 2026-10-22 as proposed. Baseline: 51 `fetch(` call sites in 36 files; 44 `as unknown as`
casts (29 modules, 10 `packages/ui`, 4 `host/client_app`, 1 setup wizard).

## #504 Typed API client

- Runtime: `openapi-fetch` (dependency of `@simple-module-py/ui`); types from `openapi-typescript`
  (dev dependency). Wrapper `packages/ui/src/lib/api.ts` (<150 lines, tested):
  `createApi<Paths>()` returns an `openapi-fetch` client whose middleware sets
  `credentials: 'same-origin'`, `Accept: application/json`, and `X-CSRF-Token` on
  POST/PUT/PATCH/DELETE when a token is known. Results normalise to
  `{ ok, status, data, detail, fieldErrors }` (`detail`: string `detail` or null; `fieldErrors`: last
  `loc` element → `msg` for 422). Untyped `apiFetch<T>(url, init)` for non-`/api` routes (`/setup/*`)
  and multipart uploads. No English strings in the wrapper.
- `useApiErrorToast(fallbackKey)` hook: opt-in toast of `detail ?? t(fallbackKey)`.
- Generated types: committed `<pkg>/pages/api.generated.ts` per module; module `pages/api.ts` exports
  `api = createApi<paths>()`.
- Generator: `smpy openapi gen-types [--module X]` (in-memory export filtered by the module tag →
  `npx openapi-typescript` → file with a generated header). Make targets `gen-api-types` and
  `ci-api-types-fresh` (hash before/after, like `ci-i18n-fresh`), added to `make lint`'s CI
  equivalent and `pr.yml`. `**/*.generated.ts` exempt from the file-size cap and Biome formatting.
- Scaffold: module templates (and `_optional/framework_repo`) ship `pages/api.ts` + an initial
  generated file and use `api.*` plus typed component args; `smpy` runs `gen-types` after scaffolding.
  Update shipped skills `simple-module-inertia-pages` / `simple-module-conventions`.
- CSRF: new shared Inertia prop `csrfToken`, only for authenticated sessions (never on anonymous or
  cacheable pages). Server enforcement unchanged (opt-in `RequiresCsrf`). Page-prop tokens in
  api_tokens and the setup wizard remain as overrides.
- Migrate in this batch: tenants (11 calls), api_tokens (1). List endpoints without a response type
  in the PR.

## #505 Typed page props

- `packages/ui/src/hooks/usePageProps.ts`: `usePageProps<T extends object>()` returning
  `T & SharedProps & { errors }` (the one justified cast lives here).
- Augment Inertia's `InertiaConfig.sharedPageProps` with `SharedProps` (incl. `i18n`) in
  `packages/ui`, so `usePage().props.auth` is typed.
- Pages use typed component args; components/layouts use `usePageProps`. Remove all 44 casts.
- Gate `scripts/check_no_double_cast.py` (`make ci-check-no-double-cast`, in `make lint` and CI):
  fails on `as unknown as` in `.ts/.tsx` under module `pages/`, `packages/ui/src`, `host/client_app`
  unless the line (or the line above) carries `// cast-ok: <reason>`. Tests excluded.
- Fix `docs/frontend/shared-props.md` and `docs/frontend/inertia.md` (CSRF/fetch guidance).

## Later

- Batch 4b: users (24 calls), background_tasks, branding, settings, file_storage (split
  `Browse.tsx` into `useFileActions` first), setup wizard → `apiFetch`; raw-`fetch(` gate.
- Follow-up issue: DTO-declared page props generated into per-module `PageProps` maps.

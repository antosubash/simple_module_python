# Branding feature — design

**Date:** 2026-06-17
**Status:** design (intended state)

## Goal

Let an administrator customise the application's identity — **app name, logo,
favicon, and primary brand colour** — from the admin UI, and have those values
applied everywhere the framework currently hard-codes "SimpleModule" (browser
title, sidebar/header label and logo, favicon, primary colour).

## Scope (MVP) and explicit non-goals

In scope:

- A `branding` module exposing **app name**, **logo image**, **favicon image**,
  and **primary colour (hex)**.
- A dedicated admin page (`/branding`) with uploads, a colour picker and a live
  preview — gated behind a `branding.manage` permission.
- Logo/favicon **image upload** reusing the existing `file_storage` module
  (stored by UUID, served via its download endpoint).
- Values persisted via the existing **settings store** (no new branding DB
  table), hydrated at boot and hot-reloaded on save.
- Values surfaced to **every** Inertia page (authenticated *and* guest) via a
  new generic framework extension point, then consumed in the React layout,
  the document `<title>`, the favicon `<link>`, and primary-colour CSS vars.

Non-goals (deliberately deferred — note where the design leaves room):

- **Per-tenant branding.** MVP is SYSTEM scope only. The settings store already
  supports TENANT/USER scope, so this is an additive change later (resolve the
  tenant in the shared-props provider).
- **Full colour-scale theming.** We override the shadcn semantic tokens
  (`--primary`, `--primary-foreground`, `--sidebar-primary`) from the single
  hex. We do *not* regenerate the `primary-50…900` OKLCH scale used by some
  gradients; that is a future enhancement.
- Custom fonts, login-page background imagery, dark/light logo variants.

## Why this shape

The framework already has every primitive this needs; the feature is mostly
*wiring*, not new infrastructure:

- **Settings store** persists arbitrary module config (SYSTEM/TENANT/USER
  scope), hydrates a pydantic `BaseSettings` at boot into
  `app.state.<module>.settings`, and hot-swaps it on save via
  `apply_changes_and_reload(...)` which also publishes `SettingsReloaded`.
  → Branding stores its four values here; **no new table**.
- **file_storage** stores an uploaded image and returns a stable UUID; the
  image is served from `GET /api/file-storage/files/{id}/download` for every
  backend (local disk or S3/MinIO).
  → Branding stores `logo_file_id` / `favicon_file_id` and derives URLs.
- **`InertiaLayoutDataMiddleware`** already assembles per-page shared props
  (`auth`, `menus`, `i18n`) and — crucially — avoids the `SM009`
  framework→plugin import ban by reading a *module-registered callable* off
  `app.state` (`principal_serializer`). Branding follows that exact precedent.

## Architecture

### New framework extension point: Inertia shared-prop providers

A generic, module-agnostic hook so any plugin can contribute layout-wide shared
props without the framework importing the plugin (mirrors `principal_serializer`).

- `app.state.inertia_shared_providers: list[Callable[[Request], dict]]`,
  initialised to `[]` in `app_builder`.
- A tiny hosting helper `register_inertia_shared_provider(app, fn)` appends to it.
- `InertiaLayoutDataMiddleware` iterates the providers and merges each returned
  dict into `shared` (after the built-in `auth`/`menus`/`i18n`). Providers must
  be cheap and total (no exceptions); a provider that raises is skipped and
  logged, never failing the request.

This is generic framework value, not a branding special-case.

### The `branding` module (plugin)

```
modules/branding/branding/
├── module.py        # registers settings, permission, menu, routes, provider
├── settings.py      # BrandingSettings(BaseSettings): app_name, logo_file_id,
│                    #   favicon_file_id, primary_color
├── services.py      # BrandingState(settings=...)
├── service.py       # BrandingService: read current branding, apply updates,
│                    #   upload+set logo/favicon via file_storage + settings store
├── shared_props.py  # provider: (request) -> {"branding": {...}} from app.state
├── contracts/       # BrandingOut, BrandingUpdate DTOs
├── deps.py
├── endpoints/api.py # JSON: GET current, PUT name/colour, POST logo, POST
│                    #   favicon, DELETE logo/favicon  (all branding.manage)
├── endpoints/views.py # Inertia: GET /branding -> "Branding/Manage"
├── pages/Manage.tsx # admin page: name, uploads, colour picker, live preview
└── locales/en.json
```

- `meta = ModuleMeta(name="Branding", route_prefix="/api/branding",
  view_prefix="/branding", depends_on=["Settings", "FileStorage"])`.
- `register_permissions`: group "Branding" with `branding.view`, `branding.manage`.
- `register_menu_items`: "Branding" under the "Administration" group,
  `roles=["admin"]`.
- `register_settings`: `register_module_settings(app, "branding",
  BrandingSettings, lambda s: BrandingState(settings=s))`.
- Shared-props provider registered in `on_startup` (after settings hydrated):
  returns `{"branding": {appName, logoUrl, faviconUrl, primaryColor}}`, reading
  the live `app.state.branding.settings`. URLs derived from file ids; `None`
  when unset so the frontend falls back to defaults.

### Data flow

```
admin saves on /branding
  → POST /api/branding/logo (UploadFile)
      → file_storage.upload() -> StoredFileOut.id (UUID)
      → settings apply_changes_and_reload(app, bus, store, "branding",
            {"logo_file_id": str(id)})
          → app.state.branding.settings hot-swapped + SettingsReloaded event
  → next request:
      InertiaLayoutDataMiddleware merges branding provider output into shared
        → inertia.share(**shared)
          → usePage().props.branding in React
              → SidebarLayout (name + logo), app.tsx title, <Head> favicon,
                CSS var override for --primary
```

### Frontend consumption (packages/ui + host)

- `app.tsx` title callback: `title ? \`${title} — ${appName}\` : appName`,
  reading the initial-page branding prop (fallback "SimpleModule").
- `SidebarLayout.tsx`: render `branding.appName` and, when `logoUrl` set, an
  `<img>` instead of the "SM" badge — both mobile and desktop. Fallback to the
  current "SM"/"SimpleModule" treatment.
- New `BrandingHead` component (packages/ui) rendered in the authenticated and
  public layouts: emits `<Head>` with a favicon `<link>` (when set) and a
  `<style>` overriding `--primary` / `--primary-foreground` /
  `--sidebar-primary` from the hex (when set).
- Branding shared prop also reaches **guest** pages (login etc.) because the
  provider runs for every request.

## Validation & error handling

- Image uploads constrained to an allow-list (`image/png`, `image/jpeg`,
  `image/svg+xml`, `image/x-icon`, `image/webp`) and a max size (e.g. 2 MB),
  enforced in the branding endpoint before handing to file_storage.
- `primary_color` validated as a `#rrggbb` hex (pydantic field validator);
  invalid input rejected with 422.
- `app_name` length-bounded (1–60 chars).
- Shared-props provider is defensive: any failure → omit branding block, log,
  never 500 a page.

## Testing

- **Unit (pytest):** `BrandingSettings` defaults/validation; `BrandingService`
  upload→settings-write happy path with a fake file_storage; shared-props
  provider output (set vs unset values); hex validator.
- **Integration (pytest + authenticated_client):** `PUT /api/branding`
  persists name/colour and the value appears in the next page's shared props;
  `POST /api/branding/logo` stores a file and sets `logo_file_id`; permission
  gate returns 403 without `branding.manage`.
- **Framework:** provider registry — a registered provider's dict is merged
  into shared; a throwing provider is skipped, not fatal.
- **JS (vitest):** `SidebarLayout` renders custom name/logo when prop present,
  falls back when absent; `BrandingHead` emits favicon + CSS var style.
- **Doctor:** `make doctor` clean (no SM00x/SM01x regressions; menu+permission
  present so no SM019).

## Build sequence

1. Framework extension point (registry + middleware merge + helper) — TDD.
2. Scaffold `branding` module (`make new-module`), strip CRUD shape to the
   settings/singleton shape above.
3. `BrandingSettings` + state + service + contracts + provider — TDD.
4. Endpoints (JSON + Inertia view) + permissions + menu — TDD.
5. Frontend: shared-prop typing, SidebarLayout, app.tsx title, BrandingHead,
   Manage.tsx page.
6. Wire provider registration; `make gen-pages`; migrations check.
7. `make lint`, `make test`, `make doctor`; e2e smoke of `/branding`.

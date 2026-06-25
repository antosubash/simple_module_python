# branding

Lets an administrator customise the application's identity — **app name**, **logo**, **favicon**, and **primary colour** — from an admin page, with no code change or redeploy. Values persist in the shared [settings](/modules/settings) store (there is no branding table) and reach **every** Inertia page (authenticated *and* guest) through a registered shared-props provider, so the frontend can render the name, swap the logo/favicon, and apply the brand colour everywhere.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Branding` |
| `route_prefix` | `/api/branding` |
| `view_prefix` | `/branding` |
| `depends_on` | `["Settings", "FileStorage"]` |

It depends on `settings` for storage and `file_storage` for the uploaded logo/favicon bytes.

## Routes

### API

All JSON endpoints — including the read — require `branding.manage` (they back the admin editor).

| Method + path | Body / response | Permission |
|---|---|---|
| `GET /api/branding/` | → `BrandingOut` | `branding.manage` |
| `PUT /api/branding/` | `BrandingUpdate` → `BrandingOut` | `branding.manage` |
| `POST /api/branding/logo` | `multipart` (field `file`) → `BrandingOut` | `branding.manage` |
| `POST /api/branding/favicon` | `multipart` (field `file`) → `BrandingOut` | `branding.manage` |
| `DELETE /api/branding/logo` | → `BrandingOut` (logo cleared) | `branding.manage` |
| `DELETE /api/branding/favicon` | → `BrandingOut` (favicon cleared) | `branding.manage` |

`PUT` only touches the text fields (`app_name`, `primary_color`); the logo and favicon are set/cleared through their dedicated upload/delete routes. Uploads are validated **before** the bytes are handed to `file_storage` — an unsupported MIME type returns `415`, an oversized image returns `413` (see [Image guard-rails](#image-guard-rails)).

### View

| Method + path | Inertia component | Permission |
|---|---|---|
| `GET /branding/` | `Branding/Manage` | `branding.view` |

The page reads the current values from the shared `branding` prop, so the view endpoint passes no page props of its own.

## Public contracts

```python
from branding.contracts import BrandingOut, BrandingUpdate
```

| Class | Purpose |
|---|---|
| `BrandingOut` | Current branding with logo/favicon resolved to download URLs: `app_name`, `primary_color`, `logo_url`, `favicon_url`. |
| `BrandingUpdate` | Editable text fields only: `app_name` (≤ 60 chars, non-blank), `primary_color` (`#rrggbb` or empty). |

## Models

**None.** Branding owns no tables. The four values are stored in the shared settings store at **SYSTEM** scope, hydrated into `app.state.branding.settings` at boot, and hot-swapped on save via the settings reload path.

## Settings

DB-backed via `register_module_settings`; pydantic defaults seed at boot. Edited from the dedicated **Branding** admin page (`/branding`) rather than the generic settings UI.

| Field | Default | Purpose |
|---|---|---|
| `app_name` | `"SimpleModule"` | Application name (trimmed; must be non-blank and ≤ 60 chars). |
| `primary_color` | `""` | Brand colour as a lowercase `#rrggbb` hex string; `""` ⇒ use the theme default. |
| `logo_file_id` | `""` | `file_storage` UUID of the uploaded logo; `""` ⇒ no custom logo. |
| `favicon_file_id` | `""` | `file_storage` UUID of the uploaded favicon; `""` ⇒ no custom favicon. |

### Image guard-rails

Enforced in the API before the upload reaches `file_storage`:

- **Max size:** 2 MB (`413` otherwise).
- **Allowed types:** `image/png`, `image/jpeg`, `image/svg+xml`, `image/webp`, `image/gif`, `image/x-icon` / `image/vnd.microsoft.icon` (`415` otherwise).

## How branding reaches the frontend

On startup the module registers a shared-props provider (`register_inertia_shared_provider`). On every Inertia render — guest pages included — it emits a `branding` block built from the live module settings:

```json
{
  "branding": {
    "appName": "Acme Corp",
    "primaryColor": "#1d4ed8",
    "logoUrl": "/api/file-storage/files/<id>/download",
    "faviconUrl": "/api/file-storage/files/<id>/download"
  }
}
```

`primaryColor` is `null` when unset; `logoUrl` / `faviconUrl` are `null` when no file is configured (otherwise a `file_storage` download URL derived from the stored id). The provider is defensive — it returns `{}` if branding state isn't mounted yet, so a half-booted app never errors a render. Because changes go through the settings store, a save hot-reloads `app.state.branding.settings`; the next render reflects the new values without a restart.

## Permissions

| Code | Granted to | Purpose |
|---|---|---|
| `branding.view` | `admin` | open the Branding admin page (`/branding`) |
| `branding.manage` | `admin` | read + write branding via the API (edit name/colour, upload/clear logo + favicon) |

## Menu

| Label | URL | Icon | Section | Group | Order | Roles |
|---|---|---|---|---|---|---|
| `Branding` | `/branding` | `palette` | `SIDEBAR` | `Administration` | `115` | `["admin"]` |

## Inertia pages

- `Branding/Manage.tsx` — the admin editor: app-name + colour form, logo and favicon upload/clear, and a live preview.

## Locales

`branding/locales/en.json` — namespace `branding`, top-level key `manage` (the admin page strings).

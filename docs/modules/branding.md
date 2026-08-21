# branding

White-labels the application. An administrator sets the **app name**, **logo** (plus an optional dark-background variant), **favicon**, **primary colour**, **[design pack](/framework-conventions#design-packs-site-wide-look)**, and a site-wide **announcement banner** — from an admin page, with no code change or redeploy.

Values persist in the shared [settings](/modules/settings) store (there is no branding table) and reach **every** Inertia page — authenticated *and* guest — through a registered shared-props provider, so the frontend can render the name, swap the logo/favicon, apply the brand colour, and show the banner everywhere. Footer content is owned by the framework site layouts, not branding.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Branding` |
| `route_prefix` | `/api/branding` |
| `view_prefix` | `/admin/branding` |
| `depends_on` | `["Settings", "FileStorage"]` |
| `i18n_audience` | `"admin"` |

It depends on `settings` for storage and `file_storage` for the uploaded logo/favicon bytes. Its catalog is admin-form strings, so it declares [`i18n_audience="admin"`](/framework/i18n#audience) and is kept out of the guest bundle — branding's *public* contribution rides the shared-props provider, not i18n keys.

## Routes

### API (admin)

Every JSON endpoint — including the reads — requires `branding.manage`; they back the admin editor.

| Method + path | Body / response |
|---|---|
| `GET /api/branding/` | → `BrandingOut` |
| `PUT /api/branding/` | `BrandingUpdate` → `BrandingOut` |
| `POST /api/branding/presets/{key}` | → `BrandingOut` (`404` for an unknown key) |
| `POST /api/branding/logo` | `multipart` (field `file`) → `BrandingOut` |
| `POST /api/branding/logo-dark` | `multipart` (field `file`) → `BrandingOut` |
| `POST /api/branding/favicon` | `multipart` (field `file`) → `BrandingOut` |
| `DELETE /api/branding/logo` | → `BrandingOut` (logo cleared) |
| `DELETE /api/branding/logo-dark` | → `BrandingOut` (dark logo cleared) |
| `DELETE /api/branding/favicon` | → `BrandingOut` (favicon cleared) |

`PUT /` only touches the text fields (`app_name`, `primary_color`, `design_pack`, `banner_message`, `banner_severity`); images are set and cleared through their dedicated upload/delete routes. A `design_pack` slug that no installed module registered is rejected with `422` — accepting it would put `"<slug>-root"` on the document with no stylesheet behind it, so the site would look unchanged with nothing in the UI explaining why.

Uploads are validated **before** the bytes reach `file_storage`: an unsupported or unconvincing type returns `415`, an oversized image `413` (see [Image guard-rails](#image-guard-rails)).

### Public assets (anonymous)

Registered through the [`register_public_routes`](/framework/public-routes) hook as `exact` + **GET-only** rules, so uploading and clearing the same paths stay behind `branding.manage`.

| Method + path | Response |
|---|---|
| `GET /api/branding/logo` | The configured logo bytes (`404` when unset) |
| `GET /api/branding/logo-dark` | The dark-background variant (`404` when unset) |
| `GET /api/branding/favicon` | The configured favicon (`404` when unset) |

Branding serves these itself rather than linking `file_storage`'s download route, which is gated by `file_storage.download` — no logged-out visitor carries that permission, and the sign-in page, the public landing page and every `<link rel="icon">` are exactly where the logo has to appear. Each route resolves **only** the id currently held in branding settings and streams that one file, so it is not a way to read arbitrary files out of `file_storage`.

Responses carry `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`. Both are ignored for subresource loads (`<img>`, `<link rel="icon">`) but stop a direct visit rendering the bytes as a document at the app's own origin.

When `file_storage` is backed by S3-compatible storage, the route returns a `302` to a presigned URL. That redirect is deliberately **uncached** — the target expires, so caching it would hand out a dead link after the TTL.

### View

| Method + path | Inertia component | Permission |
|---|---|---|
| `GET /admin/branding/` | `Branding/Manage` | `branding.view` |

Current branding reaches the page through the shared `branding` prop. The endpoint passes only what the shared prop *can't* carry: `designPacks` (which packs the installed modules registered) and `presets` (the built-in list, with swatches).

## Asset caching

The published URL carries `?v=<file id>`. Replacing an image stores a **new** `file_storage` file, so the id doubles as a content address — the URL changes and caches invalidate for free.

| Request | `Cache-Control` |
|---|---|
| With a `?v=` version | `public, max-age=31536000, immutable` (one year) |
| Without a version | `public, max-age=3600` (one hour) |

An unversioned URL can serve new bytes later, so it must never be immutable; the short TTL lets it self-correct. A `404` is never cached, so the next request retries once the setting is fixed.

## Public contracts

```python
from branding.contracts import BrandingOut, BrandingUpdate
```

| Class | Purpose |
|---|---|
| `BrandingOut` | Current branding with images resolved to URLs: `app_name`, `primary_color`, `design_pack`, `logo_url`, `logo_dark_url`, `favicon_url`, `banner_message`, `banner_severity`. |
| `BrandingUpdate` | Editable text fields, all optional: `app_name`, `primary_color`, `design_pack`, `banner_message`, `banner_severity`. |

`BrandingUpdate` is the strict one. An unknown `banner_severity` is a clear `422` here, while the settings validator normalises it to `info` — settings hydrate from the DB, where a hand-edited row must degrade to a readable banner rather than stop the app from booting. `design_pack` and `primary_color` are shape-checked in the DTO for the same reason: a malformed value becomes a `422` instead of a `500` when `BrandingSettings` re-validates.

## Models

**None.** Branding owns no tables. Every value is stored in the shared settings store at **SYSTEM** scope, hydrated into `app.state.branding.settings` at boot, and hot-swapped on save via the settings reload path.

## Settings

DB-backed via `register_module_settings`; pydantic defaults seed at boot. Edited from the dedicated **Branding** admin page (`/branding`) rather than the generic settings UI.

| Field | Default | Purpose |
|---|---|---|
| `app_name` | `"SimpleModule"` | Application name (trimmed; non-blank, ≤ 60 chars, no control characters). |
| `primary_color` | `""` | Brand colour as a lowercase `#rrggbb` hex string; `""` ⇒ use the theme default. |
| `design_pack` | `""` | Slug of a registered [design pack](/framework-conventions#design-packs-site-wide-look); `""` ⇒ base tokens only. |
| `logo_file_id` | `""` | `file_storage` UUID of the logo; `""` ⇒ no custom logo. |
| `logo_dark_file_id` | `""` | UUID of the dark-background variant; `""` ⇒ fall back to `logo_file_id`. |
| `favicon_file_id` | `""` | UUID of the favicon; `""` ⇒ no custom favicon. |
| `banner_message` | `""` | Site-wide announcement text (≤ 500 chars); `""` ⇒ no banner. |
| `banner_severity` | `"info"` | One of `info`, `warning`, `danger`. Unknown values normalise to `info`. |

`app_name` rejects control characters, not just blanks: the name is used in HTML titles and — critically — email `Subject` headers, where an embedded CR/LF would survive a bare `strip()` and then raise, breaking every transactional email.

### Image guard-rails

Enforced in the API before the upload reaches `file_storage`:

- **Max size:** 2 MB (`413` otherwise).
- **Allowed types:** `image/png`, `image/jpeg`, `image/webp`, `image/gif`, `image/x-icon` / `image/vnd.microsoft.icon` (`415` otherwise).
- **Magic-number check:** the first bytes must match the signature of *one of* the allowed formats (`415` otherwise).

The declared `Content-Type` on a multipart part is chosen by the caller, so it is a claim rather than a fact — `payload.html` renamed `logo.png` would otherwise be stored and later served back under an `image/*` type. The signature check is what rules that out.

Note the exact property: the bytes must look like **some** allowed image format, not like the one the caller declared. A genuine PNG uploaded as `image/jpeg` passes and is stored as `image/jpeg`. That mismatch is harmless here — every allowed format is a raster or icon the browser renders inertly — and the check still does the job it exists for, which is keeping non-images out of the store.

**SVG is excluded on purpose.** It is an XML document that can carry `<script>`, so serving one back from the app's own origin would be stored XSS. The `attachment` + `nosniff` headers on the asset route defend in depth, but the narrower allow-list is what actually keeps executable markup out of the store.

### Asset lifecycle

Replacing or clearing an image deletes the file it stopped referencing, so repeated logo tweaks don't leave orphans in `file_storage`. Cleanup is **best effort**: the setting change has already been persisted, so a storage fault is logged rather than failing an otherwise-successful rebrand.

## Presets

A preset is a named one-click look, applied through the ordinary update path so every validator still runs:

```http
POST /api/branding/presets/ocean
```

Seven ship with the module — `emerald`, `ocean`, `indigo`, `violet`, `amber`, `rose`, `slate` — each setting a `primary_color`.

**A preset carries appearance, never identity.** `PRESET_FIELDS` restricts a preset to `primary_color` and `design_pack`; `BrandingPreset` rejects any other field at construction. The app name, the uploaded images and a live banner are deployment identity or operational state, and survive applying a preset — a preset that overwrote a logo an admin had just uploaded would destroy exactly the work the branding page exists to do.

A preset's `design_pack` runs the same registration check a manual update gets, rather than trusting the built-in list.

Presets are **not an extension point** — the list is fixed in the module. A module that wants to contribute its own look ships a [design pack](/framework-conventions#design-packs-site-wide-look) instead, which is the registry-backed, module-contributed mechanism.

## Announcement banner

A message plus a severity, rendered above every shell — app, public and auth — because an outage notice is most useful to the people who cannot sign in. An empty message hides it entirely.

Severity colours are semantic, not brand-tinted: a warning wearing the deployment's accent colour stops reading as a warning.

## Dark-background logo

The sidebar and mobile bar sit on a near-black surface in every theme, while the sign-in card and public page are light — so a single logo cannot read on both. Uploading a *Logo (dark backgrounds)* variant swaps it in on those surfaces only.

It is optional: with none set the shared prop reports `logoDarkUrl: null` and the frontend falls back to `logoUrl`, so single-logo deployments look exactly as they did. On the frontend, use `darkSurfaceLogo(branding)` from `@simple-module-py/ui/lib/brand`, which applies that fallback in one place.

## How branding reaches the frontend

On startup the module registers a shared-props provider (`register_inertia_shared_provider`). On every Inertia render — guest pages included — it emits a `branding` block built from the live module settings:

```json
{
  "branding": {
    "appName": "Acme Corp",
    "primaryColor": "#1d4ed8",
    "designPack": "gca",
    "logoUrl": "/api/branding/logo?v=<file id>",
    "logoDarkUrl": "/api/branding/logo-dark?v=<file id>",
    "faviconUrl": "/api/branding/favicon?v=<file id>",
    "banner": { "message": "Maintenance at 22:00 UTC", "severity": "warning" }
  }
}
```

`primaryColor` and `designPack` are `null` when unset; the three image URLs are `null` when no file is configured. `banner` is `null` when no message is set, so the frontend renders nothing at all rather than an empty bar.

The provider is defensive — it returns `{}` if branding state isn't mounted yet, so a half-booted app never errors a render. Because changes go through the settings store, a save hot-reloads `app.state.branding.settings`; the next render reflects the new values without a restart.

## Permissions

| Code | Granted to | Purpose |
|---|---|---|
| `branding.view` | `admin` | open the Branding admin page (`/branding`) |
| `branding.manage` | `admin` | read + write branding via the API (name, colour, design pack, banner, image upload/clear) |

## Menu

| Label | URL | Icon | Section | Group | Order | Roles |
|---|---|---|---|---|---|---|
| `Branding` | `/admin/branding/` | `palette` | `ADMIN_SIDEBAR` | `Appearance` | `105` | `["admin"]` |

## Inertia pages

- `Branding/Manage.tsx` — the admin editor: app name, colour and design pack, preset picker, logo / dark logo / favicon upload and clear, banner editor, and a live preview.

## Locales

`branding/locales/en.json` — namespace `branding`, top-level key `manage` (the admin page strings).

## Notes

- Branding is SYSTEM-scoped (one identity per deployment). The settings store already supports tenant/user scope, leaving room for per-tenant branding later.
- The primary colour overrides the `--primary` / `--sidebar-primary` CSS variables from a single hex; the full OKLCH colour scale is not regenerated.

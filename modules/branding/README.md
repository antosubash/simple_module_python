# simple_module_branding

Customisable application branding for [simple_module_python](https://github.com/antosubash/simple_module_python) apps.

An administrator can set the **application name**, **logo**, **favicon** and
**primary brand colour** from the admin UI (`/branding`), and those values are
applied everywhere the framework would otherwise show the default identity —
the sidebar/header logo and name, the browser tab title, the favicon, and the
primary accent colour.

## Install

The module ships with the default app. To add it to a custom host, declare it
as a dependency and let entry-point discovery pick it up:

```toml
# host/pyproject.toml
dependencies = ["simple_module_branding"]

[tool.uv.sources]
simple_module_branding = { workspace = true }
```

Then `uv sync --all-packages`. It requires the `Settings` and `FileStorage`
modules to be installed too.

## Usage

1. Sign in as an admin and open **Branding** in the sidebar (or visit
   `/branding`).
2. Set the application name, pick a primary colour, and upload a logo and/or
   favicon. Changes apply immediately across the app.

Programmatically, the current branding is available on every page through the
`branding` Inertia shared prop (`appName`, `primaryColor`, `logoUrl`,
`faviconUrl`).

## How it works

- **Storage.** The four values are persisted via the `settings` module's store
  (SYSTEM scope) — there is no branding database table. They hydrate into
  `app.state.branding.settings` at boot and hot-swap on save.
- **Images.** Logo and favicon uploads are stored through the `file_storage`
  module (referenced by UUID) and served from its download endpoint.
- **Delivery.** A registered Inertia shared-props provider injects a `branding`
  block into every page's shared props (authenticated *and* guest), which the
  frontend reads for the name, logo, favicon and colour.

## Permissions

- `branding.view` — view the branding admin page.
- `branding.manage` — change branding (name, colour, logo, favicon).

## Dependencies

Depends on the `Settings` and `FileStorage` modules.

## Notes

- Branding is currently SYSTEM-scoped (one identity per deployment). The
  settings store already supports tenant/user scope, leaving room for
  per-tenant branding later.
- The primary colour overrides the `--primary` / `--sidebar-primary` CSS
  variables from a single hex; the full OKLCH colour scale is not regenerated.

License: MIT

# Scaffolded module pages render inside the app shell (#897)

## Goal and scope

The `Browse`, `Create` and `Edit` pages that `smpy create-module` (and `make new-module`)
generates set no persistent Inertia layout. They render with no sidebar, header or
footer, so a user who clicks the module's sidebar entry is left on a bare page with no
way back.

In scope: both template variants, the app one (`templates/module/__PACKAGE__/pages/`) and
the framework-repo overlay (`_optional/framework_repo/__PACKAGE__/pages/`).

Out of scope: modules that were already generated. The CHANGELOG entry gives the
two-line fix for them.

## Approach

Each page imports `AuthenticatedLayout` from
`@simple-module-py/ui/layouts/AuthenticatedLayout` and sets
`<Page>.layout = [AuthenticatedLayout];`. This is the pattern the framework's own
non-admin module pages use (`modules/api_tokens/api_tokens/pages/Index.tsx:107`,
`modules/dashboard/dashboard/pages/Home.tsx`).

The scaffolded menu item is registered in `MenuSection.SIDEBAR`, which is what
`AuthenticatedLayout` renders, so the entry shows on its own pages.

Rejected: a default layout in the host's `client_app/app.tsx`. Every existing page
already picks its own layout (`AdminLayout`, `PublicLayout`, …), so a default would add
a second mechanism, and would wrap pages that deliberately use none (the login page).

## Decisions made

- `AuthenticatedLayout` rather than `AdminLayout`: the template's `view_prefix` is
  `/<slug>` and its menu item goes in `SIDEBAR`, not `ADMIN_SIDEBAR`. CLAUDE.md requires
  `/admin/*`, `ADMIN_SIDEBAR` and `AdminLayout` together.
- The layout import is placed in Biome's sorted order. The rendered pages of both
  variants pass `biome check`.

## Testing

- `test_scaffolding_module_js.py::TestPageLayout` checks that every generated page in
  both variants imports `AuthenticatedLayout` and sets `.layout`.
- `biome check` runs on the rendered pages of both variants.
- Real check in a scaffolded app: the module's `npm run typecheck` passes, and
  `/<module>/` shows the sidebar in a browser.

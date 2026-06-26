# Branding: unified header & footer

**Date:** 2026-06-25
**Status:** approved-to-implement (proceeding under an active `/goal` directive)

## Goal

Improve the app's branding so it is consistent and present in **both the header
and the footer** of every shell — authenticated app, admin panel, public
landing, and auth-card screens.

## Current state

The codebase already has a server-driven branding system:

- A `branding` module emits a `branding` Inertia shared prop:
  `{ appName, primaryColor, logoUrl, faviconUrl }` (default `appName` =
  `"SimpleModule"`).
- `BrandingHead` applies the favicon + primary colour on every page.
- `BrandingMark` renders the logo/initial badge + wordmark and is used in the
  `SidebarLayout` header (desktop sidebar + mobile top bar).

Gaps:

1. **No footer in the authenticated/admin app shell** (`SidebarLayout`). Only
   the public landing page has a footer.
2. The public footer and the `AuthCardShell` brand lockup **hardcode** brand
   text (`simple_module_python · MIT`, `simple_module` / `python`) instead of
   reading the `branding` prop — wrong for white-labelled deploys.
3. Brand link URLs (repo / docs / changelog) are duplicated inline.

## Design

Refined-minimal, matching the existing aesthetic (emerald `oklch` primary, Sora
display font, JetBrains Mono technical caption, subtle `border-border`, gradient
brand badge). No new server settings, no migrations — purely a frontend
consolidation in `packages/ui`.

### 1. `lib/brand.ts` — single source for static brand metadata

Framework-level constants that are not part of the white-labellable
`branding` prop: `BRAND_REPO_URL`, `BRAND_LICENSE` (`MIT`), `BRAND_TECH`
(`python`), and `BRAND_FOOTER_LINKS` (Docs / Changelog / GitHub).

### 2. `BrandingMark` gains an optional stacked caption

Add optional `caption` / `captionClassName` props. When `caption` is set the
wordmark + caption stack in a column (badge stays to the left). Backward
compatible — existing callers (sidebar header, mobile bar) pass no caption and
render exactly as before. This makes `BrandingMark` the single brand-lockup
primitive used by the header, footer, and auth shell.

### 3. `BrandingFooter` — one reusable footer

New presentational component: brand lockup (`BrandingMark`, small, light label,
caption `© <year> · MIT`) on the left; `BRAND_FOOTER_LINKS` on the right.
`variant` prop: `public` (centred `max-w-6xl`) vs `app` (full content width).
Pure/props-driven so it unit-tests without Inertia. Year computed at runtime
(client-only render, no SSR — safe).

### 4. Wire it in

- `SidebarLayout`: make `<main>` a flex column (`flex-1` content wrapper +
  sticky-bottom footer) and render `<BrandingFooter variant="app" />` driven by
  the already-derived `appName` / `logoUrl`. Both `AuthenticatedLayout` and
  `AdminLayout` inherit it.
- `PublicLayout`: replace the bespoke footer with `<BrandingFooter
  variant="public" />`; point the nav's external links at `BRAND_REPO_URL`.
- `AuthCardShell`: replace the hardcoded `simple_module` / `python` lockup with
  `BrandingMark` driven by the `branding` prop (`caption` = `BRAND_TECH`).

### 5. Tests

Follow the repo's co-located `*.test.tsx` pattern: new `BrandingFooter.test.tsx`
(app name, links, year/licence caption) and an added caption case in
`BrandingMark.test.tsx`.

## Out of scope / assumptions

- No new server-side branding settings (tagline, version, custom footer links).
  Footer links remain framework constants.
- Footer link labels stay un-localised, matching the existing public footer
  (they are largely proper nouns: Docs / Changelog / GitHub).
- 300-line cap respected; all new files are small and presentational.

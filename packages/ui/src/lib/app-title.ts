import { BRAND_DEFAULT_APP_NAME } from './brand';

/**
 * Document-title formatting for the browser tab.
 *
 * Inertia's global `title` callback runs outside React (it can't read live page
 * props), so the configured app name is held in this module-level cell. It is
 * seeded once from the initial page's `branding` shared prop in `app.tsx`, and
 * refreshed by `BrandingHead` if the app is renamed without a reload. The
 * server also renders the branded name into the static `<title>` of the root
 * template, so the pre-hydration tab is already correct.
 */
let appName: string = BRAND_DEFAULT_APP_NAME;

/** Update the app name used for the title suffix (falls back to the default). */
export function setTitleAppName(name: string | null | undefined): void {
  appName = name?.trim() || BRAND_DEFAULT_APP_NAME;
}

/** `"Dashboard — Acme"` for a page title, or just `"Acme"` for the bare app. */
export function formatTitle(pageTitle?: string | null): string {
  const trimmed = pageTitle?.trim();
  return trimmed ? `${trimmed} — ${appName}` : appName;
}

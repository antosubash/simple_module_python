/**
 * Framework-level brand metadata shared across the header, footer, and auth
 * shells. These are constants of the *framework/template* itself — distinct
 * from the white-labellable `branding` shared prop (`appName`, `logoUrl`, …),
 * which a deployment can customise at runtime.
 */
export const BRAND_REPO_URL = 'https://github.com/antosubash/simple_module_python';

/** Licence shown in the footer caption. */
export const BRAND_LICENSE = 'MIT';

/** Short technology tag shown beneath the wordmark on auth screens. */
export const BRAND_TECH = 'python';

/**
 * Default app name used when the `branding` shared prop is absent (the branding
 * module is optional). Mirrors the server-side `DEFAULT_APP_NAME` so the
 * unbranded experience is identical across every shell.
 */
export const BRAND_DEFAULT_APP_NAME = 'SimpleModule';

/** Tailwind classes for the default brand badge gradient (header / footer / auth lockups). */
export const BRAND_ACCENT = 'bg-gradient-to-br from-primary-600 to-primary-800';

/**
 * Pick the logo for an always-dark surface (the sidebar and mobile bar).
 *
 * A deployment that uploads only a primary logo keeps using it everywhere, so
 * this is purely additive: the dark variant exists for logos whose ink would
 * disappear against the near-black sidebar. Kept here, rather than inlined at
 * each call site, so the fallback rule is stated once.
 */
export function darkSurfaceLogo(
  branding: { logoUrl: string | null; logoDarkUrl: string | null } | null | undefined,
): string | null {
  return branding?.logoDarkUrl ?? branding?.logoUrl ?? null;
}

export interface BrandLink {
  label: string;
  href: string;
}

/** Links rendered on the right of the application + marketing footers. */
export const BRAND_FOOTER_LINKS: BrandLink[] = [
  { label: 'Docs', href: `${BRAND_REPO_URL}#readme` },
  { label: 'Changelog', href: `${BRAND_REPO_URL}/releases` },
  { label: 'GitHub', href: BRAND_REPO_URL },
];

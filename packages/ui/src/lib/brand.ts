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

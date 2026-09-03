/** Mirrors `BANNER_SEVERITIES` in `branding/constants.py`. */
export const BANNER_SEVERITIES = ['info', 'warning', 'danger'] as const;
export type BannerSeverity = (typeof BANNER_SEVERITIES)[number];

export interface FooterLink {
  label: string;
  href: string;
}

/**
 * Everything one Publish sends.
 *
 * Images are deliberately absent: they upload on pick, because a staged file
 * would have to be held in the browser and re-posted on Publish, and a failed
 * Publish would then lose an upload the user watched succeed.
 */
export interface BrandingForm {
  appName: string;
  color: string;
  designPack: string;
  bannerMessage: string;
  bannerSeverity: BannerSeverity;
  footerLinks: FooterLink[];
}

function sameLinks(a: FooterLink[], b: FooterLink[]): boolean {
  return (
    a.length === b.length &&
    a.every((link, i) => link.label === b[i].label && link.href === b[i].href)
  );
}

/**
 * How many fields differ from what the server currently holds.
 *
 * Counts *fields*, not keystrokes: "4 unsaved changes" tells you how much of
 * the form is pending, and the whole footer list is one such decision however
 * many rows it holds.
 */
export function countBrandingChanges(form: BrandingForm, baseline: BrandingForm): number {
  let count = 0;
  if (form.appName !== baseline.appName) count += 1;
  if (form.color !== baseline.color) count += 1;
  if (form.designPack !== baseline.designPack) count += 1;
  if (form.bannerMessage !== baseline.bannerMessage) count += 1;
  // A severity change only matters while there is a banner to colour.
  if (form.bannerSeverity !== baseline.bannerSeverity && form.bannerMessage) count += 1;
  if (!sameLinks(form.footerLinks, baseline.footerLinks)) count += 1;
  return count;
}

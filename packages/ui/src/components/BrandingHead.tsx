import { Head, usePage } from '@inertiajs/react';
import { useEffect } from 'react';
import { setTitleAppName } from '../lib/app-title';
import { deriveBrandRamp } from '../lib/color';
import type { SharedProps } from '../types';

/**
 * Applies branding that lives in the document head / root, on every page:
 *
 * - the favicon `<link>` when a custom favicon is set,
 * - the primary brand colour — derived into the full `--color-primary-*` ramp
 *   (plus base `--primary` / `--sidebar-primary`) and written as inline CSS
 *   variables on `:root`. Inline wins over the stylesheet's `:root`/`.dark`
 *   rules, so every Tailwind `primary` utility — solid buttons *and* the
 *   `primary-600/700/800` gradient tints used by the brand badge — follows the
 *   configured colour site-wide, and
 * - the app name for the document `<title>` suffix on client navigations.
 *
 * Reads the `branding` shared prop, so it stays reactive across navigation.
 */
export function BrandingHead(): React.ReactElement | null {
  const { branding } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  const primaryColor = branding?.primaryColor ?? null;
  const faviconUrl = branding?.faviconUrl ?? null;
  const appName = branding?.appName ?? null;

  // Keep the title suffix in sync if the app is renamed without a reload.
  setTitleAppName(appName);

  useEffect(() => {
    const root = document.documentElement;
    const ramp = primaryColor ? deriveBrandRamp(primaryColor) : null;
    if (!ramp) return;
    const keys = Object.keys(ramp);
    for (const k of keys) root.style.setProperty(k, ramp[k]);
    return () => {
      for (const k of keys) root.style.removeProperty(k);
    };
  }, [primaryColor]);

  if (!faviconUrl) {
    return null;
  }
  return (
    <Head>
      <link rel="icon" href={faviconUrl} />
    </Head>
  );
}

import { Head, usePage } from '@inertiajs/react';
import { useEffect } from 'react';
import type { SharedProps } from '../types';

const COLOR_VARS = ['--primary', '--sidebar-primary'] as const;

/**
 * Applies branding that lives in the document head / root, on every page:
 *
 * - the favicon `<link>` when a custom favicon is set, and
 * - the primary brand colour, written as inline CSS variables on `:root`
 *   (inline wins over the stylesheet's `:root`/`.dark` rules; `--color-primary`
 *   already resolves to `var(--primary)`, so Tailwind `primary` utilities pick
 *   it up site-wide).
 *
 * Reads the `branding` shared prop, so it stays reactive across navigation.
 */
export function BrandingHead(): React.ReactElement | null {
  const { branding } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  const primaryColor = branding?.primaryColor ?? null;
  const faviconUrl = branding?.faviconUrl ?? null;

  useEffect(() => {
    const root = document.documentElement;
    for (const v of COLOR_VARS) {
      if (primaryColor) {
        root.style.setProperty(v, primaryColor);
      } else {
        root.style.removeProperty(v);
      }
    }
    return () => {
      for (const v of COLOR_VARS) root.style.removeProperty(v);
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

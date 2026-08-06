import { usePage } from '@inertiajs/react';
import type React from 'react';
import type { SharedProps } from '../types';

/**
 * Severity → colour. Deliberately semantic rather than brand-tinted: a warning
 * that adopted the deployment's primary colour would stop reading as a warning.
 */
const SEVERITY_CLASS: Record<string, string> = {
  info: 'bg-sky-600 text-white',
  warning: 'bg-amber-500 text-black',
  danger: 'bg-red-600 text-white',
};

/**
 * Site-wide announcement bar, rendered above every shell (app, public and
 * auth), driven by the `branding.banner` shared prop.
 *
 * Renders nothing when no message is set, so the layouts can mount it
 * unconditionally. Not dismissible by design — an admin sets it precisely
 * because everyone should see it, and per-user dismissal state would need
 * storage the branding module does not own.
 */
export function BrandingBanner(): React.ReactElement | null {
  const { branding } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  const banner = branding?.banner ?? null;
  if (!banner?.message) return null;

  const tone = SEVERITY_CLASS[banner.severity] ?? SEVERITY_CLASS.info;
  return (
    <div
      // `status` (not `alert`) — it is ambient page context, so it should not
      // interrupt a screen-reader user mid-task.
      role="status"
      className={`w-full px-4 py-2 text-center text-sm font-medium ${tone}`}
    >
      {banner.message}
    </div>
  );
}

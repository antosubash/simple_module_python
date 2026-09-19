import { usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import type React from 'react';
import type { SharedProps } from '../types';

/**
 * Standing "you are in a demo" bar, driven by the `demo` shared prop the users
 * module contributes.
 *
 * Per-session, not per-install: an operator signed in to their own account on
 * the same instance is doing real work and is not shown this. It is also what
 * makes the read-only guard legible — without it, a refused save on a showcase
 * instance is indistinguishable from a bug.
 *
 * Renders nothing when the viewer is not on a demo session, so layouts mount it
 * unconditionally next to `BrandingBanner`.
 */
export function DemoBanner(): React.ReactElement | null {
  const { demo } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  const { t } = useT();
  if (!demo?.active) return null;

  return (
    <div
      // `status`, matching BrandingBanner: ambient page context, not something
      // that should interrupt a screen-reader user mid-task.
      role="status"
      className="w-full bg-indigo-600 px-4 py-2 text-center text-sm font-medium text-white"
    >
      {demo.readOnly ? t(keys.ui.demo.banner_read_only) : t(keys.ui.demo.banner_writable)}
    </div>
  );
}

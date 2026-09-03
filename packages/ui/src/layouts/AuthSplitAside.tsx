import { usePage } from '@inertiajs/react';
import { Check } from 'lucide-react';
import type React from 'react';
import { BrandingMark } from '../components/BrandingMark';
import { BRAND_ACCENT, BRAND_DEFAULT_APP_NAME, darkSurfaceLogo } from '../lib/brand';
import type { SharedProps } from '../types';

/** Stable for the lifetime of the bundle — the year only matters at page load. */
const YEAR = new Date().getFullYear();

interface AuthSplitAsideProps {
  /** The one sentence the product leads with. */
  heading: string;
  body: string;
  /** Short reassurances, each rendered as a ticked row. */
  checks: string[];
}

/**
 * The dark column beside the sign-in card.
 *
 * Copy is passed in rather than held here: this is the shape of the column —
 * lockup at the top, pitch in the middle, copyright pinned to the foot — and
 * the words belong to the page's own catalog.
 */
export function AuthSplitAside({ heading, body, checks }: AuthSplitAsideProps): React.ReactElement {
  const { branding } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  const appName = branding?.appName ?? BRAND_DEFAULT_APP_NAME;

  return (
    <div className="flex h-full flex-col justify-between gap-10">
      <div className="flex items-center gap-2.5">
        <BrandingMark
          appName={appName}
          logoUrl={darkSurfaceLogo(branding)}
          accentColor={BRAND_ACCENT}
          size="md"
          labelClassName="text-[15px] font-bold tracking-tight text-dark-text font-[var(--font-display)]"
        />
      </div>

      <div className="flex flex-col gap-4">
        <h2 className="max-w-[420px] text-[28px] leading-tight font-bold tracking-tight text-white font-[var(--font-display)] sm:text-[34px]">
          {heading}
        </h2>
        <p className="max-w-[400px] text-[15.5px] leading-relaxed text-dark-text-muted">{body}</p>
        <ul className="mt-1.5 flex flex-col gap-2.5">
          {checks.map((check) => (
            <li key={check} className="flex items-center gap-2.5 text-sm text-dark-text">
              <Check aria-hidden="true" className="h-4 w-4 shrink-0 text-primary-300" />
              {check}
            </li>
          ))}
        </ul>
      </div>

      <span className="text-[12.5px] text-dark-text-subtle">{`© ${YEAR} ${appName}`}</span>
    </div>
  );
}

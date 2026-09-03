import { usePage } from '@inertiajs/react';
import type React from 'react';
import { BrandingBanner } from '../components/BrandingBanner';
import { BrandingHead } from '../components/BrandingHead';
import { BrandingMark } from '../components/BrandingMark';
import { BRAND_ACCENT, BRAND_DEFAULT_APP_NAME, BRAND_TECH } from '../lib/brand';
import type { SharedProps } from '../types';

interface AuthCardShellProps {
  children: React.ReactNode;
  /**
   * `card` centres one glass card (forgot, verify, Keycloak). The two splits
   * put a column of context beside the form: `split-dark` is the brand pitch
   * on near-black (sign in), `split-light` an intro on the page surface
   * (register, accept invite). Both stack the column above the card below `lg`.
   */
  variant?: 'card' | 'split-dark' | 'split-light';
  /** Content of the split column. Ignored by the `card` variant. */
  aside?: React.ReactNode;
  /** Card width — `lg` for the longer forms (register, invite). */
  width?: 'md' | 'lg';
  /**
   * Tints the `card` variant's border — `destructive` for a dead link
   * (reset, invite), `warning` for one that still has a way out (resend
   * verification). Ignored by the split variants.
   */
  tone?: 'default' | 'destructive' | 'warning';
}

const CARD_BORDER_TONE: Record<NonNullable<AuthCardShellProps['tone']>, string> = {
  default: 'border-border',
  destructive: 'border-red-500/35',
  warning: 'border-amber-600/35',
};

/**
 * Full-viewport shell for unauthenticated flows
 * (login, register, password reset, email verify, invite accept).
 *
 * Light surface with emerald mesh blobs and a glass card — matches the
 * SimpleModulePython HiFi auth screens. Surfaces are semantic tokens rather
 * than literal whites, so the dark theme applies here too.
 */
export function AuthCardShell({
  children,
  variant = 'card',
  aside,
  width = 'md',
  tone = 'default',
}: AuthCardShellProps) {
  const { branding } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;
  const appName = branding?.appName ?? BRAND_DEFAULT_APP_NAME;
  const logoUrl = branding?.logoUrl ?? null;
  const widthClass = width === 'lg' ? 'max-w-lg' : 'max-w-md';

  if (variant === 'card') {
    return (
      <main className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-secondary/40 p-4">
        <BrandingHead />
        {/* Absolute so the banner spans the shell's full width without the
            centring flex column shrinking it to the card's width. */}
        <div className="absolute inset-x-0 top-0 z-10">
          <BrandingBanner />
        </div>
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute -top-[10%] -right-[10%] h-[600px] w-[600px] rounded-full bg-primary-600 opacity-15 blur-[100px]" />
          <div className="absolute -bottom-[10%] -left-[10%] h-[500px] w-[500px] rounded-full bg-primary-800 opacity-15 blur-[100px]" />
        </div>
        <div className={`relative w-full ${widthClass}`}>
          <div
            className={`rounded-3xl border ${CARD_BORDER_TONE[tone]} bg-card/85 p-7 shadow-xl backdrop-blur-xl backdrop-saturate-150`}
          >
            <div className="mb-5 flex items-center gap-2.5">
              <BrandingMark
                appName={appName}
                logoUrl={logoUrl}
                accentColor={BRAND_ACCENT}
                size="lg"
                badgeClassName="shadow-md shadow-primary-600/30"
                labelClassName="text-[17px] font-bold tracking-tight font-[var(--font-display)] text-foreground"
                caption={BRAND_TECH}
              />
            </div>
            {children}
          </div>
        </div>
      </main>
    );
  }

  const dark = variant === 'split-dark';

  return (
    // The banner is a row of its own here rather than an overlay: the aside's
    // lockup sits in the top-left corner of the dark column, exactly where an
    // absolutely positioned banner would cover it.
    <main className="relative grid min-h-screen grid-cols-1 lg:grid-cols-[1.05fr_1fr] lg:grid-rows-[auto_1fr]">
      <BrandingHead />
      <div className="lg:col-span-2">
        <BrandingBanner />
      </div>
      <div
        className={
          dark
            ? 'relative flex flex-col overflow-hidden bg-landing-bg px-6 py-10 sm:px-12 sm:py-12'
            : 'flex items-center bg-background px-6 py-10 sm:px-12'
        }
      >
        {dark && (
          <div
            aria-hidden="true"
            className="pointer-events-none absolute -top-[10%] -left-[15%] h-[520px] w-[520px] rounded-full bg-primary-800 opacity-30 blur-[110px]"
          />
        )}
        <div className="relative flex w-full flex-1 flex-col">{aside}</div>
      </div>
      <div className="flex items-center justify-center bg-background px-4 py-10 sm:px-10">
        <div className={`w-full ${widthClass}`}>
          <div className="rounded-2xl border border-border bg-card p-6 shadow-xl sm:p-8">
            {children}
          </div>
        </div>
      </div>
    </main>
  );
}

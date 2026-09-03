import { usePage } from '@inertiajs/react';
import { BrandingMark } from '@simple-module-py/ui/components/BrandingMark';
import { BRAND_ACCENT, BRAND_DEFAULT_APP_NAME } from '@simple-module-py/ui/lib/brand';
import { Check } from 'lucide-react';
import type React from 'react';

interface SharedBranding {
  branding?: { appName: string; logoUrl: string | null } | null;
}

interface AuthIntroProps {
  heading: string;
  /** The paragraph under the heading. A node so copy can embed a `<code>`. */
  body: React.ReactNode;
  /** Ticked reassurance rows; nodes for the same reason as `body`. */
  checks?: React.ReactNode[];
  /** Anything that belongs under the checks — the invite summary card. */
  children?: React.ReactNode;
}

/**
 * The light column beside a form card (register, accept invite).
 *
 * `AuthSplitAside` is its dark twin and hardcodes light-on-near-black ink, so
 * it cannot serve the light split. Same anatomy — lockup, headline, sentence,
 * ticked rows — in the page's own colours.
 */
export function AuthIntro({ heading, body, checks = [], children }: AuthIntroProps) {
  const { branding } = usePage<{ props: SharedBranding }>().props as unknown as SharedBranding;
  const appName = branding?.appName ?? BRAND_DEFAULT_APP_NAME;

  return (
    <div className="flex w-full flex-col gap-4">
      <div className="flex items-center gap-2.5">
        <BrandingMark
          appName={appName}
          logoUrl={branding?.logoUrl ?? null}
          accentColor={BRAND_ACCENT}
          size="md"
          labelClassName="text-[15px] font-bold tracking-tight text-foreground font-[var(--font-display)]"
        />
      </div>
      <h1 className="text-[28px] leading-tight font-bold tracking-tight text-foreground font-[var(--font-display)] sm:text-[32px]">
        {heading}
      </h1>
      <p className="text-[15px] leading-relaxed text-muted-foreground">{body}</p>
      {checks.length > 0 && (
        <ul className="flex flex-col gap-2.5">
          {checks.map((check, index) => (
            // Index-keyed: a fixed prop for the life of the render, and
            // nothing forbids a caller repeating a line.
            // biome-ignore lint/suspicious/noArrayIndexKey: see above
            <li key={index} className="flex items-center gap-2.5 text-[13.5px] text-muted-foreground">
              <Check aria-hidden="true" className="h-4 w-4 shrink-0 text-primary-700" />
              {check}
            </li>
          ))}
        </ul>
      )}
      {children}
    </div>
  );
}

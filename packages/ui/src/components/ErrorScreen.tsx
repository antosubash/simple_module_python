import type { ReactNode } from 'react';

interface Props {
  hero: ReactNode;
  title: string;
  /** Node, not string: the 403 copy names the missing permission in a `<code>`. */
  description: ReactNode;
  details?: ReactNode;
  children: ReactNode;
  /** Visual accent for the numeral (403=warning, 404=primary, 5xx=destructive). */
  accent?: 'primary' | 'warning' | 'destructive';
}

/**
 * The numeral is the entire illustration, so its colour has to carry the
 * status class — emerald "wrong turn", amber "not allowed", red "we broke".
 * It used to be a fixed emerald gradient whatever the status, which said the
 * same thing three times and left the accent prop showing only in a blob.
 */
const ACCENT_NUMERAL: Record<NonNullable<Props['accent']>, string> = {
  primary: 'text-primary-700',
  warning: 'text-amber-700',
  destructive: 'text-red-600',
};

export function ErrorScreen({
  hero,
  title,
  description,
  details,
  children,
  accent = 'primary',
}: Props) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-10">
      <div className="flex w-full max-w-md flex-col items-center gap-3.5 rounded-2xl border border-border bg-card p-8 text-center shadow-sm sm:p-10">
        <p
          className={`text-[64px] font-bold leading-none tracking-[-0.03em] font-display ${ACCENT_NUMERAL[accent]}`}
        >
          {hero}
        </p>
        <h1 className="text-[21px] font-bold tracking-tight text-foreground font-display">
          {title}
        </h1>
        <p className="max-w-[280px] text-sm leading-[1.7] text-muted-foreground">{description}</p>
        {/* Full width so a caller's block-level details (the dev-mode stack
            trace in ErrorBoundary) fill the card instead of shrinking to
            their content and spilling out of it. */}
        {details ? <div className="w-full">{details}</div> : null}
        <div className="mt-1 flex flex-wrap items-center justify-center gap-2.5">{children}</div>
      </div>
    </div>
  );
}

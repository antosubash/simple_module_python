import type { ReactNode } from 'react';

interface Props {
  hero: ReactNode;
  title: string;
  description: string;
  details?: ReactNode;
  children: ReactNode;
  /** Visual accent for HTTP-style hero (403=warning, 404=info, 500=destructive). */
  accent?: 'primary' | 'warning' | 'destructive';
}

const ACCENT_COLOR: Record<NonNullable<Props['accent']>, string> = {
  primary: 'oklch(0.59 0.14 158)',
  warning: 'oklch(0.66 0.16 70)',
  destructive: 'oklch(0.55 0.2 25)',
};

const ACCENT_BADGE: Record<NonNullable<Props['accent']>, string> = {
  primary: 'border-primary-200 bg-primary-50 text-primary-700',
  warning: 'border-amber-200 bg-amber-50 text-amber-700',
  destructive: 'border-red-200 bg-red-50 text-red-700',
};

export function ErrorScreen({
  hero,
  title,
  description,
  details,
  children,
  accent = 'primary',
}: Props) {
  const blob = ACCENT_COLOR[accent];
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div
          className="absolute -top-[10%] -right-[10%] h-[500px] w-[500px] rounded-full opacity-10 blur-[100px]"
          style={{ background: blob }}
        />
      </div>
      <div className="relative z-10 max-w-xl text-center">
        <span
          className={`mb-4 inline-flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-xs font-semibold ${ACCENT_BADGE[accent]}`}
        >
          <span
            className="h-1.5 w-1.5 rounded-full"
            style={{ background: blob }}
            aria-hidden="true"
          />
          HTTP {hero}
        </span>
        <p
          className="bg-clip-text text-transparent font-bold leading-none tracking-tight font-[var(--font-display)]"
          style={{
            backgroundImage: 'linear-gradient(135deg, oklch(0.59 0.14 158), oklch(0.5 0.11 168))',
            fontSize: 'clamp(72px, 12vw, 120px)',
          }}
        >
          {hero}
        </p>
        <h1 className="mt-3 text-2xl font-bold tracking-tight text-foreground font-[var(--font-display)] sm:text-3xl">
          {title}
        </h1>
        <p className="mx-auto mt-2 max-w-md text-base text-muted-foreground leading-relaxed">
          {description}
        </p>
        {details}
        <div className="mt-8 flex items-center justify-center gap-2 flex-wrap">{children}</div>
      </div>
    </div>
  );
}

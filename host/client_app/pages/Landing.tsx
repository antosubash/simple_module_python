import { Link, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';

interface Props {
  isAuthenticated: boolean;
}

const STATS = ['14k+ datasets', '·', '2.4M validated points', '·', 'open source'];
const FEATURE_GRID: [string, string][] = [
  ['Datasets', 'Upload COG/PMTiles'],
  ['Sampling', '7 strategies'],
  ['Validation', 'Map-side classify'],
  ['Reports', 'Confusion matrix'],
];

const SAMPLE_DOTS: [number, number][] = [
  [30, 40],
  [60, 55],
  [75, 30],
  [45, 70],
  [20, 55],
];

const MAP_BG = `radial-gradient(ellipse at 30% 40%, oklch(0.92 0.03 155) 0%, transparent 35%),
  radial-gradient(ellipse at 70% 60%, oklch(0.88 0.04 200) 0%, transparent 40%),
  repeating-linear-gradient(45deg, transparent 0 14px, rgba(0,0,0,0.025) 14px 15px),
  repeating-linear-gradient(-45deg, transparent 0 14px, rgba(0,0,0,0.025) 14px 15px),
  oklch(0.93 0.005 250)`;

function Landing() {
  const { isAuthenticated } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  const ctaHref = isAuthenticated ? '/dashboard/' : '/auth/login';
  const ctaLabel = isAuthenticated
    ? t(keys.host.landing.cta_dashboard)
    : t(keys.host.landing.cta_get_started);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Top nav */}
      <header className="border-b border-border/60">
        <div className="mx-auto flex max-w-6xl items-center gap-8 px-6 py-3.5">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="h-5 w-5 rounded bg-primary" />
            <span className="text-[13px] font-semibold tracking-tight">SimpleModule</span>
          </Link>
          <nav className="hidden gap-5 text-xs text-muted-foreground sm:flex">
            <span>Product</span>
            <span>Datasets</span>
            <span>Methodology</span>
            <span>Docs</span>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <a
              href="/auth/login"
              className="rounded border border-border bg-card px-3 py-1.5 text-xs font-medium hover:border-primary-400"
            >
              Sign in
            </a>
            <a
              href={ctaHref}
              className="rounded border border-foreground bg-foreground px-3 py-1.5 text-xs font-medium text-background"
            >
              Request access
            </a>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-[1.1fr_1fr]">
          <div className="flex flex-col gap-4">
            <span className="inline-flex w-fit items-center gap-1.5 rounded-full border border-primary-300 bg-primary-50 px-2.5 py-0.5 font-mono text-[11px] text-primary-800">
              {t(keys.host.landing.badge)}
            </span>
            <h1 className="font-[var(--font-display)] text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
              {t(keys.host.landing.hero_title_line1)}
              <br />
              {t(keys.host.landing.hero_title_line2)}
            </h1>
            <p className="max-w-md text-sm text-muted-foreground sm:text-[15px]">
              {t(keys.host.landing.hero_subtitle)}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <a
                href={ctaHref}
                className="inline-flex items-center gap-1.5 rounded border border-foreground bg-foreground px-3.5 py-2 text-xs font-medium text-background"
              >
                {ctaLabel}
              </a>
              <a
                href="https://github.com"
                className="inline-flex items-center gap-1.5 rounded border border-border bg-card px-3.5 py-2 text-xs font-medium"
              >
                {t(keys.host.landing.cta_docs)}
              </a>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3 font-mono text-[11px] text-muted-foreground">
              {STATS.map((s) => (
                <span key={s}>{s}</span>
              ))}
            </div>
          </div>

          {/* Map preview + accuracy callout */}
          <div className="relative">
            <div
              className="relative h-72 overflow-hidden rounded-lg border bg-secondary"
              style={{ backgroundImage: MAP_BG }}
            >
              {SAMPLE_DOTS.map(([x, y]) => (
                <span
                  key={`${x}-${y}`}
                  className="absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-[1.5px] border-foreground"
                  style={{
                    left: `${x}%`,
                    top: `${y}%`,
                    background: x === 75 ? 'oklch(0.62 0.12 200)' : 'white',
                  }}
                />
              ))}
            </div>
            <div className="absolute -bottom-4 -right-4 w-52 rounded-md border bg-card p-3 text-[11px] shadow-card">
              <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                Overall accuracy
              </div>
              <div className="mt-1 text-2xl font-semibold tabular-nums">87.3%</div>
              <div className="text-muted-foreground">±2.1% at 95% CI</div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature row */}
      <section className="mx-auto max-w-6xl px-6 pb-16">
        <div className="grid grid-cols-2 gap-4 border-t border-border/60 pt-6 sm:grid-cols-4">
          {FEATURE_GRID.map(([title, sub]) => (
            <div key={title}>
              <div className="text-xs font-semibold">{title}</div>
              <div className="text-[11px] text-muted-foreground">{sub}</div>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-border/60 py-6 text-center text-xs text-muted-foreground">
        SimpleModule — built with FastAPI, Inertia.js, React, Tailwind
      </footer>
    </div>
  );
}

Landing.layout = (page: React.ReactNode) => page;
export default Landing;

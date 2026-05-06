import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { PublicLayout } from '@simple-module-py/ui/layouts/PublicLayout';
import {
  BookOpen,
  Copy,
  Database,
  LayoutTemplate,
  Package,
  Rocket,
  Route,
  ShieldCheck,
  Sparkles,
  Stethoscope,
} from 'lucide-react';

const QUICKSTART = `# 1. install python and js deps
$ sm install

# 2. copy env template
$ cp .env.example .env

# 3. run migrations
$ sm migrate

# 4. start API + Vite in parallel
$ sm dev
`;

function Landing() {
  const { t } = useT();

  const features = [
    {
      icon: Package,
      title: keys.host.landing.features.schema_title,
      desc: keys.host.landing.features.schema_description,
    },
    {
      icon: Route,
      title: keys.host.landing.features.module_system_title,
      desc: keys.host.landing.features.module_system_description,
    },
    {
      icon: LayoutTemplate,
      title: keys.host.landing.features.inertia_title,
      desc: keys.host.landing.features.inertia_description,
    },
    {
      icon: Database,
      title: keys.host.landing.features.devtools_title,
      desc: keys.host.landing.features.devtools_description,
    },
    {
      icon: ShieldCheck,
      title: keys.host.landing.features.auth_title,
      desc: keys.host.landing.features.auth_description,
    },
    {
      icon: Stethoscope,
      title: keys.host.landing.features.diagnostics_title,
      desc: keys.host.landing.features.diagnostics_description,
    },
  ];

  return (
    <>
      {/* Hero with mesh blobs */}
      <section className="relative overflow-hidden">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 z-0 overflow-hidden"
        >
          <div className="absolute -top-[15%] -right-[10%] h-[600px] w-[600px] rounded-full bg-primary-600 opacity-15 blur-[100px]" />
          <div className="absolute top-[40%] -left-[10%] h-[500px] w-[500px] rounded-full bg-primary-800 opacity-15 blur-[100px]" />
        </div>
        <div className="relative z-10 mx-auto max-w-5xl px-4 pt-16 pb-12 text-center sm:px-8 sm:pt-24 sm:pb-16">
          <span className="inline-flex items-center gap-2 rounded-full border border-primary-600/20 bg-primary-600/10 px-3.5 py-1.5 text-xs font-semibold text-primary-700">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            {t(keys.host.landing.badge)}
          </span>
          <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-bold leading-[1.05] tracking-tight font-[var(--font-display)] sm:text-5xl lg:text-6xl">
            {t(keys.host.landing.hero_title_line1)}
            <br />
            <span className="bg-gradient-to-r from-primary-600 to-primary-800 bg-clip-text text-transparent">
              {t(keys.host.landing.hero_title_line2)}
            </span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-base text-muted-foreground sm:text-lg">
            {t(keys.host.landing.hero_subtitle)}
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row sm:gap-3">
            <Button asChild size="lg" className="w-full gap-2 sm:w-auto">
              <a href="/auth/login">
                <Rocket className="h-4 w-4" aria-hidden="true" />
                {t(keys.host.landing.cta_get_started)}
              </a>
            </Button>
            <Button asChild size="lg" variant="outline" className="w-full gap-2 sm:w-auto">
              <a href="https://github.com/antosubash/simple_module_python">
                <BookOpen className="h-4 w-4" aria-hidden="true" />
                {t(keys.host.landing.cta_docs)}
              </a>
            </Button>
          </div>
          {/* Terminal CTA */}
          <div className="mx-auto mt-7 flex max-w-xl items-center gap-3 rounded-xl border border-white/[0.06] bg-slate-900 px-4 py-3 text-left font-mono text-sm shadow-lg">
            <span className="shrink-0 text-primary-300">$</span>
            <code className="flex-1 truncate text-slate-200">
              uvx --from simple_module_cli sm new my-app
            </code>
            <button
              type="button"
              aria-label="Copy command"
              className="shrink-0 text-slate-400 transition-colors hover:text-slate-200"
            >
              <Copy className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="border-t border-border bg-secondary/40 px-4 py-16 sm:px-8 sm:py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mb-10 text-center">
            <span className="text-xs font-semibold uppercase tracking-[0.10em] text-primary-700">
              How it works
            </span>
            <h2 className="mt-2 text-2xl font-bold tracking-tight font-[var(--font-display)] sm:text-3xl">
              One process · many modules · zero glue.
            </h2>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {features.map((f) => (
              <Card
                key={f.title}
                className="border-border bg-card transition-colors hover:border-primary-200"
              >
                <CardContent className="pt-5">
                  <span className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-primary-600/10 text-primary-700">
                    <f.icon className="h-[18px] w-[18px]" aria-hidden="true" />
                  </span>
                  <h3 className="mb-1.5 text-base font-bold font-[var(--font-display)]">
                    {t(f.title)}
                  </h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">{t(f.desc)}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Quickstart split */}
      <section className="bg-background px-4 py-16 sm:px-8 sm:py-20">
        <div className="mx-auto grid max-w-5xl items-center gap-10 lg:grid-cols-[1fr_1.2fr]">
          <div>
            <span className="text-xs font-semibold uppercase tracking-[0.10em] text-primary-700">
              Quickstart
            </span>
            <h2 className="mt-2 text-2xl font-bold tracking-tight font-[var(--font-display)] sm:text-[28px]">
              Working app in five commands.
            </h2>
            <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
              Land on{' '}
              <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[13px]">
                http://localhost:8000
              </code>{' '}
              with users, dashboard, and permissions pre-wired. Sign in with the admin account you
              bootstrap and go from there.
            </p>
            <div className="mt-5 flex flex-col gap-2.5">
              {[
                ['users', 'Email + cookie sessions via fastapi-users'],
                ['dashboard', 'Authenticated home with module tiles'],
                ['permissions', 'Per-module permission registry'],
              ].map(([n, d]) => (
                <div key={n} className="flex items-center gap-2.5">
                  <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary-600/10 text-primary-700">
                    <svg
                      aria-hidden="true"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.5"
                      className="h-3.5 w-3.5"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  </span>
                  <code className="font-mono text-[13px] text-foreground">{n}</code>
                  <span className="text-[13px] text-muted-foreground">{d}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="overflow-hidden rounded-2xl border border-white/[0.06] bg-slate-900 shadow-xl">
            <div className="flex items-center gap-1.5 border-b border-white/[0.06] px-4 py-2.5">
              <span className="h-2.5 w-2.5 rounded-full bg-red-500" />
              <span className="h-2.5 w-2.5 rounded-full bg-yellow-500" />
              <span className="h-2.5 w-2.5 rounded-full bg-green-500" />
              <span className="ml-2 font-mono text-[11px] text-slate-400">~/my-app — bash</span>
            </div>
            <pre className="m-0 px-5 py-4 font-mono text-[13px] leading-7 text-slate-200">
              {QUICKSTART}
              <span className="text-primary-300">✓ ready on http://localhost:8000</span>
              {'\n\n# 5. scaffold a new module\n$ sm new module orders\n'}
              <span className="text-primary-300">✓ scaffolded modules/orders/</span>
            </pre>
          </div>
        </div>
      </section>

      {/* CTA strip */}
      <section className="border-t border-border bg-secondary/40 px-4 py-12 sm:px-8 sm:py-14">
        <div className="mx-auto flex max-w-4xl flex-col items-center justify-between gap-4 rounded-3xl bg-gradient-to-br from-primary-600 to-primary-800 px-9 py-8 shadow-xl sm:flex-row">
          <div>
            <h3 className="text-xl font-bold tracking-tight text-white font-[var(--font-display)] sm:text-[22px]">
              Ready to ship modules?
            </h3>
            <p className="mt-1 text-sm text-white/85">
              Sign up for the admin UI, or hack on the framework directly.
            </p>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button
              asChild
              variant="secondary"
              className="bg-white text-primary-700 hover:bg-white/90"
            >
              <a href="/auth/login">Sign up</a>
            </Button>
            <Button
              asChild
              variant="ghost"
              className="text-white hover:bg-white/10 hover:text-white"
            >
              <a href="https://github.com/antosubash/simple_module_python">GitHub →</a>
            </Button>
          </div>
        </div>
      </section>
    </>
  );
}

Landing.layout = (page: React.ReactNode) => <PublicLayout>{page}</PublicLayout>;
export default Landing;

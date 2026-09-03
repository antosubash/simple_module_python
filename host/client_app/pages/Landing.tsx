import { Head, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { PublicLayout } from '@simple-module-py/ui/layouts/PublicLayout';
import { LOGIN_PATH } from '@simple-module-py/ui/lib/auth-routes';
import type { SharedProps } from '@simple-module-py/ui/types';
import { Database, LayoutTemplate, Package, Route, ShieldCheck, Stethoscope } from 'lucide-react';
import { CopyCommand } from '../components/CopyCommand';

/** The one command the hero exists to hand over. */
const INSTALL_COMMAND = 'uvx --from simple_module_cli smpy new my-app';

/**
 * The terminal transcript, one entry per numbered step.
 *
 * Structured rather than one template literal so the `#` comments can be
 * greyed and the `✓` results tinted: a wall of one colour reads as output,
 * not as a script with commentary, which is the whole point of showing a
 * transcript instead of a list.
 */
const QUICKSTART: { comment: string; command: string; ok?: string }[] = [
  { comment: '# 1. install python and js deps', command: '$ make install' },
  { comment: '# 2. copy env template', command: '$ cp .env.example .env' },
  { comment: '# 3. run migrations', command: '$ make migrate' },
  {
    comment: '# 4. start API + Vite in parallel',
    command: '$ make dev',
    ok: '✓ ready on http://localhost:8000',
  },
  {
    comment: '# 5. scaffold a new module',
    command: '$ make new-module name=orders',
    ok: '✓ scaffolded modules/orders/',
  },
];

function Landing() {
  const { t } = useT();
  const { auth } = usePage<{ props: SharedProps }>().props as unknown as SharedProps;

  // The admin UI is the only thing behind a session here, so the one CTA that
  // leads anywhere private is auth-aware: a signed-in visitor is offered the
  // dashboard, everyone else the sign-in page. Never /auth/* — that is the
  // JSON API prefix and has no page (see host/tests/test_public_auth_links).
  const adminHref = auth?.isAuthenticated ? '/dashboard/' : LOGIN_PATH;

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
      <Head title={t(keys.host.landing.head_title)} />
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
          <span className="inline-flex items-center rounded-full border border-primary-600/20 bg-primary-600/10 px-3.5 py-1.5 text-[12.5px] font-bold text-primary-700">
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
            {/* An anchor, not a route: the page answers "how do I start?"
                two sections down, and sending a first-time visitor to a login
                form for a thing they can run locally was the wrong door. */}
            <Button asChild size="lg" className="w-full max-lg:min-h-11 sm:w-auto">
              <a href="#quickstart">{t(keys.host.landing.cta_get_started)}</a>
            </Button>
            <Button
              asChild
              size="lg"
              variant="outline"
              className="w-full max-lg:min-h-11 sm:w-auto"
            >
              <a href="https://github.com/antosubash/simple_module_python">
                {t(keys.host.landing.cta_docs)}
              </a>
            </Button>
          </div>
          {/* Terminal CTA */}
          <CopyCommand command={INSTALL_COMMAND} />
          <p className="mx-auto mt-3.5 text-[13px] text-muted-foreground">
            {t(keys.host.landing.terminal_helper)}
          </p>
        </div>
      </section>

      {/* Features */}
      <section className="border-t border-border bg-secondary/40 px-4 py-16 sm:px-8 sm:py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mb-10 text-center">
            <span className="text-xs font-semibold uppercase tracking-[0.10em] text-primary-700">
              {t(keys.host.landing.how_it_works_eyebrow)}
            </span>
            <h2 className="mt-2 text-2xl font-bold tracking-tight font-[var(--font-display)] sm:text-3xl">
              {t(keys.host.landing.how_it_works_heading)}
            </h2>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {features.map((f) => (
              <Card
                key={f.title}
                className="border-border bg-card transition-all hover:border-primary hover:shadow-lg"
              >
                <CardContent className="pt-5">
                  <span className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-primary-600/10 text-primary-700">
                    <f.icon className="h-[18px] w-[18px]" aria-hidden="true" />
                  </span>
                  <h3 className="mb-1.5 text-[17px] font-bold font-[var(--font-display)]">
                    {t(f.title)}
                  </h3>
                  <p className="text-[14.5px] leading-[1.65] text-muted-foreground">{t(f.desc)}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Quickstart split */}
      <section id="quickstart" className="bg-background px-4 py-16 sm:px-8 sm:py-20">
        <div className="mx-auto grid max-w-5xl items-center gap-10 lg:grid-cols-[1fr_1.2fr]">
          <div>
            <span className="text-xs font-semibold uppercase tracking-[0.10em] text-primary-700">
              {t(keys.host.landing.quickstart_eyebrow)}
            </span>
            <h2 className="mt-2 text-2xl font-bold tracking-tight font-[var(--font-display)] sm:text-[28px]">
              {t(keys.host.landing.quickstart_heading)}
            </h2>
            <p className="mt-3 text-[15px] leading-relaxed text-muted-foreground">
              {t(keys.host.landing.quickstart_body_prefix)}{' '}
              <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[13px]">
                http://localhost:8000
              </code>{' '}
              {t(keys.host.landing.quickstart_body_suffix)}
            </p>
            <div className="mt-5 flex flex-col gap-2.5">
              {[
                ['users', t(keys.host.landing.module_users_description)],
                ['dashboard', t(keys.host.landing.module_dashboard_description)],
                ['permissions', t(keys.host.landing.module_permissions_description)],
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
              {/* i18n-exempt: a fake terminal titlebar — a shell path and a program name. */}
              <span className="ml-2 font-mono text-[11px] text-slate-400">~/my-app — bash</span>
            </div>
            <pre className="m-0 overflow-x-auto px-5 py-4 font-mono text-[13px] leading-[1.85] text-slate-200">
              {QUICKSTART.map((step, index) => (
                <span key={step.command}>
                  {index > 0 ? '\n' : ''}
                  <span className="text-slate-400">{step.comment}</span>
                  {`\n${step.command}\n`}
                  {step.ok ? <span className="text-primary-300">{`${step.ok}\n`}</span> : null}
                </span>
              ))}
            </pre>
          </div>
        </div>
      </section>

      {/* CTA strip */}
      <section className="border-t border-border bg-secondary/40 px-4 py-12 sm:px-8 sm:py-14">
        <div className="mx-auto flex max-w-4xl flex-col items-center justify-between gap-4 rounded-3xl bg-gradient-to-br from-primary-600 to-primary-800 px-9 py-8 shadow-xl sm:flex-row">
          <div>
            <h3 className="text-xl font-bold tracking-tight text-white font-[var(--font-display)] sm:text-[22px]">
              {t(keys.host.landing.cta_heading)}
            </h3>
            <p className="mt-1 text-sm text-white/85">{t(keys.host.landing.cta_body)}</p>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button
              asChild
              variant="secondary"
              className="bg-white text-primary-700 hover:bg-white/90 max-lg:min-h-11"
            >
              <a href={adminHref}>
                {auth?.isAuthenticated
                  ? t(keys.host.landing.cta_dashboard)
                  : t(keys.host.landing.cta_sign_in)}
              </a>
            </Button>
            <Button
              asChild
              variant="outline"
              className="border-white/45 bg-transparent text-white hover:bg-white/10 hover:text-white max-lg:min-h-11"
            >
              <a href="https://github.com/antosubash/simple_module_python">
                {t(keys.host.landing.cta_github)}
              </a>
            </Button>
          </div>
        </div>
      </section>
    </>
  );
}

Landing.layout = (page: React.ReactNode) => <PublicLayout>{page}</PublicLayout>;
export default Landing;

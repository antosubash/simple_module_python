import { usePage } from '@inertiajs/react';
import { useT } from '@simple-module/i18n';
import { Badge } from '@simple-module/ui/components/ui/badge';
import { Button } from '@simple-module/ui/components/ui/button';
import { Card, CardContent } from '@simple-module/ui/components/ui/card';
import { Separator } from '@simple-module/ui/components/ui/separator';
import { PublicLayout } from '@simple-module/ui/layouts/PublicLayout';

interface Props {
  isAuthenticated: boolean;
}

function Landing() {
  const { isAuthenticated } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  const features = [
    {
      icon: (
        <svg
          aria-hidden="true"
          className="w-6 h-6"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="m21 7.5-9-5.25L3 7.5m18 0-9 5.25m9-5.25v9l-9 5.25M3 7.5l9 5.25M3 7.5v9l9 5.25m0-9v9"
          />
        </svg>
      ),
      title: t('host.landing.features.module_system_title'),
      description: t('host.landing.features.module_system_description'),
    },
    {
      icon: (
        <svg
          aria-hidden="true"
          className="w-6 h-6"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 12.75 11.25 15 15 9.75m-3-7.036A11.959 11.959 0 0 1 3.598 6 11.99 11.99 0 0 0 3 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285Z"
          />
        </svg>
      ),
      title: t('host.landing.features.auth_title'),
      description: t('host.landing.features.auth_description'),
    },
    {
      icon: (
        <svg
          aria-hidden="true"
          className="w-6 h-6"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125"
          />
        </svg>
      ),
      title: t('host.landing.features.schema_title'),
      description: t('host.landing.features.schema_description'),
    },
    {
      icon: (
        <svg
          aria-hidden="true"
          className="w-6 h-6"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z"
          />
        </svg>
      ),
      title: t('host.landing.features.inertia_title'),
      description: t('host.landing.features.inertia_description'),
    },
    {
      icon: (
        <svg
          aria-hidden="true"
          className="w-6 h-6"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 0 1 4.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0 1 12 15a9.065 9.065 0 0 0-6.23.693L5 14.5m14.8.8 1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0 1 12 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5"
          />
        </svg>
      ),
      title: t('host.landing.features.diagnostics_title'),
      description: t('host.landing.features.diagnostics_description'),
    },
    {
      icon: (
        <svg
          aria-hidden="true"
          className="w-6 h-6"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z"
          />
        </svg>
      ),
      title: t('host.landing.features.devtools_title'),
      description: t('host.landing.features.devtools_description'),
    },
  ];

  return (
    <>
      {/* Hero */}
      <section className="max-w-5xl mx-auto px-4 pt-12 pb-12 text-center sm:px-8 sm:pt-24 sm:pb-20">
        <div className="animate-fade-in-up">
          <Badge
            variant="outline"
            className="border-primary-400/20 bg-primary-400/10 text-primary-300 mb-6 sm:mb-8 gap-2"
          >
            <span className="w-2 h-2 rounded-full bg-primary-400 animate-pulse" />
            {t('host.landing.badge')}
          </Badge>
        </div>

        <h1
          className="text-3xl font-extrabold tracking-tight leading-tight font-[var(--font-display)] sm:text-5xl lg:text-6xl animate-fade-in-up"
          style={{ animationDelay: '100ms' }}
        >
          {t('host.landing.hero_title_line1')}
          <br />
          <span className="bg-gradient-to-r from-primary-300 via-primary-400 to-primary-200 bg-clip-text text-transparent">
            {t('host.landing.hero_title_line2')}
          </span>
        </h1>

        <p
          className="mt-4 text-base text-dark-text-muted max-w-2xl mx-auto leading-relaxed sm:mt-6 sm:text-lg animate-fade-in-up"
          style={{ animationDelay: '200ms' }}
        >
          {t('host.landing.hero_subtitle')}
        </p>

        <div
          className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center sm:gap-4 sm:mt-10 animate-fade-in-up"
          style={{ animationDelay: '300ms' }}
        >
          <Button asChild size="lg" className="w-full sm:w-auto">
            <a href="/auth/login">
              {isAuthenticated
                ? t('host.landing.cta_dashboard')
                : t('host.landing.cta_get_started')}
            </a>
          </Button>
          <Button
            asChild
            variant="outline"
            size="lg"
            className="w-full sm:w-auto bg-transparent border-dark-border text-white hover:text-white hover:border-dark-border-hover hover:bg-white/10"
          >
            <a href="https://github.com">{t('host.landing.cta_docs')}</a>
          </Button>
        </div>
      </section>

      <Separator className="max-w-6xl mx-auto bg-white/[0.06]" />

      {/* Features */}
      <section className="max-w-6xl mx-auto px-4 py-16 sm:px-8 sm:py-24">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {features.map((feature, index) => (
            <Card
              key={feature.title}
              className="group border-white/[0.06] bg-white/[0.03] backdrop-blur-sm hover:border-primary-400/20 hover:bg-white/[0.06] transition-all duration-300 animate-fade-in-up"
              style={{ animationDelay: `${400 + index * 80}ms` }}
            >
              <CardContent className="pt-6">
                <div className="w-10 h-10 rounded-lg bg-primary-400/10 flex items-center justify-center text-primary-400 mb-4 transition-colors duration-300 group-hover:bg-primary-400/15">
                  {feature.icon}
                </div>
                <h3 className="text-lg font-semibold text-white mb-2 font-[var(--font-display)]">
                  {feature.title}
                </h3>
                <p className="text-sm text-dark-text-muted leading-relaxed">
                  {feature.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </>
  );
}

Landing.layout = (page: React.ReactNode) => <PublicLayout>{page}</PublicLayout>;
export default Landing;

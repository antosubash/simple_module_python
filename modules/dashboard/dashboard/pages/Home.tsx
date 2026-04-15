import { usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module/i18n';
import { PageShell } from '@simple-module/ui/components/PageShell';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@simple-module/ui/components/ui/card';
import { Separator } from '@simple-module/ui/components/ui/separator';
import { AuthenticatedLayout } from '@simple-module/ui/layouts/AuthenticatedLayout';
import { Box, Package, Users } from 'lucide-react';

interface Props {
  welcome: string;
}

function Home() {
  const { welcome } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();

  return (
    <PageShell title={t(keys.dashboard.home.title)} description={t(keys.dashboard.home.description)}>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
        <StatCard
          title={t(keys.dashboard.home.stats.products)}
          value="-"
          icon={<Package className="size-4" />}
          accent="primary"
        />
        <StatCard
          title={t(keys.dashboard.home.stats.users)}
          value="-"
          icon={<Users className="size-4" />}
          accent="emerald"
        />
        <StatCard
          title={t(keys.dashboard.home.stats.modules)}
          value="3"
          icon={<Box className="size-4" />}
          accent="violet"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="font-[var(--font-display)]">
            {t(keys.dashboard.home.welcome_card_title)}
          </CardTitle>
          <CardDescription>{welcome}</CardDescription>
        </CardHeader>
        <Separator />
        <CardContent>
          <p className="text-sm text-muted-foreground">{t(keys.dashboard.home.description_body)}</p>
        </CardContent>
      </Card>
    </PageShell>
  );
}

function StatCard({
  title,
  value,
  icon,
  accent,
}: {
  title: string;
  value: string;
  icon: React.ReactNode;
  accent: string;
}) {
  const styles: Record<string, { card: string; icon: string; value: string }> = {
    primary: {
      card: 'border-primary-200 bg-gradient-to-br from-primary-50 to-card',
      icon: 'text-primary-500 bg-primary-100',
      value: 'text-primary-900',
    },
    emerald: {
      card: 'border-emerald-border bg-gradient-to-br from-emerald-bg to-card',
      icon: 'text-emerald-icon-fg bg-emerald-icon-bg',
      value: 'text-emerald-value',
    },
    violet: {
      card: 'border-violet-border bg-gradient-to-br from-violet-bg to-card',
      icon: 'text-violet-icon-fg bg-violet-icon-bg',
      value: 'text-violet-value',
    },
  };

  const s = styles[accent] || styles.primary;

  return (
    <Card className={s.card}>
      <CardContent className="pt-5">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-muted-foreground">{title}</span>
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${s.icon}`}>
            {icon}
          </div>
        </div>
        <p className={`text-3xl font-bold font-[var(--font-display)] ${s.value}`}>{value}</p>
      </CardContent>
    </Card>
  );
}

Home.layout = (page: React.ReactNode) => <AuthenticatedLayout>{page}</AuthenticatedLayout>;
export default Home;

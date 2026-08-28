import { keys, useT } from '@simple-module-py/i18n';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Badge } from '@simple-module-py/ui/components/ui/badge';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { TONE } from '@simple-module-py/ui/lib/tone';

export interface Migration {
  current_revision: string | null;
  head_revision: string | null;
  is_current: boolean;
  recent: { revision: string; message: string; modules: string[] }[];
}

export function MigrationsCard({ migration }: { migration: Migration }) {
  const { t } = useT();
  if (migration.recent.length === 0) return null;
  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <SectionTitle
          right={
            <Badge variant="outline" className={migration.is_current ? TONE.success : TONE.warning}>
              {migration.is_current
                ? t(keys.dashboard.doctor.at_head)
                : t(keys.dashboard.doctor.behind)}
            </Badge>
          }
        >
          {t(keys.dashboard.doctor.recent_migrations)}
        </SectionTitle>
        <div className="-mx-1">
          {migration.recent.map((m) => (
            <div
              key={m.revision}
              className="flex items-center gap-3 border-t border-border px-1 py-3 first:border-t-0"
            >
              <code className="w-24 shrink-0 truncate font-mono text-[11px] text-muted-foreground">
                {m.revision}
              </code>
              {m.modules.map((mod) => (
                <Badge key={mod} variant="outline" className={TONE.default}>
                  {mod}
                </Badge>
              ))}
              <div className="flex-1 truncate text-sm text-foreground">{m.message}</div>
              <Badge variant="outline" className={TONE.success}>
                {t(keys.dashboard.doctor.applied)}
              </Badge>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

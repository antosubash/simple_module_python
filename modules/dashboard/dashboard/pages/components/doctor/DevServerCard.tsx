import { keys, useT } from '@simple-module-py/i18n';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import type { DevServer } from './types';

/**
 * Where this process's moving parts are listening.
 *
 * `running` is whether the app is serving assets from the Vite dev server at
 * all, not a health probe of the port — the row values are configuration, and
 * claiming liveness we never checked would be the fixture problem again.
 */
export function DevServerCard({ devServer }: { devServer: DevServer }) {
  const { t } = useT();

  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-base font-bold font-display">
            {t(keys.dashboard.doctor.dev_server)}
          </h2>
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-medium ${
              devServer.running
                ? 'bg-primary-600/10 text-primary-700'
                : 'bg-secondary text-muted-foreground'
            }`}
          >
            {devServer.running
              ? t(keys.dashboard.doctor.running)
              : t(keys.dashboard.doctor.not_running)}
          </span>
        </div>
        <div className="flex flex-col gap-2.5">
          {devServer.rows.map((row) => (
            <div key={row.name} className="flex items-center justify-between gap-3 text-[13px]">
              <span className="text-muted-foreground">{row.name}</span>
              <code className="font-mono text-[12.5px]">{row.value}</code>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

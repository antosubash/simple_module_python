import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { CheckCircle2, PlugZap, XCircle } from 'lucide-react';
import { useState } from 'react';

export interface CheckResult {
  name: string;
  status: string;
  detail: string;
}

/**
 * Live pass/fail for the services this install depends on.
 *
 * Shows the failure reason rather than a bare "unhealthy": "connection
 * refused", "authentication required" and a wrong database number need three
 * different fixes, and an operator staring at a red dot has no way to tell
 * which one they have.
 */
export function ConnectionList({ initial }: { initial: CheckResult[] }) {
  const { t } = useT();
  const [checks, setChecks] = useState(initial);
  const [busy, setBusy] = useState(false);

  async function retest() {
    setBusy(true);
    try {
      const resp = await fetch('/setup/test-connections', { method: 'POST' });
      const body = await resp.json();
      setChecks(body.checks ?? []);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <ul className="space-y-2">
        {checks.map((check) => {
          const ok = check.status === 'healthy';
          return (
            <li key={check.name} className="flex items-start gap-2 text-sm">
              {ok ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary-700" />
              ) : (
                <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
              )}
              <span className="font-medium">{check.name}</span>
              <span className={ok ? 'text-muted-foreground' : 'text-destructive'}>
                {check.detail}
              </span>
            </li>
          );
        })}
      </ul>

      <Button type="button" variant="outline" size="sm" disabled={busy} onClick={retest}>
        <PlugZap className="size-4" />
        {busy ? t(keys.host.setup.connections.testing) : t(keys.host.setup.connections.retest)}
      </Button>
    </div>
  );
}

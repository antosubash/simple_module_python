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
  const [error, setError] = useState<string | null>(null);

  async function retest() {
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch('/setup/test-connections', { method: 'POST' });
      // A 404 here means setup completed in another tab, and the body is not
      // the JSON this expects. Without the check, `resp.json()` throws into an
      // unhandled rejection and the button just stops responding.
      if (!resp.ok) throw new Error(resp.statusText || String(resp.status));
      const body = await resp.json();
      setChecks(body.checks ?? []);
    } catch (err) {
      setError((err as Error).message);
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

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Button type="button" variant="outline" size="sm" disabled={busy} onClick={retest}>
        <PlugZap className="size-4" />
        {busy ? t(keys.host.setup.connections.testing) : t(keys.host.setup.connections.retest)}
      </Button>
    </div>
  );
}

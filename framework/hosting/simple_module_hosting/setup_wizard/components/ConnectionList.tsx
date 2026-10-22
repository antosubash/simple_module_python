import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { apiFetch } from '@simple-module-py/ui/lib/api';
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
export function ConnectionList({
  initial,
  csrfToken,
}: {
  initial: CheckResult[];
  csrfToken: string;
}) {
  const { t } = useT();
  const [checks, setChecks] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function retest() {
    setBusy(true);
    setError(null);
    // A 404 here means setup completed in another tab; it arrives as a failed
    // result instead of a JSON parse error.
    const result = await apiFetch<{ checks?: CheckResult[] }>('/setup/test-connections', {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrfToken },
    });
    if (result.ok) setChecks(result.data?.checks ?? []);
    else setError(result.detail ?? t(keys.hosting.setup.request_failed));
    setBusy(false);
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
        {busy
          ? t(keys.hosting.setup.connections.testing)
          : t(keys.hosting.setup.connections.retest)}
      </Button>
    </div>
  );
}

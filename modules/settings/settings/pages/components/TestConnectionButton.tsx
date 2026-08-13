import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { CheckCircle2, PlugZap, XCircle } from 'lucide-react';
import { useState } from 'react';
import { ROUTES } from '../routes';

interface CheckResult {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  detail: string;
}

/**
 * Runs the module's health checks on demand.
 *
 * Mailer and storage credentials were previously only testable by using them
 * — triggering a password reset, or waiting for a user's upload to fail. This
 * exercises the same checks the readiness probe runs, so a wrong host or a
 * bad key surfaces while the admin is still looking at the form.
 */
export function TestConnectionButton({ pkg }: { pkg: string }) {
  const { t } = useT();
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<CheckResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    setResults(null);
    try {
      const resp = await fetch(ROUTES.testConnection(pkg), { method: 'POST' });
      if (!resp.ok) throw new Error(resp.statusText);
      const body = await resp.json();
      setResults(body.checks ?? []);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <Button type="button" variant="outline" size="sm" disabled={busy} onClick={run}>
        <PlugZap className="size-4" />
        {busy ? t(keys.settings.modules.testing) : t(keys.settings.modules.test_connection)}
      </Button>

      {error && <p className="text-xs text-destructive">{error}</p>}

      {results?.map((result) => {
        const ok = result.status === 'healthy';
        return (
          <p
            key={result.name}
            className={`flex items-center gap-1 text-xs ${
              ok ? 'text-primary-700' : 'text-destructive'
            }`}
          >
            {ok ? <CheckCircle2 className="size-3.5" /> : <XCircle className="size-3.5" />}
            {/* The reason is the whole point: "connection refused" and
                "authentication failed" need different fixes. */}
            {result.detail || result.status}
          </p>
        );
      })}
    </div>
  );
}

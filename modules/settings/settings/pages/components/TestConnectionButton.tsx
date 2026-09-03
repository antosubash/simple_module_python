import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { useRelativeTime } from '@simple-module-py/ui/hooks/use-relative-time';
import { CheckCircle2, PlugZap, XCircle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { ROUTES } from '../routes';
import { type LastTest, readLastTest, writeLastTest } from './last-test';

interface CheckResult {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  detail: string;
}

interface Props {
  pkg: string;
  /** Names of the health checks this module registered, e.g. `users.mailer`. */
  checks: string[];
}

/**
 * Runs the module's health checks on demand.
 *
 * Mailer and storage credentials were previously only testable by using them
 * — triggering a password reset, or waiting for a user's upload to fail. This
 * exercises the same checks the readiness probe runs, so a wrong host or a
 * bad key surfaces while the admin is still looking at the form.
 */
export function TestConnectionButton({ pkg, checks }: Props) {
  const { t } = useT();
  const { ago } = useRelativeTime();
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<CheckResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<LastTest | null>(null);

  // Read on mount rather than during render: the result is per-tab session
  // state, and touching sessionStorage while rendering breaks SSR hydration.
  useEffect(() => setLast(readLastTest(pkg)), [pkg]);

  // "users.mailer" → "mailer". Naming the check is the difference between
  // "Test connection" and knowing an SMTP dial is about to happen; with two
  // checks there is no single honest name, so the generic label wins.
  const label =
    checks.length === 1
      ? t(keys.settings.modules.test_connection, {
          name: checks[0].split('.').pop() ?? checks[0],
        })
      : t(keys.settings.modules.test_connection_generic);

  async function run() {
    setBusy(true);
    setError(null);
    setResults(null);
    try {
      const resp = await fetch(ROUTES.testConnection(pkg), { method: 'POST' });
      if (!resp.ok) throw new Error(resp.statusText);
      const body = await resp.json();
      const checkResults: CheckResult[] = body.checks ?? [];
      setResults(checkResults);
      setLast(
        writeLastTest(
          pkg,
          checkResults.every((c) => c.status === 'healthy'),
        ),
      );
    } catch (err) {
      setError((err as Error).message);
      setLast(writeLastTest(pkg, false));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={busy}
        onClick={run}
        className="max-lg:min-h-11"
      >
        <PlugZap className="size-4" aria-hidden="true" />
        {busy ? t(keys.settings.modules.testing) : label}
      </Button>

      {last && !busy && (
        <p
          className={`flex items-center gap-1 text-[12.5px] ${
            last.ok ? 'text-primary-700' : 'text-destructive'
          }`}
        >
          {last.ok ? (
            <CheckCircle2 className="size-3.5" aria-hidden="true" />
          ) : (
            <XCircle className="size-3.5" aria-hidden="true" />
          )}
          {last.ok
            ? t(keys.settings.modules.last_test_success, { ago: ago(last.at) })
            : t(keys.settings.modules.last_test_failure, { ago: ago(last.at) })}
        </p>
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}

      {/* The reason is the whole point: "connection refused" and
          "authentication failed" need different fixes. */}
      {results?.map((result) => (
        <p
          key={result.name}
          className={`text-xs ${
            result.status === 'healthy' ? 'text-muted-foreground' : 'text-destructive'
          }`}
        >
          {result.detail || result.status}
        </p>
      ))}
    </div>
  );
}

import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { useState } from 'react';

/** Mirrors the server's `AdministratorIn.password` rule. */
const MIN_PASSWORD_LENGTH = 8;

/**
 * Turn a FastAPI error body into one line of text.
 *
 * `detail` is a string for `HTTPException`, but an array of
 * `{loc, msg, ...}` objects for a 422 — which is exactly what a short password
 * or a malformed address produces here. Interpolating that array straight into
 * an Error yields "[object Object]", i.e. the one form of the message that
 * tells the operator nothing.
 */
function errorMessage(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown })?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => (typeof item === 'string' ? item : (item as { msg?: string })?.msg))
      .filter(Boolean);
    if (parts.length > 0) return parts.join('; ');
  }
  return fallback;
}

/**
 * Creates the first administrator, which is what releases the setup gate.
 *
 * On success the page reloads rather than navigating: every /setup route
 * starts 404ing the moment an admin exists, so a client-side transition would
 * land on a route that has just disappeared.
 */
export function AdministratorForm() {
  const { t } = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    const form = new FormData(event.currentTarget);
    try {
      const resp = await fetch('/setup/administrator', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: form.get('email'),
          password: form.get('password'),
          full_name: form.get('full_name') || null,
        }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        throw new Error(errorMessage(body, resp.statusText || String(resp.status)));
      }
      setDone(true);
      window.location.href = '/';
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="setup-email">{t(keys.host.setup.administrator.email)}</Label>
        <Input id="setup-email" name="email" type="email" required autoComplete="email" />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="setup-password">{t(keys.host.setup.administrator.password)}</Label>
        <Input
          id="setup-password"
          name="password"
          type="password"
          required
          minLength={MIN_PASSWORD_LENGTH}
          autoComplete="new-password"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="setup-full-name">{t(keys.host.setup.administrator.full_name)}</Label>
        <Input id="setup-full-name" name="full_name" type="text" autoComplete="name" />
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}
      {done && (
        <p className="text-sm text-primary-700">{t(keys.host.setup.administrator.created)}</p>
      )}

      <Button type="submit" disabled={busy}>
        {busy
          ? t(keys.host.setup.administrator.submitting)
          : t(keys.host.setup.administrator.submit)}
      </Button>
    </form>
  );
}

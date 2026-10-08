import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { useState } from 'react';

/** One input of a step's form — `SetupField` on the server. */
export interface StepField {
  name: string;
  label: string;
  type: string;
  required: boolean;
  autocomplete: string;
  minLength: number | null;
}

/** `SetupAction` on the server, minus the handler. Labels arrive translated. */
export interface StepAction {
  submitLabel: string;
  fields: StepField[];
}

/**
 * Turn a FastAPI error body into one line of text.
 *
 * `detail` is a string for `HTTPException`, but an array of
 * `{loc, msg, ...}` objects for a 422 — which is exactly what a short password
 * or a malformed address produces. Interpolating that array straight into an
 * Error yields "[object Object]", the one form of the message that tells the
 * operator nothing.
 */
export function errorMessage(body: unknown, fallback: string): string {
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
 * Completes one setup step through the action its module registered.
 *
 * On success the browser goes to `/` rather than reloading the wizard: if this
 * was the last required step every /setup route now 404s, and if it was not,
 * the gate sends the browser straight back here.
 */
export function StepForm({
  stepId,
  action,
  csrfToken,
}: {
  stepId: string;
  action: StepAction;
  csrfToken: string;
}) {
  const { t } = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    const form = new FormData(event.currentTarget);
    const data: Record<string, string | null> = {};
    for (const field of action.fields) {
      const value = form.get(field.name);
      // An empty optional field is "not given", not an empty string.
      data[field.name] = typeof value === 'string' && value !== '' ? value : null;
    }

    try {
      const resp = await fetch(`/setup/steps/${encodeURIComponent(stepId)}`, {
        method: 'POST',
        // Accept: application/json matters. The host renders an Inertia error
        // *page* for a 4xx unless the caller prefers JSON, and a bare fetch()
        // sends Accept: */* — so without it the body is HTML, json() throws,
        // and the operator never sees why the request was refused.
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-CSRF-Token': csrfToken,
        },
        body: JSON.stringify(data),
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
      {action.fields.map((field) => {
        const id = `setup-${stepId}-${field.name}`;
        return (
          <div key={field.name} className="space-y-1.5">
            <Label htmlFor={id}>{field.label}</Label>
            <Input
              id={id}
              name={field.name}
              type={field.type}
              required={field.required}
              minLength={field.minLength ?? undefined}
              autoComplete={field.autocomplete || undefined}
            />
          </div>
        );
      })}

      {error && <p className="text-sm text-destructive">{error}</p>}
      {done && <p className="text-sm text-primary-700">{t(keys.hosting.setup.done)}</p>}

      <Button type="submit" disabled={busy}>
        {busy ? t(keys.hosting.setup.working) : action.submitLabel}
      </Button>
    </form>
  );
}

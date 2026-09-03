import { keys, useT } from '@simple-module-py/i18n';
import { PasswordInput } from '@simple-module-py/ui/components/PasswordInput';
import { PasswordStrength } from '@simple-module-py/ui/components/PasswordStrength';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { useId, useState } from 'react';
import { toast } from 'sonner';

/**
 * Change your own password.
 *
 * The current password is asked for even though you are already signed in: an
 * unattended browser is exactly what that guards against, and the server
 * refuses without it. Rendered only for accounts that have a local password —
 * an SSO user has nothing here to change.
 */
export function PasswordCard() {
  const { t } = useT();
  const currentId = useId();
  const newId = useId();
  const confirmId = useId();

  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    // Checked here as well as by the two fields being separate: the server
    // never sees the confirmation, so this is the only place a typo in it can
    // be caught.
    if (next !== confirm) {
      setError(t(keys.users.common.passwords_no_match));
      return;
    }
    setSaving(true);
    try {
      const resp = await fetch('/api/users/me/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        setError(
          typeof body?.detail === 'string'
            ? body.detail
            : t(keys.users.profile.toast_password_failed),
        );
        return;
      }
      toast.success(t(keys.users.profile.toast_password_changed));
      setCurrent('');
      setNext('');
      setConfirm('');
    } catch {
      setError(t(keys.users.common.error_occurred));
    } finally {
      setSaving(false);
    }
  }

  const showLabel = t(keys.users.common.show_password);
  const hideLabel = t(keys.users.common.hide_password);

  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <SectionTitle>{t(keys.users.profile.password_title)}</SectionTitle>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor={currentId} className="text-sm font-medium text-muted-foreground">
                {t(keys.users.profile.password_current)}
              </Label>
              <PasswordInput
                id={currentId}
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
                autoComplete="current-password"
                showLabel={showLabel}
                hideLabel={hideLabel}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={newId} className="text-sm font-medium text-muted-foreground">
                {t(keys.users.profile.password_new)}
              </Label>
              <PasswordInput
                id={newId}
                value={next}
                onChange={(e) => setNext(e.target.value)}
                autoComplete="new-password"
                showLabel={showLabel}
                hideLabel={hideLabel}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={confirmId} className="text-sm font-medium text-muted-foreground">
                {t(keys.users.profile.password_confirm)}
              </Label>
              <PasswordInput
                id={confirmId}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
                showLabel={showLabel}
                hideLabel={hideLabel}
                required
              />
            </div>
          </div>

          <PasswordStrength
            password={next}
            hint={t(keys.users.common.password_hint)}
            labels={{
              weak: t(keys.users.common.strength_weak),
              ok: t(keys.users.common.strength_ok),
              strong: t(keys.users.common.strength_strong),
            }}
          />

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end">
            <Button
              type="submit"
              variant="outline"
              disabled={saving || !current || !next}
              className="max-lg:min-h-11"
            >
              {saving
                ? t(keys.users.profile.changing_password)
                : t(keys.users.profile.change_password)}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

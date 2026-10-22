import { keys, useT } from '@simple-module-py/i18n';
import { PasswordInput } from '@simple-module-py/ui/components/PasswordInput';
import { PasswordStrength } from '@simple-module-py/ui/components/PasswordStrength';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { apiResult } from '@simple-module-py/ui/lib/api';
import { useId, useState } from 'react';
import { toast } from 'sonner';
import { api } from '../../pages/api';
import { failureMessage } from '../../pages/failureMessage';

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
      const resp = await apiResult(
        api.POST('/api/users/me/password', {
          body: { current_password: current, new_password: next },
        }),
      );
      if (!resp.ok) {
        setError(
          failureMessage(
            resp,
            t(keys.users.profile.toast_password_failed),
            t(keys.users.common.error_occurred),
            true,
          ),
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
                className="max-lg:min-h-11"
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
                className="max-lg:min-h-11"
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
                className="max-lg:min-h-11"
                showLabel={showLabel}
                hideLabel={hideLabel}
                required
              />
            </div>
          </div>

          <PasswordStrength
            password={next}
            hint={t(keys.users.profile.password_hint)}
            labels={{
              weak: t(keys.users.common.strength_weak),
              ok: t(keys.users.common.strength_ok),
              strong: t(keys.users.common.strength_strong),
            }}
          />

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

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

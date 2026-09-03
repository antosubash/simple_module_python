import { keys, useT } from '@simple-module-py/i18n';
import { SectionTitle } from '@simple-module-py/ui/components/SectionTitle';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { initials } from '@simple-module-py/ui/lib/initials';
import { useId, useState } from 'react';
import { toast } from 'sonner';
import type { ProfileUser } from './profile-user';

/**
 * Your name and address.
 *
 * The avatar is initials and nothing else: there is no per-user upload and no
 * column to hold one, and the "Upload avatar" button that used to sit here did
 * nothing at all. Saying so beside the circle is more useful than a control
 * that lies.
 *
 * The email is read-only. Changing it means re-verifying it, which is a flow
 * this app does not have — an editable box that silently refuses is worse than
 * a field that plainly is not one.
 */
export function ProfileDetailsCard({ user }: { user: ProfileUser }) {
  const { t } = useT();
  const nameId = useId();
  const emailId = useId();
  const [fullName, setFullName] = useState(user.full_name ?? '');
  const [saving, setSaving] = useState(false);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setSaving(true);
    fetch('/api/users/me', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ full_name: fullName }),
    })
      .then(async (res) => {
        if (res.ok) {
          toast.success(t(keys.users.profile.toast_updated));
          return;
        }
        const data = await res.json().catch(() => ({}));
        toast.error(
          typeof data?.detail === 'string' ? data.detail : t(keys.users.profile.toast_failed),
        );
      })
      .catch(() => toast.error(t(keys.users.common.error_occurred)))
      .finally(() => setSaving(false));
  };

  return (
    <Card className="border-border">
      <CardContent className="pt-5">
        <SectionTitle>{t(keys.users.profile.details_title)}</SectionTitle>
        <div className="mb-5 flex items-center gap-3.5">
          <span className="inline-flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-primary-600/10 text-lg font-bold text-primary-700 font-[var(--font-display)]">
            {initials(user.full_name, user.email)}
          </span>
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{user.email}</div>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {t(keys.users.profile.avatar_hint)}
            </p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor={nameId} className="text-sm font-medium text-muted-foreground">
                {t(keys.users.common.full_name)}
              </Label>
              <Input
                id={nameId}
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder={t(keys.users.common.name_placeholder)}
                maxLength={200}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor={emailId} className="text-sm font-medium text-muted-foreground">
                {t(keys.users.common.email)}
              </Label>
              <Input id={emailId} type="email" value={user.email} readOnly className="bg-muted" />
            </div>
          </div>
          <div className="flex justify-end">
            <Button type="submit" disabled={saving} className="max-lg:min-h-11">
              {saving ? t(keys.users.common.saving) : t(keys.users.profile.save_details)}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

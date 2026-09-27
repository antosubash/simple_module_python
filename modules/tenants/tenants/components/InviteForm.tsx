import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@simple-module-py/ui/components/ui/card';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@simple-module-py/ui/components/ui/native-select';
import { Copy } from 'lucide-react';
import type React from 'react';
import { useState } from 'react';
import { toast } from 'sonner';
import { useTenantErrors } from '../hooks/useTenantErrors';

interface Props {
  onInvited: () => void;
}

const ROLE_KEY = keys.tenants.roles;

/**
 * The invite form and the one-time reveal of the accept link it mints.
 *
 * The link is shown only right after creation — the API never returns the
 * raw token again — so it stays in local state rather than in the reloaded
 * `invitations` prop.
 */
export function InviteForm({ onInvited }: Props) {
  const { t } = useT();
  const { describe } = useTenantErrors();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'admin' | 'member'>('member');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acceptUrl, setAcceptUrl] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch('/api/tenants/current/invitations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ email, role }),
      });
      if (!response.ok) {
        setError(await describe(response));
        return;
      }
      const data = (await response.json()) as { accept_url: string };
      setAcceptUrl(data.accept_url);
      setEmail('');
      toast.success(t(keys.tenants.members.toast_invited));
      onInvited();
    } catch {
      setError(t(keys.tenants.errors.generic));
    } finally {
      setSubmitting(false);
    }
  }

  async function copyLink() {
    if (!acceptUrl) return;
    try {
      await navigator.clipboard.writeText(acceptUrl);
      toast.success(t(keys.tenants.members.toast_link_copied));
    } catch {
      toast.error(t(keys.tenants.members.toast_copy_failed));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t(keys.tenants.members.invite_title)}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
          <div className="min-w-[220px] flex-1 space-y-1.5">
            <Label htmlFor="invite-email">{t(keys.tenants.members.invite_email_label)}</Label>
            <Input
              id="invite-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t(keys.tenants.members.invite_email_placeholder)}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="invite-role">{t(keys.tenants.members.invite_role_label)}</Label>
            <NativeSelect
              id="invite-role"
              value={role}
              onChange={(e) => setRole(e.target.value as 'admin' | 'member')}
            >
              <NativeSelectOption value="member">{t(ROLE_KEY.member)}</NativeSelectOption>
              <NativeSelectOption value="admin">{t(ROLE_KEY.admin)}</NativeSelectOption>
            </NativeSelect>
          </div>
          <Button type="submit" disabled={submitting || !email.trim()} className="max-lg:min-h-11">
            {submitting
              ? t(keys.tenants.members.invite_submitting)
              : t(keys.tenants.members.invite_submit)}
          </Button>
        </form>
        {error && <p className="text-sm text-destructive">{error}</p>}

        {acceptUrl && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
            <p className="mb-2 text-sm font-medium text-amber-800">
              {t(keys.tenants.members.invite_link_title)}
            </p>
            <p className="mb-2 text-xs text-amber-700">
              {t(keys.tenants.members.invite_link_description)}
            </p>
            <div className="flex items-center gap-2">
              <code className="flex-1 truncate rounded bg-white px-2 py-1 text-xs">
                {acceptUrl}
              </code>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="max-lg:min-h-11"
                onClick={copyLink}
              >
                <Copy className="size-3.5" aria-hidden="true" />
                {t(keys.tenants.members.invite_link_copy)}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

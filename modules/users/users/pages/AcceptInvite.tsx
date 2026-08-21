import { Head, router, usePage } from '@inertiajs/react';
import { keys, useT } from '@simple-module-py/i18n';
import { Button } from '@simple-module-py/ui/components/ui/button';
import { Input } from '@simple-module-py/ui/components/ui/input';
import { Label } from '@simple-module-py/ui/components/ui/label';
import { AuthCardShell } from '@simple-module-py/ui/layouts/AuthCardShell';
import { CheckCircle2 } from 'lucide-react';
import { useState } from 'react';

interface InvitePreview {
  email: string;
  roles: string[];
  already_accepted: boolean;
}

interface Props {
  token: string;
  /** null when the token cannot be read — expired, tampered, or absent. */
  invite: InvitePreview | null;
}

function AcceptInvite() {
  const { token: initialToken, invite } = usePage<{ props: Props }>().props as unknown as Props;
  const { t } = useT();
  const urlToken =
    typeof window !== 'undefined'
      ? (new URLSearchParams(window.location.search).get('token') ?? '')
      : '';
  const token = urlToken || initialToken;

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError(t(keys.users.common.passwords_no_match));
      return;
    }
    setLoading(true);
    fetch('/api/users/auth/accept-invite', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, password }),
    })
      .then(async (res) => {
        if (res.status === 204 || res.status === 200) {
          router.visit('/dashboard/');
        } else {
          const data = await res.json().catch(() => ({}));
          const detail = typeof data?.detail === 'string' ? data.detail : '';
          if (detail === 'INVITE_BAD_TOKEN') {
            setError(t(keys.users.accept_invite.error_bad_token));
          } else {
            setError(detail || t(keys.users.accept_invite.error_failed));
          }
        }
      })
      .catch(() => setError(t(keys.users.common.error_try_again)))
      .finally(() => setLoading(false));
  };

  return (
    <AuthCardShell>
      <Head title={t(keys.users.accept_invite.head_title)} />
      {/* Who the invite is for, and what it grants. Without this the card asks
          for a password while identifying neither — a forwarded link, or an
          invite addressed to the wrong person, is indistinguishable from the
          right one. */}
      <div className="flex items-start gap-3 rounded-xl border border-primary-200 bg-primary-50 p-3 text-sm text-primary-800">
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <div className="min-w-0">
          <p className="font-semibold">
            {invite
              ? t(keys.users.accept_invite.invited_as, { email: invite.email })
              : t(keys.users.accept_invite.invited_generic)}
          </p>
          <p className="mt-0.5">{t(keys.users.accept_invite.pick_password)}</p>
          {invite && invite.roles.length > 0 && (
            <p className="mt-1.5 flex flex-wrap items-center gap-1">
              <span className="text-xs text-primary-700">
                {t(keys.users.accept_invite.access_label)}
              </span>
              {invite.roles.map((role) => (
                <span
                  key={role}
                  className="rounded-full border border-primary-200 bg-white/60 px-2 py-0.5 text-[11px] font-semibold"
                >
                  {role}
                </span>
              ))}
            </p>
          )}
        </div>
      </div>

      {invite?.already_accepted && (
        <p className="mt-3 rounded-lg bg-amber-50 p-2.5 text-sm text-amber-900">
          {t(keys.users.accept_invite.already_used)}
        </p>
      )}
      <h1 className="mt-5 mb-1.5 text-[22px] font-bold tracking-tight font-[var(--font-display)] text-foreground">
        {t(keys.users.accept_invite.heading)}
      </h1>
      <form onSubmit={handleSubmit} className="space-y-3.5">
        <div className="space-y-1.5">
          <Label htmlFor="password" className="text-sm font-medium text-muted-foreground">
            {t(keys.users.common.password)}
          </Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t(keys.users.common.password_placeholder)}
            required
            autoComplete="new-password"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="confirm" className="text-sm font-medium text-muted-foreground">
            {t(keys.users.common.confirm_password)}
          </Label>
          <Input
            id="confirm"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            autoComplete="new-password"
          />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <Button type="submit" size="lg" className="w-full" disabled={loading || !token}>
          {loading ? t(keys.users.accept_invite.submitting) : t(keys.users.accept_invite.submit)}
        </Button>
      </form>
      {token && (
        <p className="mt-4 text-center font-mono text-[11px] text-muted-foreground">
          token={token.slice(0, 16)}…
        </p>
      )}
    </AuthCardShell>
  );
}

export default AcceptInvite;
